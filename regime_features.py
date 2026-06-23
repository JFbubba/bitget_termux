"""
regime_features.py — primitives de régime & microstructure issues de l'intake Drive
(package/PDF). Pur, testable, SAFE (aucune I/O, aucun ordre).

Extraites de 3 papiers analysés (package/PDF) :
  • up_fraction      — « drift-regime factor » (arXiv 2511.12490) : fraction de
    périodes positives sur une fenêtre = état de régime de dérive (gating
    d'activation d'un agent, pas seulement pondération).
  • slope_to_prob    — « Forecast-to-Fill » (arXiv 2511.08571) : pente lissée
    standardisée -> probabilité haussière bornée [0,1] (sortie normalisée pour
    l'ensemble pondéré).
  • orderflow_entropy — « Hidden Order in Trades » (arXiv 2512.15720) : entropie
    de la matrice de transition d'order-flow ; BASSE entropie -> gros mouvement
    imminent, SANS information de direction (agent de MAGNITUDE/gating).

Ces briques sont volontairement PURES : la construction des états/séries depuis
les données live (Bitget) se branchera ensuite, mais le cœur mathématique est ici
et testé. On ne déploie rien à l'aveugle (cf. scepticisme des papiers sur les
performances annoncées).
"""

import collections
import math
import statistics


def up_fraction(values, window=63):
    """Fraction de variations POSITIVES sur les `window` dernières périodes. Pur.

    Régime de dérive (arXiv 2511.12490) : > 0.60 = dérive haussière établie
    (les auteurs n'activent leur signal que dans ce régime)."""
    v = [float(x) for x in values]
    if len(v) < 2:
        return 0.0
    rets = [v[i] - v[i - 1] for i in range(1, len(v))]
    w = rets[-window:] if window else rets
    if not w:
        return 0.0
    return sum(1 for r in w if r > 0) / len(w)


def slope_to_prob(values, lookback=20, clip=3.0):
    """Pente OLS standardisée -> probabilité haussière bornée [0,1]. Pur.

    p = (clip(z, -3, 3) + 3) / 6 avec z = pente/σ (arXiv 2511.08571). 0.5 = neutre."""
    v = [float(x) for x in values][-lookback:]
    n = len(v)
    if n < 3:
        return 0.5
    mx = (n - 1) / 2.0
    my = sum(v) / n
    num = sum((i - mx) * (v[i] - my) for i in range(n))
    den = sum((i - mx) ** 2 for i in range(n)) or 1e-9
    slope = num / den
    diffs = [v[i] - v[i - 1] for i in range(1, n)]
    sd = statistics.pstdev(diffs) or 1e-9
    z = max(-clip, min(clip, slope / sd))
    return (z + clip) / (2.0 * clip)


def orderflow_entropy(states, n_states=15):
    """Entropie normalisée [0,1] de la matrice de transition d'une séquence d'états
    d'order-flow (arXiv 2512.15720). Pur.

    0 = ordre parfait (transitions déterministes -> gros mouvement imminent),
    1 = aléatoire. Pondérée par la distribution stationnaire EMPIRIQUE des états
    sources. `states` : entiers dans [0, n_states-1]."""
    if len(states) < 2:
        return 1.0
    trans = collections.defaultdict(lambda: collections.defaultdict(int))
    count = collections.defaultdict(int)
    for a, b in zip(states[:-1], states[1:]):
        trans[a][b] += 1
        count[a] += 1
    total = sum(count.values()) or 1
    H = 0.0
    for i, ci in count.items():
        pi = ci / total                      # poids stationnaire empirique
        row = trans[i]
        ri = sum(row.values()) or 1
        hi = 0.0
        for cij in row.values():
            p = cij / ri
            if p > 0:
                hi -= p * math.log(p)
        H += pi * hi
    return H / math.log(n_states) if n_states > 1 else 0.0
