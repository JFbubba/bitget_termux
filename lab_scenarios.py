"""
lab_scenarios.py — scénarios DÉTERMINISTES de coûts + seeds de robustesse pour les labos.

Classement : SAFE (pur, aucun réseau, aucun ordre, aucune écriture).
WIRING-RESERVE : bibliothèque test/audit-only ASSUMÉE (consommée par tests_audit,
exclu du scan de câblage par construction) — vérifié le 22/07, pas un dormant ERR-013.

POURQUOI (décision propriétaire 21/07). Un « seed » RNG n'a pas d'humeur : il initialise
le hasard, il n'oriente pas la mesure. Ce que « optimiste / pessimiste / neutre »
recouvre réellement, ce sont deux pratiques distinctes, toutes deux installées ici :

1. des SCÉNARIOS d'hypothèses de coûts/exécution (perturbation des frais, du slippage,
   des fills — l'axe « perturbation des coûts » de la validation robuste) ;
2. la ROBUSTESSE MULTI-SEEDS pour les composantes stochastiques (NN/QML) : le MÊME
   calcul répété sur PLUSIEURS seeds figés — la stabilité par seed est la mesure,
   aucun seed n'est « meilleur » qu'un autre.

RÈGLE DE VERDICT (anti-sur-optimisme, doctrine module-builder) : un edge ne PROMEUT que
s'il survit au scénario PESSIMISTE. L'optimiste sert à borner le POTENTIEL, jamais à
valider. Base des coûts : ~6 bps/côté mesurés live (cf. exec-fees-lever) + ~2 bps de
slippage ; surchargeables via LAB_FEE_BPS_COTE / LAB_SLIP_BPS_COTE (la base bouge, les
FACTEURS de scénario restent).
"""

import os

# scénario -> (facteur frais/côté, facteur slippage/côté, facteur funding de portage)
# Famille COMPLÈTE des perturbations de coûts (validation robuste / méga-prompt §10) :
# frais (maker vs taker plein), slippage (calme -> spread stressé -> cascade), funding
# porté (position tenue). La barre de PROMOTION reste le pessimiste ; stress_crise est
# INFORMATIF (queue au-delà de l'historique : il dimensionne le pire, il ne juge pas).
FACTEURS = {
    "optimiste":    (1.0 / 3.0, 0.25, 0.0),  # tout favorable : borne le POTENTIEL, ne valide jamais
    "maker":        (1.0 / 3.0, 0.0, 1.0),   # post-only REMPLI : frais maker, zéro traversée du spread
    "neutre":       (1.0, 1.0, 1.0),         # coûts MESURÉS live : la base de tout verdict chiffré
    "pessimiste":   (1.5, 3.0, 2.0),         # taker plein + spread stressé : le verdict de PROMOTION
    "stress_crise": (1.5, 10.0, 4.0),        # cascade/gap : spread ×10, funding extrême — INFORMATIF
}

SCENARIOS = tuple(FACTEURS)

# composantes stochastiques (NN/QML) : mesurer sur CHAQUE seed, juger la STABILITÉ
SEEDS_ROBUSTESSE = (1337, 2718, 31415)


def cout_aller_retour_bps(scenario="neutre"):
    """Coût TOTAL d'un aller-retour en bps (2 côtés : frais + slippage) pour le
    scénario. Pur (la base vient de l'env ou du défaut mesuré)."""
    ffee, fslip, _ = FACTEURS[scenario]
    fee = float(os.getenv("LAB_FEE_BPS_COTE", "6")) * ffee
    slip = float(os.getenv("LAB_SLIP_BPS_COTE", "2")) * fslip
    return 2.0 * (fee + slip)


def funding_bps_jour(scenario="neutre"):
    """Coût de PORTAGE en bps par jour de position tenue (funding perp ; baseline
    0,01 %/8h ≈ 3 bps/j), modulé par le scénario. Pur."""
    _, _, ffund = FACTEURS[scenario]
    return float(os.getenv("LAB_FUNDING_BPS_JOUR", "3")) * ffund


def net_bps(brut_bps, scenario="neutre", allers_retours=1.0, jours_portage=0.0):
    """Rendement NET en bps après les coûts du scénario (aller-retours + funding
    porté sur `jours_portage` jours). Pur."""
    return (float(brut_bps) - float(allers_retours) * cout_aller_retour_bps(scenario)
            - float(jours_portage) * funding_bps_jour(scenario))


def verdict_promotion(brut_bps, allers_retours=1.0, jours_portage=0.0):
    """Verdict multi-scénarios d'un edge BRUT (bps) : nets par scénario + décision.
    Ne PROMEUT que si le net PESSIMISTE est positif — l'optimiste ne valide jamais,
    le stress_crise informe (queue) sans juger."""
    nets = {sc: round(net_bps(brut_bps, sc, allers_retours, jours_portage), 3)
            for sc in SCENARIOS}
    return {
        "nets_bps": nets,
        "promeut": nets["pessimiste"] > 0.0,
        "stress_info": nets["stress_crise"],
        "regle": ("PROMOTION seulement si net PESSIMISTE > 0 ; l'optimiste borne le "
                  "potentiel, ne valide pas ; stress_crise = information de queue"),
    }
