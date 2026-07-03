"""
xs_paper.py — voie PAPER : momentum CROSS-SECTIONNEL long-short (§60). SAFE.

Dernier survivant de la feuille de route §52 : chaque JOUR (throttle interne),
classe l'univers par rendement 7 j, panier PAPER dollar-neutre long top-K /
short bottom-K équipondéré (10 $ par jambe, fictifs). Au rebalance suivant, le
PnL du panier précédent est réalisé au prix courant et journalisé
(xs_paper_journal.jsonl, gitignored). AUCUN ordre réel, AUCUN vote — c'est un
LABORATOIRE : ses semaines de journal diront si la stratégie mérite mieux.
NB mesuré (§53) : nos données crypto penchent réversion — le laboratoire
tranchera dans les deux sens (un momentum xs NÉGATIF stable = candidat inverse).

Cœurs PURS testables. CLI : python xs_paper.py --status
"""

import json
import time
from pathlib import Path

from config_utils import cfg as _cfg
from numeric_utils import safe_float

JOURNAL = Path(__file__).resolve().parent / "xs_paper_journal.jsonl"
ETAT = Path(__file__).resolve().parent / ".xs_paper_etat.json"
K = 2                                        # jambes par côté
NOTIONAL_JAMBE = 10.0                        # $ fictifs par jambe
LOOKBACK_H = 168                             # rendement 7 j (bougies 1h)
REBALANCE_H = 24.0


def classement(rendements, k=K):
    """PUR. {symbol: rendement 7 j} -> (longs top-k, shorts bottom-k), triés.
    Exige >= 2k symboles lisibles, sinon ([], [])."""
    ok = [(s, r) for s, r in (rendements or {}).items() if r is not None]
    if len(ok) < 2 * k:
        return [], []
    tri = sorted(ok, key=lambda x: -x[1])
    return [s for s, _ in tri[:k]], [s for s, _ in tri[-k:]]


def pnl_panier(panier, prix_courants, notional=NOTIONAL_JAMBE):
    """PUR. PnL $ du panier {longs: {sym: prix_entree}, shorts: {...}} aux prix
    courants (jambes équipondérées). None si un prix manque (fail-honest :
    pas de PnL partiel silencieux)."""
    total = 0.0
    for sym, pe in (panier.get("longs") or {}).items():
        pc = safe_float((prix_courants or {}).get(sym))
        pe = safe_float(pe)
        if not pc or not pe:
            return None
        total += notional * (pc / pe - 1.0)
    for sym, pe in (panier.get("shorts") or {}).items():
        pc = safe_float((prix_courants or {}).get(sym))
        pe = safe_float(pe)
        if not pc or not pe:
            return None
        total += notional * (1.0 - pc / pe)
    return round(total, 6)


def _rendements_7j():
    """{symbol: rendement 7 j} sur l'univers (best-effort par symbole)."""
    out = {}
    try:
        import futures_auto as fa
        import market_sources as ms
        for s in fa._universe():
            try:
                closes = ms.closes(s, LOOKBACK_H + 2)
                if closes and len(closes) > LOOKBACK_H:
                    out[s] = float(closes[-1]) / float(closes[-LOOKBACK_H]) - 1.0
                else:
                    out[s] = None
            except Exception:
                out[s] = None
    except Exception:
        pass
    return out


def _prix_courants(symbols):
    out = {}
    try:
        import market_sources as ms
        for s in symbols:
            try:
                c = ms.closes(s, 3)
                out[s] = float(c[-1]) if c else None
            except Exception:
                out[s] = None
    except Exception:
        pass
    return out


def run(now=None):
    """Un pas de laboratoire : si >= 24 h depuis le dernier rebalance, réalise le
    PnL paper du panier courant puis en construit un nouveau. AUCUN ordre."""
    now = time.time() if now is None else now
    try:
        etat = json.loads(ETAT.read_text(encoding="utf-8"))
    except Exception:
        etat = {}
    if etat.get("ts") and (now - etat["ts"]) < REBALANCE_H * 3600:
        return {"action": "rien", "raison": "rebalance quotidien pas encore dû"}
    rend = _rendements_7j()
    longs, shorts = classement(rend)
    resultat = {"action": "rebalance", "ts": int(now)}
    if etat.get("panier"):
        syms = list((etat["panier"].get("longs") or {})) + list((etat["panier"].get("shorts") or {}))
        pnl = pnl_panier(etat["panier"], _prix_courants(syms))
        resultat["pnl_usdt"] = pnl
        try:
            import journal_append as ja
            ja.append_jsonl(JOURNAL, {"ts": int(now), "pnl_usdt": pnl,
                                      "panier": etat["panier"]}, max_bytes=10_000_000)
        except Exception:
            pass
    if longs and shorts:
        prix = _prix_courants(longs + shorts)
        panier = {"longs": {s: prix.get(s) for s in longs},
                  "shorts": {s: prix.get(s) for s in shorts}}
        if all(panier["longs"].values()) and all(panier["shorts"].values()):
            etat = {"ts": int(now), "panier": panier}
            ETAT.write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
            resultat["panier"] = panier
        else:
            resultat["raison"] = "prix illisibles — panier inchangé"
    else:
        resultat["raison"] = "univers trop court pour 2x2 jambes"
    return resultat


def status():
    """Lecture seule : panier courant + PnL cumulé du journal."""
    try:
        etat = json.loads(ETAT.read_text(encoding="utf-8"))
    except Exception:
        etat = {}
    cumul, n = 0.0, 0
    try:
        with open(JOURNAL, "r", encoding="utf-8") as f:
            for ligne in f:
                try:
                    e = json.loads(ligne)
                    if e.get("pnl_usdt") is not None:
                        cumul += float(e["pnl_usdt"])
                        n += 1
                except Exception:
                    continue
    except Exception:
        pass
    return {"panier": etat.get("panier"), "depuis": etat.get("ts"),
            "rebalances": n, "pnl_cumule_usdt": round(cumul, 4)}


def build_report(s=None, resultat=None):
    s = status() if s is None else s
    lignes = ["=== XS PAPER — momentum cross-sectionnel long-short (LABORATOIRE) ==="]
    p = s.get("panier") or {}
    if p:
        lignes.append("longs  : " + " · ".join(f"{k.replace('USDT','')}" for k in (p.get("longs") or {})))
        lignes.append("shorts : " + " · ".join(f"{k.replace('USDT','')}" for k in (p.get("shorts") or {})))
    lignes.append(f"{s.get('rebalances', 0)} rebalances journalisés · PnL paper cumulé "
                  f"{s.get('pnl_cumule_usdt', 0):+.4f} $ (2×{K} jambes de {NOTIONAL_JAMBE:.0f} $ fictifs)")
    if resultat:
        lignes.append(f"ce cycle : {resultat.get('action')} {resultat.get('raison', '')}"
                      + (f" · PnL réalisé {resultat.get('pnl_usdt'):+.4f} $"
                         if resultat.get("pnl_usdt") is not None else ""))
    lignes.append("PAPER pur : aucun ordre, aucun vote. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    import sys
    if "--status" in sys.argv:
        print(build_report())
        return
    r = run()
    print(build_report(resultat=r))


if __name__ == "__main__":
    main()
