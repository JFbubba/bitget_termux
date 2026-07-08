"""Entraînement de la 18ᵉ voix QUANTIQUE — à exécuter dans le venv du labo.

Usage (depuis la racine du dépôt) :
    ./qml_prototype/.venv/bin/python qml_prototype/train_voice.py            # entraîne
    ./qml_prototype/.venv/bin/python qml_prototype/train_voice.py --parity  # parité sim

Rôle : entraîner le circuit variationnel (6 qubits, AmplitudeEmbedding +
StronglyEntanglingLayers) sur les MÊMES données que la 16ᵉ voix (dataset de
`neural_net._dataset` : votes du banc + contextuelles causales, étiquettes
hygiéniques §71/§73), avec la MÊME validation walk-forward (6 plis temporels,
purge anti-fuite, edge = acc − base par pli, borne prudente = moyenne − se).

Sortie : `qml_voice_weights.json` à la racine du dépôt — poids (4×6×3) + méta
(wf_edge, wf_edge_se, feature_hash…). L'inférence LIVE ne passe PAS par ici :
elle est faite en numpy pur par `qml_quantum_sim.py` (ERR-004 — PennyLane reste
confiné au venv du labo). `--parity` prouve l'équivalence des deux chemins.
"""

import os

# Cap de threads par défaut (VPS 2 cœurs partagé avec le bot LIVE — ERR-004/C4).
os.environ.setdefault("OMP_NUM_THREADS", "2")

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pennylane as qml
import torch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import neural_net as nnmod            # noqa: E402 — features/dataset PARTAGÉS 16ᵉ voix
import qml_quantum_sim as qsim        # noqa: E402 — simulateur numpy de l'inférence

# Hyperparamètres du circuit (doivent rester alignés avec qml_quantum_sim).
N_QUBITS = 6
N_LAYERS = 4
SEED = 42
EPOCHS = int(os.getenv("QML_TRAIN_EPOCHS", "60"))
LR = 0.1
MAX_N = int(os.getenv("QML_TRAIN_MAX_N", "6000"))
WEIGHTS_PATH = REPO / "qml_voice_weights.json"

dev = qml.device("default.qubit", wires=N_QUBITS)


@qml.qnode(dev, interface="torch", diff_method="backprop")
def circuit(inputs, weights):
    """Même circuit que l'inférence numpy (voir qml_quantum_sim, parité vérifiée)."""
    qml.AmplitudeEmbedding(inputs, wires=range(N_QUBITS), normalize=True, pad_with=0.0)
    qml.StronglyEntanglingLayers(weights, wires=range(N_QUBITS))
    return qml.expval(qml.PauliZ(0))


def _fit_quantum(X_tr, y_tr, seed=SEED, epochs=EPOCHS, lr=LR, init=None):
    """Entraîne le circuit en BCE sur p = (1+<Z0>)/2. Renvoie les poids (numpy)."""
    torch.manual_seed(seed)
    if init is None:
        weights = torch.nn.Parameter(
            torch.rand(N_LAYERS, N_QUBITS, 3, dtype=torch.float64) * 2 * np.pi)
    else:
        weights = torch.nn.Parameter(torch.tensor(init, dtype=torch.float64))
    opt = torch.optim.Adam([weights], lr=lr)
    x_t = torch.tensor(np.asarray(X_tr), dtype=torch.float64)
    y_t = torch.tensor(np.asarray(y_tr), dtype=torch.float64)
    for _ in range(epochs):
        opt.zero_grad()
        z = circuit(x_t, weights)
        p = torch.clamp((1.0 + z) / 2.0, 1e-6, 1.0 - 1e-6)
        loss = torch.nn.functional.binary_cross_entropy(p, y_t)
        loss.backward()
        opt.step()
    return weights.detach().numpy()


def _acc_base(z, y):
    """Précision directionnelle vs taux de base majoritaire (même déf. que la 16ᵉ)."""
    pred_up = (np.asarray(z) > 0.0).astype(float)
    y = np.asarray(y, dtype=float)
    acc = float((pred_up == y).mean())
    up = float(y.mean())
    return acc, max(up, 1.0 - up)


def walk_forward_quantum(X, y, ts, folds=nnmod.WF_FOLDS):
    """Réplique neural_net.walk_forward (plis temporels, purge) pour le circuit."""
    n = len(X)
    block = n // (folds + 1)
    if block < 50:
        return {"folds": [], "wf_edge": None, "note": f"trop peu d'exemples ({n})"}
    out = []
    for f in range(folds):
        lo = (f + 1) * block
        hi = (f + 2) * block if f < folds - 1 else n
        tr_idx = nnmod._purged_train_idx(ts, lo)
        if len(tr_idx) < 100 or hi - lo < 50:
            continue
        w = _fit_quantum([X[i] for i in tr_idx], [y[i] for i in tr_idx], seed=SEED + f)
        with torch.no_grad():
            z = circuit(torch.tensor(np.asarray(X[lo:hi]), dtype=torch.float64),
                        torch.tensor(w, dtype=torch.float64)).numpy()
        acc, base = _acc_base(z, y[lo:hi])
        out.append({"fold": f, "n_train": len(tr_idx), "n_val": hi - lo,
                    "acc": round(acc, 4), "base": round(base, 4),
                    "edge": round(acc - base, 4)})
        print(f"  pli {f}: acc {acc:.3f} vs base {base:.3f} (edge {acc - base:+.3f} "
              f"· train {len(tr_idx)})")
    if not out:
        return {"folds": [], "wf_edge": None, "note": "plis insuffisants"}
    edges = [o["edge"] for o in out]
    mean_edge = sum(edges) / len(edges)
    var = sum((e - mean_edge) ** 2 for e in edges) / len(edges)
    se = (var ** 0.5) / (len(edges) ** 0.5)
    return {"folds": out, "wf_edge": round(mean_edge, 4), "wf_edge_se": round(se, 4),
            "wf_acc": round(sum(o["acc"] for o in out) / len(out), 4),
            "wf_base": round(sum(o["base"] for o in out) / len(out), 4)}


def parity_check(trials=20, tol=1e-9):
    """PennyLane (venv) vs qml_quantum_sim (numpy pur) : mêmes poids, mêmes entrées."""
    rng = np.random.default_rng(SEED)
    worst = 0.0
    for _ in range(trials):
        x = rng.normal(size=nnmod.IN_DIM)
        w = rng.uniform(0, 2 * np.pi, size=(N_LAYERS, N_QUBITS, 3))
        z_pl = float(circuit(torch.tensor(x, dtype=torch.float64),
                             torch.tensor(w, dtype=torch.float64)))
        z_np = qsim.predict_score(x, w, n_qubits=N_QUBITS)
        worst = max(worst, abs(z_pl - z_np))
    ok = worst < tol
    print(f"Parité PennyLane <-> numpy : écart max {worst:.2e} sur {trials} tirages "
          f"-> {'OK' if ok else 'ÉCHEC'} (tolérance {tol:.0e})")
    return ok


def _notify_gate_transition(old_meta, new_meta):
    """Alerte Telegram (best-effort) quand la PORTE D'EDGE de la 18ᵉ voix change
    d'état après réentraînement — même mécanique que la 16ᵉ voix (§71)."""
    try:
        import qml_agent
        mode = qml_agent._gate_mode()
        prudent = mode != "brut"
        avant = nnmod.edge_bound(old_meta or {}, prudent=prudent)
        apres = nnmod.edge_bound(new_meta or {}, prudent=prudent)
        if avant is None or apres is None:
            return
        ouvre = avant <= 0.0 < apres
        ferme = apres <= 0.0 < avant
        if not (ouvre or ferme):
            return
        import telegram_notifier as tn
        if ouvre:
            tn.send_telegram(f"🔮 18ᵉ voix (QML) : edge {mode} PASSÉ POSITIF ({apres:+.3f}) — "
                             "si QML_AGENT_ENABLED=1 elle PARLE désormais dans le consensus "
                             "(confiance plafonnée, murs argent intacts).")
        else:
            tn.send_telegram(f"🔮 18ᵉ voix (QML) : edge {mode} repassé ≤ 0 ({apres:+.3f}) — "
                             "elle se TAIT de nouveau (porte d'edge).")
    except Exception:
        pass


def train():
    old_meta = None
    try:
        old_meta = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8")).get("meta")
    except Exception:
        pass
    X, y, ts = nnmod._dataset(with_ts=True)
    n0 = len(X)
    if n0 > MAX_N:
        # Cap ASSUMÉ et journalisé (pas de troncature silencieuse) : on garde la
        # fin de l'historique (le plus récent), l'ordre temporel est déjà global.
        X, y, ts = X[-MAX_N:], y[-MAX_N:], ts[-MAX_N:]
        print(f"Dataset {n0} exemples -> cap aux {MAX_N} plus récents (QML_TRAIN_MAX_N).")
    print(f"Dataset : {len(X)} exemples · {nnmod.IN_DIM} features -> {N_QUBITS} qubits "
          f"× {N_LAYERS} couches · walk-forward {nnmod.WF_FOLDS} plis")
    t0 = time.time()
    wf = walk_forward_quantum(X, y, ts)
    print(f"Walk-forward — edge {wf.get('wf_edge')} (se {wf.get('wf_edge_se')}) "
          f"· acc {wf.get('wf_acc')} vs base {wf.get('wf_base')}")
    w_final = _fit_quantum(X, y, seed=SEED)
    # Parité entraînement<->inférence sur les poids FINAUX (échantillon).
    with torch.no_grad():
        z_pl = float(circuit(torch.tensor(np.asarray(X[0]), dtype=torch.float64),
                             torch.tensor(w_final, dtype=torch.float64)))
    z_np = qsim.predict_score(X[0], w_final, n_qubits=N_QUBITS)
    assert abs(z_pl - z_np) < 1e-9, f"parité rompue sur poids finaux ({z_pl} vs {z_np})"
    meta = {"version": 1, "algo": f"qml-sel-{N_QUBITS}q{N_LAYERS}l",
            "n_qubits": N_QUBITS, "n_layers": N_LAYERS,
            "in_dim": nnmod.IN_DIM, "feature_hash": nnmod.feature_hash(),
            "n_samples": len(X), "trained_at": int(time.time()),
            "train_seconds": round(time.time() - t0, 1),
            "wf_edge": wf.get("wf_edge"), "wf_edge_se": wf.get("wf_edge_se"),
            "wf_acc": wf.get("wf_acc"), "wf_base": wf.get("wf_base"),
            "wf_folds": wf.get("folds")}
    WEIGHTS_PATH.write_text(json.dumps(
        {"weights": np.asarray(w_final).tolist(), "meta": meta}, indent=1),
        encoding="utf-8")
    print(f"Poids écrits : {WEIGHTS_PATH.name} (wf_edge {meta['wf_edge']} · "
          f"borne prudente {None if meta['wf_edge'] is None else round(meta['wf_edge'] - (meta['wf_edge_se'] or 0), 4)})")
    _notify_gate_transition(old_meta, meta)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parity", action="store_true",
                    help="vérifie l'équivalence PennyLane <-> simulateur numpy")
    args = ap.parse_args()
    if args.parity:
        sys.exit(0 if parity_check() else 1)
    train()
