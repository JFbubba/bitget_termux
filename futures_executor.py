"""
futures_executor.py — EXÉCUTION FUTURES RÉELLE BORNÉE. Étape 2 (RESEARCH_NOTES §45).

⚠️ 2e module d'exécution AUTORISÉ — avec spot_executor, les SEULS endroits qui peuvent
passer un ordre réel. Le chemin réel est CÂBLÉ depuis le §45 : décision explicite du
propriétaire (02/07/2026, trois questions d'engagement répondues : périmètre carry +
directionnel, directement réel, plafond = solde). La porte d'edge (agent LIVE) peut
être OUTREPASSÉE par `FUTURES_EDGE_GATE_OVERRIDE` (config, décision §45) — remettre
à 0 la referme instantanément.

Périmètre BORNÉ par conception :
  ouverture/réduction d'une position futures (side 'long'/'short', reduce), marge
  ISOLÉE (la perte max d'une position = sa marge), levier ≤ mur ×5, notional/trade et
  exposition cumulée plafonnés par _capped (env/config peuvent ABAISSER, JAMAIS
  dépasser les murs absolus en dur), stop de perte JOURNALIER (arme le kill-switch).
  JAMAIS de retrait, JAMAIS de virement, JAMAIS d'annulation ici.

Gardes DURS (8 de §34 + pré-vol perte journalière) : voir guards() et execute().
Mode --dry par DÉFAUT : imprime le preview, n'exécute RIEN sans --confirm.
"""

import contextlib
import json
import math
import time
from pathlib import Path

SYMBOL = "BTCUSDT"
PRODUCT_TYPE = "USDT-FUTURES"
MARGIN_COIN = "USDT"

# Murs ABSOLUS en dur (defense-in-depth, comme spot_executor) : ni .env ni config ne
# peuvent les DÉPASSER (les abaisser, oui). Le plafond réel effectif démarre BAS
# (config : 15/trade, 60 cumulé) et monte progressivement si l'exécution est propre —
# le mur cumulé 250 ≈ le solde autorisé par le propriétaire (§45).
FUT_ABS_MAX_PER_TRADE_USDT = 50.0
FUT_ABS_MAX_GROSS_USDT = 250.0
FUT_ABS_MAX_LEVERAGE = 5.0   # mur dur levier : ni .env ni config ne peuvent le DÉPASSER

# Sérialisation des OUVERTURES (Thème 2, §revue chemin argent). Le mur cumulé 250 ne
# tient QUE si l'exposition présentée à guards() est (a) lue sous mutex inter-processus
# et (b) consciente des ouvertures in-flight pas encore reflétées par le livre exchange.
FUTURES_OPEN_LOCK = "futures_open.lock"     # verrou flock partagé par TOUS les ouvreurs
FUTURES_PENDING_FILE = "futures_pending.json"   # réservations in-flight (gitignored)
PENDING_TTL_S = 90.0                          # durée de vie d'une réservation (borne la sur-prudence)


from config_utils import cfg as _cfg, env_num as _env_num, load_env as _load_env
_load_env()   # .env dès l'import : lectures env-first déterministes même à froid (revue §111)


def _limit(name, fallback):
    """Plafond numérique : env > config > défaut (comme spot_executor)."""
    import os
    v = os.getenv(name)
    if v is not None:
        try:
            return float(v)
        except ValueError:
            pass
    return float(_cfg(name, fallback))


def _capped(name, fallback, absolute):
    """Plafond EFFECTIF = min(env > config > défaut, mur ABSOLU en dur). PUR (lit l'env)."""
    return min(_limit(name, fallback), float(absolute))


def _autonomous_on():
    """2e verrou FUTURES_AUTONOMOUS_LIVE : .env OU config (comme l'accumulation —
    l'option .env évite d'éditer un fichier suivi par git)."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    env_on = os.getenv("FUTURES_AUTONOMOUS_LIVE", "").strip().lower() in ("1", "true", "yes", "on")
    return env_on or bool(_cfg("FUTURES_AUTONOMOUS_LIVE", False))


def _env_str(name, default):
    """Chaîne .env > config > défaut (charge dotenv best-effort, idempotent). Base commune des
    leviers-chaîne lus au RUNTIME sans éditer un fichier suivi par git."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    v = os.getenv(name)
    if v is not None and str(v).strip():
        return str(v)
    return str(_cfg(name, default))


def _exec_style():
    """Style d'exécution des OUVERTURES futures : .env > config > 'limit_ioc'. ARMABLE via .env.
    Valeurs : 'limit_ioc' (taker plafonné, défaut) | 'maker' (post-only + repli taker) | 'market'.
    Lu au ROUTAGE (_place_real) ; le builder `to_bitget_order` reste piloté par son `style`
    explicite (hermétique)."""
    return _env_str("FUTURES_EXEC_STYLE", "limit_ioc").strip().lower()


def _maker_symbols():
    """Symboles autorisés au mode maker (CSV, .env > config). VIDE = tous. Sert à restreindre
    le maker à un périmètre PRUDENT (ex. BTCUSDT seul) pendant la validation en réel — un
    symbole hors liste retombe sur le taker éprouvé même si FUTURES_EXEC_STYLE=maker."""
    return {s.strip().upper() for s in _env_str("FUTURES_MAKER_SYMBOLS", "").split(",") if s.strip()}


def _execution_mode():
    """Mode affiché dans les previews/journaux : RÉEL borné si le double verrou est armé."""
    try:
        import mandate
        live = bool(mandate.live_enabled())
    except Exception:
        live = False
    return "FUTURES_REAL_BOUNDED" if (live and _autonomous_on()) else "FUTURES_DRY_RUN_ONLY"


# ---------- journal DRY-RUN (gitignored) ----------

def _ledger_path():
    return Path(__file__).resolve().parent / str(_cfg("FUTURES_REAL_LEDGER", "futures_real_ledger.json"))


# §108 — TÉLÉMÉTRIE opérationnelle, canal SÉPARÉ du registre d'ARGENT.
# Le registre est borné à 1000 évènements TOUTES ACTIONS CONFONDUES. Mesuré le 20/07 :
# l'auto-réparation de stop y occupait 600 places (60 %) contre 14 évènements d'argent (1,4 %),
# et à ~29 évts/h tout se renouvelait en ~34 h. Or CINQ consommateurs filtrent sur FUTURES_REAL
# (real_positions._parse_ledger_sltp, stop_guardian, trade_forensics,
# futures_report._symboles_trades, intended_sl_from_events) et AUCUN ne lit cette télémétrie :
# du bruit en écriture seule évinçait la donnée dont tout le monde dépend.
# PIRE : `intended_sl_from_events` relit FUTURES_REAL pour retrouver le SL INTENTIONNEL à
# re-poser — l'auto-réparation évinçait donc la donnée dont ELLE-MÊME a besoin. Auto-saboteur.
# Ici : append-only borné (pas de lecture-modification-écriture de 500 Ko à chaque tic sur le
# chemin de l'argent), et le registre retrouve ses 1000 places pour ce qui compte.
TELEMETRIE = Path(__file__).resolve().parent / "futures_telemetrie.jsonl"
TELEMETRIE_MAX_BYTES = 20_000_000


def _journal_telemetrie(event):
    """Télémétrie opérationnelle (auto-réparation de stop) — JAMAIS le registre d'argent.
    Best-effort : ne lève jamais, et son échec n'affecte aucune exécution."""
    try:
        import journal_append as ja
        return ja.append_jsonl(TELEMETRIE, event, max_bytes=TELEMETRIE_MAX_BYTES)
    except Exception:
        return False


def _journal(event):
    """Journalise un évènement d'ARGENT (best-effort). Le ledger est gitignored.
    La télémétrie opérationnelle passe par `_journal_telemetrie` (§108) : elle évinçait
    autrement les évènements que cinq consommateurs relisent."""
    path = _ledger_path()
    try:
        led = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"events": []}
    except Exception:
        led = {"events": []}
    led.setdefault("events", []).append(event)
    led["events"] = led["events"][-1000:]
    _write_ledger(led)                # atomique (journal d'argent réel, audit P3)


# ---------- sérialisation des OUVERTURES (Thème 2 : mur 250 sous concurrence) ----------

def _open_lock_path():
    return Path(__file__).resolve().parent / str(_cfg("FUTURES_OPEN_LOCK", FUTURES_OPEN_LOCK))


def _pending_path():
    return Path(__file__).resolve().parent / str(_cfg("FUTURES_PENDING_FILE", FUTURES_PENDING_FILE))


@contextlib.contextmanager
def open_gate(path=None):
    """Mutex INTER-PROCESSUS des ouvertures futures (flock exclusif NON bloquant).
    Sérialise « lire gross -> execute -> enregistrer la réservation » entre TOUS les
    ouvreurs de l'hôte (futures_auto, carry_auto, cycle manuel). yield True si la porte
    est prise, False si un autre ouvreur la tient déjà : l'appelant DOIT alors SAUTER le
    cycle (fail-closed — jamais ouvrir en concurrence d'un autre ouvreur). Fail-closed
    aussi si la couche verrou est indisponible (yield False). Le verrou est libéré à la
    sortie du bloc ET automatiquement par le noyau si le processus meurt (flock advisory
    sur un fd) : pas de verrou fantôme."""
    import os
    p = Path(path) if path else _open_lock_path()
    fd = None
    acquired = False
    try:
        try:
            import fcntl                                 # dans le try : indispo -> yield False (fail-closed)
            fd = os.open(str(p), os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except Exception:
            acquired = False      # porte tenue ailleurs OU couche verrou KO -> fail-closed
        yield acquired
    finally:
        if fd is not None:
            if acquired:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except Exception:
                    pass
            try:
                os.close(fd)
            except Exception:
                pass


def record_pending_open(client_oid, notional_usdt, book_before_usdt, now=None, path=None):
    """Enregistre une ouverture RÉELLE tout juste placée, pas forcément encore reflétée
    par le livre exchange (cohérence éventuelle). Sert de réservation « in-flight » à
    effective_gross pour que l'ouvreur SUIVANT ne soit pas aveugle à cette exposition.
    book_before_usdt = exposition EFFECTIVE au moment de l'ouverture (claim cumulé =
    book_before + notional). À appeler SOUS open_gate, juste après un execute()
    executed=True. Écriture atomique (tmp + os.replace)."""
    import os
    now = time.time() if now is None else now
    p = Path(path) if path else _pending_path()
    try:
        items = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        if not isinstance(items, list):
            items = []
    except Exception:
        # Illisible : on repart d'une liste vide pour NE PAS perdre CETTE réservation
        # (la sécurité vit dans effective_gross, qui, lui, fail-closed en INF sur corruption).
        items = []
    items.append({"oid": str(client_oid), "notional": float(notional_usdt or 0),
                  "book_before": float(book_before_usdt or 0), "ts": float(now)})
    items = [r for r in items if isinstance(r, dict)          # purge des périmées (borne le fichier)
             and float(now) - float(r.get("ts") or 0) <= PENDING_TTL_S]
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        pass


def remove_pending(client_oid, path=None):
    """Retire une réservation in-flight — rollback d'une pré-réservation (I3) dont l'ordre
    n'a finalement PAS ouvert, pour ne pas laisser d'exposition fantôme. Best-effort
    atomique ; fichier illisible -> ne touche à rien (effective_gross reste fail-closed
    en +inf tant qu'il est corrompu, donc l'expo n'est jamais sous-estimée entre-temps)."""
    import os
    p = Path(path) if path else _pending_path()
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            return
    except Exception:
        return
    kept = [r for r in items if not (isinstance(r, dict) and str(r.get("oid")) == str(client_oid))]
    if len(kept) == len(items):
        return
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        pass


def effective_gross(book_gross_usdt, now=None, path=None, ttl_s=None):
    """Exposition EFFECTIVE = max(livre exchange, plus haut niveau réclamé par une
    ouverture in-flight pas encore reflétée par le livre). Les réservations sont
    CUMULATIVES (record_pending_open enregistre l'expo EFFECTIVE à l'ouverture + notional)
    -> le MAX des claims = le niveau que le livre atteindra, sans double-compter l'expo
    partagée entre ouvreurs (la SOMME sur-compterait). Ferme le trou où un ouvreur lit un
    gross périmé juste après l'ouverture d'un autre. Fail-closed : livre non numérique ou
    réservations corrompues -> +inf (guards rejette toute ouverture). PUR (chemins injectables)."""
    now = time.time() if now is None else now
    ttl = PENDING_TTL_S if ttl_s is None else float(ttl_s)
    try:
        base = float(book_gross_usdt or 0)
    except (TypeError, ValueError):
        return float("inf")                       # livre non numérique -> fail-closed
    if not math.isfinite(base):
        return float("inf")                       # livre nan/inf -> fail-closed (jamais propager nan)
    p = Path(path) if path else _pending_path()
    if not p.exists():
        return base
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return float("inf")                       # réservations corrompues -> fail-closed
    if not isinstance(items, list):
        return float("inf")
    best = base
    for r in items:
        try:
            if not isinstance(r, dict):
                return float("inf")               # entrée inattendue -> fail-closed
            ts = float(r.get("ts"))
            if now - ts > ttl:
                continue                          # périmée : le livre a eu le temps de rattraper
            claim = float(r.get("book_before")) + float(r.get("notional"))  # expo effective cumulée réclamée
            if claim > best:                      # le livre atteindra ce niveau -> on le prend
                best = claim
        except (TypeError, ValueError):
            return float("inf")                   # champ non numérique -> fail-closed
    return best


def gated_open(agent, side, notional_usdt, leverage, *, read_book_gross, now=None,
               lock_path=None, pending_path=None, **execute_kwargs):
    """OUVERTURE SÉRIALISÉE — le point de câblage unique des ouvreurs (auto_dir, carry,
    alt_carry). Sous le verrou inter-processus open_gate :
      1. relit le gross du LIVRE via read_book_gross() (lecteur réseau de l'appelant) —
         SOUS le verrou, pour ne pas rater une ouverture concurrente ;
      2. y ajoute l'exposition in-flight (effective_gross) ;
      3. appelle execute() avec ce gross effectif ;
      4. si l'ordre part RÉELLEMENT, enregistre la réservation (record_pending_open) pour
         que l'ouvreur suivant en tienne compte avant que le livre ne l'ait reflétée.
    Fail-closed : porte tenue ailleurs -> skip ; livre illisible (None) -> skip. Dans les
    deux cas execute() n'est PAS appelé et on renvoie {'skipped': True, executed False}.
    Les FERMETURES/réductions n'utilisent PAS gated_open (exemptées du cap cumulé)."""
    now = time.time() if now is None else now
    with open_gate(path=lock_path) as locked:
        if not locked:
            return {"ok": False, "executed": False, "skipped": True,
                    "reasons": ["ouverture concurrente en cours (verrou d'ouverture)"]}
        book = read_book_gross()
        if book is None:
            return {"ok": False, "executed": False, "skipped": True,
                    "reasons": ["livre futures illisible — ouverture suspendue (fail-closed)"]}
        eff = effective_gross(book, now=now, path=pending_path)
        # Réserve l'expo EFFECTIVE à l'ouverture (claim cumulé = eff + notional) AVANT
        # l'ordre réel (I3) : si le process meurt entre l'ordre exécuté et l'enregistrement,
        # la réservation existe DÉJÀ -> l'ouvreur suivant n'est pas aveugle (fail-CLOSED).
        # On enregistre eff (pas le livre brut) pour que effective_gross prenne le MAX des
        # claims cumulatifs, sans double-compter l'in-flight partagé entre ouvreurs.
        token = f"prov{str(agent)[:3]}{int(now * 1000)}"
        record_pending_open(token, notional_usdt, eff, now=now, path=pending_path)
        res = execute(agent, side, notional_usdt, leverage, now=now,
                      gross_open_usdt=eff, **execute_kwargs)
        if not res.get("executed") and not res.get("ambiguous"):
            # rollback SEULEMENT sur un échec NET ; une réponse AMBIGUË (orderId:null, fill non
            # confirmé) peut avoir ouvert -> on GARDE la réservation (fail-closed pour le mur 250).
            remove_pending(token, path=pending_path)
        return res


def open_duplicate_reason(agent, symbol, side, *, par_sym=None, events=None, now=None, cooldown_s=None):
    """Raison de REFUS si OUVRIR (agent, symbol, side) ferait DOUBLON, sinon None. Protège le CLI
    manuel main() d'une double-invocation accidentelle (ou d'un re-run après réponse perdue dont
    l'ordre a rempli — les boucles auto, elles, ont leur throttle 4 h/8 h) :
      • côté déjà OUVERT dans le livre (par_sym) ; OU
      • ouverture RÉELLE récente du même (agent, symbole, côté) au journal (fenêtre cooldown).
    Fail-closed si le livre est illisible : on ne peut pas prouver l'absence de doublon. PUR
    (par_sym/events injectés). Le --force du CLI outrepasse délibérément."""
    now = time.time() if now is None else now
    cooldown = (float(_cfg("FUTURES_MANUAL_DUP_COOLDOWN_S", 120.0))
                if cooldown_s is None else float(cooldown_s))
    sym = str(symbol or SYMBOL).upper()
    side = str(side)
    if not isinstance(par_sym, dict) or par_sym.get("erreur"):
        return "livre des positions illisible — vérification anti-doublon impossible (fail-closed)"
    cotes = par_sym.get(sym) or {}
    if isinstance(cotes, dict) and cotes.get(side):
        return f"position {side} {sym} déjà ouverte (livre) — ouverture refusée (anti-doublon)"
    for e in reversed(events or []):
        if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
            continue
        o = e.get("order") or {}
        if o.get("reduce"):
            continue
        if (str(o.get("agent")) == str(agent) and str(o.get("side")) == side
                and str(o.get("symbol") or SYMBOL).upper() == sym):
            try:
                if now - float(e.get("ts")) <= cooldown:
                    return (f"ouverture {side} {sym} par '{agent}' il y a < {int(cooldown)}s "
                            "(journal) — ouverture refusée (anti-doublon)")
            except (TypeError, ValueError):
                pass
            break                                       # le plus récent ordre réel d'ouverture examiné
    return None


# ---------- gardes DURS (les 8 de §34 ; purs si on injecte l'état) ----------

def guards(agent, notional_usdt, leverage, *, equity_curve=None, gross_open_usdt=0.0,
           client_oid=None, seen_oids=None, hour_utc=None, macro_events=None, now=None,
           live=None, autonomous=None, futures_live=None, kill=None, edge_override=None,
           reduce=False):
    """Vérifie TOUTES les gardes avant un ordre futures. Retourne (ok, raisons).
    PUR si l'état est injecté (live/autonomous/futures_live/kill/equity_curve/...)."""
    reasons = []

    # 1. kill_switch : bloque les OUVERTURES. Une RÉDUCTION reste permise (audit P3) :
    # fermer n'aggrave jamais le risque — après un stop journalier, la boucle doit
    # pouvoir sortir d'une position même kill-switch armé (même principe que le
    # pré-vol daily_loss d'execute()).
    if kill is None:
        try:
            import risk_manager
            kill = risk_manager.kill_switch_active()
        except Exception:
            # Fail-CLOSED : la couche kill-switch est indisponible (import/exécution qui
            # lève). On lit le fichier DIRECTEMENT (chemin absolu ancré au dépôt) pour ne
            # pas rater un halt armé ; en cas de doute (lecture qui échoue), on BLOQUE.
            try:
                kill = (Path(__file__).resolve().parent / "KILL_SWITCH").exists()
            except Exception:
                kill = True
    if kill and not reduce:
        reasons.append("kill_switch actif")

    # 2. DOUBLE verrou : MANDATE_LIVE_ENABLED ET FUTURES_AUTONOMOUS_LIVE
    if live is None:
        try:
            import mandate
            live = mandate.live_enabled()
        except Exception:
            live = False
    if autonomous is None:
        autonomous = _autonomous_on()
    if not (live and autonomous):
        reasons.append("double verrou coupé (MANDATE_LIVE_ENABLED ET FUTURES_AUTONOMOUS_LIVE requis)")

    # 3. porte d'edge : agent réellement éligible LIVE (replay ET live). Peut être
    # OUTREPASSÉE par FUTURES_EDGE_GATE_OVERRIDE — décision propriétaire §45
    # (02/07/2026), consciente que 0 agent n'a d'edge mesuré. Remettre à 0 la referme.
    if futures_live is None:
        try:
            import mandate
            futures_live = mandate.futures_live_allowed(agent)
        except Exception:
            futures_live = False
    if edge_override is None:
        # _cfg = config.py SEUL, VOLONTAIRE : l'override est un knob de DÉCISION propriétaire
        # (comme les murs), pas un réglage .env. NE PAS basculer vers env_num/env_flag — un
        # FUTURES_EDGE_GATE_OVERRIDE=1 resté dans .env rouvrirait alors EN SILENCE une boucle
        # directionnelle à edge RÉFUTÉ sur argent réel. Reprise = éditer config.py (décision).
        edge_override = int(_cfg("FUTURES_EDGE_GATE_OVERRIDE", 0) or 0)
    if not futures_live and not edge_override:
        reasons.append(f"agent '{agent}' non éligible LIVE (porte d'edge non franchie)")

    # 4. levier ≤ mur dur (fail-closed : non numérique -> rejeté, jamais d'exception)
    #    _capped (pas _limit) : env/config peuvent ABAISSER le levier, JAMAIS dépasser ×5.
    max_lev = _capped("MANDATE_MAX_LEVERAGE", 5.0, FUT_ABS_MAX_LEVERAGE)
    try:
        lev = float(leverage or 0)
    except (TypeError, ValueError):
        lev = None
        reasons.append("levier invalide (non numérique)")
    if lev is not None and not math.isfinite(lev):
        reasons.append("levier non fini (nan/inf) — fail-closed")
        lev = None                                    # neutralise les comparaisons nan (toujours False)
    if lev is not None:
        if lev <= 0:
            reasons.append("levier ≤ 0")
        elif lev > max_lev:
            reasons.append(f"levier {lev} > mur dur {max_lev}")

    # 5. caps notional par trade ET exposition cumulée (fail-closed sur non numérique)
    try:
        notion = float(notional_usdt or 0)
    except (TypeError, ValueError):
        notion = None
        reasons.append("notional invalide (non numérique)")
    if notion is not None and not math.isfinite(notion):
        reasons.append("notional non fini (nan/inf) — fail-closed")
        notion = None                                 # neutralise les comparaisons nan (toujours False)
    if notion is not None:
        if notion <= 0:
            reasons.append("notional ≤ 0")
        # Les caps notional s'appliquent aux OUVERTURES : une RÉDUCTION (reduceOnly,
        # bornée à la position côté exchange) ne crée aucune exposition — l'exempter
        # permet de fermer en UN ordre une position construite par tranches
        # (cap carry 200, décision propriétaire 03/07).
        if not reduce:
            per_cap = _capped("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0, FUT_ABS_MAX_PER_TRADE_USDT)
            if notion > per_cap:
                reasons.append(f"notional {notion} > plafond/trade {per_cap}")
            gross_cap = _capped("FUTURES_REAL_MAX_GROSS_USDT", 20.0, FUT_ABS_MAX_GROSS_USDT)
            gross = float(gross_open_usdt or 0)
            if not math.isfinite(gross):              # nan/inf défaisait le mur (comparaison nan = False)
                reasons.append("exposition cumulée non finie (nan/inf) — fail-closed")
            elif gross + notion > gross_cap:
                reasons.append(f"exposition cumulée dépassée ({gross}+{notion} > {gross_cap})")

    # 6. halte drawdown (equity réelle)
    if equity_curve is not None:
        try:
            import mandate
            halt, dd_pct = mandate.drawdown_halt(equity_curve)
            if halt:
                reasons.append(f"halte drawdown ({dd_pct}% ≥ MDD toléré)")
        except Exception:
            pass

    # 7. session active + pas de black-out macro
    # NB (audit B-6) : gate de session ADVISORY/OPT-IN. La boucle futures RÉELLE appelle guards()
    # avec hour_utc=None (crypto = marché 24/7, aucune restriction de session PAR CONCEPTION) ->
    # ce filtre ne s'active que si un appelant fournit hour_utc (ex. bitget_hub_bridge advisory).
    if hour_utc is not None:
        try:
            import mandate
            if not mandate.in_active_session(hour_utc):
                reasons.append("hors fenêtre de session active")
        except Exception:
            pass
    if macro_events is not None:
        try:
            import mandate
            nw = time.time() if now is None else now
            if mandate.macro_blackout(nw, macro_events):
                reasons.append("black-out macro (annonce à fort impact)")
        except Exception:
            pass

    # 8. idempotence clientOid (rejoue sans doubler)
    if client_oid is not None and seen_oids is not None:
        if str(client_oid) in set(str(o) for o in seen_oids):
            reasons.append(f"clientOid déjà vu ({client_oid}) — anti-doublon")

    return (not reasons, reasons)


# ---------- construction de la demande (pure) ----------

def _qty(x, decimals=6):
    """Notation DÉCIMALE (jamais scientifique) — Bitget rejette '8.3e-05'."""
    return f"{round(float(x), decimals):.{decimals}f}"


def build_futures_order(agent, side, notional_usdt, leverage, entry=None,
                        stop_loss=None, take_profit=None, client_oid=None, *, reduce=False,
                        size_btc=None, symbol=None):
    """Construit la demande d'ordre futures BORNÉE. PUR, sans effet de bord.

      • side ∈ {'long','short'} (vocabulaire neutre — l'open/close venue vient à l'étape 2) ;
      • reduce=True -> réduit/ferme une position existante ; False -> ouvre/augmente ;
      • le levier est CLAMPÉ au mur dur (jamais au-delà de mandate.max_leverage()).
    Retourne un dict descriptif (symbole, side, reduce, notional, levier, marge, oid, SL/TP).
    """
    s = str(side).lower()
    if s not in ("long", "short"):
        raise ValueError(f"side invalide: {side!r} (attendu 'long' ou 'short')")
    max_lev = _capped("MANDATE_MAX_LEVERAGE", 5.0, FUT_ABS_MAX_LEVERAGE)
    lev = max(1.0, min(float(max_lev), float(leverage)))   # borné par le mur, jamais au-delà
    notion = float(notional_usdt)
    order = {
        "symbol": str(symbol or SYMBOL).upper(),
        "side": s,
        "reduce": bool(reduce),
        "agent": str(agent),
        "notional_usdt": round(notion, 2),
        "leverage": round(lev, 2),
        "marginUsdt": round(notion / lev, 2) if lev else None,
        "size": _qty(notion / float(entry)) if entry else None,
        "clientOid": str(client_oid) if client_oid is not None else None,
        "execution_mode": _execution_mode(),
    }
    if size_btc is not None:
        # taille EXPLICITE (fermetures : la taille exacte de la position, pas un
        # notional re-converti qui laisserait une poussière infermable après floor)
        order["size_btc"] = float(size_btc)
    if entry is not None:
        order["entry"] = float(entry)
    if stop_loss is not None:
        order["stop_loss"] = float(stop_loss)
    if take_profit is not None:
        order["take_profit"] = float(take_profit)
    return order


def liquidity_capped_notional(notional, side, top_of_book):
    """PUR (§98). Plafonne le notionnel d'OUVERTURE par la liquidité AFFICHÉE au top-of-book,
    du côté que l'ordre TRAVERSE (long achète -> traverse l'ASK ; short vend -> traverse le BID) :
    on ne balaie jamais plus que ce qui est visible. Via data_guards.cap_by_liquidity — NE PEUT
    QUE réduire (jamais augmenter). FAIL-OPEN : top illisible / taille nulle / side inconnu ->
    notional INCHANGÉ (une garde de données ne doit pas empêcher de trader quand la profondeur
    est illisible). Retourne (notional_capé, a_capé:bool). Réservé aux OUVERTURES par l'appelant
    (jamais une réduction : fermer doit rester possible en entier)."""
    try:
        import data_guards as dg
        n = float(notional)
    except (TypeError, ValueError):
        return notional, False
    if not top_of_book or n <= 0:
        return notional, False
    s = str(side).lower()
    if s == "long":
        price, size = top_of_book.get("ask"), top_of_book.get("ask_size")
    elif s == "short":
        price, size = top_of_book.get("bid"), top_of_book.get("bid_size")
    else:
        return notional, False
    capped = dg.cap_by_liquidity(n, price, size)
    if capped is None:
        return notional, False
    capped = round(float(capped), 2)
    return (capped, capped < n - 1e-9)


def _equity_now(equity_curve):
    """Dernière equity LISIBLE du livre (dernier point fini > 0 de la courbe), ou None.
    Base du cap de risque par trade ; sans historique lisible -> None (fail-open)."""
    from numeric_utils import safe_float
    if not equity_curve:
        return None
    for v in reversed(list(equity_curve)):
        f = safe_float(v)
        if f is not None and math.isfinite(f) and f > 0:
            return f
    return None


def risk_capped_notional(notional, entry, stop_loss, equity, risk_pct=None):
    """Cap de RISQUE PAR TRADE (Kovner, *Market Wizards*), PUR si `risk_pct` est injecté
    (sinon lit `FUTURES_RISK_PCT_PER_TRADE`) — garde additionnelle SOUS les murs absolus 50/250. Réduit le notionnel pour que la perte encourue si le stop-loss
    est touché (|entry−SL|/entry × notional) ne dépasse pas `risk_pct` % de l'equity du
    livre. Le mur 50/trade est en DOLLARS fixes (donc en *notional*) ; cette garde borne le
    *risque réellement encouru* (distance au stop × taille), l'invariant le plus universel
    des grands traders. Elle ne fait que RÉDUIRE — jamais augmenter, jamais desserrer un mur.

    FAIL-OPEN (retourne le notional INCHANGÉ, binds=False) si : garde désactivée
    (`risk_pct` ≤ 0 via FUTURES_RISK_PCT_PER_TRADE), ou entry/SL/equity/notional
    illisible / non fini / ≤ 0, ou distance de stop nulle (SL collé/absent). Une equity
    illisible ne BLOQUE pas ici : le stop de perte journalier interdit déjà d'OUVRIR à
    l'aveugle (daily_loss_breach). Retourne (notional_capé, binds:bool). OUVERTURES only."""
    from numeric_utils import safe_float
    try:
        # UN SEUL lecteur du knob (revue §111, défaut 2) : env-first, comme le chemin Kelly —
        # un resserrage via .env vaut AUSSI pour le chemin fail-open (risk_pct=None).
        risk_pct = float(_env_num("FUTURES_RISK_PCT_PER_TRADE", 1.0) if risk_pct is None else risk_pct)
    except (TypeError, ValueError):
        return notional, False
    if not math.isfinite(risk_pct) or risk_pct <= 0:              # garde désactivée
        return notional, False
    n, e, sl, eq = (safe_float(notional), safe_float(entry),
                    safe_float(stop_loss), safe_float(equity))
    if None in (n, e, sl, eq) or not all(math.isfinite(x) for x in (n, e, sl, eq)):
        return notional, False
    if n <= 0 or e <= 0 or eq <= 0:
        return notional, False
    dist = abs(e - sl)
    if not math.isfinite(dist) or dist <= 0:                      # SL absent/collé -> incalculable
        return notional, False
    budget = risk_pct / 100.0 * eq                                # perte USDT tolérée
    if n * dist / e <= budget:                                    # le notionnel plein ne mord pas
        return notional, False
    capped = math.floor(budget * e / dist * 100.0) / 100.0        # floor : ne JAMAIS dépasser le budget
    return min(capped, n), True                                   # garde-fou : jamais d'agrandissement


# ---------- stop de perte JOURNALIER (arme le kill-switch, fail-closed) ----------

def daily_loss_state_check(equity, state, now=None, stop_pct=None, cliff_pct=None):
    """PUR. Compare l'equity courante à l'equity d'OUVERTURE du jour (mémorisée dans
    `state` = {"day", "open_equity", "last_equity"}). Retourne (breach, nouvel_état).
    Nouveau jour -> l'equity courante devient l'ouverture. Equity illisible -> BREACH
    (fail-closed : on ne trade pas à l'aveugle).

    RE-BASELINE sur FLUX DE CAPITAL (correctif faux breach 05/07) : un saut du livre
    d'un tick à l'autre > cliff_pct de l'ouverture est impossible en P&L de trading
    borné (murs 50/250, progressif) -> c'est un dépôt/retrait/CONVERT (ex. conversion
    BGBTC). On DÉCALE l'ouverture du même montant : le stop continue de mesurer le P&L,
    jamais un mouvement de fonds. Une vraie perte, elle, s'accumule par petits pas et ne
    franchit jamais ce seuil -> le stop la capte normalement."""
    stop_pct = float(_cfg("FUTURES_DAILY_LOSS_STOP_PCT", 5.0) if stop_pct is None else stop_pct)
    cliff_pct = float(_cfg("FUTURES_BOOK_CLIFF_REBASE_PCT", 15.0) if cliff_pct is None else cliff_pct)
    now = time.time() if now is None else now
    day = int(now // 86400)
    from numeric_utils import safe_float
    eq = safe_float(equity)
    state = dict(state or {})
    if eq is None or eq <= 0:
        return True, state                        # aveugle -> on n'ouvre pas
    if state.get("day") != day or safe_float(state.get("open_equity")) is None:
        state = {"day": day, "open_equity": eq, "last_equity": eq}
        return False, state
    ouverture = float(state["open_equity"])
    last = safe_float(state.get("last_equity"))
    if last is not None and cliff_pct > 0 and abs(eq - last) > ouverture * cliff_pct / 100.0:
        ouverture += (eq - last)                   # la baseline SUIT le flux de capital
        state["open_equity"] = ouverture
    state["last_equity"] = eq
    breach = eq < ouverture * (1.0 - stop_pct / 100.0)
    return breach, state


def _futures_equity():
    """Equity USDT du wallet futures (lecture seule). None si illisible."""
    try:
        import bitget_balance_reader as br
        from numeric_utils import safe_float
        for r in (br.get_futures_accounts() or {}).get("data") or []:
            if str(r.get("marginCoin", "")).upper() == MARGIN_COIN:
                return safe_float(r.get("accountEquity") or r.get("usdtEquity")
                                  or r.get("available"))
    except Exception:
        pass
    return None


def _expo_spot_btc_usdt():
    """Valeur USDT de l'exposition BTC SPOT (BTC + wrappers décotés, mêmes tokens
    que la couverture carry). None si illisible. Lecture seule."""
    try:
        import bitget_balance_reader as br
        from numeric_utils import safe_float
        tokens = dict(_cfg("CARRY_COUVERTURE_TOKENS", {"BTC": 1.0, "BGBTC": 0.9}))
        quantite, vu = 0.0, False
        for r in (br.get_spot_assets() or {}).get("data") or []:
            coin = str(r.get("coin", "")).upper()
            if coin in tokens:
                vu = True
                quantite += ((safe_float(r.get("available")) or 0.0)
                             + (safe_float(r.get("frozen")) or 0.0)) * float(tokens[coin])
        if not vu:
            return None
        prix = _mark_price()
        return quantite * prix if prix else None
    except Exception:
        return None


def _book_equity():
    """Equity du LIVRE piloté = wallet futures + exposition BTC spot (la jambe longue
    des carrys). C'est la base du stop journalier depuis le cap carry 200 (décision
    propriétaire 03/07) : un short carry HEDGÉ par le spot ferait osciller l'equity
    futures seule (faux breach kill-switch sur tout BTC +6 %) alors que le livre
    couvert, lui, est stable. None si UNE composante est illisible (bases mélangées
    entre deux mesures = faux breach garanti — on préfère l'aveu d'aveuglement)."""
    fut = _futures_equity()
    expo = _expo_spot_btc_usdt()
    if fut is None or expo is None:
        return None
    return fut + expo


def _write_ledger(led):
    """Écriture ATOMIQUE du ledger (tmp + os.replace — audit P3 : un write direct
    concurrent scan/CLI pouvait laisser un JSON à moitié écrit sur le journal
    d'ARGENT RÉEL). Best-effort."""
    import os
    path = _ledger_path()
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass


def daily_loss_breach(now=None):
    """Stop de perte JOURNALIER réel : lit l'equity futures, compare à l'ouverture du
    jour (état persisté dans le ledger). Deux régimes distincts (audit P3) :
      • equity LISIBLE et stop franchi -> BREACH CONFIRMÉ : KILL-SWITCH armé + alerte
        (dédup 1/jour) ;
      • equity ILLISIBLE (blip API/réseau) -> True (on n'OUVRE pas à l'aveugle,
        fail-closed) mais SANS armer le kill-switch global — un raté de lecture
        horaire gelait toute la machine, accumulation spot comprise."""
    path = _ledger_path()
    try:
        led = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        led = {}
    ancien = led.get("daily_loss_state") or {}
    equity = _book_equity()                       # livre couvert (futures + expo BTC spot)
    breach, state = daily_loss_state_check(equity, led.get("daily_loss_state"), now=now)
    led["daily_loss_state"] = state
    if state.get("day") is not None and state.get("day") != ancien.get("day"):
        # journal d'EQUITY quotidien (une ligne par jour UTC, cap 400) : la courbe
        # qui tranchera la revue des caps — gratuite, le tripwire lit déjà l'equity.
        led.setdefault("equity_journal", []).append(
            {"day": state["day"], "open_equity": state.get("open_equity")})
        led["equity_journal"] = led["equity_journal"][-400:]
    confirme = breach and equity is not None and equity > 0 and state.get("open_equity")
    jour = int((time.time() if now is None else now) // 86400)
    deja_alerte = int(led.get("daily_loss_alert_day", -1) or -1) == jour
    if confirme and not deja_alerte:
        led["daily_loss_alert_day"] = jour            # dédup : une alerte par jour UTC
    _write_ledger(led)
    if confirme:
        try:
            (Path(__file__).resolve().parent / "KILL_SWITCH").touch()   # idempotent
        except Exception:
            pass
        if not deja_alerte:
            try:
                import telegram_notifier as tn
                tn.send_telegram("🛑 STOP PERTE JOURNALIER FUTURES franchi — kill-switch ARMÉ "
                                 "(plus aucun ordre réel). Lever : supprimer KILL_SWITCH.")
            except Exception:
                pass
    return breach


def journal_equity_point(now=None, min_interval_s=600, cap=2016):
    """Point d'équité INTRAJOURNALIÈRE du LIVRE dans le ledger (best-effort,
    throttlé ≥10 min, plafonné 2016 points ≈ 7 jours à 5 min). Appelé par la boucle
    auto à chaque cycle : avec 1 point/jour, la halte MDD (garde 6) raisonnait sur
    2 points — elle raisonne désormais sur une vraie courbe. True si écrit."""
    now = time.time() if now is None else now
    try:
        led = json.loads(_ledger_path().read_text(encoding="utf-8"))
    except Exception:
        led = {}
    pts = [p for p in led.get("equity_intraday", []) if isinstance(p, list) and len(p) == 2]
    if pts and (now - float(pts[-1][0])) < float(min_interval_s):
        return False
    eq = _book_equity()
    if not eq or eq <= 0:
        return False                              # illisible -> pas de faux point
    pts.append([int(now), round(float(eq), 6)])
    led["equity_intraday"] = pts[-int(cap):]
    _write_ledger(led)
    return True


def place_partial_tp(symbol, side, size_btc, price, runner=None):
    """TP PARTIEL (§82) : ordre LIMITE GTC de RÉDUCTION qui écrème une fraction de la
    position au premier objectif (TP1) — le TP/SL PRÉRÉGLÉ à l'ouverture couvre le
    reste (et si le SL ferme tout, l'ordre réduction devient caduc côté exchange).
    RÉDUCTION pure : n'ouvre jamais d'exposition (même exemption de caps que les
    reduce §45) ; kill-switch respecté ; sous les minima du contrat -> refus propre
    (c'est le « quand c'est possible ») ; échec journalisé, JAMAIS bloquant — le
    préréglé reste le filet."""
    from numeric_utils import safe_float
    symbol = str(symbol or SYMBOL).upper()
    if (Path(__file__).resolve().parent / "KILL_SWITCH").exists():
        return {"ok": False, "executed": False, "reasons": ["kill-switch actif"]}
    spec = _contract_spec(symbol)
    px = safe_float(price)
    size = safe_float(size_btc)
    if not spec or not px or px <= 0 or not size or size <= 0:
        return {"ok": False, "executed": False, "reasons": ["spec/prix/taille illisibles"]}
    step = safe_float(spec.get("step")) or 0.0001
    mini = safe_float(spec.get("min_size")) or step
    vol_place = int(safe_float(spec.get("vol_place")) or 4)
    price_place = int(safe_float(spec.get("price_place")) or 1)
    size = round(int(size / step) * step, vol_place)
    if size < mini:
        return {"ok": False, "executed": False,
                "reasons": [f"tranche TP1 {size} sous le minimum {mini} (partiel impossible)"]}
    marge_mode = _marge_mode()
    pos_mode = resolve_pos_mode(positions_ouvertes(), _cfg("FUTURES_POSITION_MODE", "hedge_mode"))
    long_ = str(side) == "long"
    o = {"symbol": symbol, "productType": PRODUCT_TYPE, "marginCoin": MARGIN_COIN,
         "marginMode": str(marge_mode or "isolated"),
         "size": f"{size:.{vol_place}f}",
         "orderType": "limit", "force": "gtc",
         "price": f"{round(px, price_place):.{price_place}f}",
         "clientOid": f"tp1{int(time.time() * 1000)}"}
    if str(pos_mode) == "hedge_mode":
        o["side"] = "buy" if long_ else "sell"        # côté de la POSITION à réduire
        o["tradeSide"] = "close"
    else:
        o["side"] = "sell" if long_ else "buy"
        o["reduceOnly"] = "YES"
    out = _run(["futures", "futures_place_order", "--orders", json.dumps([o])], runner=runner)
    compact = (out or "").replace(" ", "").lower()
    ok = bool(out) and '"ok":false' not in compact and "error" not in compact
    _journal({"ts": int(time.time()), "action": "FUTURES_TP_PARTIAL",
              "order": {"symbol": symbol, "side": side, "size_btc": size,
                        "price": round(px, price_place), "clientOid": o["clientOid"]},
              "ok": ok, "response": str(out)[:300]})
    return {"ok": ok, "executed": ok, "clientOid": o["clientOid"], "response": out}


def drawdown_status():
    """État LECTURE SEULE de la halte drawdown (garde 6) : {halt, dd_pct, max_dd_pct,
    peak, equity, n_points}. Best-effort ({} si illisible) — consommé par
    futures_report et futures_auto --status pour que la halte soit VISIBLE (une
    halte silencieuse laissait croire que la boucle allait ouvrir alors que chaque
    tentative était refusée)."""
    try:
        import mandate
        curve = equity_curve()
        halt, dd_pct = mandate.drawdown_halt(curve)
        return {"halt": bool(halt), "dd_pct": dd_pct,
                "max_dd_pct": float(_cfg("MANDATE_MAX_DRAWDOWN_PCT", 20.0)),
                "peak": round(max(curve), 2) if curve else None,
                "equity": round(curve[-1], 2) if curve else None,
                "n_points": len(curve)}
    except Exception:
        return {}


def rebase_equity(confirm=False, now=None):
    """OUTIL PROPRIÉTAIRE : réancre la courbe d'equity intrajournalière APRÈS un
    mouvement de capital délibéré (dépôt/retrait/virement hors du livre piloté).

    Pourquoi : la garde 6 (halte MDD) mesure le drawdown du LIVRE (wallet futures +
    expo BTC spot). Un retrait légitime y est indistinguable d'une perte -> halte
    « fantôme » qui ne se lève pas d'elle-même (le pic reste ~7 j dans la fenêtre
    intrajournalière, même si les fonds reviennent). Constaté le 05/07 : equity
    402 -> 240 par mouvement de capital (PnL bot −0.10 $), halte 40 % permanente.

    Ce réancrage est une DÉCISION PROPRIÉTAIRE EXPLICITE (--confirm obligatoire,
    DRY sinon) : il repart la courbe du point courant. Il ne desserre AUCUN mur
    (caps 50/250, levier ×5, stop journalier, kill-switch, porte d'edge intacts)
    et JOURNALISE l'état remplacé (pic, dd, n points) dans le ledger — traçable.
    Refus si l'equity du livre est illisible (fail-closed)."""
    now = time.time() if now is None else now
    avant = drawdown_status()
    eq = _book_equity()
    if eq is None or eq <= 0:
        return {"ok": False, "avant": avant,
                "raison": "equity du livre illisible — réancrage refusé (fail-closed)"}
    if not confirm:
        return {"ok": True, "dry": True, "avant": avant, "equity_livre": round(float(eq), 2),
                "note": "préview — relancer avec --confirm pour réancrer la courbe"}
    try:
        led = json.loads(_ledger_path().read_text(encoding="utf-8"))
    except Exception:
        led = {}
    led["equity_intraday"] = [[int(now), round(float(eq), 6)]]
    _write_ledger(led)
    _journal({"ts": int(now), "action": "FUTURES_EQUITY_REBASE", "avant": avant,
              "equity_livre": round(float(eq), 6),
              "note": "réancrage propriétaire après mouvement de capital"})
    return {"ok": True, "dry": False, "avant": avant, "apres": drawdown_status(),
            "equity_livre": round(float(eq), 2)}


def equity_curve():
    """Courbe d'equity du LIVRE : points INTRAJOURNALIERS (equity_intraday, écrits
    par la boucle via journal_equity_point) sinon repli sur les ouvertures
    JOURNALIÈRES (equity_journal, écrites par le tripwire) ; + point courant.
    Alimente la HALTE DRAWDOWN du mandat (garde 6) sur le chemin réel. [] si rien
    (pas de halte sans historique : la protection grandit avec les points)."""
    try:
        led = json.loads(_ledger_path().read_text(encoding="utf-8"))
    except Exception:
        led = {}
    from numeric_utils import safe_float
    pts = [safe_float(p[1]) for p in led.get("equity_intraday", [])
           if isinstance(p, list) and len(p) == 2]
    pts = [p for p in pts if p and p > 0]
    if not pts:                                   # repli : journal quotidien (1 pt/jour)
        pts = [safe_float(r.get("open_equity")) for r in led.get("equity_journal", [])
               if isinstance(r, dict)]
        pts = [p for p in pts if p and p > 0]
    eq = _book_equity()                           # même base que le journal (livre couvert)
    if eq:
        pts.append(eq)
    return pts


# ---------- mode de marge ADAPTATIF (union -> crossed forcé) ----------

def resolve_marge_mode(mode_cfg, asset_mode):
    """PUR. Mode de marge EFFECTIF : en mode multi-devises (assetMode 'union'),
    Bitget INTERDIT l'isolé (« currencies mixed » -> HTTP 400) — on force 'crossed'.
    Compte en mode mono-devise (ou illisible) -> le mode configuré (défaut isolé :
    perte max d'une position = sa marge)."""
    if str(asset_mode or "").lower() == "union":
        return "crossed"
    return str(mode_cfg or "isolated")


def _asset_mode():
    """assetMode du compte futures ('union'/'single'), caché 1h. None si illisible."""
    def _fetch():
        import bitget_balance_reader as br
        for r in (br.get_futures_accounts() or {}).get("data") or []:
            if str(r.get("marginCoin", "")).upper() == MARGIN_COIN:
                return r.get("assetMode")
        return None
    try:
        import runtime_cache as rc
        return rc.get("fut_asset_mode", 3600, _fetch, fallback=None)
    except Exception:
        return None


def _marge_mode():
    """Mode de marge effectif du moment (adaptatif au réglage du compte)."""
    return resolve_marge_mode(_cfg("FUTURES_MARGIN_MODE", "isolated"), _asset_mode())


# ---------- mapping vers l'API Bitget v2 (purs) ----------

def size_for(notional_usdt, price, spec):
    """PUR. Taille en BTC : notional/prix, arrondie VERS LE BAS au pas du contrat.
    None si spec/prix illisibles, sous la taille minimale ou sous le notional minimal
    (on n'envoie jamais un ordre que l'exchange rejetterait ou gonflerait)."""
    from numeric_utils import safe_float
    notional, price = safe_float(notional_usdt), safe_float(price)
    if not spec or notional is None or price is None or price <= 0 or notional <= 0:
        return None
    step = safe_float(spec.get("step")) or 0.0001
    mini = safe_float(spec.get("min_size")) or step
    min_usdt = safe_float(spec.get("min_usdt")) or 5.0
    vol_place = int(safe_float(spec.get("vol_place")) or 4)
    brut = notional / price
    size = int(brut / step) * step                # arrondi VERS LE BAS au pas
    size = round(size, vol_place)
    if size < mini or size * price < min_usdt:
        return None
    return size


def to_bitget_order(order, spec, price, marge_mode=None, pos_mode=None, style=None, maker_price=None):
    """PUR. Demande bornée -> ordre API Bitget v2, au FORMAT DU MODE DE POSITION :
      • hedge_mode (cible depuis le 03/07 — long ET short simultanés) : side = côté
        de la POSITION (buy=long, sell=short, convention Bitget), tradeSide
        open/close, pas de reduceOnly ;
      • one_way_mode (transitoire tant qu'une position historique est ouverte) :
        side = direction d'exécution + reduceOnly YES/NO.
    Ouvertures en limit IOC plafonné (anti-slippage), RÉDUCTIONS en market ;
    marge selon `marge_mode` (crossed forcé en compte multi-devises) ; TP/SL
    préréglés au tick. None si la taille est infaisable (sous les minima)."""
    from numeric_utils import safe_float
    reduce = bool(order.get("reduce"))
    explicite = safe_float(order.get("size_btc")) if reduce else None
    if explicite is not None and explicite > 0:
        # fermeture à taille EXACTE : reduceOnly borne à la position côté exchange,
        # on relève au minimum du contrat pour que même une poussière soit fermable.
        mini = safe_float((spec or {}).get("min_size")) or 0.0001
        size = max(explicite, mini)
    else:
        size = size_for(order.get("notional_usdt"), price, spec)
    if size is None:
        return None
    long_ = str(order.get("side")) == "long"
    vol_place = int((spec or {}).get("vol_place") or 4)
    price_place = int((spec or {}).get("price_place") or 1)
    o = {"symbol": str(order.get("symbol") or SYMBOL).upper(),
         "productType": PRODUCT_TYPE, "marginCoin": MARGIN_COIN,
         "marginMode": str(marge_mode or _cfg("FUTURES_MARGIN_MODE", "isolated")),
         "size": f"{size:.{vol_place}f}"}
    pm = str(pos_mode or _cfg("FUTURES_POSITION_MODE", "hedge_mode"))
    if pm == "hedge_mode":
        o["side"] = "buy" if long_ else "sell"        # côté de la POSITION (convention Bitget)
        o["tradeSide"] = "close" if reduce else "open"
        side_exec = o["side"]                          # ouverture : buy exécute achat, sell exécute vente
    else:
        side_exec = ("sell" if long_ else "buy") if reduce else ("buy" if long_ else "sell")
        o["side"] = side_exec
        o["reduceOnly"] = "YES" if reduce else "NO"
    # style d'exécution (parité avec spot_executor, audit « plein potentiel ») :
    #   • MAKER : OUVERTURE post-only au prix FOURNI (l'appelant passe le meilleur bid pour
    #     un achat / ask pour une vente). Bitget REJETTE si l'ordre croiserait -> jamais de
    #     frais taker (~2 bps vs ~6). Un non-fill est géré en aval (_place_maker : poll court
    #     -> annulation -> repli taker du restant). Le `style` peut être forcé par l'appelant
    #     (le repli taker construit un limit_ioc même quand FUTURES_EXEC_STYLE=maker).
    #   • LIMIT_IOC (défaut) : OUVERTURE en limit IOC plafonné à ±tol% : remplit tout de suite
    #     comme un market mais JAMAIS au-delà du plafond (anti-slippage borné ; partiel = risque
    #     réduit) ;
    #   • RÉDUCTION en market : la sortie doit TOUJOURS réussir.
    style = str(style if style is not None else _cfg("FUTURES_EXEC_STYLE", "limit_ioc")).lower()
    if not reduce and style == "maker" and safe_float(price):
        # TAILLE déjà calculée sur `price` (mark, plus haut via size_for) -> respecte le
        # notional approuvé par guards(). PRIX D'ORDRE = maker_price fourni (meilleur bid pour
        # un achat / ask pour une vente) pour le post-only ; repli sur `price` si absent.
        o["orderType"] = "limit"
        o["force"] = "post_only"
        px = float(maker_price) if safe_float(maker_price) else float(price)
        o["price"] = f"{round(px, price_place):.{price_place}f}"
    elif not reduce and style == "limit_ioc" and safe_float(price):
        tol = float(_cfg("FUTURES_SLIPPAGE_TOL_PCT", 0.10)) / 100.0
        cap = float(price) * (1.0 + tol) if side_exec == "buy" else float(price) * (1.0 - tol)
        o["orderType"] = "limit"
        o["force"] = "ioc"
        o["price"] = f"{round(cap, price_place):.{price_place}f}"
    else:
        o["orderType"] = "market"
    if order.get("clientOid"):
        o["clientOid"] = str(order["clientOid"])
    if not reduce:                                # TP/SL préréglés à l'ouverture seulement
        if order.get("take_profit") is not None:
            o["presetStopSurplusPrice"] = f"{round(float(order['take_profit']), price_place):.{price_place}f}"
        if order.get("stop_loss") is not None:
            o["presetStopLossPrice"] = f"{round(float(order['stop_loss']), price_place):.{price_place}f}"
    return o


# ---------- lectures marché (best-effort, cachées) ----------

def _contract_spec(symbol=None):
    """Spécifications du contrat (pas, minima, décimales), PAR SYMBOLE. None si illisible."""
    symbol = str(symbol or SYMBOL).upper()
    def _fetch():
        import bitget_hub_bridge as hub
        from numeric_utils import safe_float
        d = hub._read(["futures", "futures_get_contracts", "--productType", PRODUCT_TYPE,
                       "--symbol", symbol])
        rows = (d or {}).get("data") or []
        r = rows[0] if rows else {}
        if not r:
            return None
        return {"min_size": safe_float(r.get("minTradeNum")),
                "step": safe_float(r.get("sizeMultiplier")),
                "vol_place": int(safe_float(r.get("volumePlace")) or 4),
                "price_place": int(safe_float(r.get("pricePlace")) or 1),
                "min_usdt": safe_float(r.get("minTradeUSDT"))}
    try:
        import runtime_cache as rc
        return rc.get(f"fut_contract_spec:{symbol}", 86400, _fetch, fallback=None)
    except Exception:
        return None


def _mark_price(symbol=None):
    """Dernier prix d'un perp (lecture seule). None si illisible."""
    try:
        import bitget_hub_bridge as hub
        from numeric_utils import safe_float
        d = hub._read(["futures", "futures_get_ticker", "--productType", PRODUCT_TYPE,
                       "--symbol", str(symbol or SYMBOL).upper()])
        rows = (d or {}).get("data") or []
        r = rows[0] if rows else {}
        return safe_float(r.get("lastPr") or r.get("markPrice") or r.get("last"))
    except Exception:
        return None


def _top_of_book(symbol=None):
    """Meilleur bid/ask + TAILLES du perp (MÊME ticker que _mark_price, aucune requête en
    plus). Sert de plafond de liquidité (§98). Lecture seule, best-effort -> None si illisible
    (fail-open : pas de cap). Gardé par hub.available() (hermétique hors-ligne / tests)."""
    try:
        import bitget_hub_bridge as hub
        from numeric_utils import safe_float
        if not hub.available():
            return None
        d = hub._read(["futures", "futures_get_ticker", "--productType", PRODUCT_TYPE,
                       "--symbol", str(symbol or SYMBOL).upper()])
        rows = (d or {}).get("data") or []
        r = rows[0] if rows else {}
        bid, ask = safe_float(r.get("bidPr")), safe_float(r.get("askPr"))
        if bid and ask and bid > 0 and ask > 0:
            ts = safe_float(r.get("ts"))              # horodatage marché (ms) de la cotation
            age_ms = (time.time() * 1000.0 - ts) if ts else None
            return {"bid": bid, "ask": ask,
                    "bid_size": safe_float(r.get("bidSz")) or 0.0,
                    "ask_size": safe_float(r.get("askSz")) or 0.0,
                    "ts": ts, "age_ms": age_ms}
    except Exception:
        pass
    return None


def quote_too_stale(top_of_book, max_age_ms=None):
    """PUR/testable (§98). True SEULEMENT si le carnet est CONFIRMÉ périmé (âge LISIBLE
    et > seuil) — via data_guards.quote_fresh. Âge absent/illisible -> False (FAIL-OPEN :
    on ne bloque pas sur une donnée manquante, seulement sur une staleness AVÉRÉE, ex.
    flux gelé). Petit âge négatif (dérive d'horloge : notre horloge derrière celle de
    Bitget) clampé à 0 -> considéré frais. Seuil généreux (feed sain ~260 ms) via
    FUTURES_MAX_QUOTE_AGE_MS (défaut 3000) : ne mord qu'un flux réellement gelé."""
    if not top_of_book:
        return False
    from numeric_utils import safe_float
    age = safe_float(top_of_book.get("age_ms"))
    if age is None:
        return False
    import data_guards as dg
    if max_age_ms is None:
        from config_utils import cfg as _cfg
        max_age_ms = _cfg("FUTURES_MAX_QUOTE_AGE_MS", 3000)
    return not dg.quote_fresh(max(0.0, age), max_age_ms=float(max_age_ms))


# ---------- exécution RÉELLE (étape 2, §45) ----------

def _run(cmd, runner=None):
    """Lance la commande bgc d'ÉCRITURE (sans --read-only). runner injectable (tests)."""
    if runner is not None:
        return runner(cmd)
    try:
        import bitget_hub_bridge as hub
        if not hub.available():
            return None
        import subprocess
        p = subprocess.run(["bgc", *cmd], capture_output=True, text=True,
                           timeout=30, env=hub._hub_env())
        return ((p.stdout or "") + (p.stderr or "")).strip() or None
    except Exception:
        return None


_POS_MODE_MEMO = {"ts": 0.0, "mode": None}


def positions_ouvertes(runner=None, symbol=None):
    """Lignes de positions ouvertes (lecture seule) — TOUS les symboles par défaut
    (multi-symbole §47), filtre optionnel. None si illisible."""
    try:
        import bitget_hub_bridge as hub
        d = hub._read(["futures", "futures_get_positions", "--productType", PRODUCT_TYPE])
        rows = (d or {}).get("data")
        if rows is None:
            return None
        if symbol:
            return [r for r in rows if str(r.get("symbol", "")).upper() == str(symbol).upper()]
        return rows
    except Exception:
        return None


def resolve_pos_mode(rows_positions, mode_cfg):
    """PUR. Mode de position EFFECTIF : une position OUVERTE fait AUTORITÉ (Bitget
    refuse de changer de mode en position — son posMode est la seule vérité) ;
    à plat -> le mode CIBLE configuré (hedge_mode depuis la décision du 03/07)."""
    for r in rows_positions or []:
        pm = str((r or {}).get("posMode") or "")
        if pm in ("one_way_mode", "hedge_mode"):
            return pm
    return str(mode_cfg or "hedge_mode")


def _ensure_position_mode(runner=None, rows=None):
    """Aligne le compte sur le mode de position EFFECTIF (resolve_pos_mode) :
    à plat, bascule vers le mode cible (hedge_mode — déclaré par le propriétaire
    03/07, permet carry ET directionnel simultanés) ; en position, AUCUN appel de
    bascule (l'exchange refuserait : on formate les ordres au mode de la position).
    Retourne le mode effectif, ou None si l'alignement échoue (fail-closed).
    `rows` injectable (tests) ; avec runner injecté et rows omis -> à plat."""
    cible = str(_cfg("FUTURES_POSITION_MODE", "hedge_mode"))
    if runner is None and time.time() - _POS_MODE_MEMO["ts"] < 3600 and _POS_MODE_MEMO["mode"]:
        return _POS_MODE_MEMO["mode"]
    if rows is None:
        rows = positions_ouvertes() if runner is None else []
    if rows is None:
        return None                                  # positions illisibles -> pas d'ordre
    effectif = resolve_pos_mode(rows, cible)
    if rows:                                         # en position : pas de bascule possible
        if runner is None:
            _POS_MODE_MEMO.update(ts=0.0, mode=None)  # re-résoudre à chaque ordre
        return effectif
    out = _run(["futures", "futures_update_config", "--setting", "positionMode",
                "--value", effectif, "--symbol", SYMBOL,
                "--productType", PRODUCT_TYPE, "--marginCoin", MARGIN_COIN],
               runner=runner)
    compact = (out or "").replace(" ", "").lower()
    ok = bool(out) and "error" not in compact and '"ok":false' not in compact
    if not ok:
        return None
    if runner is None:
        _POS_MODE_MEMO.update(ts=time.time(), mode=effectif)
    return effectif


def _ensure_leverage(leverage, runner=None, marge_mode=None, symbol=None):
    """Fixe le levier (déjà borné au mur par build_futures_order) AVANT l'ordre.
    Marge isolée : les deux holdSide ; crossed : un appel sans holdSide.
    Fail-closed : échec -> False (pas d'ordre)."""
    lev = str(int(max(1, round(float(leverage)))))
    mode = str(marge_mode or _cfg("FUTURES_MARGIN_MODE", "isolated"))
    sides = ["long", "short"] if mode == "isolated" else [None]
    for hs in sides:
        cmd = ["futures", "futures_set_leverage", "--symbol", str(symbol or SYMBOL).upper(),
               "--productType", PRODUCT_TYPE, "--marginCoin", MARGIN_COIN,
               "--leverage", lev]
        if hs:
            cmd += ["--holdSide", hs]
        out = _run(cmd, runner=runner)
        compact = (out or "").replace(" ", "").lower()
        if not out or "error" in compact or '"ok":false' in compact:
            return False
    return True


def _parse_hub_json(out):
    """STRING de sortie bgc -> dict (best-effort ; isole le 1er objet JSON si du bruit
    l'entoure). None si illisible."""
    if not out:
        return None
    try:
        return json.loads(out)
    except Exception:
        try:
            i, j = out.index("{"), out.rindex("}")
            return json.loads(out[i:j + 1])
        except Exception:
            return None


def _read_hub(cmd, runner=None):
    """LECTURE PROPRE du hub. En test : via `runner` (string -> _parse_hub_json). En prod :
    via bitget_hub_bridge._read (force --read-only -> stdout PUR, pas de stderr mêlé comme
    _run) -> dict déjà parsé. None si indisponible/illisible. Utilisé par les lectures d'état
    d'ordre (poll maker) pour éviter le parsing fragile d'un flux stdout+stderr fusionné."""
    if runner is not None:
        return _parse_hub_json(runner(cmd))
    try:
        import bitget_hub_bridge as hub
        if not hub.available():
            return None
        return hub._read(cmd)
    except Exception:
        return None


def _order_id_from(out):
    """orderId d'une réponse futures_place_order (single, ou 1er du batch). None si absent."""
    d = _parse_hub_json(out)
    data = d.get("data") if isinstance(d, dict) else None
    if isinstance(data, dict):
        oid = data.get("orderId")
        if not oid:
            lst = data.get("orderInfo") or data.get("successList") or []
            oid = lst[0].get("orderId") if lst and isinstance(lst[0], dict) else None
        return str(oid) if oid else None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        oid = data[0].get("orderId")
        return str(oid) if oid else None
    return None


def _order_fill_state(symbol, order_id, runner=None):
    """(state, filled_qty) d'un ordre futures via /detail (--orderId). state normalisé
    ∈ filled/partial/live/canceled (ou brut) ; filled_qty en base = baseVolume de /detail
    (champ standard, confirmé en réel le 09/07). Lecture PROPRE via _read_hub (hub._read en
    prod = stdout pur ; runner en test). None si la ligne est illisible : l'appelant traite
    None en fail-closed (jamais de repli aveugle)."""
    from numeric_utils import safe_float
    d = _read_hub(["futures", "futures_get_orders", "--productType", PRODUCT_TYPE,
                   "--symbol", str(symbol).upper(), "--orderId", str(order_id)], runner=runner)
    data = d.get("data") if isinstance(d, dict) else None
    row = None
    if isinstance(data, dict):
        row = data if (data.get("orderId") or data.get("state") or data.get("status")) else None
        if row is None:
            lst = data.get("entrustedList") or data.get("orderList") or []
            row = lst[0] if lst and isinstance(lst[0], dict) else None
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        row = data[0]
    if not isinstance(row, dict):
        return None
    raw = str(row.get("state") or row.get("status") or "").lower()
    # baseVolume = quantité remplie (/detail, champ standard). safe_float sur baseVolume SEUL
    # d'abord (ne PAS court-circuiter un "0" légitime — chaîne truthy — vers un autre champ) ;
    # fallback seulement si baseVolume est absent.
    filled = safe_float(row.get("baseVolume"))
    if filled is None:
        filled = safe_float(row.get("fillSize") or row.get("filledQty")
                            or row.get("accBaseVolume")) or 0.0
    if "partial" in raw:
        state = "partial"
    elif "fill" in raw:
        state = "filled"
    elif "cancel" in raw:
        state = "canceled"
    elif raw in ("live", "new", "init", "open"):
        state = "live"
    else:
        state = raw or None
    return (state, filled)


def _pending_order_by_client_oid(symbol, client_oid, runner=None):
    """orderId d'un ordre futures OUVERT (orders-pending) portant ce clientOid ; "" si le
    carnet d'ordres ouverts est LISIBLE mais ne le contient pas ; None si la lecture échoue
    ou est douteuse (fail-closed). Sert à réconcilier un placement MAKER (post-only) dont la
    RÉPONSE est perdue : un post-only qui a atterri RESTE vivant (il ne prend jamais de
    liquidité) -> il figure ici. Distingue « vraiment non placé » (repli taker SÛR) de
    « lecture KO / ordre présent » (pas de repli : l'ordre a peut-être atterri -> anti-doublon)."""
    if not client_oid:
        return None
    d = _read_hub(["futures", "futures_get_orders", "--productType", PRODUCT_TYPE,
                   "--symbol", str(symbol).upper(), "--clientOid", str(client_oid)], runner=runner)
    if not isinstance(d, dict):
        return None                                   # lecture KO -> fail-closed
    data = d.get("data")
    if data is None:
        return None                                   # pas de bloc data -> douteux -> fail-closed
    if isinstance(data, dict):
        rows = data.get("entrustedList") or data.get("orderList") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    for row in (rows or []):
        if isinstance(row, dict) and str(row.get("clientOid")) == str(client_oid):
            oid = row.get("orderId")
            return str(oid) if oid else None          # atterri mais id illisible -> fail-closed
    if rows:
        # des ordres OUVERTS existent mais aucun ne matche notre clientOid : soit un autre
        # ordre, soit le CLI n'a pas renvoyé le champ clientOid -> on NE conclut PAS « absent »
        # (risque de stacker un taker sur un maker atterri) -> fail-closed.
        return None
    return ""                                         # carnet VIDE -> ordre vraiment non placé -> repli taker SÛR


def _confirm_futures_fill(order, phase, runner=None, since_ts=None, tries=None, delay=None,
                          sleeper=None):
    """NOYAU de réconciliation par les fills, commun à l'OUVERTURE et à la FERMETURE.
    Bitget peut remplir un ordre en renvoyant orderId:null (ordre identifié par clientOid,
    ABSENT des fills) : on ne peut donc PAS matcher par id -> on matche par SYMBOLE + côté
    d'exécution + tradeSide (`phase`) + cTime >= since_ts.

    CÔTÉ : pour une FERMETURE aussi, Bitget rend `side` = DIRECTION DE LA POSITION (un short
    s'ouvre en `sell open` ET se ferme en `sell close`, relevé réel du 2026-07-20) — le mapping
    est donc le même aux deux phases, seul `phase` change. Retourne {size_btc, price_avg,
    amount_usdt} agrégé, ou None. FAIL-SAFE : ne lève jamais (l'ordre est DÉJÀ passé)."""
    from numeric_utils import safe_float
    sym = str(order.get("symbol") or SYMBOL).upper()
    exec_side = "buy" if str(order.get("side")) == "long" else "sell"
    veut_close = str(phase) == "close"
    since = 0.0 if since_ts is None else float(since_ts) - 5.0     # marge d'horloge (serveur vs local)
    tries = int(_cfg("FUTURES_FILL_CONFIRM_TRIES", 3)) if tries is None else int(tries)
    delay = float(_cfg("FUTURES_FILL_CONFIRM_DELAY_S", 1.0)) if delay is None else float(delay)
    sleeper = sleeper or time.sleep
    for i in range(max(1, tries)):
        d = _read_hub(["futures", "futures_get_fills", "--productType", PRODUCT_TYPE,
                       "--symbol", sym], runner=runner)
        data = d.get("data") if isinstance(d, dict) else None
        rows = data.get("fillList") if isinstance(data, dict) else (data if isinstance(data, list) else None)
        size = notion = 0.0
        for r in (rows or []):
            if not isinstance(r, dict) or str(r.get("side")).lower() != exec_side:
                continue
            est_close = "close" in str(r.get("tradeSide") or "").lower()
            if est_close != veut_close:            # on veut la phase DEMANDÉE, jamais l'autre
                continue
            ct = safe_float(r.get("cTime"))
            if ct is None or ct / 1000.0 < since:                  # fill antérieur au placement -> pas le nôtre
                continue
            b, p = safe_float(r.get("baseVolume")), safe_float(r.get("price"))
            if b and b > 0 and p and p > 0:
                size += b
                notion += b * p
        if size > 0:
            # price_avg à 8 décimales : un arrondi à 2 écrasait le prix des alts sous le dollar
            # (BANK 0.2798 -> 0.28) dans un registre d'ARGENT. size_btc/amount_usdt inchangés.
            return {"size_btc": round(size, 8), "price_avg": round(notion / size, 8),
                    "amount_usdt": round(notion, 6)}
        if i < tries - 1:
            sleeper(delay)
    return None


def _confirm_futures_open_fill(order, runner=None, since_ts=None, tries=None, delay=None, sleeper=None):
    """Confirme qu'un ordre d'OUVERTURE a RÉELLEMENT rempli (tradeSide 'open'). Sous le verrou
    d'ouverture, un fill d'ouverture frais est le nôtre."""
    return _confirm_futures_fill(order, "open", runner=runner, since_ts=since_ts,
                                 tries=tries, delay=delay, sleeper=sleeper)


def _confirm_futures_close_fill(order, runner=None, since_ts=None, tries=None, delay=None, sleeper=None):
    """Confirme qu'une RÉDUCTION a RÉELLEMENT rempli (tradeSide 'close') — ERR-020.

    Le confirmateur n'existait QUE pour les ouvertures : une fermeture recevant la réponse
    ambiguë orderId:null était journalisée FUTURES_REAL_FAILED « position à vérifier » alors
    qu'elle avait rempli (2 cas réels le 2026-07-20 : HYPEUSDT 05:56, BANKUSDT 15:07, toutes
    deux intégralement remplies, positions ensuite à plat).

    SENS DE L'ERREUR : on ne déclare soldé qu'après avoir VU le fill de fermeture — un faux
    positif ferait croire une position fermée alors qu'elle est ouverte. Le garde-fou de dernier
    ressort reste le livre : `flatten_all`/`futures_auto` relisent `positions_ouvertes()` à
    chaque tick, donc l'autorité finale est la position réelle, jamais ce drapeau."""
    return _confirm_futures_fill(order, "close", runner=runner, since_ts=since_ts,
                                 tries=tries, delay=delay, sleeper=sleeper)


def _submit_taker(order, runner, spec, price, marge_mode, pos_mode, style="limit_ioc", now=None):
    """Placement TAKER (limit_ioc plafonné à l'ouverture / market pour une réduction) —
    chemin éprouvé §45. Construit le bo, envoie via l'Agent Hub, lit le succès. Retourne
    un dict. Le style est FORCÉ (jamais post_only ici) : ce chemin n'exécute que du taker.

    RÉPONSE AMBIGUË : Bitget peut REMPLIR un limit_ioc en renvoyant data:{orderId:null}
    (ordre identifié par clientOid). L'ancien test strict `_order_id_from is not None` classait
    ça FAILED à tort (faux négatif réel le 07-09). On distingue donc : orderId extrait -> succès ;
    code d'erreur EXPLICITE -> rejet net ; sinon (orderId:null sans erreur) -> RÉCONCILIER via les
    fills avant de conclure (executed si fill confirmé, ambiguous sinon)."""
    bo = to_bitget_order(order, spec, price, marge_mode=marge_mode, pos_mode=pos_mode, style=style)
    if bo is None:
        return {"ok": False, "executed": False,
                "reasons": [f"taille infaisable (notional {order.get('notional_usdt')} "
                            "sous les minima du contrat)"]}
    t0 = time.time() if now is None else now
    out = _run(["futures", "futures_place_order", "--orders", json.dumps([bo])], runner=runner)
    order_id = _order_id_from(out)
    fill, ambiguous, filled_taker, reasons = None, False, None, None
    if order_id is not None:
        if str(bo.get("force")) == "ioc":
            # DURCI 21/07 : un IOC ACCEPTÉ n'est PAS un IOC REMPLI — il peut s'annuler sec à
            # ZÉRO rempli (cas réel BANKUSDT 02:05 : orderId rendu, rien rempli, faux
            # FUTURES_REAL au registre + TP1 posé sur une position inexistante). On relit
            # l'état TERMINAL de l'ordre : rempli > 0 -> executed (taille exposée pour le
            # TP1) ; canceled -> contre-vérifié par les fills puis ZÉRO CONFIRMÉ (échec NET,
            # retry court du throttle) ; état illisible/non terminal -> réconciliation par
            # les fills, et sans fill on reste AMBIGU (fenêtre pleine, prudence).
            st = _order_fill_state(str(order.get("symbol") or SYMBOL).upper(), order_id,
                                   runner=runner)
            q = st[1] if st else None
            confirmer = (_confirm_futures_close_fill if order.get("reduce")
                         else _confirm_futures_open_fill)
            if q is not None and q > 0:
                success, filled_taker = True, q
            elif st is not None and st[0] == "canceled":
                # zéro APPARENT : une ligne de fill reste l'autorité — un /detail sans champ
                # volume ne suffit pas à déclarer zéro (2 essais : ~1 s pour fermer la
                # fenêtre d'un fill en retard, revue 21/07).
                fill = confirmer(order, runner=runner, since_ts=t0, tries=2)
                if fill and (fill.get("size_btc") or 0) > 0:
                    success = True
                else:
                    success, filled_taker = False, 0.0
                    reasons = ["IOC accepté mais rempli à ZÉRO (annulé sec — carnet absent "
                               "au prix plafonné) ; rien d'ouvert"]
            else:
                fill = confirmer(order, runner=runner, since_ts=t0)
                if fill and (fill.get("size_btc") or 0) > 0:
                    success = True
                else:
                    success, ambiguous = False, True
        else:
            success = True        # market (réductions) : rempli ou rejeté, jamais annulé à zéro
    else:
        parsed = _parse_hub_json(out)
        raw_code = parsed.get("code") if isinstance(parsed, dict) else None
        code = str(raw_code) if raw_code is not None else ""
        rejet_definitif = bool(code) and code not in ("00000", "0")     # erreur explicite -> rien placé
        if not rejet_definitif:
            # ERR-020 : les RÉDUCTIONS étaient exclues de la réconciliation -> FAILED à tort.
            # Même geste des deux côtés, sur la phase correspondante (open vs close).
            fill = (_confirm_futures_close_fill(order, runner=runner, since_ts=t0)
                    if order.get("reduce") else
                    _confirm_futures_open_fill(order, runner=runner, since_ts=t0))
        if fill and (fill.get("size_btc") or 0) > 0:
            success = True                                              # fill RÉEL constaté -> ordre exécuté
        else:
            success = False
            ambiguous = not rejet_definitif                            # accepté mais fill non confirmé
    res = {"ok": True, "executed": success, "bitget_order": bo, "exec_style": style,
           "response": (out or "")[:2000], "clientOid": order.get("clientOid")}
    if fill:
        res["fill"] = fill
    if filled_taker is not None:
        res["filled_taker"] = filled_taker
    if ambiguous:
        res["ambiguous"] = True
        reasons = ["réponse ambiguë (orderId:null ou état IOC illisible), fill non confirmé "
                   "— position à vérifier"]
    if reasons:
        res["reasons"] = reasons
    return res


def _place_maker(order, runner, spec, price, marge_mode, pos_mode, top_of_book):
    """MAKER post-only + repli taker GARDÉ (§exec-frais). TAILLE au prix de référence `price`
    (mark -> respecte le notional approuvé par guards) ; PRIX D'ORDRE au meilleur bid (achat)
    / ask (vente). Attend un remplissage court (FUTURES_MAKER_WAIT_S) ; sinon ANNULE et replie
    le RESTANT en taker sous un clientOid NEUF.

    GARDES (argent réel) :
      • ANTI-DOUBLE-POSITION : on ne replie QUE si l'annulation est CONFIRMÉE — état TERMINAL
        (canceled/filled) relu après annulation. Si l'ordre reste live/partial (annulation non
        effective), illisible, ou non confirmé -> AUCUN repli : l'ordre maker reste vivant et
        remplira en maker, jamais de taker empilé sur un ordre encore actif.
      • clientOid du repli DISTINCT (Bitget déduplique -> sinon le repli est rejeté).
      • une position réellement ouverte (fill maker > 0) est signalée executed=True (jamais
        journalée en échec).
    Ouvertures seulement (routage dans `_place_real`)."""
    from numeric_utils import safe_float
    symbole = str(order.get("symbol") or SYMBOL).upper()
    long_ = str(order.get("side")) == "long"
    bid, ask = safe_float(top_of_book.get("bid")), safe_float(top_of_book.get("ask"))
    prix_maker = bid if long_ else ask
    if not prix_maker or prix_maker <= 0 or not safe_float(price):   # carnet/mark illisible -> taker
        return _submit_taker(order, runner, spec, price, marge_mode, pos_mode)
    # TAILLE au mark (price), PRIX D'ORDRE au bid/ask (maker_price) : respecte le notional
    # approuvé par guards() et poste en post-only (§exec-frais).
    bo = to_bitget_order(order, spec, price, marge_mode=marge_mode, pos_mode=pos_mode,
                         style="maker", maker_price=prix_maker)
    if bo is None:
        return {"ok": False, "executed": False, "reasons": ["taille infaisable (maker)"]}
    demande = safe_float(bo.get("size")) or 0.0
    try:                                                 # réglages lus AVANT le placement
        wait_s = max(0.0, float(_cfg("FUTURES_MAKER_WAIT_S", 12)))
        poll_s = max(0.2, float(_cfg("FUTURES_MAKER_POLL_S", 2)))
    except (TypeError, ValueError):
        wait_s, poll_s = 12.0, 2.0
    out = _run(["futures", "futures_place_order", "--orders", json.dumps([bo])], runner=runner)
    order_id = _order_id_from(out)                       # succès = un orderId RÉELLEMENT extrait
    if not order_id:
        # Pas d'orderId : soit post-only REJETÉ (code d'erreur EXPLICITE -> RIEN placé, repli
        # taker SÛR), soit réponse PERDUE/vide (l'ordre a peut-être ATTERRI). Un post-only qui
        # atterrit reste VIVANT -> sur une réponse AMBIGUË (sans code d'erreur) on le cherche
        # par clientOid dans les ordres OUVERTS AVANT tout repli taker, sinon un taker s'empile
        # sur un maker déjà posé = DOUBLE POSITION.
        parsed = _parse_hub_json(out)
        raw_code = parsed.get("code") if isinstance(parsed, dict) else None
        code = str(raw_code) if raw_code is not None else ""            # code ABSENT -> "" (pas "None")
        rejet_definitif = bool(code) and code not in ("00000", "0")     # erreur explicite -> rien placé
        rec = "" if rejet_definitif else _pending_order_by_client_oid(
            symbole, order.get("clientOid"), runner=runner)
        if rec:                                          # l'ordre maker est VIVANT -> on le gère (pas de taker)
            order_id = rec
        elif rec == "":                                  # rejet explicite OU carnet VIDE -> rien placé -> taker sûr
            taker = _submit_taker(order, runner, spec, price, marge_mode, pos_mode)
            taker["exec_style"] = "taker_apres_rejet_maker"
            return taker
        else:                                            # rec is None : réponse ambiguë + lecture KO/douteuse
            return {"ok": True, "executed": False, "bitget_order": bo,   # -> fail-closed, PAS de taker
                    "exec_style": "maker_incertain", "filled": 0.0,
                    "ambiguous": True,                   # a peut-être atterri -> fenêtre pleine du throttle
                    "response": (out or "")[:2000], "clientOid": order.get("clientOid"),
                    "reasons": ["réponse de placement maker illisible ET réconciliation par "
                                "clientOid indisponible — repli taker SUPPRIMÉ (anti-doublon)"]}

    def _res(exec_style, executed, filled_q, reasons=None, ambiguous=False):
        r = {"ok": True, "executed": bool(executed), "bitget_order": bo,
             "exec_style": exec_style, "filled": filled_q,
             "response": (out or "")[:2000], "clientOid": order.get("clientOid")}
        if reasons:
            r["reasons"] = reasons
        if ambiguous and not executed:
            # ordre peut-être encore VIVANT/atterri : le throttle doit garder la fenêtre
            # PLEINE (jamais de retry court qui empilerait un 2e ordre) et gated_open garde
            # la réservation du mur cumulé.
            r["ambiguous"] = True
        return r

    # poll du remplissage jusqu'au délai (au moins une lecture)
    deadline = time.time() + wait_s
    state, filled = None, 0.0
    while True:
        st = _order_fill_state(symbole, order_id, runner=runner)
        if st is not None:
            state, filled = st
            if state == "filled":
                break
        if time.time() >= deadline:
            break
        time.sleep(poll_s)
    if state == "filled":
        return _res("maker", True, filled)

    # non/partiellement rempli -> ANNULER et CONFIRMER un état TERMINAL (retry court).
    term_state, term_filled = None, None
    for _ in range(3):
        _run(["futures", "futures_cancel_orders", "--productType", PRODUCT_TYPE,
              "--symbol", symbole, "--orderId", str(order_id)], runner=runner)
        st = _order_fill_state(symbole, order_id, runner=runner)
        if st is not None and st[0] in ("canceled", "filled"):
            term_state, term_filled = st
            break
        time.sleep(poll_s)
    if term_state is None or term_filled is None:
        # annulation NON confirmée : l'ordre maker peut être ENCORE VIVANT -> AUCUN repli taker
        # (anti-doublon). Il remplira en maker ; position signalée ouverte si déjà remplie.
        return _res("maker_non_confirme", filled > 0, filled, ambiguous=True,
                    reasons=["annulation non confirmée (ordre possiblement encore actif) : "
                             "repli taker SUPPRIMÉ (anti-doublon)"])
    if term_state == "filled":
        return _res("maker", True, term_filled)
    # CANCELED confirmé -> repli TAKER du RESTANT sous clientOid NEUF
    min_size = safe_float((spec or {}).get("min_size")) or 0.0
    restant = max(0.0, demande - term_filled)
    if restant < max(min_size, 1e-12):                   # tout rempli en maker (ou reste négligeable)
        return _res("maker", term_filled > 0, term_filled)
    reste = dict(order)
    reste["notional_usdt"] = restant * float(price)
    reste["reduce"] = False
    reste["clientOid"] = (str(order.get("clientOid") or "o") + "t")[-64:]   # clientOid DISTINCT
    taker = _submit_taker(reste, runner, spec, price, marge_mode, pos_mode)
    f = taker.get("fill")
    if isinstance(f, dict):
        q = safe_float(f.get("size_btc"))
        if q is not None and q > restant:
            # anti double-compte (revue 21/07) : la réconciliation par les fills (marge
            # d'horloge −5 s de _confirm_futures_fill) peut englober le fill MAKER tout
            # juste rempli — la part attribuée au restant TAKER est plafonnée au restant
            # demandé (le registre d'ARGENT ne doit jamais sur-compter).
            taker["fill"] = dict(f, size_btc=round(restant, 8))
    taker["exec_style"] = "maker_puis_taker"
    taker["filled_maker"] = term_filled
    taker["executed"] = bool(taker.get("executed")) or term_filled > 0     # position réelle si maker rempli
    return taker


def _place_real(order, runner=None, spec=None, price=None, marge_mode=None, pos_mode=None,
                top_of_book=None):
    """Chemin RÉEL (étape 2, §45). Résout le mode de position EFFECTIF (position
    ouverte = autorité ; à plat = bascule vers la cible hedge_mode, décision 03/07),
    fixe le levier borné, puis ROUTE l'exécution :
      • MAKER post-only + repli taker (§exec-frais) SI FUTURES_EXEC_STYLE=maker, sur une
        OUVERTURE, et si le carnet (top_of_book) est fourni ;
      • sinon TAKER limit_ioc (défaut ; et TOUTE réduction reste market).
    FAIL-CLOSED à chaque étape illisible. Retourne un dict."""
    symbole = str(order.get("symbol") or SYMBOL).upper()
    spec = _contract_spec(symbole) if spec is None else spec
    if not spec:
        return {"ok": False, "executed": False,
                "reasons": ["spécifications contrat illisibles (fail-closed)"]}
    price = (order.get("entry") or _mark_price(symbole)) if price is None else price
    if not price:
        return {"ok": False, "executed": False,
                "reasons": ["prix du perp illisible (fail-closed)"]}
    marge_mode = _marge_mode() if marge_mode is None else marge_mode   # adaptatif : union -> crossed
    if pos_mode is None:
        pos_mode = _ensure_position_mode(runner=runner)                # adaptatif + bascule à plat
    if pos_mode is None:
        return {"ok": False, "executed": False,
                "reasons": ["mode de position irrésoluble/refusé (fail-closed)"]}
    # faisabilité de taille VÉRIFIÉE AVANT de régler le levier : un futures_set_leverage mute
    # le prix de liquidation d'une position VIVANTE (compte union/crossed) — ne pas le faire
    # pour un ordre ensuite abandonné (taille sous les minima). Réductions exclues (leur taille
    # vient de size_btc, pas du notional).
    if not order.get("reduce") and size_for(order.get("notional_usdt"), price, spec) is None:
        return {"ok": False, "executed": False,
                "reasons": [f"taille infaisable (notional {order.get('notional_usdt')} "
                            "sous les minima du contrat)"]}
    if not _ensure_leverage(order.get("leverage") or 1, runner=runner, marge_mode=marge_mode,
                            symbol=symbole):
        return {"ok": False, "executed": False,
                "reasons": ["réglage du levier refusé par l'exchange (fail-closed)"]}
    style = _exec_style()                              # .env > config > 'limit_ioc' (armable)
    allowed = _maker_symbols()                         # {} = tous ; sinon périmètre prudent (ex. BTCUSDT)
    if (style == "maker" and not bool(order.get("reduce")) and top_of_book
            and (not allowed or symbole in allowed)):
        return _place_maker(order, runner, spec, price, marge_mode, pos_mode, top_of_book)
    return _submit_taker(order, runner, spec, price, marge_mode, pos_mode)


def filled_size(res):
    """PUR. Taille BASE réellement REMPLIE d'un résultat d'exécution, tous chemins confondus
    (maker : `filled` ; repli : `filled_maker` + `filled_taker` ; réconciliation par les
    fills : `fill.size_btc`). None si le résultat ne porte AUCUNE trace de fill (échec avant
    placement, réponse illisible) — inconnu ≠ zéro : l'appelant reste prudent (pas de TP1,
    fenêtre pleine du throttle)."""
    from numeric_utils import safe_float
    if not isinstance(res, dict):
        return None
    total, known = 0.0, False
    f = res.get("fill")
    if isinstance(f, dict):
        q = safe_float(f.get("size_btc"))
        if q is not None:
            total, known = total + max(0.0, q), True
    for k in ("filled", "filled_maker", "filled_taker"):
        q = safe_float(res.get(k))
        if q is not None:
            total, known = total + max(0.0, q), True
    return total if known else None


def execute(agent, side, notional_usdt, leverage, entry=None, stop_loss=None,
            take_profit=None, *, reduce=False, confirm=False, runner=None, now=None,
            equity_curve=None, gross_open_usdt=0.0, seen_oids=None, hour_utc=None,
            macro_events=None, journal=True, daily_loss=None, spec=None, price=None,
            marge_mode=None, size_btc=None, pos_mode=None, symbol=None,
            top_of_book=None, risk_pct=None, **gate_overrides):
    """Ordre futures RÉEL SI confirm=True ET les 8 gardes passent ET le stop de perte
    journalier n'est pas franchi. Sinon DRY (construit, journalise, n'exécute rien).
    Retourne un dict de résultat. gate_overrides (live/autonomous/futures_live/kill/
    edge_override) + daily_loss/spec/price injectables (tests hermétiques)."""
    now = time.time() if now is None else now
    oid = f"fut{str(agent)[:3]}{int(now * 1000)}"
    # §98 : cap de LIQUIDITÉ sur les OUVERTURES — ne pas balayer plus que le top-of-book affiché
    # (thin alts : LAB/HYPE/BGB). Réservé à reduce=False (une fermeture doit rester entière).
    # AVANT guards() -> les caps durs voient le notionnel déjà réduit. Fail-open (pas de carnet
    # -> inchangé). Le carnet est FOURNI par l'appelant (futures_auto lit fe._top_of_book à côté
    # de _mark_price) : execute() ne déclenche aucune requête réseau lui-même -> tests hermétiques.
    notional_capped_from = None
    if not reduce and top_of_book is not None:
        capped, binds = liquidity_capped_notional(notional_usdt, side, top_of_book)
        if binds:
            notional_capped_from, notional_usdt = float(notional_usdt), capped
    # §risk-pct : cap de RISQUE PAR TRADE (Kovner) — SOUS les murs 50/250. Réduit le notionnel
    # pour que la perte au stop-loss ne dépasse pas FUTURES_RISK_PCT_PER_TRADE % de l'equity du
    # livre. OUVERTURES seulement, AVANT guards() (les murs voient le notionnel déjà réduit).
    # Fail-open : entry/SL/equity manquants -> inchangé (le stop journalier bloque déjà l'aveugle).
    # `risk_pct` injectable (§111) : l'appelant (futures_auto) passe min(garde fixe, Kelly) —
    # RÉDUCTEUR-seulement. None -> lecture config inchangée. Un Kelly à 0 ne DOIT jamais
    # arriver ici (0 = « garde désactivée » pour risk_capped_notional) : l'appelant s'abstient.
    risk_capped_from = None
    if not reduce:
        capped_r, binds_r = risk_capped_notional(notional_usdt, entry, stop_loss,
                                                  _equity_now(equity_curve), risk_pct=risk_pct)
        if binds_r:
            risk_capped_from, notional_usdt = float(notional_usdt), capped_r
    ok, reasons = guards(agent, notional_usdt, leverage, equity_curve=equity_curve,
                         gross_open_usdt=gross_open_usdt, client_oid=oid, seen_oids=seen_oids,
                         hour_utc=hour_utc, macro_events=macro_events, now=now,
                         reduce=reduce, **gate_overrides)
    order = build_futures_order(agent, side, notional_usdt, leverage, entry, stop_loss,
                                take_profit, oid, reduce=reduce, size_btc=size_btc,
                                symbol=symbol)
    if notional_capped_from is not None:          # trace : le cap de liquidité a mordu
        order["liquidity_capped_from"] = round(notional_capped_from, 2)
    if risk_capped_from is not None:              # trace : le cap de risque par trade a mordu
        order["risk_capped_from"] = round(risk_capped_from, 2)
    if risk_pct is not None:                      # trace : % de risque effectif injecté (§111 Kelly)
        try:
            order["risk_pct_applied"] = round(float(risk_pct), 4)
        except (TypeError, ValueError):
            pass
    mode = order.get("execution_mode")
    preview = (f"futures {order['side']}{' reduce' if order['reduce'] else ''} "
               f"{order['notional_usdt']}USDT x{order['leverage']} "
               f"agent={agent} oid={oid} [{mode}]")

    if not ok:
        if journal:
            _journal({"action": "FUTURES_REFUSED", "ts": now, "order": order,
                      "reasons": reasons, "real_order_sent": False})
        return {"ok": False, "executed": False, "reasons": reasons,
                "preview": preview, "clientOid": oid}

    if not confirm:
        if journal:
            _journal({"action": "FUTURES_DRY_RUN", "ts": now, "order": order,
                      "real_order_sent": False})
        return {"ok": True, "executed": False, "dry": True, "preview": preview,
                "clientOid": oid,
                "note": "DRY — ajouter confirm=True pour le RÉEL (gardes + stop journalier)."}

    # confirm=True ET gardes passées : PRÉ-VOL stop de perte journalier (fail-closed),
    # puis chemin RÉEL (étape 2, §45). L'ouverture est bloquée après breach ; une
    # RÉDUCTION reste permise (fermer une position n'aggrave jamais le risque).
    if daily_loss is None and not reduce:
        daily_loss = daily_loss_breach(now=now)
    if daily_loss and not reduce:
        if journal:
            _journal({"action": "FUTURES_REFUSED", "ts": now, "order": order,
                      "reasons": ["stop de perte journalier franchi"], "real_order_sent": False})
        return {"ok": False, "executed": False, "preview": preview, "clientOid": oid,
                "reasons": ["stop de perte journalier franchi (kill-switch armé)"]}
    # Marqueur DURABLE d'attente (crash-mid-placement) : journalisé AVANT l'ordre réel, il
    # survit à un SIGKILL entre le placement et l'issue (journalisée APRÈS) -> le throttle
    # (dernier_ordre_auto_ts) le compte, donc reste armé même si l'issue REAL/FAILED est perdue.
    # OUVERTURES seulement (le throttle ne gate que les ouvertures). Tous les AUTRES
    # consommateurs du ledger l'ignorent (ils filtrent action == 'FUTURES_REAL').
    if journal and not reduce:
        _journal({"action": "FUTURES_REAL_SUBMIT", "ts": now, "order": order,
                  "real_order_sent": None})     # in-flight : issue inconnue tant que non journalisée
    res = _place_real(order, runner=runner, spec=spec, price=price, marge_mode=marge_mode,
                      pos_mode=pos_mode, top_of_book=top_of_book)
    if journal:
        _journal({"action": "FUTURES_REAL" if res.get("executed") else "FUTURES_REAL_FAILED",
                  "ts": now, "order": order, "bitget_order": res.get("bitget_order"),
                  "real_order_sent": bool(res.get("executed")),
                  "exec_style": res.get("exec_style"),      # maker | maker_puis_taker | taker_apres_rejet_maker
                  "filled_maker": res.get("filled_maker"),  # base remplie en maker avant repli (si repli)
                  "filled": filled_size(res),               # taille TOTALE remplie ; 0.0 = zéro CONFIRMÉ ; None = inconnue
                  "ambiguous": res.get("ambiguous"),        # True = a peut-être ouvert -> fenêtre pleine du throttle
                  "reasons": res.get("reasons"), "response": res.get("response")})
    return {**res, "preview": preview, "clientOid": oid}


# ---------- ENFORCEUR de stop (Couche 2, indépendant de brain/scan) ----------

def flatten_all(runner=None, now=None, motif="stop journalier"):
    """SOLDE toutes les positions futures ouvertes en RÉDUCTION market (reduceOnly).
    Fail-safe : fermer n'aggrave JAMAIS le risque — un flatten de sécurité ne dépend
    d'AUCUN verrou d'OUVERTURE (double verrou, porte d'edge, kill-switch) : on passe
    les overrides pour qu'une réduction reste TOUJOURS exécutable, même mandat coupé.

    Idempotent (à plat -> aucun ordre). Fail-closed par position : une ligne illisible
    n'empêche pas de solder les autres. Retourne un récapitulatif (aucun secret)."""
    now = time.time() if now is None else now
    from numeric_utils import safe_float
    rows = positions_ouvertes(runner=runner)
    if rows is None:
        return {"lisible": False, "tentees": 0, "soldees": 0, "positions": [],
                "erreurs": ["positions illisibles (fail-closed) — nouvelle tentative au prochain tick"]}
    recap = {"lisible": True, "motif": str(motif), "tentees": 0, "soldees": 0,
             "positions": [], "erreurs": []}
    for r in rows:
        if not isinstance(r, dict):
            continue
        cote = str(r.get("holdSide", "")).lower()
        taille = safe_float(r.get("total") or r.get("size")) or 0.0
        symbole = str(r.get("symbol", "")).upper()
        if cote not in ("long", "short") or taille <= 1e-12 or not symbole:
            continue
        prix = safe_float(r.get("markPrice")) or _mark_price(symbole)
        notional = round(taille * prix, 2) if prix and prix > 0 else 1.0
        if notional <= 0:
            notional = 1.0
        recap["tentees"] += 1
        try:
            res = execute("guardian", cote, notional, 1.0, reduce=True, confirm=True,
                          now=now, size_btc=taille, symbol=symbole, runner=runner,
                          live=True, autonomous=True, futures_live=True, edge_override=1,
                          kill=False)
            ok = bool(res.get("executed"))
            recap["positions"].append({"symbol": symbole, "side": cote,
                                       "size": round(taille, 6), "executed": ok})
            if ok:
                recap["soldees"] += 1
            else:
                recap["erreurs"].append(f"{cote} {symbole}: {res.get('reasons') or 'échec exchange'}")
        except Exception as exc:
            recap["erreurs"].append(f"{cote} {symbole}: {type(exc).__name__}")
    return recap


def enforce_daily_loss(runner=None, now=None):
    """ENFORCEUR complet du stop journalier −5 % (Couche 2). Appelé par un organe
    INDÉPENDANT de brain/scan (stop_guardian) à cadence serrée :
      1) daily_loss_breach() : arme le kill-switch + alerte Telegram (dédup 1/jour),
         persiste l'état — inchangé ;
      2) si le breach est CONFIRMÉ (equity LISIBLE sous le seuil, signalé par
         daily_loss_alert_day == jour dans le ledger), SOLDE toutes les positions.
         Un breach 'aveugle' (API illisible) NE solde RIEN (jamais de fermeture sur
         un simple blip de lecture ; fail-closed = on n'OUVRE pas, pas on ne ferme).
    Retourne {breach, confirme, flatten}."""
    now = time.time() if now is None else now
    breach = daily_loss_breach(now=now)               # effets protecteurs (kill-switch + alerte)
    jour = int(now // 86400)
    try:
        led = json.loads(_ledger_path().read_text(encoding="utf-8"))
    except Exception:
        led = {}
    confirme = int(led.get("daily_loss_alert_day", -1) or -1) == jour
    recap = {"breach": bool(breach), "confirme": bool(confirme), "flatten": None}
    if confirme:
        recap["flatten"] = flatten_all(runner=runner, now=now, motif="stop journalier -5%")
    return recap


def opens_sans_stop(events=None, agents_directionnels=("auto_dir", "directional", "dir")):
    """PUR (si events injecté). Ouvertures RÉELLES directionnelles passées SANS
    stop-loss préréglé côté exchange (invariant Couche 1). Le carry est exclu :
    short volontairement couvert par le spot (sans SL, protégé par le stop du LIVRE).
    Retourne [{ts, agent, symbol, oid}] — [] = tout ordre directionnel portait son SL."""
    if events is None:
        try:
            events = json.loads(_ledger_path().read_text(encoding="utf-8")).get("events", [])
        except Exception:
            events = []
    nus = []
    for e in events or []:
        if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
            continue
        order = e.get("order") or {}
        if order.get("reduce"):
            continue                                  # une réduction n'a pas à porter de SL
        agent = str(order.get("agent", ""))
        if not any(agent.startswith(a) for a in agents_directionnels):
            continue                                  # carry/autres : hors invariant
        if order.get("stop_loss") is None:
            nus.append({"ts": e.get("ts"), "agent": agent,
                        "symbol": order.get("symbol"), "oid": order.get("clientOid")})
    return nus


def positions_sans_sl_exchange(positions, plan_sls, events=None,
                               agents_directionnels=("auto_dir", "directional", "dir")):
    """PUR — DURCISSEMENT de la réconciliation SL EXCHANGE (§durcis-sl). Complète
    `opens_sans_stop` (qui prouve l'INTENTION au ledger) en réconciliant contre le SL
    RÉELLEMENT préréglé côté exchange (ordre plan/TPSL). Retourne les positions futures
    DIRECTIONNELLES OUVERTES sans SL plan exchange — celles qu'une auto-pose devrait couvrir.

      • positions : [{symbol, side(LONG/SHORT), notional_usdt?}] (real_positions.futures) ;
      • plan_sls  : itérable de (symbol, side) portant un SL plan RÉEL (cf. plan_sl_orders) ;
      • events    : ledger de l'exécuteur — sert à CLASSER l'agent ouvreur par (symbol, side).

    Le carry est exclu (short couvert par le spot, protégé par le stop du LIVRE, pas de SL
    propre — même exclusion qu'`opens_sans_stop`). Un agent NON classable (aucune ouverture
    au ledger) n'est PAS signalé : conservateur, pour ne JAMAIS déclencher un heal sur une
    position mal attribuée. FAIL-CLOSED : positions OU plan_sls illisibles (None) -> None
    (l'appelant s'abstient : ni faux vert, ni faux heal — on ne pose pas un SL en aveugle)."""
    if positions is None or plan_sls is None:
        return None
    have = set()
    for k in plan_sls:                                # accepte set/dict de (symbol, side)
        try:
            s, d = k
            have.add((str(s).upper(), str(d).upper()))
        except (TypeError, ValueError):
            continue
    opener = {}                                       # (symbol, side) -> (ts, agent) de la dernière OUVERTURE réelle
    for e in events or []:
        if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
            continue
        o = e.get("order") or {}
        if o.get("reduce"):
            continue
        sym = str(o.get("symbol") or "").upper()
        side = str(o.get("side") or "").upper()
        if not sym or not side:
            continue
        try:
            ts = float(e.get("ts"))
        except (TypeError, ValueError):
            ts = -1.0
        if ts >= opener.get((sym, side), (-1.0, ""))[0]:
            opener[(sym, side)] = (ts, str(o.get("agent") or ""))
    nus = []
    for p in positions or []:
        if not isinstance(p, dict):
            continue
        sym = str(p.get("symbol") or "").upper()
        side = str(p.get("side") or "").upper()
        if not sym or side not in ("LONG", "SHORT"):
            continue
        agent = opener.get((sym, side), (None, ""))[1]
        if not agent or not any(agent.startswith(a) for a in agents_directionnels):
            continue                                  # carry / inconnu -> hors invariant (pas de heal)
        if (sym, side) not in have:
            nus.append({"symbol": sym, "side": side, "agent": agent,
                        "notional": p.get("notional_usdt")})
    return nus


# ─── §durcis-sl Étape 2 : lecteur SL exchange + réconciliation live + auto-pose (DRY) ───

_UNSET = object()


def parse_plan_sl_orders(entrusted_list):
    """PUR. `entrustedList` d'orders-plan-pending (peut être None) -> set {(SYMBOL, SIDE)} des
    positions couvertes par un SL plan RÉEL côté exchange. SIDE = `posSide` (LONG/SHORT).
    Un item compte comme SL si son `planType` porte une PERTE (…loss…) OU s'il porte un
    `stopLossTriggerPrice` > 0. Schéma ancré sur le SDK officiel (`FuturesPendingPlanOrderV2`,
    18/07) + enveloppe live vérifiée `{entrustedList, endId}`. `posSide` ambigu (net/vide) ->
    ignoré (conservateur : ne JAMAIS conclure « couvert » à tort)."""
    out = set()
    for it in (entrusted_list or []):
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "").upper()
        side = str(it.get("posSide") or "").upper()
        if not sym or side not in ("LONG", "SHORT"):
            continue
        pt = str(it.get("planType") or "").lower()
        try:
            sl_px = float(it.get("stopLossTriggerPrice") or 0)
        except (TypeError, ValueError):
            sl_px = 0.0
        if "loss" in pt or sl_px > 0:
            out.add((sym, side))
    return out


def plan_sl_orders(product_type=None, plan_type="profit_loss", timeout=10):
    """I/O LECTURE SEULE best-effort. GET signé `orders-plan-pending` -> set {(SYMBOL, SIDE)}
    couverts par un SL plan exchange. None si illisible -> FAIL-CLOSED (l'Étape 1 s'abstient :
    ni faux vert, ni faux heal en aveugle). Le namespace d'ordre reste dans l'executor autorisé
    (real_positions l'évite à dessein) ; on n'emprunte QUE son signeur read-only."""
    pt = product_type or PRODUCT_TYPE
    try:
        import real_positions as rp
        d = rp._signed_get("/api/v2/mix/order/orders-plan-pending",
                           {"productType": pt, "planType": plan_type}, timeout=timeout)
        el = d.get("entrustedList") if isinstance(d, dict) else d
        return parse_plan_sl_orders(el)
    except Exception:
        return None


def positions_sans_sl_exchange_live(runner=None):
    """I/O best-effort. Câble les 3 sources RÉELLES (positions futures + SL plan exchange + ledger)
    et retourne les positions directionnelles OUVERTES sans SL plan exchange (cf.
    `positions_sans_sl_exchange`). None si une source est illisible (fail-closed)."""
    try:
        import real_positions as rp
        positions = rp.futures()
    except Exception:
        return None
    plan_sls = plan_sl_orders()
    if plan_sls is None:
        return None
    try:
        events = json.loads(_ledger_path().read_text(encoding="utf-8")).get("events", [])
    except Exception:
        events = []
    return positions_sans_sl_exchange(positions, plan_sls, events)


def intended_sl_from_events(symbol, side, events):
    """PUR. Prix de SL INTENTIONNEL (ledger) de la DERNIÈRE ouverture directionnelle réelle pour
    (symbol, side). None si aucune / SL absent. Base de l'auto-pose : re-poser l'intention perdue
    plutôt qu'inventer un SL."""
    sym, sd = str(symbol).upper(), str(side).upper()
    best_ts, best_sl = -1.0, None
    for e in events or []:
        if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
            continue
        o = e.get("order") or {}
        if o.get("reduce"):
            continue
        if str(o.get("symbol") or "").upper() != sym or str(o.get("side") or "").upper() != sd:
            continue
        try:
            ts = float(e.get("ts"))
        except (TypeError, ValueError):
            ts = -1.0
        if ts >= best_ts and o.get("stop_loss") is not None:
            best_ts, best_sl = ts, o.get("stop_loss")
    return best_sl


def _place_position_sl(symbol, side, size, trigger_price, runner=None):
    """Pose un SL de POSITION (planType `pos_loss`) via le tool hub `futures_place_tpsl_order`
    (ajouté 18/07). PROTECTIF (réduit le risque) -> autorisé même sous kill-switch, comme un
    flatten. Trigger sur `mark_price`, exécution marché. Retourne {ok, response, clientOid}."""
    from numeric_utils import safe_float
    sym = str(symbol or SYMBOL).upper()
    px = safe_float(trigger_price)
    sz = safe_float(size)
    if not px or px <= 0 or not sz or sz <= 0:
        return {"ok": False, "reason": "prix/taille SL illisibles (pas de pose en aveugle)"}
    coid = f"slheal{int(time.time() * 1000)}"
    cmd = ["futures", "futures_place_tpsl_order",
           "--symbol", sym, "--productType", PRODUCT_TYPE, "--marginCoin", MARGIN_COIN,
           "--planType", "pos_loss", "--triggerPrice", f"{px}", "--triggerType", "mark_price",
           "--holdSide", str(side).lower(), "--size", f"{sz}", "--clientOid", coid]
    out = _run(cmd, runner=runner)
    compact = (out or "").replace(" ", "").lower()
    ok = bool(out) and '"ok":false' not in compact and "error" not in compact
    _journal_telemetrie({"ts": int(time.time()), "action": "FUTURES_SL_PLACED",   # §108 : canal séparé
                         "order": {"symbol": sym, "side": side, "size": sz, "trigger": px,
                                   "clientOid": coid},
                         "ok": ok, "response": str(out)[:300]})
    return {"ok": ok, "response": out, "clientOid": coid}


def enforce_position_sl(dry=None, live=None, nus=_UNSET, events=_UNSET, positions=_UNSET, runner=None):
    """Auto-pose PROTECTIVE du SL exchange manquant (§durcis-sl Étape 2). Derrière le verrou
    `FUTURES_SL_AUTOHEAL` (défaut OFF) et DRY par défaut. Idempotent (ne pose que pour les positions
    ACTUELLEMENT nues, cf. `positions_sans_sl_exchange_live`), journalisé.

    DRY : calcule et JOURNALISE le SL qu'elle poserait (intention re-dérivée du ledger), SANS ordre.
    LIVE (gate ON) : re-pose le SL via `_place_position_sl` (tool hub `futures_place_tpsl_order`,
    planType pos_loss, holdSide=côté position, triggerPrice=intention, size=taille position).
    Protectif -> autorisé même sous kill-switch (comme un flatten). Jamais de pose en aveugle : si
    l'intention (ledger) OU la taille (position) manque, on s'abstient. `nus`/`events`/`positions`
    injectables (tests / réutilisation). FAIL-CLOSED : sources illisibles (None) -> pas de heal."""
    if live is None:
        from config_utils import env_flag           # env-first (armable via .env, cf. verrous §67)
        live = env_flag("FUTURES_SL_AUTOHEAL", False)
    if dry is None:
        dry = not live
    if nus is _UNSET:
        nus = positions_sans_sl_exchange_live(runner=runner)
    if nus is None:
        return {"ok": False, "dry": bool(dry), "reason": "sources SL illisibles (fail-closed)",
                "planned": [], "placed": []}
    if events is _UNSET:
        try:
            events = json.loads(_ledger_path().read_text(encoding="utf-8")).get("events", [])
        except Exception:
            events = []
    size_by = {}
    if not dry:                                            # taille position requise seulement pour poser
        if positions is _UNSET:
            try:
                import real_positions as rp
                positions = rp.futures()
            except Exception:
                positions = []
        size_by = {(str(p.get("symbol")).upper(), str(p.get("side")).upper()): p.get("size")
                   for p in (positions or []) if isinstance(p, dict)}
    planned = [{"symbol": p["symbol"], "side": p["side"], "agent": p.get("agent"),
                "intended_sl": intended_sl_from_events(p["symbol"], p["side"], events),
                "size": size_by.get((p["symbol"], p["side"]))}
               for p in nus]
    if planned:
        _journal_telemetrie({"ts": int(time.time()),                      # §108 : canal séparé
                             "action": "FUTURES_SL_AUTOHEAL_DRY" if dry else "FUTURES_SL_AUTOHEAL",
                             "dry": bool(dry), "planned": planned})
    if dry or not planned:
        return {"ok": True, "dry": True, "planned": planned, "placed": []}
    placed = []
    for pl in planned:
        if pl["intended_sl"] and pl["size"]:
            r = _place_position_sl(pl["symbol"], pl["side"], pl["size"], pl["intended_sl"], runner=runner)
        else:
            r = {"ok": False, "reason": "intention (ledger) ou taille (position) manquante"}
        placed.append({**pl, "result": r})
    return {"ok": all(x["result"].get("ok") for x in placed), "dry": False,
            "planned": planned, "placed": placed}


def main():
    import argparse
    p = argparse.ArgumentParser(description="Ordre futures RÉEL borné (étape 2, §45).")
    p.add_argument("--agent", default="carry", help="origine de l'ordre (agent/stratégie)")
    p.add_argument("--side", default="long", choices=["long", "short"], help="sens")
    p.add_argument("--reduce", action="store_true", help="réduit/ferme au lieu d'ouvrir")
    p.add_argument("--usdt", type=float, default=10.0, help="notional en USDT")
    p.add_argument("--leverage", type=float, default=2.0, help="levier (clampé au mur ×5)")
    p.add_argument("--entry", type=float, help="prix d'entrée (optionnel)")
    p.add_argument("--sl", type=float, help="stop loss (optionnel)")
    p.add_argument("--tp", type=float, help="take profit (optionnel)")
    p.add_argument("--confirm", action="store_true",
                   help="exécute le VRAI ordre (sinon DRY : preview seulement)")
    p.add_argument("--force", action="store_true",
                   help="outrepasse le garde anti-doublon (ouvre même si une position identique "
                        "est déjà ouverte ou vient d'être ouverte)")
    p.add_argument("--rebase-equity", action="store_true",
                   help="OUTIL PROPRIÉTAIRE : réancre la courbe d'equity après un "
                        "mouvement de capital (halte MDD fantôme). DRY sans --confirm.")
    args = p.parse_args()

    if args.rebase_equity:
        print("=== RÉANCRAGE EQUITY (halte MDD, garde 6) — décision propriétaire ===")
        r = rebase_equity(confirm=args.confirm)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        if r.get("dry"):
            print("Mode DRY — rien n'a été modifié. Ajouter --confirm pour réancrer.")
        elif r.get("ok"):
            print("✅ Courbe réancrée. La garde 6 repart du point courant (murs intacts).")
        return

    print("=== ORDRE FUTURES RÉEL BORNÉ (étape 2, §45) ===")
    if args.reduce:                                   # FERMETURE : exemptée du cap cumulé
        r = execute(args.agent, args.side, args.usdt, args.leverage, args.entry,
                    args.sl, args.tp, reduce=True, confirm=args.confirm)
    else:
        # OUVERTURE (I1, revue Thème 2) : passe par la sérialisation. Sinon ce CLI
        # présenterait gross=0 à guards -> aveugle au mur cumulé 250, et ne serait
        # sérialisé avec AUCUN ouvreur. gated_open pose le verrou + le gross effectif
        # cross-livre (lecteur via futures_auto ; import tardif -> pas de cycle d'import).
        import futures_auto as _fa
        # Anti-doublon du CLI manuel (double-invocation accidentelle / re-run après réponse
        # perdue) : le CLI n'a pas de throttle comme les boucles auto. --force outrepasse.
        if args.confirm and not args.force:
            dup = open_duplicate_reason(args.agent, SYMBOL, args.side,
                                        par_sym=_fa.positions_par_symbole(),
                                        events=_fa._executor_events())
            if dup:
                print(f"REFUSÉ (anti-doublon) : {dup}")
                print("Ajoute --force pour ouvrir/empiler intentionnellement.")
                return
        r = gated_open(args.agent, args.side, args.usdt, args.leverage,
                       entry=args.entry, stop_loss=args.sl, take_profit=args.tp,
                       confirm=args.confirm, read_book_gross=_fa.gross_book_usdt)
    print(f"Preview : {r.get('preview')}")
    if not r.get("ok"):
        print("REFUSÉ : " + " ; ".join(r.get("reasons", [])))
    elif r.get("dry"):
        print("Mode DRY — aucun ordre passé. " + r.get("note", ""))
    elif r.get("executed"):
        print(f"✅ ORDRE RÉEL exécuté (clientOid {r.get('clientOid')}).")
        print(f"Réponse : {str(r.get('response'))[:400]}")
    else:
        print(f"⚠️ Échec d'exécution : {r.get('reasons') or str(r.get('response'))[:400]}")
    print("Périmètre : futures borné (murs 50/trade · 250 cumulé · stop journalier -> kill-switch).")


if __name__ == "__main__":
    main()
