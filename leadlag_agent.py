"""
leadlag_agent.py — agent LEAD-LAG contrarian BTC->alts. Classement : SAFE.
Déterministe, lecture seule, AUCUN ordre, AUCUN NN.

Idée (littérature) : les mouvements de BTC mènent le marché (lead-lag haute
fréquence, arXiv:1111.7103 ; facteur BTC dans les alts, arXiv:1903.06033). La
question empirique est le SIGNE à notre horizon (8 barres) : suivi ou fade ?

MESURÉ AVANT ADOPTION (étalon replay, bougies FIGÉES, 2 fenêtres indépendantes,
3 alts, sous-échantillonnage anti-autocorrélation — §52) :
  • suivi (les alts suivent BTC)      : IC poolé −0.178 (1h) / −0.201 (15m) ;
  • CONTRARIAN (fader le z BTC)       : IC poolé +0.178 (1h, t +3.5) /
                                        +0.201 (15m, t +4.0) — ADOPTÉ.
  • réversion vers le facteur bêta×BTC (1903.06033 littéral) : fenêtres
    contradictoires (+0.03 / −0.09) — REJETÉE à la barre des deux fenêtres.
C'est la 4e confirmation du fait stylisé de réversion court terme (§35-38),
exprimée CROSS-ASSET : un mouvement marqué de BTC se dégonfle marché-large, et
les alts (bêta élevé) le rendent avec lui.

HONNÊTETÉ (validation 1 AN, §53) : sur 12 mois de bougies 1h (n=4356, pas 6 h),
l'IC poolé tombe à +0.014 (t 0.9) — positif sur CHACUN des 3 alts mais faible :
le +0.18/+0.20 des fenêtres récentes est en partie un RÉGIME (marché très
réversif en juin-juillet 2026). L'agent reste (signe jamais négatif sur 3
fenêtres × 3 symboles) mais son espérance de croisière est modeste — le
hit-rate EWMA (§51) le pèsera à sa juste valeur.

L'agent vote 0 sur BTCUSDT lui-même (pas de self lead-lag — la réversion propre
au symbole est le domaine de geometric §48). Poids appris par l'EARCP corrigé
(§51) ; l'audit d'IC live le jugera comme les autres.
"""

import math

from numeric_utils import safe_float

SYMBOL_REF = "BTCUSDT"


def signal(closes_alt, closes_btc, k=8, w=64):
    """Cœur PUR. vote = −tanh(z/2) où z = mouvement BTC des k dernières barres,
    réduit par sa vol w barres — le FADE du mouvement du meneur, appliqué à
    l'alt. Borné [−1,1]. 0.0 si données insuffisantes (fail-closed)."""
    pb = [safe_float(c) for c in closes_btc or []]
    pb = [p for p in pb if p and p > 0]
    if len(pb) < w + k + 1 or not closes_alt or len(closes_alt) < 8:
        return 0.0
    rb = [math.log(pb[i] / pb[i - 1]) for i in range(1, len(pb))]
    fen = rb[-w:]
    mu = sum(fen) / len(fen)
    sd = math.sqrt(sum((x - mu) ** 2 for x in fen) / len(fen))
    z = sum(rb[-k:]) / (sd * math.sqrt(k) + 1e-9)
    return float(-math.tanh(z / 2.0))


def analyze(symbol="ETHUSDT", ttl=45):
    """Analyse live (cachée, best-effort). BTC lui-même -> vote 0."""
    import runtime_cache as rc

    symbol = str(symbol).upper()
    if symbol == SYMBOL_REF:
        return {"vote": 0.0, "confidence": 0.0,
                "note": "BTC est la référence (pas de self lead-lag)"}

    def fetch():
        try:
            import market_sources as ms
            alt = ms.closes(symbol, 90)
            btc = ms.closes(SYMBOL_REF, 90)
        except Exception:
            return {"vote": 0.0, "confidence": 0.0, "note": "n/a"}
        v = signal(alt, btc)
        conf = round(0.45 * abs(v), 3)
        note = (f"fade BTC {'-' if v < 0 else '+'}{abs(v):.2f}"
                if v else "BTC calme — rien à fader")
        return {"vote": round(v, 3), "confidence": conf, "note": note}
    return rc.get(f"leadlag:{symbol}", ttl, fetch,
                  fallback={"vote": 0.0, "confidence": 0.0, "note": "n/a"})


def agent(symbol="ETHUSDT"):
    """Adaptateur agent du cerveau : {vote, confidence, note}. Best-effort."""
    a = analyze(symbol)
    return {"vote": a.get("vote", 0.0), "confidence": a.get("confidence", 0.0),
            "note": a.get("note", "n/a")}


def build_report(a):
    return ("=== AGENT LEAD-LAG (contrarian BTC->alts, §52) ===\n"
            f"Vote {a.get('vote', 0):+} · conf {a.get('confidence', 0)} | {a.get('note', '')}\n"
            "Déterministe, LECTURE SEULE. Aucun ordre, aucun NN. VERDICT: SAFE")


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "ETHUSDT"
    print(build_report(analyze(sym)))


if __name__ == "__main__":
    main()
