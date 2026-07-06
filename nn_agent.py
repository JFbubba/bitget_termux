"""Agent réseau neuronal — 16ᵉ voix OPT-IN du cerveau mixture-of-experts.

Classement : SAFE (lecture seule, AUCUN ordre). Émet un vote directionnel de même
interface que les 14 agents déterministes ({vote∈[-1,1], confidence∈[0,1], note}),
produit par le méta-modèle de FUSION `neural_net.py` (MLP PyTorch entraîné sur les
votes historiques du banc).

Politique (contrainte « aucun réseau de neurones » LEVÉE le 06/07/2026, §65) —
STRICTEMENT symétrique à l'agent LLM (llm_agent.py, 15ᵉ voix) :
  • DÉTERMINISTE D'ABORD : gated NN_AGENT_ENABLED (défaut OFF). Le banc 14 reste le
    socle ; cette voix est ADDITIVE, à poids FIXE BORNÉ (jamais persisté -> l'EARCP
    du banc gelé à 14 reste intact, §62). Absente du dict de votes tant qu'OFF.
  • FAIL-SAFE TOTAL : OFF, torch absent, poids absents, erreur -> {vote:0,
    confidence:0} -> ignoré par aggregate. JAMAIS de crash, jamais de blocage.
  • AUCUN pouvoir sur les murs argent : guards() (caps 50/250, levier ×5, stop
    journalier, kill-switch, porte d'edge) reste ABSOLU et déterministe.

Le réseau LIT les votes déjà calculés par le cerveau (passés via `context`) — il ne
recalcule rien et ne récursione pas. Il les FUSIONNE non-linéairement en P(hausse).
"""
from __future__ import annotations

import os

from config_utils import cfg as _cfg

NEUTRE = {"vote": 0, "confidence": 0, "note": "n/a"}


def enabled():
    """Interrupteur maître (défaut OFF). Tant qu'il est False, agent() est un no-op
    neutre de confiance nulle -> le cerveau se comporte EXACTEMENT comme aujourd'hui.
    Armable via .env (NN_AGENT_ENABLED=1) OU config."""
    v = os.getenv("NN_AGENT_ENABLED", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg("NN_AGENT_ENABLED", False))


def _produce_vote(symbol, context=None):
    """Une inférence -> vote FRAIS. LÈVE si le modèle est indisponible (torch/poids
    absents) pour que runtime_cache dégrade proprement (stale/fallback neutre)."""
    import neural_net
    votes = (context or {}).get("votes")             # votes déjà calculés (pas de recalcul)
    pred = neural_net.predict(symbol, votes=votes)
    if not pred:
        raise RuntimeError("nn:modèle indisponible")
    # confiance BORNÉE : une voix opt-in ne doit pas dominer le banc déterministe.
    conf = max(0.0, min(float(pred["confidence"]), float(_cfg("NN_AGENT_CONF_CAP", 0.5))))
    return {"vote": round(float(pred["vote"]), 3), "confidence": round(conf, 3),
            "note": pred.get("note", "nn")}


def agent(symbol, context=None):
    """{vote, confidence, note}. FAIL-SAFE : neutre de confiance nulle si OFF / erreur
    (donc ignoré par l'agrégation).

    Le vote frais est CACHÉ par symbole (runtime_cache, TTL NN_AGENT_TTL_S, défaut
    60 s). L'inférence CPU est rapide, mais le cache évite de rappeler le modèle à
    chaque symbole si `context` (les votes) n'a pas changé dans l'intervalle."""
    if not enabled():
        return {**NEUTRE, "note": "off"}
    ttl = float(_cfg("NN_AGENT_TTL_S", 60))
    try:
        import runtime_cache as rc
        return rc.get(f"nn_vote_{symbol.upper()}", ttl,
                      lambda: _produce_vote(symbol, context),
                      fallback={**NEUTRE, "note": "n/a"})
    except Exception:                                # runtime_cache indispo -> direct, fail-safe
        try:
            return _produce_vote(symbol, context)
        except Exception as exc:                     # noqa: BLE001 — fail-safe volontaire
            return {**NEUTRE, "note": f"err {type(exc).__name__}"}
