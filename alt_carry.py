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
paient les shorts). Le cas funding NÉGATIF exigerait un emprunt marge : HORS
périmètre v1 (volontairement réduit).

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


def decider(etat, cands, pctl_min=None, apr_min=None, pctl_exit=None, apr_exit=None):
    """PUR. UNE action par cycle : fermer si la position ne paie plus (percentile ou
    APR retombés), sinon ouvrir le meilleur candidat EXTRÊME (funding POSITIF
    uniquement, v1 sans emprunt). {"action": "ouvrir"|"fermer"|"rien", ...}."""
    pctl_min = _flt("ALT_CARRY_PCTL", 90.0) if pctl_min is None else float(pctl_min)
    apr_min = _flt("ALT_CARRY_MIN_APR", 12.0) if apr_min is None else float(apr_min)
    pctl_exit = _flt("ALT_CARRY_EXIT_PCTL", 50.0) if pctl_exit is None else float(pctl_exit)
    apr_exit = _flt("ALT_CARRY_EXIT_APR", 5.0) if apr_exit is None else float(apr_exit)
    pos = (etat or {}).get("position")
    par_sym = {c["symbol"]: c for c in cands or []}
    if pos:
        c = par_sym.get(pos.get("symbol"))
        if not c:
            return {"action": "rien", "raison": f"{pos.get('symbol')} : funding illisible — on tient (fail-safe)"}
        if (c.get("pctl") is not None and c["pctl"] < pctl_exit) or (c.get("apr_pct") or 0) < apr_exit:
            return {"action": "fermer", "symbol": pos["symbol"],
                    "raison": f"funding retombé (pctl {c.get('pctl')}, APR {c.get('apr_pct')} %)"}
        return {"action": "rien", "raison": f"jambe {pos['symbol']} paie encore "
                                            f"(pctl {c.get('pctl')}, APR {c.get('apr_pct')} %)"}
    for c in cands or []:
        if (c.get("taux") or 0) > 0 and (c.get("pctl") or 0) >= pctl_min \
                and (c.get("apr_pct") or 0) >= apr_min:
            return {"action": "ouvrir", "symbol": c["symbol"],
                    "raison": f"funding extrême (pctl {c['pctl']}, APR {c['apr_pct']} %)"}
    return {"action": "rien", "raison": "aucun funding extrême positif sur l'univers"}


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
        res = _ouvrir(d["symbol"], usdt, arme)
        out["resultat"] = {k: (v if k in ("ok", "etape") else
                               {kk: v.get(kk) for kk in ("ok", "dry", "executed", "reasons")})
                           for k, v in res.items() if v is not None}
        if arme and res.get("ok"):
            etat["position"] = {"symbol": d["symbol"], "usdt": usdt, "ts": int(now)}
            _sauve_etat(etat)
            out["executed"] = True
            _notifie(f"🌾 Alt-carry OUVERT : {d['symbol']} {usdt} $/jambe — {d['raison']} "
                     "(delta-neutre, funding encaissé toutes les 8 h).")
    elif d["action"] == "fermer":
        pos = etat.get("position") or {}
        res = _fermer(d["symbol"], pos.get("usdt", usdt), arme)
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
    lignes.append("Décision seule ici — jambes via spot_trader (§67) et futures_executor (§45), "
                  "chacune avec SES gardes. Funding négatif (emprunt) : hors périmètre v1. VERDICT: SAFE")
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
        print("EXÉCUTÉ" if r.get("executed") else "DRY/riens — aucun mouvement réel.")
        print("VERDICT: SAFE")
    else:
        print(build_report())


if __name__ == "__main__":
    main()
