---
source: package/Bitget/ (« exchange_intel_radar »)
category: bitget-tooling
action: tool-adapted
target: nouveau module `radar/` ou fusion avec `journal_scanner.py`
---

## Contenu
- Projet Python autonome : `main.py`, `exchange_intel_radar.py`, `radar_config.py`,
  `terminal_dashboard.py`, `simulate_events.py`.
- Modules : `alerts/`, `collectors/`, `normalizers/`, `scoring/`, `scripts/`,
  `src/`, `storage/`, `tests/`, `docs/`, `files/`.
- Configuration : `setup_bitget_env.ps1`, `requirements.txt`.
- Storage : `radar.sqlite3` (déjà des données collectées).
- `llm_provider.py` — wrapper LLM générique.

## Valeur extraite
- **Architecture intéressante** : collecteur → normaliseur → scoring → alertes.
  C'est une variante du `journal_scanner.py` du repo, avec en plus une couche
  alerte et un terminal dashboard.
- `terminal_dashboard.py` peut inspirer un mode terminal (ASCII) du dashboard
  existant.
- `simulate_events.py` est précieux pour les tests (rejouer des événements).

## Cible d'intégration
- Comparer la **logique de scoring** avec ce que produit `journal_scanner.py` /
  `order_signal_engine.py` ; piocher 1-2 idées si meilleures (ex. normaliseurs
  par source).
- Pas d'import direct du projet ; **extraire** les fichiers/idées utiles dans
  des modules du repo.
