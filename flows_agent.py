"""flows_agent.py — agent FLOWS du cerveau : flux de capitaux marché-large (LECTURE SEULE).

Classement : SAFE. Réseau public en lecture seule (via stablecoin_flow), aucun ordre,
aucun secret.

Pourquoi : l'offre totale de stablecoins est le « dry powder » du marché crypto —
en expansion, des liquidités entrent (historiquement haussier) ; en contraction,
elles sortent (repli). Cette famille de données n'a JAMAIS été couverte par la
recherche d'alpha du dépôt (RESEARCH_NOTES §36-37 n'a balayé que des dérivés de
bougies). Comme macro/sentiment, l'agent IGNORE le symbole (signal marché-large) :
son edge éventuel est TEMPOREL (market-timing, §39), mesuré par le chemin 3 de la
validation (`evaluate_market_timing`) — jamais transversal.

Contrat d'échec : fail-safe -> vote nul/confiance nulle (« l'agent muet ne pèse
rien » dans le consensus), jamais d'exception propagée au cerveau.
"""

import math

# ---------- cœur pur (testable) ----------

# Échelles alignées sur stablecoin_flow.signal_flux : ±0.5 % sur 7 j et ±2 % sur
# 30 j sont des mouvements notables de l'offre (donnée quotidienne, lente).
ECHELLE_7J = 0.5
ECHELLE_30J = 2.0
CONF_MAX = 0.5      # humilité maximale : agent marché-large jamais validé à l'étalon


def signal(pct7, pct30):
    """Cœur PUR du vote : momentum de l'offre de stablecoins -> vote [-1, 1].

    vote = 0.6·tanh(pct7/0.5) + 0.4·tanh(pct30/2.0) ; si une seule variation est
    disponible, son poids est renormalisé à 1. confidence = min(0.5, |vote|),
    PLAFONNÉE à 0.5. PUR, déterministe, aucune I/O."""
    if pct7 is None and pct30 is None:
        return {"vote": 0.0, "confidence": 0.0, "note": "données insuffisantes"}
    termes = []
    if pct7 is not None:
        termes.append((0.6, math.tanh(float(pct7) / ECHELLE_7J)))
    if pct30 is not None:
        termes.append((0.4, math.tanh(float(pct30) / ECHELLE_30J)))
    poids_total = sum(p for p, _ in termes)
    vote = sum(p * v for p, v in termes) / poids_total if poids_total > 0 else 0.0
    vote = max(-1.0, min(1.0, vote))
    conf = min(CONF_MAX, abs(vote))
    def _fmt(x):
        return f"{x:+.2f}%" if x is not None else "n/a"
    return {"vote": round(vote, 3), "confidence": round(conf, 3),
            "note": f"stables 7j {_fmt(pct7)} 30j {_fmt(pct30)}"}


# ---------- adaptateurs (best-effort) ----------

def analyze(ttl=3600):
    """Analyse live cachée, best-effort : fallback neutre si la source est
    injoignable (jamais d'exception). Marché-large -> une seule clé de cache."""
    def _fetch():
        import stablecoin_flow as sf
        snap = sf.snapshot() or {}
        return signal(snap.get("pct_7j"), snap.get("pct_30j"))
    try:
        import runtime_cache as rc
        return rc.get("flows", ttl, _fetch,
                      fallback={"vote": 0.0, "confidence": 0.0, "note": "n/a"})
    except Exception:
        return {"vote": 0.0, "confidence": 0.0, "note": "n/a"}


def agent(symbol="BTCUSDT"):
    """Adaptateur essaim : {vote, confidence, note}. Le paramètre symbol est accepté
    mais IGNORÉ (signal marché-large, uniformité du contrat des agents)."""
    a = analyze()
    return {"vote": a.get("vote", 0.0), "confidence": a.get("confidence", 0.0),
            "note": a.get("note", "n/a")}


# ---------- rapport ----------

def build_report():
    a = analyze()
    return ("=== AGENT FLOWS (flux de capitaux stablecoins) ===\n"
            f"Vote : {a.get('vote', 0.0):+.3f} | confiance : {a.get('confidence', 0.0):.3f}\n"
            f"Détail : {a.get('note', 'n/a')}\n"
            "Signal de RÉGIME marché-large (edge temporel §39), jamais une prédiction par symbole.\n"
            "Lecture seule. Aucun ordre. VERDICT: SAFE")


def main():
    print(build_report())


if __name__ == "__main__":
    main()
