"""Simulateur EXACT du circuit quantique de la 18ᵉ voix — NumPy PUR.

Classement : SAFE (calcul pur, AUCUN ordre, AUCUNE écriture, AUCUN réseau).

Pourquoi ce module existe (ERR-004) : PennyLane vit UNIQUEMENT dans le venv du
laboratoire (`qml_prototype/.venv`) — l'installer dans le Python système forcerait
numpy 2.x et casserait la pile du bot. Or un circuit de 6 qubits n'est qu'un vecteur
d'état de 2**6 = 64 amplitudes complexes : on le simule EXACTEMENT ici, en numpy
seul (déjà pivot du bot), sans nouvelle dépendance. L'entraînement (torch/PennyLane)
reste au labo ; les poids sont échangés en JSON ; l'inférence live passe par ici.

Conventions répliquées de PennyLane (parité vérifiée par
`qml_prototype/train_voice.py --parity`) :
  • fil 0 = bit de POIDS FORT de l'index de base ;
  • ``qml.Rot(phi, theta, omega)`` = RZ(omega)·RY(theta)·RZ(phi) (RZ(phi) d'abord) ;
  • ``StronglyEntanglingLayers`` (imprimitive CNOT) : par couche l, une Rot par fil
    puis CNOT(i -> (i + r_l) mod n) pour chaque fil i, avec la portée par défaut
    r_l = (l mod (n-1)) + 1 ;
  • ``AmplitudeEmbedding(normalize=True, pad_with=0.0)`` : complétion à 2**n puis
    normalisation L2 ;
  • sortie = <PauliZ> sur le fil 0.
"""
from __future__ import annotations

import numpy as np


def amplitude_embed(x, n_qubits):
    """Vecteur d'état initial |psi> depuis un vecteur de features classique.

    Complète avec des zéros jusqu'à 2**n_qubits puis normalise en L2 (contrainte
    quantique). Un vecteur nul (ou quasi) est remplacé par |0...0> — état neutre
    déterministe plutôt qu'une division par zéro."""
    dim = 2 ** n_qubits
    v = np.zeros(dim, dtype=np.complex128)
    x = np.asarray(x, dtype=np.float64).ravel()[:dim]
    v[: x.size] = x
    norm = np.linalg.norm(v)
    if norm < 1e-12:
        v[0] = 1.0
        return v
    return v / norm


def rot_matrix(phi, theta, omega):
    """Matrice 2×2 de ``qml.Rot(phi, theta, omega)`` = RZ(omega)·RY(theta)·RZ(phi)."""
    def rz(a):
        return np.array([[np.exp(-0.5j * a), 0.0], [0.0, np.exp(0.5j * a)]],
                        dtype=np.complex128)

    def ry(t):
        c, s = np.cos(t / 2.0), np.sin(t / 2.0)
        return np.array([[c, -s], [s, c]], dtype=np.complex128)

    return rz(omega) @ ry(theta) @ rz(phi)


def apply_1q(state, gate, wire, n_qubits):
    """Applique une porte 1-qubit sur `wire` (0 = poids fort) au vecteur d'état."""
    psi = state.reshape([2] * n_qubits)
    psi = np.tensordot(gate, psi, axes=(1, wire))
    psi = np.moveaxis(psi, 0, wire)
    return psi.reshape(2 ** n_qubits)


def apply_cnot(state, control, target, n_qubits):
    """CNOT(control -> target) par permutation des indices de base (involution)."""
    dim = 2 ** n_qubits
    idx = np.arange(dim)
    ctrl_bit = (idx >> (n_qubits - 1 - control)) & 1
    perm = idx ^ (ctrl_bit << (n_qubits - 1 - target))
    return state[perm]


def strongly_entangling(state, weights, n_qubits, ranges=None):
    """Applique les couches ``StronglyEntanglingLayers`` (convention PennyLane)."""
    weights = np.asarray(weights, dtype=np.float64)
    n_layers = weights.shape[0]
    if ranges is None:
        ranges = [(l % (n_qubits - 1)) + 1 for l in range(n_layers)] \
            if n_qubits > 1 else [0] * n_layers
    for layer in range(n_layers):
        for w in range(n_qubits):
            phi, theta, omega = weights[layer, w]
            state = apply_1q(state, rot_matrix(phi, theta, omega), w, n_qubits)
        if n_qubits > 1:
            r = int(ranges[layer])
            for w in range(n_qubits):
                state = apply_cnot(state, w, (w + r) % n_qubits, n_qubits)
    return state


def expval_z0(state, n_qubits):
    """<PauliZ> sur le fil 0 : +|amp|² si bit fort = 0, −|amp|² sinon."""
    dim = 2 ** n_qubits
    signs = 1.0 - 2.0 * ((np.arange(dim) >> (n_qubits - 1)) & 1)
    return float(np.real(np.sum(signs * np.abs(state) ** 2)))


def predict_score(x, weights, n_qubits=None, ranges=None):
    """Passe avant complète : features -> <Z0> ∈ [-1, 1]. PUR et déterministe."""
    weights = np.asarray(weights, dtype=np.float64)
    if n_qubits is None:
        n_qubits = int(weights.shape[1])
    state = amplitude_embed(x, n_qubits)
    state = strongly_entangling(state, weights, n_qubits, ranges=ranges)
    return expval_z0(state, n_qubits)
