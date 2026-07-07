"""
alt_carry.py — carry de funding MULTI-SYMBOLES borné (§82) : moisson des extrêmes.

Classement : module de DÉCISION — aucun appel d'écriture direct. Les DEUX jambes
sont DÉLÉGUÉES aux exécuteurs audités : jambe spot via `spot_trader` (surface §67 :
verrou SPOT_TRADE_LIVE, caps par opération et par jour, kill-switch fail-closed) et
jambe perp via `futures_executor` (§45 : double verrou, porte d'edge/override, caps,
murs 50/250, stop journalier). Le RETRAIT n'existe nulle part (clé Trade-only).

Méthode (mandat propriétaire du 06/07 : « diversifier les méthodes ») : le funding
est un revenu CONTRACTUEL versé toutes les 8 h — pas une prédiction. Quand le
funding d'un alt est EXTRÊME (percentile ≥ ALT_CARRY_PCTL sur l'historique local
~90 j ET APR annualisé ≥ ALT_CARRY_MIN_APR), on l'encaisse SANS direction :
funding POSITIF -> acheter X $ de spot + vendre X $ de perp (delta ≈ 0, les longs
paient les shorts). Funding NÉGATIF (v2, AUTORISÉ par décision propriétaire du
06/07 « j'autorise les emprunts marge si bonne gestion ») : perp LONG + vente du
coin EMPRUNTÉ en marge (delta ≈ 0, les shorts paient) — le COÛT D'EMPRUNT estimé
(ALT_CARRY_BORROW_APR) est DÉDUIT de l'APR avant toute entrée, et chaque étage a
sa compensation (jamais de jambe nue, jamais d'emprunt orphelin).

Sortie : percentile < ALT_CARRY_EXIT_PCTL ou APR < ALT_CARRY_EXIT_APR -> fermer.
Anti-jambe-nue : à l'ENTRÉE le spot s'achète D'ABORD ; si la jambe perp échoue,
le spot est revendu immédiatement (compensation journalisée). À la SORTIE le perp
se ferme d'abord (un spot seul n'est pas un risque directionnel vendu).

Gate maître ALT_CARRY_LIVE (défaut OFF -> DRY : décisions journalisées, AUCUN
mouvement — les exécuteurs reçoivent confirm=False). UNE action par cycle,
UNE position à la fois (v1 frugale). État `.alt_carry_state.json` ; journal
`.alt_carry_journal.jsonl` ; Telegram sur action réelle.

CLI :
    python alt_carry.py --status    # lecture seule : scan + décision PRÉVUE
    python alt_carry.py --cycle     # un cycle (n'agit que si ALT_CARRY_LIVE=1)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from config_utils import cfg as _cfg
from numeric_utils import safe_float

ETAT = Path(__file__).resolve().parent / ".alt_carry_state.json"
JOURNAL = Path(__file__).resolve().parent / ".alt_carry_journal.jsonl"


def enabled():
    """Gate maître (défaut OFF). Armable via env ALT_CARRY_LIVE=1 OU config."""
    v = os.getenv("ALT_CARRY_LIVE", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg("ALT_CARRY_LIVE", False))


def _flt(name, default):
    try:
        return float(os.getenv(name) or _cfg(name, default))
    except (TypeError, ValueError):
        return float(default)


def _etat():
    try:
        return json.loads(ETAT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sauve_etat(st):
    try:
        tmp = ETAT.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, ETAT)
    except Exception:
        pass


def _journalise(entree):
    try:
        with JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entree, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _notifie(msg):
    try:
        import telegram_notifier as tn
        tn.send_telegram(msg)
    except Exception:
        pass


def scan(universe=None):
    """Scan des funding de l'univers (hors BTC — carry_auto s'en occupe déjà) :
    consolide l'historique local (download déduplique, paginé public) puis mesure
    taux courant, percentile ~90 j et APR annualisé. Trié APR décroissant.
    Best-effort par symbole (un échec n'écrase pas le scan)."""
    import funding_history as fh
    if universe is None:
        try:
            import universe as un
            universe = [str(s).upper() for s in un.symbols()]
        except Exception:
            universe = ["ETHUSDT", "SOLUSDT", "XRPUSDT"]
    out = []
    for sym in universe:
        if sym == "BTCUSDT":
            continue
        try:
            fh.download(sym, annees=1, max_pages=4)   # consolidation incrémentale (dédup)
            rows = fh.load(sym)                        # [(ts_ms, taux)] — format attendu
            if len(rows) < 30:
                continue
            taux = rows[-1][1]
            pctl = fh.percentile_taux(rows, taux)
            apr = taux * 3 * 365 * 100.0
            out.append({"symbol": sym, "taux": round(taux, 8),
                        "pctl": round(pctl, 1) if pctl is not None else None,
                        "apr_pct": round(apr, 2)})
        except Exception:
            continue
    out.sort(key=lambda r: -(r["apr_pct"] or 0))
    return out


def _neg_on():
    v = (os.getenv("ALT_CARRY_NEG") or "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    return bool(_cfg("ALT_CARRY_NEG", False))


def decider(etat, cands, pctl_min=None, apr_min=None, pctl_exit=None, apr_exit=None,
            borrow_apr=None, neg=None):
    """PUR. UNE action par cycle : fermer si la position ne paie plus, sinon ouvrir
    le meilleur EXTRÊME. Deux modes :
      • classic (funding POSITIF, pctl ≥ pctl_min, APR ≥ apr_min) ;
      • reverse (funding NÉGATIF, pctl ≤ 100−pctl_min, APR NET d'emprunt ≥ apr_min —
        gated ALT_CARRY_NEG, décision propriétaire).
    {"action": "ouvrir"|"fermer"|"rien", "mode": "classic"|"reverse", ...}."""
    pctl_min = _flt("ALT_CARRY_PCTL", 90.0) if pctl_min is None else float(pctl_min)
    apr_min = _flt("ALT_CARRY_MIN_APR", 12.0) if apr_min is None else float(apr_min)
    pctl_exit = _flt("ALT_CARRY_EXIT_PCTL", 50.0) if pctl_exit is None else float(pctl_exit)
    apr_exit = _flt("ALT_CARRY_EXIT_APR", 5.0) if apr_exit is None else float(apr_exit)
    borrow_apr = _flt("ALT_CARRY_BORROW_APR", 15.0) if borrow_apr is None else float(borrow_apr)
    neg = _neg_on() if neg is None else bool(neg)
    pos = (etat or {}).get("position")
    par_sym = {c["symbol"]: c for c in cands or []}
    if pos:
        c = par_sym.get(pos.get("symbol"))
        mode = pos.get("mode", "classic")
        if not c:
            return {"action": "rien", "raison": f"{pos.get('symbol')} : funding illisible — on tient (fail-safe)"}
        if mode == "reverse":
            net = abs(c.get("apr_pct") or 0) - borrow_apr
            if (c.get("taux") or 0) >= 0 or (c.get("pctl") is not None and c["pctl"] > 100 - pctl_exit) \
                    or net < apr_exit:
                return {"action": "fermer", "symbol": pos["symbol"], "mode": mode,
                        "raison": f"funding normalisé (pctl {c.get('pctl')}, net {round(net, 1)} %)"}
            return {"action": "rien", "raison": f"jambe reverse {pos['symbol']} paie encore "
                                                f"(net {round(net, 1)} % après emprunt)"}
        if (c.get("pctl") is not None and c["pctl"] < pctl_exit) or (c.get("apr_pct") or 0) < apr_exit:
            return {"action": "fermer", "symbol": pos["symbol"], "mode": mode,
                    "raison": f"funding retombé (pctl {c.get('pctl')}, APR {c.get('apr_pct')} %)"}
        return {"action": "rien", "raison": f"jambe {pos['symbol']} paie encore "
                                            f"(pctl {c.get('pctl')}, APR {c.get('apr_pct')} %)"}
    for c in cands or []:
        taux, pctl, apr = c.get("taux") or 0, c.get("pctl") or 50, c.get("apr_pct") or 0
        if taux > 0 and pctl >= pctl_min and apr >= apr_min:
            return {"action": "ouvrir", "symbol": c["symbol"], "mode": "classic",
                    "raison": f"funding extrême (pctl {pctl}, APR {apr} %)"}
        if neg and taux < 0 and pctl <= (100 - pctl_min) and (abs(apr) - borrow_apr) >= apr_min:
            if _reverse_bloque(etat, c["symbol"]):
                continue                               # coin non empruntable (liste noire §90)
            return {"action": "ouvrir", "symbol": c["symbol"], "mode": "reverse",
                    "raison": (f"funding extrême NÉGATIF (pctl {pctl}, APR {apr} % ; "
                               f"net ~{round(abs(apr) - borrow_apr, 1)} % après emprunt "
                               f"{borrow_apr} %)")}
    return {"action": "rien", "raison": "aucun funding extrême exploitable sur l'univers"}


def _prix(sym):
    try:
        import bitget_market_data as bmd
        return (bmd.mark_prices() or {}).get(str(sym).upper())
    except Exception:
        return None


def _coin(sym):
    return str(sym).upper().replace("USDT", "")


def _bloquer_reverse(sym, now=None):
    """§90 — LISTE NOIRE reverse : l'exchange a refusé l'EMPRUNT de ce coin (aucun
    endpoint hub ne liste les coins empruntables — la capacité se découvre par
    l'échec). Bloqué ALT_CARRY_BLOCK_DAYS jours (défaut 7) pour ne pas re-payer
    des frais de compensation à chaque extrême du même coin."""
    try:
        etat = _etat()
        etat.setdefault("reverse_bloque", {})[_coin(sym)] = int(now or time.time())
        _sauve_etat(etat)
    except Exception:
        pass


def _reverse_bloque(etat, sym, now=None):
    ts = ((etat or {}).get("reverse_bloque") or {}).get(_coin(sym))
    if not ts:
        return False
    jours = _flt("ALT_CARRY_BLOCK_DAYS", 7.0)
    return (float(now or time.time()) - float(ts)) < jours * 86400


def _collateral_manquant(besoin, disponible):
    """PUR. Ce qu'il faut VRAIMENT virer en marge : le manquant (0 si le float §91
    couvre déjà, ou si le solde est illisible -> on vire tout, fail-safe)."""
    if disponible is None:
        return round(float(besoin), 2)
    return round(max(0.0, float(besoin) - float(disponible)), 2)


def _ouvrir_reverse(sym, usdt, arme):
    """Entrée REVERSE (funding négatif, §83) : perp LONG d'abord (jambe la plus fiable,
    compensable d'un reduce), puis EMPRUNT du coin (quantité = usdt/prix — le notionnel
    USDT borne les caps, la quantité coin part à l'API), puis VENTE marge. Compensations
    étagées : emprunt raté -> reduce du perp ; vente ratée -> remboursement + reduce.
    Jamais de jambe nue, jamais d'emprunt orphelin."""
    import futures_auto as fa
    import futures_executor as fe
    import margin_trader as mt
    prix = _prix(sym)
    if not prix or prix <= 0:
        return {"ok": False, "etape": "prix", "raison": "prix illisible (fail-closed)"}
    mtype = str(os.getenv("ALT_CARRY_MARGIN_TYPE") or _cfg("ALT_CARRY_MARGIN_TYPE", "crossed")).lower()
    coin_qte = round(float(usdt) / float(prix), 6)
    # étape 0 — COLLATÉRAL au MANQUANT (§91) : le gestionnaire de liquidité maintient
    # un float marge (LIQ_MARGIN_MIN_USDT) ; on ne vire que le complément éventuel.
    # Rendu à la fermeture (seul ce qu'on a AJOUTÉ). Échec -> abandon avant toute jambe.
    import account_transfers as at
    import liquidity_manager as lm
    besoin_collat = round(min(float(usdt) * 1.2, 60.0), 2)
    disponible = lm._marge_usdt()
    collat = _collateral_manquant(besoin_collat, disponible)
    depot = {"skipped": True, "raison": f"marge dispo {disponible} ≥ besoin {besoin_collat}"}         if collat <= 0 else at.execute("spot", "crossed_margin", "USDT", collat, confirm=arme)
    if arme and collat > 0 and not depot.get("executed"):
        return {"ok": False, "etape": "collateral", "depot": depot}
    jambe_perp = fe.execute("alt_carry", "long", usdt, 1.0, symbol=sym, confirm=arme,
                            gross_open_usdt=fa.gross_book_usdt(),
                            equity_curve=fe.equity_curve())
    if arme and not jambe_perp.get("executed"):
        if collat > 0:
            at.execute("crossed_margin", "spot", "USDT", collat, confirm=arme)   # rend l'ajout
        return {"ok": False, "etape": "perp", "perp": jambe_perp, "depot": depot}
    emprunt = mt.borrow(_coin(sym), usdt, amount=coin_qte, margin_type=mtype, confirm=arme)
    if arme and not emprunt.get("executed"):
        comp = fe.execute("alt_carry", "long", usdt, 1.0, symbol=sym, reduce=True,
                          confirm=arme, gross_open_usdt=fa.gross_book_usdt(),
                          equity_curve=fe.equity_curve())
        retour = (None if collat <= 0
                  else at.execute("crossed_margin", "spot", "USDT", collat, confirm=arme))
        _bloquer_reverse(sym)                          # coin probablement non empruntable
        return {"ok": False, "etape": "emprunt", "perp": jambe_perp, "depot": depot,
                "emprunt": emprunt, "compensation": comp, "retour_collateral": retour}
    vente = mt.order(sym, "sell", usdt, margin_type=mtype, confirm=arme)
    if arme and not vente.get("executed"):
        remb = mt.repay(_coin(sym), usdt, amount=coin_qte, margin_type=mtype, confirm=arme)
        comp = fe.execute("alt_carry", "long", usdt, 1.0, symbol=sym, reduce=True,
                          confirm=arme, gross_open_usdt=fa.gross_book_usdt(),
                          equity_curve=fe.equity_curve())
        retour = (None if collat <= 0
                  else at.execute("crossed_margin", "spot", "USDT", collat, confirm=arme))
        return {"ok": False, "etape": "vente", "perp": jambe_perp, "depot": depot,
                "emprunt": emprunt, "vente": vente, "remboursement": remb,
                "compensation": comp, "retour_collateral": retour}
    return {"ok": (not arme) or vente.get("executed"), "perp": jambe_perp,
            "depot": depot, "emprunt": emprunt, "vente": vente, "coin_qte": coin_qte,
            "prix": prix, "margin_type": mtype, "collateral": collat}


def _fermer_reverse(sym, pos, arme):
    """Sortie REVERSE : rachat marge (avec petit coussin ≤ cap pour couvrir les
    intérêts), remboursement de l'emprunt, puis fermeture du perp long."""
    import futures_auto as fa
    import futures_executor as fe
    import margin_trader as mt
    usdt = float(pos.get("usdt") or _flt("ALT_CARRY_PER_LEG_USDT", 10.0))
    mtype = str(pos.get("margin_type") or "crossed")
    coin_qte = float(pos.get("coin_qte") or 0) or None
    cap_op = mt._caps()[0]
    rachat = mt.order(sym, "buy", min(round(usdt * 1.02, 2), cap_op), margin_type=mtype, confirm=arme)
    if arme and not rachat.get("executed"):
        return {"ok": False, "etape": "rachat", "rachat": rachat}
    remb = mt.repay(_coin(sym), usdt, amount=coin_qte, margin_type=mtype, confirm=arme)
    perp = fe.execute("alt_carry", "long", usdt, 1.0, symbol=sym, reduce=True,
                      confirm=arme, gross_open_usdt=fa.gross_book_usdt(),
                      equity_curve=fe.equity_curve())
    retour = None
    if pos.get("collateral"):                     # rend le collatéral au spot
        import account_transfers as at
        retour = at.execute("crossed_margin", "spot", "USDT", float(pos["collateral"]),
                            confirm=arme)
    return {"ok": (not arme) or (remb.get("executed") and perp.get("executed")),
            "rachat": rachat, "remboursement": remb, "perp": perp, "retour": retour}


def _taille_jambe(sym, base=None, spec=None, px=None, caps=None):
    """§90 — taille/jambe ADAPTÉE aux minima du contrat (leçon LAB : min 1 coin
    ≈ 16.6 $ > jambe de 10 $ -> l'extrême à 795 % net est passé sans moisson),
    BORNÉE par le plus petit cap par opération des surfaces impliquées (les DEUX
    jambes doivent passer). (taille, besoin, plafond) — taille=None si infaisable."""
    base = _flt("ALT_CARRY_PER_LEG_USDT", 10.0) if base is None else float(base)
    if spec is None or px is None or caps is None:
        import bitget_execute as ex
        import futures_executor as fe
        import margin_trader as mt
        import spot_trader as st
        spec = fe._contract_spec(sym) or {}
        px = _prix(sym)
        caps = (ex.capped("SPOT_TRADE_MAX_PER_OP_USDT", 10.0, st.ABS_PER_OP_USDT),
                ex.capped("MARGIN_MAX_PER_OP_USDT", 10.0, mt.ABS_PER_OP_USDT),
                fe._capped("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0, fe.FUT_ABS_MAX_PER_TRADE_USDT))
    if not px or px <= 0:
        return None, None, None
    mini = max(float(spec.get("min_usdt") or 0.0),
               float(spec.get("min_size") or 0.0) * float(px)) * 1.06
    besoin = max(base, mini)
    plafond = min(float(c) for c in caps)
    if besoin > plafond + 1e-9:
        return None, round(besoin, 2), round(plafond, 2)
    return round(besoin, 2), round(besoin, 2), round(plafond, 2)


def _ouvrir(sym, usdt, arme):
    """Entrée deux jambes, anti-jambe-nue : spot D'ABORD, perp ensuite ; si le perp
    échoue, le spot est revendu (compensation). Chaque jambe porte SES gardes."""
    import futures_auto as fa
    import futures_executor as fe
    import spot_trader as st
    jambe_spot = st.execute(sym, "buy", usdt, confirm=arme)
    if arme and not jambe_spot.get("executed"):
        return {"ok": False, "etape": "spot", "spot": jambe_spot}
    jambe_perp = fe.execute("alt_carry", "short", usdt, 1.0, symbol=sym, confirm=arme,
                            gross_open_usdt=fa.gross_book_usdt(),
                            equity_curve=fe.equity_curve())
    if arme and jambe_spot.get("executed") and not jambe_perp.get("executed"):
        compensation = st.execute(sym, "sell", usdt, confirm=arme)   # jamais de jambe nue
        return {"ok": False, "etape": "perp", "spot": jambe_spot,
                "perp": jambe_perp, "compensation": compensation}
    return {"ok": (not arme) or jambe_perp.get("executed"),
            "spot": jambe_spot, "perp": jambe_perp}


def _fermer(sym, usdt, arme):
    """Sortie : perp d'abord (reduce), puis revente du spot."""
    import futures_auto as fa
    import futures_executor as fe
    import spot_trader as st
    jambe_perp = fe.execute("alt_carry", "short", usdt, 1.0, symbol=sym, reduce=True,
                            confirm=arme, gross_open_usdt=fa.gross_book_usdt(),
                            equity_curve=fe.equity_curve())
    if arme and not jambe_perp.get("executed"):
        return {"ok": False, "etape": "perp", "perp": jambe_perp}
    jambe_spot = st.execute(sym, "sell", usdt, confirm=arme)
    return {"ok": (not arme) or jambe_spot.get("executed"),
            "perp": jambe_perp, "spot": jambe_spot}


def cycle(now=None):
    """Un cycle : scan -> décision -> exécution déléguée (DRY tant que ALT_CARRY_LIVE
    est OFF — les décisions sont journalisées pour observation avant armement)."""
    now = time.time() if now is None else now
    etat = _etat()
    cands = scan()
    d = decider(etat, cands)
    arme = enabled()
    out = {"ts": int(now), "armed": arme, "decision": d, "cands": cands[:5],
           "executed": False}
    usdt = _flt("ALT_CARRY_PER_LEG_USDT", 10.0)
    if d["action"] == "ouvrir":
        taille, besoin, plafond = _taille_jambe(d["symbol"])
        if taille is None:
            d = {"action": "rien", "raison": (f"{d['symbol']} INFAISABLE : jambe requise "
                                              f"{besoin} $ (minima contrat) > plafond {plafond} $ "
                                              f"des surfaces — extrême détecté mais hors caps")}
            out["decision"] = d
            _journalise(out)
            return out
        usdt = taille
        res = (_ouvrir_reverse(d["symbol"], usdt, arme) if d.get("mode") == "reverse"
               else _ouvrir(d["symbol"], usdt, arme))
        out["resultat"] = {k: (v if k in ("ok", "etape") else
                               {kk: v.get(kk) for kk in ("ok", "dry", "executed", "reasons")})
                           for k, v in res.items() if v is not None}
        if arme and res.get("ok"):
            etat["position"] = {"symbol": d["symbol"], "usdt": usdt, "ts": int(now),
                                "mode": d.get("mode", "classic"),
                                "coin_qte": res.get("coin_qte"),
                                "margin_type": res.get("margin_type"),
                                "collateral": res.get("collateral")}
            _sauve_etat(etat)
            out["executed"] = True
            _notifie(f"🌾 Alt-carry OUVERT ({d.get('mode', 'classic')}) : {d['symbol']} "
                     f"{usdt} $/jambe — {d['raison']} (delta-neutre, funding 8 h).")
    elif d["action"] == "fermer":
        pos = etat.get("position") or {}
        res = (_fermer_reverse(d["symbol"], pos, arme) if pos.get("mode") == "reverse"
               else _fermer(d["symbol"], pos.get("usdt", usdt), arme))
        out["resultat"] = {k: (v if k in ("ok", "etape") else
                               {kk: v.get(kk) for kk in ("ok", "dry", "executed", "reasons")})
                           for k, v in res.items() if v is not None}
        if arme and res.get("ok"):
            etat.pop("position", None)
            _sauve_etat(etat)
            out["executed"] = True
            _notifie(f"🌾 Alt-carry FERMÉ : {d['symbol']} — {d['raison']}.")
    _journalise(out)
    return out


def status():
    """Lecture seule : scan + décision PRÉVUE (aucun mouvement)."""
    etat = _etat()
    cands = scan()
    return {"consultation": True, "armed": enabled(), "position": etat.get("position"),
            "decision": decider(etat, cands), "cands": cands[:5]}


def build_report(s=None):
    s = status() if s is None else s
    d = s.get("decision") or {}
    lignes = ["=== ALT-CARRY multi-symboles (§82, borné) — CONSULTATION ===",
              f"Armé : {s.get('armed')} · position : {s.get('position') or 'aucune'}",
              f"Décision : {str(d.get('action', 'rien')).upper()} {d.get('symbol') or ''} — {d.get('raison', '')}"]
    for c in s.get("cands") or []:
        lignes.append(f"  {c['symbol']:10s} taux {c['taux']:+.6f} · pctl {c['pctl']} · APR {c['apr_pct']:+.1f} %")
    lignes.append("Décision seule ici — jambes via spot_trader/margin_trader (§67) et "
                  "futures_executor (§45), chacune avec SES gardes. Funding négatif : REVERSE "
                  "autorisé (§83, emprunt marge net d'intérêts, collatéral géré). VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    import sys
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    if "--cycle" in sys.argv[1:]:
        r = cycle()
        d = r.get("decision") or {}
        print("=== ALT-CARRY — CYCLE ===")
        print(f"armé {r.get('armed')} · décision {str(d.get('action', 'rien')).upper()} "
              f"{d.get('symbol') or ''} — {d.get('raison', '')}")
        if r.get("executed"):
            print("EXÉCUTÉ (jambes réelles passées)")
        elif not r.get("armed"):
            print("DRY — non armé, aucun mouvement.")
        elif (r.get("decision") or {}).get("action") == "rien":
            print("RIEN — aucun mouvement.")
        else:
            print("⚠️ NON EXÉCUTÉ malgré armement — voir 'resultat' du journal.")
        print("VERDICT: SAFE")
    else:
        print(build_report())


if __name__ == "__main__":
    main()
