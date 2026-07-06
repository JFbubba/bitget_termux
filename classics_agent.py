"""Agent « classiques » — 17ᵉ voix OPT-IN du cerveau mixture-of-experts (§72).

Classement : SAFE (lecture seule, AUCUN ordre). Émet un vote directionnel de même
interface que les 14 agents déterministes ({vote∈[-1,1], confidence∈[0,1], note}),
obtenu en fusionnant AU DERNIER PAS les stratégies classiques paramétrées du
laboratoire (`strategy_lab`, §72) que le banc gelé ne vote PAS en live :
MACD, Bollinger, Donchian, VWAP, grille de range, pairs z-score.
(L'EMA-cross et le RSI, eux, votent déjà via agent_technicals — pas de doublon.)

Politique — STRICTEMENT symétrique aux 15ᵉ (LLM) et 16ᵉ (NN) voix :
  • DÉTERMINISTE et gated CLASSICS_AGENT_ENABLED (défaut OFF). Voix ADDITIVE, à
    poids FIXE BORNÉ (jamais persisté -> l'EARCP du banc gelé à 14 reste intact §62).
    Absente du dict de votes tant qu'OFF.
  • FAIL-SAFE TOTAL : OFF, données indisponibles, erreur -> {vote:0, confidence:0}
    -> ignoré par aggregate. JAMAIS de crash, jamais de blocage.
  • AUCUN pouvoir sur les murs argent : guards() (caps 50/250, levier ×5, stop
    journalier, kill-switch, porte d'edge) reste ABSOLU et déterministe.

La MESURE de ces stratégies (Sharpe, edge, PBO, promotion) reste au laboratoire
(cron dimanche) : la voix n'expose que leur consensus courant, borné.
"""
from __future__ import annotations

import os

from config_utils import cfg as _cfg

NEUTRE = {"vote": 0, "confidence": 0, "note": "n/a"}


def enabled():
    """Interrupteur maître (défaut OFF). Tant qu'il est False, agent() est un no-op
    neutre de confiance nulle -> le cerveau se comporte EXACTEMENT comme aujourd'hui.
    Armable via env (CLASSICS_AGENT_ENABLED=1) OU config."""
    v = os.getenv("CLASSICS_AGENT_ENABLED", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg("CLASSICS_AGENT_ENABLED", False))


def _signals(symbol):
    """Signaux {-1,0,+1} AU DERNIER PAS des classiques non couverts par le banc.
    Chaque composant est fail-safe (0 si son calcul échoue) ; LÈVE seulement si les
    bougies elles-mêmes sont indisponibles (runtime_cache dégrade alors en neutre)."""
    import strategy_lab as L
    import technicals as tk
    tf = str(_cfg("CLASSICS_AGENT_TF", "15m"))
    candles = tk.fetch_candles(symbol, tf, 240)
    if not candles or len(candles) < 80:
        raise RuntimeError("classics:données insuffisantes")
    sym = str(symbol).upper()
    ref = "ETHUSDT" if sym == "BTCUSDT" else "BTCUSDT"
    out = {}
    for name in ("macd_12_26_9", "bollinger_20", "donchian_20", "vwap_24",
                 "grid_60_8", f"pairs_{ref}_20", f"fundfade_{sym}_60"):
        try:
            sig = L.build_named(name, candles)
            out[name.split("_")[0]] = int(sig[-1]) if sig else 0
        except Exception:
            out[name.split("_")[0]] = 0
    return out


def _produce_vote(symbol, context=None):
    """Fusion des signaux classiques -> un vote borné. La moyenne de signaux ∈{-1,0,1}
    porte déjà l'ACCORD entre stratégies : conviction haute seulement quand elles
    convergent (trend ET reversion d'accord = signal rare et fort)."""
    s = _signals(symbol)
    vals = list(s.values())
    vote = (sum(vals) / len(vals)) if vals else 0.0
    cap = max(0.0, min(1.0, float(_cfg("CLASSICS_AGENT_CONF_CAP", 0.5))))
    conf = min(abs(vote), cap)
    note = "classics " + " ".join(
        f"{k}{'+' if v > 0 else '-' if v < 0 else '·'}" for k, v in s.items())
    return {"vote": round(vote, 3), "confidence": round(conf, 3), "note": note,
            "evidence": [f"{k}={v:+d}" for k, v in s.items()]}


def agent(symbol, context=None):
    """{vote, confidence, note}. FAIL-SAFE : neutre de confiance nulle si OFF / erreur
    (donc ignoré par l'agrégation). Vote CACHÉ par symbole (TTL CLASSICS_AGENT_TTL_S,
    défaut 60 s) : un fetch de bougies par symbole et par minute au plus."""
    if not enabled():
        return {**NEUTRE, "note": "off"}
    ttl = float(_cfg("CLASSICS_AGENT_TTL_S", 60))
    try:
        import runtime_cache as rc
        return rc.get(f"classics_vote_{str(symbol).upper()}", ttl,
                      lambda: _produce_vote(symbol, context),
                      fallback={**NEUTRE, "note": "n/a"})
    except Exception:                                # runtime_cache indispo -> direct, fail-safe
        try:
            return _produce_vote(symbol, context)
        except Exception as exc:                     # noqa: BLE001 — fail-safe volontaire
            return {**NEUTRE, "note": f"err {type(exc).__name__}"}
