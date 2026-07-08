"""Entraînement autonome du modèle QML sur données synthétiques.

Usage : ``python3 train.py`` (aucun argument requis).
Le script génère un jeu de données L2-normalisé (contrainte de
l'encodage d'amplitude), entraîne le circuit avec Adam et affiche
les métriques (MSE, MAE) au fil des époques.
"""

import torch
from torch import nn

from quantum_model import DIFF_METHOD, NB_FEATURES, NOM_DEVICE, QuantumModel

# Hyperparamètres de l'entraînement.
NB_ECHANTILLONS = 64
NB_EPOQUES = 40
TAUX_APPRENTISSAGE = 0.05
GRAINE = 42


def generer_donnees(nb_echantillons):
    """Génère un jeu synthétique compatible avec l'encodage d'amplitude.

    Chaque entrée est un vecteur de NB_FEATURES composantes normalisé en
    L2 (somme des carrés = 1, contrainte des amplitudes quantiques).
    La cible est le contraste de probabilité entre les deux moitiés du
    vecteur d'état — une grandeur bornée dans [-1, 1], donc directement
    comparable à la mesure <PauliZ> du circuit.

    Args:
        nb_echantillons: nombre de lignes du jeu de données.

    Returns:
        Tuple (x, y) : x de forme (n, NB_FEATURES), y de forme (n, 1).
    """
    x = torch.randn(nb_echantillons, NB_FEATURES)
    # Normalisation L2 ligne par ligne : ||x_i|| = 1.
    x = x / x.norm(dim=1, keepdim=True)
    # Cible : P(qubit 0 = |0>) - P(qubit 0 = |1>) de l'état encodé.
    moitie = NB_FEATURES // 2
    y = x[:, :moitie].pow(2).sum(dim=1) - x[:, moitie:].pow(2).sum(dim=1)
    return x, y.unsqueeze(-1)


def main():
    """Boucle d'entraînement principale."""
    torch.manual_seed(GRAINE)

    x_train, y_train = generer_donnees(NB_ECHANTILLONS)
    model = QuantumModel()
    optimizer = torch.optim.Adam(model.parameters(), lr=TAUX_APPRENTISSAGE)
    criterion = nn.MSELoss()

    print(
        f"Entraînement QML : {NB_ECHANTILLONS} échantillons, "
        f"{NB_EPOQUES} époques, {NB_FEATURES} features -> 6 qubits "
        f"(device {NOM_DEVICE}, diff {DIFF_METHOD})."
    )

    for epoque in range(1, NB_EPOQUES + 1):
        optimizer.zero_grad()
        predictions = model(x_train)
        loss = criterion(predictions, y_train)
        loss.backward()  # Gradients calculés à travers le circuit quantique.
        optimizer.step()

        if epoque == 1 or epoque % 5 == 0:
            mae = (predictions - y_train).abs().mean().item()
            print(
                f"Époque {epoque:3d}/{NB_EPOQUES} — "
                f"MSE : {loss.item():.6f} — MAE : {mae:.6f}"
            )

    print("Entraînement terminé.")


if __name__ == "__main__":
    main()
