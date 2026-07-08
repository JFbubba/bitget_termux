# NOTE DE CORRECTION — déploiement quantique (qml_prototype), 08/07/2026

**Destinataire.** Agent correcteur (`autodidacte.py` + revue de jugement `/lance-correction`).
**Objet.** Points de contrôle issus du déploiement du prototype QML (PennyLane/PyTorch,
6 qubits, `qml_prototype/`) — à vérifier sur ce prototype ET globalement sur le dépôt.
**Périmètre.** Le prototype est un LABORATOIRE : aucun lien avec le chemin d'exécution
réel, aucun code d'ordre. Les 3 portes sont passées à chaque commit (bdc0c8e, 547d324).

---

## C1 — Isolation des dépendances de laboratoire (voir ERR-004)

**Constat.** Installer PennyLane dans le Python SYSTÈME aurait forcé numpy 1.26.4 → 2.5.1
et scipy 1.11.4 → 1.18.0 (mesuré par `pip install --dry-run`) — rupture probable de la
pile du bot LIVE (le matplotlib système casse déjà sous numpy 2). Évité : venv isolé
`qml_prototype/.venv`.
**Contrôle global.**
- Tout dossier de laboratoire/prototype a son `requirements.txt` et son venv ignoré par git.
- `grep -rn "break-system-packages" *.sh *.py docs/` → toute occurrence hors doc = suspect.
- Versions pivots du bot attestées au 08/07 : numpy 1.26.4, scipy 1.11.4, torch 2.12.1+cpu.
  Toute dérive non journalisée = anomalie à remonter.

## C2 — Artefacts d'environnement hors git

**Constat.** `.venv/` ajouté au `.gitignore` (commit bdc0c8e) ; `__pycache__/` déjà couvert.
**Contrôle global.** `git status --short` ne doit montrer ni venv, ni caches, ni artefacts
d'entraînement (poids de modèles de labo). `git check-ignore qml_prototype/.venv` doit passer.

## C3 — Séparation stricte du chemin d'exécution réel

**Constat.** `qml_prototype/` n'importe que pennylane/torch — aucun import des modules
d'exécution (`spot_executor`, `futures_executor`, `bitget_execute`, surfaces §67).
**Contrôle global.** Pour CHAQUE laboratoire (qml_prototype, strategy lab, xs paper…) :
`grep -rn "spot_executor\|futures_executor\|bitget_execute" <dossier>/` doit être vide.
Un labo qui gagne un chemin vers un ordre réel = violation majeure (règle d'engagement 1).

## C4 — Ressources partagées avec le bot LIVE (VPS 2 cœurs / 8 Go)

**Constat.** L'entraînement QML tourne sur la même machine que les boucles cadencées
(cerveau 1 min, scan ~1 min). Exécuté avec `OMP_NUM_THREADS=2` et durée courte (<1 min).
**Contrôle global.** Tout script d'entraînement/simulation de labo doit borner ses threads
(`OMP_NUM_THREADS` ≤ cœurs physiques) et sa durée ; les gros entraînements passent en
heures creuses (modèle : cron neural-train 04:20). Vérifier qu'aucun cron de labo ne
chevauche les cadences critiques.

## C5 — Contraintes QML spécifiques (si le labo quantique évolue)

- `AmplitudeEmbedding` : entrée L2-normalisée OBLIGATOIRE (somme des |amplitudes|² = 1) ;
  NON différentiable par rapport aux données — n'entraîner que les poids du circuit.
- Simulateur : `lightning.qubit` + différentiation adjointe ; repli `default.qubit`.
- Mémoire : 2^n amplitudes — ~20–24 qubits max sur 8 Go ; privilégier la PROFONDEUR
  du circuit (barren plateaus croissent avec la largeur).
- Sources et acquis : `qml_prototype/README.md`.

## C6 — Rappels de méthode applicables au labo QML

- **ERR-001** : si le prototype est un jour testé sur données de MARCHÉ, l'échelle
  complète `M1·M5·M15·M30·H1·H4·D1·W1` s'applique — pas de sous-ensemble.
- **ERR-002** : si le circuit devient une stratégie séquentielle, la tester ENTIÈRE d'abord.
- **ERR-003** : vérifier les capacités (device, versions, API) contre le système réel
  avant d'affirmer — le repli `lightning.qubit`/`default.qubit` en est l'application.

---

**Action demandée au correcteur.** Exécuter les contrôles C1–C4 sur tout le dépôt
(C5–C6 en revue de jugement), journaliser toute occurrence dans `docs/AGENT_ERRORS.md`,
corriger ce qui est clairement corrigeable dans les 3 portes, notifier.
