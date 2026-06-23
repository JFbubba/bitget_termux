---
source: package/documents-trading/
category: bitget-tooling
action: tool-adapted
target: risk_manager.py (ATR_RISK_MANAGER), comparaison `BITGET_MASTER_SYSTEM-10.py`
---

## Contenu
- `ATR_RISK_MANAGER.py` — risk manager basé ATR.
- `BITGET_MASTER_SYSTEM-10.py` — gros script trading "tout-en-un" version 10.
- `crypto-wealth-management-v1-application-complète-prête-au-déploiement (1).md`
  — doc app wealth management.
- `Sans titre.canvas` (Obsidian canvas).

## Valeur extraite
- `ATR_RISK_MANAGER.py` à **comparer ligne à ligne** avec `risk_manager.py` du
  repo — vérifier qu'on n'a rien oublié (trailing stop ATR, gap stop, etc.).
- `BITGET_MASTER_SYSTEM-10.py` = version monolithique probable d'une stratégie ;
  intérêt limité car le repo est éclaté en modules ; à ouvrir seulement si on
  cherche une règle particulière manquante.
- Le `.canvas` Obsidian est un schéma visuel — pas exploitable hors Obsidian.

## Cible d'intégration
- `risk_manager.py` — diff conceptuel avec `ATR_RISK_MANAGER.py` et patcher si
  manque (souvent : trailing ATR dynamique).
- `docs/RESEARCH_NOTES.md` — § court si on récupère une règle.
