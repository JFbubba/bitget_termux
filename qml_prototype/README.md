# Prototype QML — PennyLane + PyTorch (laboratoire, hors trading)

Circuit variationnel **6 qubits** purement quantique, entraîné par PyTorch.
Laboratoire isolé : aucun lien avec le chemin d'exécution réel du bot.

## Architecture

- `quantum_model.py` — QNode PennyLane : `AmplitudeEmbedding` (64 features
  L2-normalisées → amplitudes), `StronglyEntanglingLayers` (profondeur 4,
  design « circuit-centric classifier », arXiv:1804.00633), mesure `<PauliZ>`
  sur le qubit 0. Device `lightning.qubit` (C++) + différentiation adjointe,
  repli automatique sur `default.qubit`.
- `train.py` — entraînement autonome : données synthétiques, Adam, MSE/MAE.

## Usage

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
OMP_NUM_THREADS=2 ./.venv/bin/python train.py   # threads <= cœurs physiques
```

Résultat vérifié sur le VPS (2 cœurs) : MSE 0.048 → 0.008 en 40 époques.

## Acquis de la formation (sources techniques)

1. **Simulateur** : `lightning.qubit` (plugin
   [PennyLane-Lightning](https://pypi.org/project/pennylane-lightning/),
   state-vector C++) est plus rapide que `default.qubit` et supporte la
   [différentiation adjointe](https://docs.pennylane.ai/projects/lightning/en/stable/lightning_qubit/device.html)
   — la méthode la plus efficace sur simulateur d'état ; la parallélisation
   se règle par `OMP_NUM_THREADS` (≤ cœurs physiques).
2. **Encodage** : `AmplitudeEmbedding` n'est
   [pas différentiable par rapport aux données](https://discuss.pennylane.ai/t/differentiation-with-amplitudeembedding/638)
   — sans conséquence ici (seuls les poids sont entraînés) ; la contrainte
   physique est la normalisation L2 (somme des |amplitudes|² = 1).
3. **Profondeur vs largeur** : la littérature récente
   ([arXiv:2601.11937](https://arxiv.org/html/2601.11937v1)) montre que la
   profondeur du circuit pèse plus que le nombre de qubits pour
   l'expressivité ; les « barren plateaus » (gradients qui s'effondrent
   exponentiellement, [revue arXiv:2405.00781](https://arxiv.org/html/2405.00781v1))
   croissent avec les qubits → à 6 qubits, profondeur 4 est un bon compromis.
4. **Intégration PyTorch** :
   [`qml.qnn.TorchLayer`](https://docs.pennylane.ai/en/stable/introduction/interfaces/torch.html)
   convertit le QNode en couche `torch.nn` (gradients à travers le circuit).

## Limites connues (VPS 2 cœurs / 8 Go)

Un simulateur d'état double la mémoire par qubit ajouté : ~20–24 qubits
maximum sur 8 Go. Ce prototype (6 qubits = 64 amplitudes) est très loin de
la limite ; la profondeur du circuit est le levier d'expressivité à coût
mémoire quasi nul.
