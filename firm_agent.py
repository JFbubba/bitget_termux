"""firm_agent.py — 19ᵉ voix OPT-IN du cerveau : la décision de la firme multi-agents
(TradingAgents, `trading_firm.py`). STRICTEMENT symétrique aux 15ᵉ/16ᵉ/17ᵉ/18ᵉ voix.

Classement : SAFE (lecture seule, AUCUN ordre). Émet un vote directionnel de même interface
que les 14 agents ({vote∈[-1,1], confidence∈[0,1], note}). Ne RELANCE PAS le pipeline en
ligne (trop lent pour le cerveau 1 min) : elle LIT la dernière `FirmDecision` cachée par le
cron de la firme (`trading_firm.latest`).

Politique :
  • DÉTERMINISTE D'ABORD : gated FIRM_AGENT_ENABLED (défaut OFF). Banc 14 = socle ; voix
    ADDITIVE à poids FIXE BORNÉ, jamais persisté (EARCP du banc gelé à 14 intact, §62).
  • FAIL-SAFE TOTAL : OFF / cache absent / périmé / erreur -> {vote:0, confidence:0} ->
    ignoré par aggregate. JAMAIS de crash ni de blocage.
  • AUCUN pouvoir sur les murs : guards() reste ABSOLU et déterministe.
  • PORTE D'EDGE : la firme LLM n'a pas de walk-forward d'entraînement (non « entraînable »
    à bas coût) -> gate FERMÉ par défaut, la voix se TAIT. Son ombre `firm_shadow` (journalisée
    par le cron de la firme) est mesurée net-de-frais par le même audit que les 14. L'ouverture
    = acte DÉLIBÉRÉ FIRM_EDGE_OVERRIDE, après le flag de revue de voice_shadow_measure —
    JAMAIS une promotion silencieuse (cf. docstring voice_shadow_measure.py).
"""
from __future__ import annotations

import os

from config_utils import cfg as _cfg

NEUTRE = {"vote": 0, "confidence": 0, "note": "n/a"}


def enabled():
    """Interrupteur maître (défaut OFF). OFF -> agent() est un no-op neutre -> cerveau
    inchangé. Armable via .env (FIRM_AGENT_ENABLED=1) OU config."""
    v = str(os.getenv("FIRM_AGENT_ENABLED", "")).strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg("FIRM_AGENT_ENABLED", False))


def _edge_override():
    """Ouverture DÉLIBÉRÉE de la porte d'edge de la firme (défaut OFF). Sans walk-forward,
    la voix reste muette tant que ce levier n'est pas armé — après revue de l'IC live
    d'ombre (voice_shadow_measure). Env prioritaire (FIRM_EDGE_OVERRIDE)."""
    v = str(os.getenv("FIRM_EDGE_OVERRIDE", "") or _cfg("FIRM_EDGE_OVERRIDE", 0)).strip().lower()
    return v in ("1", "true", "yes", "on")


def _produce_vote(symbol):
    """Lit la dernière décision cachée -> vote. LÈVE si indisponible (runtime_cache dégrade)."""
    import time

    import trading_firm as tf
    dec = tf.latest(symbol)
    if not dec:
        raise RuntimeError("firm:pas de décision cachée")
    age = time.time() - float(dec.get("ts", 0) or 0)
    if age > float(_cfg("FIRM_AGENT_MAX_AGE_S", 6 * 3600 + 1800)):   # ~6 h 30 -> périmée
        return {"vote": 0, "confidence": 0, "note": "firm:périmée"}
    # PORTE D'EDGE : sans edge walk-forward prouvé, la voix se TAIT (sauf override délibéré).
    if not _edge_override():
        return {"vote": 0, "confidence": 0, "note": "firm:sans-edge(gate)"}
    direction = max(-1.0, min(1.0, float(dec.get("direction") or 0.0)))
    conv = max(0.0, min(float(dec.get("conviction") or 0.0), float(_cfg("FIRM_AGENT_CONF_CAP", 0.5))))
    return {"vote": round(direction, 3), "confidence": round(conv, 3),
            "note": f"firm:{dec.get('rating', '?')}"}


def agent(symbol, context=None):
    """{vote, confidence, note}. FAIL-SAFE : neutre de confiance nulle si OFF / erreur
    (ignoré par l'agrégation). Vote caché par symbole (runtime_cache, TTL FIRM_AGENT_TTL_S)."""
    if not enabled():
        return {**NEUTRE, "note": "off"}
    ttl = float(_cfg("FIRM_AGENT_TTL_S", 120))
    try:
        import runtime_cache as rc
        return rc.get(f"firm_vote_{symbol.upper()}", ttl,
                      lambda: _produce_vote(symbol),
                      fallback={**NEUTRE, "note": "n/a"})
    except Exception:                                # runtime_cache indispo -> direct, fail-safe
        try:
            return _produce_vote(symbol)
        except Exception as exc:                     # noqa: BLE001 — fail-safe volontaire
            return {**NEUTRE, "note": f"err {type(exc).__name__}"}
