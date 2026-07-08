# Collecteur de données — scraper + trieur thématique (SAFE, hors trading)

Deux agents en pipeline, aucun ordre, aucun secret :

1. **`scraper_agent.py`** (venv isolé, dépendance `scrapling`) — lit `sources.json`
   (flux RSS / pages publiques crypto), collecte via GET poli (pause, timeout,
   plafond par source), déduplique et ajoute au journal brut `raw_items.jsonl`.
2. **`sorter_agent.py`** (Python système, ZÉRO dépendance) — lit le journal brut,
   extrait les mots-clés (titre boosté, mots vides FR/EN exclus) et **crée ses
   catégories selon les thèmes** : cosinus ≥ 0.18 avec une catégorie existante →
   l'élément la rejoint (et enrichit son profil) ; sinon nouvelle catégorie nommée
   d'après ses mots-clés dominants. Déterministe : mêmes entrées → mêmes catégories.

## Installation & usage

```bash
cd ~/bitget_termux_repo
python3 -m venv data_collector/.venv
./data_collector/.venv/bin/pip install -r data_collector/requirements.txt

./data_collector/.venv/bin/python data_collector/scraper_agent.py   # collecte
python3 data_collector/sorter_agent.py                              # tri
```

## Fichiers produits (locaux, non committés)

- `raw_items.jsonl` — éléments bruts `{id, ts, source, url, title, text, published}`
- `sorted_items.jsonl` — éléments classés `{…, category, sim}`
- `categories.json` — profils des catégories `{keywords, n_items, created_ts}`
- `sorter_state.json` — ids déjà triés (tri incrémental)

## Garde-fous (ERR-004 / règles du dépôt)

- `scrapling` vit UNIQUEMENT dans `data_collector/.venv` (gitignored) — le Python
  système du bot n'est pas touché (pivots numpy/scipy verrouillés).
- Lecture seule web : GET uniquement, politesse (1,5 s entre sources, ≤ 20
  éléments/source), fail-safe par source (une source morte ne casse rien).
- Aucun lien avec le chemin d'exécution réel (pas d'import des exécuteurs).
