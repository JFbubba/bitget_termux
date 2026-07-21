"""
lab_scenarios.py — scénarios DÉTERMINISTES de coûts + seeds de robustesse pour les labos.

Classement : SAFE (pur, aucun réseau, aucun ordre, aucune écriture).

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

# scénario -> (facteur sur les frais/côté, facteur sur le slippage/côté)
FACTEURS = {
    "neutre":     (1.0, 1.0),      # coûts MESURÉS live : la base de tout verdict chiffré
    "pessimiste": (1.5, 3.0),      # taker plein + spread stressé : le verdict de PROMOTION
    "optimiste":  (1.0 / 3.0, 0.25),  # maker rempli + marché calme : borne le potentiel
}

SCENARIOS = tuple(FACTEURS)

# composantes stochastiques (NN/QML) : mesurer sur CHAQUE seed, juger la STABILITÉ
SEEDS_ROBUSTESSE = (1337, 2718, 31415)


def cout_aller_retour_bps(scenario="neutre"):
    """Coût TOTAL d'un aller-retour en bps (2 côtés : frais + slippage) pour le
    scénario. Pur (la base vient de l'env ou du défaut mesuré)."""
    ffee, fslip = FACTEURS[scenario]
    fee = float(os.getenv("LAB_FEE_BPS_COTE", "6")) * ffee
    slip = float(os.getenv("LAB_SLIP_BPS_COTE", "2")) * fslip
    return 2.0 * (fee + slip)


def net_bps(brut_bps, scenario="neutre", allers_retours=1.0):
    """Rendement NET en bps après les coûts du scénario. Pur."""
    return float(brut_bps) - float(allers_retours) * cout_aller_retour_bps(scenario)


def verdict_promotion(brut_bps, allers_retours=1.0):
    """Verdict multi-scénarios d'un edge BRUT (bps) : nets par scénario + décision.
    Ne PROMEUT que si le net PESSIMISTE est positif — l'optimiste ne valide jamais."""
    nets = {sc: round(net_bps(brut_bps, sc, allers_retours), 3) for sc in SCENARIOS}
    return {
        "nets_bps": nets,
        "promeut": nets["pessimiste"] > 0.0,
        "regle": "PROMOTION seulement si net PESSIMISTE > 0 ; l'optimiste borne le potentiel, ne valide pas",
    }
