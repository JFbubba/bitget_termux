"""Modèle de Machine Learning Quantique (QML) — PennyLane + PyTorch.

Architecture purement quantique : le circuit variationnel est l'unique
couche apprenante du modèle (pas de couches classiques ``nn.Linear``).

Circuit à 6 qubits :
- ``qml.AmplitudeEmbedding`` charge un vecteur classique de 2**6 = 64
  composantes dans les amplitudes du registre quantique (le vecteur doit
  être L2-normalisé : contrainte physique somme des |amplitudes|² = 1).
  NB : cet encodage n'est pas différentiable par rapport aux DONNÉES —
  sans conséquence ici, seuls les POIDS du circuit sont entraînés ;
- ``qml.StronglyEntanglingLayers`` fournit les rotations paramétrées et
  l'intrication (design « circuit-centric classifier », arXiv:1804.00633).
  Profondeur 4 : la littérature indique que la profondeur du circuit
  pèse plus que le nombre de qubits pour l'expressivité, tout en restant
  assez faible pour éviter les « barren plateaus » (gradients évanescents) ;
- la mesure ``<PauliZ>`` sur le qubit 0 donne une sortie scalaire
  différentiable dans l'intervalle [-1, 1].

Simulateur : ``lightning.qubit`` (plugin C++ PennyLane-Lightning) avec la
différentiation adjointe — la méthode la plus rapide sur simulateur
d'état — et repli automatique sur ``default.qubit`` + backprop si le
plugin n'est pas disponible.
"""

import pennylane as qml
import torch
from torch import nn

# Nombre de qubits simulés localement.
NB_QUBITS = 6
# Dimension d'entrée classique : une composante par amplitude (2**6 = 64).
NB_FEATURES = 2 ** NB_QUBITS
# Profondeur du circuit variationnel (nombre de couches intriquantes).
NB_COUCHES = 4

# Sélection du simulateur : lightning.qubit (C++, rapide, gradients
# adjoints) si disponible, sinon default.qubit (Python, backprop).
try:
    dev = qml.device("lightning.qubit", wires=NB_QUBITS)
    DIFF_METHOD = "adjoint"
except qml.DeviceError:
    dev = qml.device("default.qubit", wires=NB_QUBITS)
    DIFF_METHOD = "best"

NOM_DEVICE = dev.name


@qml.qnode(dev, interface="torch", diff_method=DIFF_METHOD)
def quantum_circuit(inputs, weights):
    """Circuit quantique variationnel (QNode différentiable par PyTorch).

    Args:
        inputs: vecteur (ou lot de vecteurs) de NB_FEATURES composantes.
        weights: poids entraînables de forme (NB_COUCHES, NB_QUBITS, 3).

    Returns:
        Valeur moyenne de Pauli-Z sur le qubit 0, dans [-1, 1].
    """
    # Encodage d'amplitude : le vecteur d'entrée devient l'état |psi>.
    # ``normalize=True`` re-normalise en L2 par sécurité (contrainte
    # quantique) ; ``pad_with=0.0`` complète à 64 composantes si besoin.
    qml.AmplitudeEmbedding(
        features=inputs,
        wires=range(NB_QUBITS),
        normalize=True,
        pad_with=0.0,
    )
    # Couches entraînables : rotations paramétrées + intrication (CNOT).
    qml.StronglyEntanglingLayers(weights, wires=range(NB_QUBITS))
    # Mesure finale : projection classique du calcul quantique.
    return qml.expval(qml.PauliZ(0))


# Géométrie des poids attendue par StronglyEntanglingLayers.
WEIGHT_SHAPES = {"weights": (NB_COUCHES, NB_QUBITS, 3)}


class QuantumModel(nn.Module):
    """Modèle QML pur : le circuit quantique est la seule couche apprenante."""

    def __init__(self):
        super().__init__()
        # Conversion du QNode en couche PyTorch entraînable (les gradients
        # traversent le simulateur quantique via la rétropropagation).
        self.quantum_layer = qml.qnn.TorchLayer(quantum_circuit, WEIGHT_SHAPES)

    def forward(self, x):
        """Propagation avant.

        Args:
            x: tenseur de forme (batch, NB_FEATURES), idéalement L2-normalisé
               ligne par ligne (l'embedding re-normalise par sécurité).

        Returns:
            Tenseur de forme (batch, 1), valeurs dans [-1, 1].
        """
        return self.quantum_layer(x).unsqueeze(-1)
