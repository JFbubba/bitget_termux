# Agent testeur de code base mql5 (labo SAFE)

Prend les idées d'indicateurs/stratégies de mql5.com, les **réimplémente en Python**
et **mesure leur edge net de frais** sur les données réelles Bitget. Garde ce qui
survit à la mesure, rejette le reste. Lecture seule, aucun ordre.

## Ligne rouge (non négociable)
**Jamais** de téléchargement ni d'exécution de code tiers `.mq5`/`.ex5` (non audité,
et MQL5 ne tourne pas en Python). « Tester la code base » = réimplémenter la LOGIQUE
en Python et la mesurer — pas exécuter le code d'origine.

## Composants
| Fichier | Rôle | Env |
|---|---|---|
| `catalog.py` | Catalogue des candidats (source : corpus d'ARTICLES mql5 — la section `/code` refuse le fetch, anti-bot ; les articles décrivent mieux la logique de toute façon) | système |
| `triage.py` | Score chaque item : pertinence signal − bruit − déjà-couvert-par-le-bot → `queue.json` | système |
| `candidates.py` | Réimplémentations Python de la logique (registre `CANDIDATES`) | système |
| `harness.py` | Banc de test : IC, hit, **PnL net de frais** (0/4/12 bps), t sur plis NON chevauchants purgés, porte §77 (t≥3), échelle TF complète (ERR-001) | système |
| `run_candidate.py` | Teste un candidat → rapport + verdict dans `verdicts.jsonl` | système |

## Workflow
```bash
# 1. (option) rafraîchir le corpus d'articles : ../mql5_backfill.py puis sorter_agent
python3 catalog.py            # construit catalog.json
python3 triage.py             # priorise -> queue.json (TOP = à réimplémenter)
# 2. réimplémenter un TOP candidat comme fonction signal dans candidates.py
python3 run_candidate.py <nom> [SYM ...]   # mesure + verdict journalisé
```

## Verdicts à ce jour (`verdicts.jsonl`)
- `kalman_slope` (Kalman price smoother) : **REJETÉ** 0/34 — edge net de frais négatif
  partout (un IC significatif isolé sur XAU 1H, mais < frais). Conforme au prior :
  les signaux simples sont mangés par les frais (§104).
- `struct_break_suite` + `csw_cusum`/`sadf_dir`/`chow_dir` (AFML Ch.17, art. 23158) :
  **REJETÉ** 0/40 — testé en SUITE d'abord (ERR-002) puis décomposé, 5 symboles ×
  échelle TF complète, h=1 et h=5. IC médian **négatif partout** (−0.03 à −0.05) : lus
  en momentum, les ruptures sont légèrement contrariennes à court TF (1m/5m très
  négatifs, |t| élevé) mais l'edge est < frais ; quelques nets positifs isolés en
  1D/1W avec |t| < 3 (bruit). L'article donne ces tests comme FEATURES ML, pas comme
  signal directionnel autonome — la lecture directionnelle est une construction du
  testeur. Encore le prior §104 : le levier est l'EXÉCUTION (frais), pas plus de signaux.
  Runner : `python3 run_struct_break.py`.

## Note
Le test réel (réimplémentation Python) est fait au cas par cas par l'agent — le module
fournit le catalogue, le triage et le **harness réutilisable**. C'est l'outil, pas un
pilote automatique : chaque candidat passe par une réimplémentation humaine vérifiée.
