"""Agent quantique — 18ᵉ voix OPT-IN du cerveau mixture-of-experts.

Classement : SAFE (lecture seule, AUCUN ordre). Émet un vote directionnel de même
interface que les 14 agents déterministes ({vote∈[-1,1], confidence∈[0,1], note}),
produit par un CIRCUIT QUANTIQUE variationnel (6 qubits, AmplitudeEmbedding +
StronglyEntanglingLayers) entraîné au laboratoire (`qml_prototype/train_voice.py`)
sur les MÊMES features que la 16ᵉ voix (votes du banc + contextuelles causales).

Politique — STRICTEMENT symétrique aux 15ᵉ/16ᵉ/17ᵉ voix :
  • DÉTERMINISTE D'ABORD : gated QML_AGENT_ENABLED (défaut OFF). Le banc 14 reste
    le socle ; cette voix est ADDITIVE, à poids FIXE BORNÉ (jamais persisté ->
    l'EARCP du banc gelé à 14 reste intact, §62). Absente du dict de votes tant
    qu'OFF.
  • FAIL-SAFE TOTAL : OFF, poids absents, erreur -> {vote:0, confidence:0} ->
    ignoré par aggregate. JAMAIS de crash, jamais de blocage.
  • AUCUN pouvoir sur les murs argent : guards() reste ABSOLU et déterministe.
  • ERR-004 RESPECTÉ : l'inférence live est du NUMPY PUR (`qml_quantum_sim.py`,
    simulation exacte du vecteur d'état, parité PennyLane vérifiée) — AUCUNE
    dépendance nouvelle dans le Python système. PennyLane/torch ne servent qu'à
    l'ENTRAÎNEMENT, confiné au venv du labo ; les poids transitent en JSON.

Porte d'edge (même philosophie que la 16ᵉ, §71) : tant que le walk-forward du
dernier entraînement n'est pas POSITIF selon le critère QML_EDGE_GATE (prudent =
wf_edge − se | brut = wf_edge seul), la voix se TAIT — mais journalise son ombre
`qml_shadow` (§89) pour accumuler un IC live jugé par le même audit que les 14.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from config_utils import cfg as _cfg

NEUTRE = {"vote": 0, "confidence": 0, "note": "n/a"}
WEIGHTS_PATH = Path(__file__).resolve().parent / "qml_voice_weights.json"
_CACHE = {"mtime": None, "weights": None, "meta": None}


def enabled():
    """Interrupteur maître (défaut OFF). Tant qu'il est False, agent() est un no-op
    neutre de confiance nulle -> le cerveau se comporte EXACTEMENT comme avant.
    Armable via .env (QML_AGENT_ENABLED=1) OU config."""
    v = os.getenv("QML_AGENT_ENABLED", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg("QML_AGENT_ENABLED", False))


def _gate_mode():
    """Critère de la PORTE D'EDGE : 'prudent' (wf_edge − erreur-type, §71) | 'brut'
    (moyenne walk-forward seule) | 'deflated' (wf_edge − déflation multi-essais,
    Deflated Sharpe §recherche-17/07). Env prioritaire (QML_EDGE_GATE)."""
    v = (os.getenv("QML_EDGE_GATE", "") or "").strip().lower()
    if v in ("prudent", "brut", "deflated"):
        return v
    v = str(_cfg("QML_EDGE_GATE", "prudent")).strip().lower()
    return v if v in ("prudent", "brut", "deflated") else "prudent"


def _load_weights():
    """Charge (et met en cache par mtime) les poids JSON exportés par le labo.
    Renvoie (weights, meta) ou (None, None) — fail-safe, jamais d'exception."""
    try:
        st = WEIGHTS_PATH.stat()
        if _CACHE["mtime"] != st.st_mtime:
            data = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
            _CACHE.update(mtime=st.st_mtime, weights=data.get("weights"),
                          meta=data.get("meta") or {})
        return _CACHE["weights"], _CACHE["meta"]
    except Exception:
        return None, None


def predict(symbol="BTCUSDT", votes=None):
    """Prédiction quantique. Renvoie {p_up, vote, confidence, val_edge,
    val_edge_brut, note} OU None si indisponible (fail-safe total).

    Le vecteur de features est ASSEMBLÉ par neural_net.assemble_live (PUR, sans
    torch) — mêmes entrées que la 16ᵉ voix, donc comparaison propre des deux
    fusions. Un feature_hash désaligné (banc modifié depuis l'entraînement)
    REFUSE le modèle plutôt que de prédire n'importe quoi."""
    weights, meta = _load_weights()
    if not weights:
        return None
    try:
        import neural_net
        import qml_quantum_sim

        if meta.get("feature_hash") != neural_net.feature_hash():
            return None
        x = neural_net.assemble_live(symbol, votes)
        z = qml_quantum_sim.predict_score(x, weights,
                                          n_qubits=int(meta.get("n_qubits") or 6))
        z = max(-1.0, min(1.0, float(z)))
        p = (1.0 + z) / 2.0
        return {"p_up": round(p, 4), "vote": round(z, 4),
                "confidence": round(abs(z), 4),
                "val_edge": neural_net.edge_bound(meta, prudent=True),
                "val_edge_brut": neural_net.edge_bound(meta, prudent=False),
                "val_edge_deflated": neural_net.edge_deflated(meta),
                "note": f"qml v{meta.get('version', '?')}"}
    except Exception:
        return None


def _journalise_ombre(symbol, pred):
    """§89 — OMBRE de la voix muette : même mécanique que nn_shadow. Tuée par la
    porte d'edge, la prédiction part quand même au journal overlay sous le nom
    `qml_shadow` (jugée par le même audit IC que les 14, sans toucher le
    consensus). Sa réactivation s'appuiera sur DEUX preuves (wf_edge ET IC live).
    Best-effort."""
    try:
        import time

        import runtime_cache as rc

        def _px():
            import technicals as tk
            c = tk.fetch_candles(symbol, "1m", 1)
            return float(c[-1]["close"]) if c else None
        px = rc.get(f"qmlshadow_px:{symbol}", 45, _px)
        v = float(pred.get("vote") or 0.0)
        if not px or abs(v) < 1e-9:
            return
        import journal_append as ja
        ja.append_jsonl(Path(__file__).resolve().parent / ".overlay_votes.jsonl",
                        {"ts": int(time.time()), "symbol": symbol, "price": px,
                         "votes": {"qml_shadow": round(v, 3)}})
    except Exception:
        pass


def _produce_vote(symbol, context=None):
    """Une inférence -> vote FRAIS. LÈVE si le modèle est indisponible (poids
    absents/désalignés) pour que runtime_cache dégrade proprement."""
    votes = (context or {}).get("votes")             # votes déjà calculés (pas de recalcul)
    pred = predict(symbol, votes=votes)
    if not pred:
        raise RuntimeError("qml:modèle indisponible")
    # PORTE D'EDGE : tant que l'entraînement n'a pas démontré un edge hors-
    # échantillon POSITIF selon le critère configuré, la 18ᵉ voix se TAIT.
    mode = _gate_mode()
    edge = {"brut": pred.get("val_edge_brut"),
            "deflated": pred.get("val_edge_deflated")}.get(mode, pred.get("val_edge"))
    if edge is not None and float(edge) <= 0.0:
        _journalise_ombre(symbol, pred)              # §89 : muette mais MESURÉE
        return {"vote": 0, "confidence": 0,
                "note": f"qml:sans-edge({float(edge):+.3f},{mode})"}
    # confiance BORNÉE : une voix opt-in ne doit pas dominer le banc déterministe.
    conf = max(0.0, min(float(pred["confidence"]), float(_cfg("QML_AGENT_CONF_CAP", 0.5))))
    return {"vote": round(float(pred["vote"]), 3), "confidence": round(conf, 3),
            "note": pred.get("note", "qml")}


def agent(symbol, context=None):
    """{vote, confidence, note}. FAIL-SAFE : neutre de confiance nulle si OFF /
    erreur (donc ignoré par l'agrégation). Vote frais caché par symbole
    (runtime_cache, TTL QML_AGENT_TTL_S, défaut 60 s) — l'inférence numpy est
    en microsecondes, le cache évite juste de rejournaliser l'ombre en rafale."""
    if not enabled():
        return {**NEUTRE, "note": "off"}
    ttl = float(_cfg("QML_AGENT_TTL_S", 60))
    try:
        import runtime_cache as rc
        return rc.get(f"qml_vote_{symbol.upper()}", ttl,
                      lambda: _produce_vote(symbol, context),
                      fallback={**NEUTRE, "note": "n/a"})
    except Exception:                                # runtime_cache indispo -> direct, fail-safe
        try:
            return _produce_vote(symbol, context)
        except Exception as exc:                     # noqa: BLE001 — fail-safe volontaire
            return {**NEUTRE, "note": f"err {type(exc).__name__}"}
