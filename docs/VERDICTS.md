# VERDICTS — registre des idées testées et de leur sort

**But** : source unique de « qu'est‑ce qui a été essayé, et avec quel résultat ». À
CONSULTER avant de (re)tester une idée — pour ne JAMAIS re‑mesurer ce qui est déjà mort.
Chaque ligne : preuve mesurée, pas opinion. Mettre à jour à chaque verdict rendu.

Statuts : **REJETÉ** (mesuré perdant, ne pas re‑tester) · **GARDÉ** (branché, mesuré gagnant) ·
**MUET** (branché mais neutralisé par une porte, mesure en ombre) · **VIVANT** (piste ouverte,
à re‑mesurer) · **ÉVALUÉ** (service/donnée jugé sans mesure d'edge).

## REJETÉ — mesuré perdant, NE PAS re‑tester
| Idée | Verdict | Preuve | Réf |
|---|---|---|---|
| SMC / AIO (FVG + Order Blocks) | REJETÉ | net‑négatif, 5 symboles × 3 régimes | mém. `smc-aio-rejected` |
| geometric v2 (topologie/dcor/nolds) | REJETÉ | 0/14 features sur 1m→1W ; dcor n'ajoute rien vs Pearson ; nolds prohibitif | mém. `geometric-mirage-24h`, `pypi-tools-watchlist` |
| forecast Darts (NHITS/AutoETS/statsforecast) | REJETÉ | 0/32 net de frais (BTC/ETH×8TF×h1/h4) ; IC faible mangé par frais | mém. `openbb-ecosystem-verdict` · `scratchpad/openbb_forecast_lab` |
| mql5 kalman_slope (Kalman price smoother) | REJETÉ | 0/34 net de frais ; IC signif. isolé XAU 1H mais < frais | mém. `mql5-codebase-tester` |
| filtre de conviction | REJETÉ | consensus contrarien à 1 h | mém. `edge-tuning-68` |
| gate de régime (démotion Priorité 2) | REJETÉ ×2 | réfuté en croisé | `docs/BACKLOG_RECHERCHE.md` §104 |
| carry cible 2.5 | REJETÉ (artefact) | 0.25 sur 15/15 refits walk‑forward | mém. `measurement-blind-spot` |
| voix classics (MACD/Bollinger/Donchian/VWAP/grille/pairs/funding_fade) | REJETÉ (coupée) | t ≈ −11 | mém. `edge-tuning-68` |
| voix LLM (15ᵉ) | REJETÉ (coupée) | t ≈ −4.5 | mém. `edge-tuning-68` |
| pré‑ordre (pipeline) | REJETÉ | mesuré perdant | RESEARCH_NOTES §52 |
| ema_cross / crossovers simples | REJETÉ | −83 % backtest ; WF OOS ~break‑even mais DD −65 % | `scratchpad/strategy_tester` |

## GARDÉ — branché, mesuré gagnant
| Idée | Preuve | Réf |
|---|---|---|
| GARCH figé (`volatility.py`) | bat `arch` 11/12 QLIKE | mém. `pypi-tools-watchlist` |
| Banc 14 agents déterministes (EARCP assaini §51) | socle, banc GELÉ à 14 (§62) | CLAUDE.md |
| régime = instrument de VOL (CVIX) | module le sizing, sain | `learning_health` |

## MUET — branché mais neutralisé par la porte d'edge (mesure en ombre)
| Voix | État | Réf |
|---|---|---|
| NN fusion (16ᵉ) | armée, voix MUETTE (porte edge), ombre `nn_shadow` | mém. `llm-agent-and-no-nn-lifted` |
| QML quantique (18ᵉ) | armée, voix MUETTE (porte edge), ombre `qml_shadow` | mém. `qml-voice-18` |

## VIVANT — piste ouverte, à re‑mesurer
| Piste | Statut | Prochaine mesure |
|---|---|---|
| **régime → consensus (c)** | edge banc DOUBLE en haute‑vol +0.12/+0.16 mais 1 seul bloc | re‑mesurer ~15/07 · mém. `pypi-tools-watchlist` |
| **EXÉCUTION / frais** = le vrai levier | les signaux §72 sont mangés par les frais → travailler l'exécution, pas plus de signaux | `docs/BACKLOG_RECHERCHE.md` §104 |
| mode MAKER futures (post-only + repli taker) | **CODÉ + ARMÉ 09/07** (tout l'univers, décision proprio) : `FUTURES_EXEC_STYLE=maker`, post-only au bid/ask + poll court + annulation + repli taker du RESTANT (garde anti-double-position) ; testé hermétiquement. **MESURE EN COURS** : économie réelle (~4 bps/side attendus) + taux de fill maker vs repli taker à relever ~1-2 sem. via `trade_forensics`. Réversible (style=limit_ioc) | `futures_executor.py` `_place_maker` · §exec-frais |
| futures edge directionnel | notional 25 $, edge robuste mais fragile | re‑mesurer ~14/07 · mém. `futures-edge-unproven` |
| momentum cross‑sectionnel | à élever (les signaux mono‑actif sont de la réversion redondante) | BACKLOG §104 |
| forecast Darts — panier diversifié → **REJETÉ 09/07** | 21 sym × 8 TF net de frais : 0/477 passe (seule UNI 1D = faux positif multiple-testing). IC RÉEL surtout actions US (0.20 t4.7)/alts (0.23 t3.5) mais mangé par frais (§104) | fait — ne pas re-tester |

## ÉVALUÉ — service/donnée jugé (sans mesure d'edge)
| Source | Verdict | Réf |
|---|---|---|
| Écosystème OpenBB (platform/bot/ai/forecast) | rien à brancher (data/UI, pas de signal) | mém. `openbb-ecosystem-verdict` |
| Adanos (sentiment Reddit crypto) | clé rangée ; redondant LunarCrush ; MESURER avant de brancher | mém. `adanos-koinju-services` |
| Koinju (données marché) | ne couvre PAS Bitget → hors sujet ; deribit options = piste futur (payant) | mém. `adanos-koinju-services` |
| mql5.com (articles + code base) | recoupe l'existant (topologie/quantique/Hurst/classiques) ; peu de neuf | mém. `mql5-codebase-tester` |
