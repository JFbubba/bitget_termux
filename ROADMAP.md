# Roadmap  Bitget Termux Agent

## Phase actuelle

FULL LIVE borne (decision proprietaire du 02/07/2026, RESEARCH_NOTES §45) :
- accumulation spot BTC reelle (2-5 $/j proportionnel a l'opportunite, §44) ;
- boucle futures directionnelle reelle bornee (10 $ x2, seuil consensus 0.35) ;
- jambes cash-and-carry reelles couvertes par le spot (seuil APR net 5 %).
Murs durs : 50 $/trade, 250 $ cumule, stop journalier -5 % -> kill-switch.

Objectif : laisser les donnees trancher (PnL net de frais via /futures), monter
les caps par paliers si l'execution est propre, debrayer ce qui ne paie pas.

## Priorite 1  Securite

- Maintenir tous les agents avec can_trade=False
- Bloquer tout ajout de fonction de trading reel
- Garder .env hors Git
- Ajouter safe_push_check.sh
- Ajouter verification avant push
- Tester security_agent.py avant chaque commit

## Priorite 2  Exploitation Termux

- [x] Ajouter bootstrap_termux.sh
- [x] Ajouter rotation des journaux (rotate_logs.sh)
- [x] Ajouter commande Telegram /git_version
- [x] Ajouter verification de processus agent_loop.py (watchdog.py + /watchdog)
- [x] Ajouter procedure restart propre (restart_agent.sh + agent_loop.pid)

## Priorite 3  Observabilite

- [x] Resume sante systeme (/system_health)
- [x] Dernier commit Git (/git_version)
- [x] Dernier tag stable (/git_version)
- [x] Taille des journaux (/system_health)
- [x] Nombre de pre-ordres pending/rejected/dry-run (/system_health)
- [x] Statut pause/resume (/pause_status)
- [x] Dashboard : sources orthogonales §40 (on-chain BTC, stablecoins, DVOL/VRP, carry)
- [x] Dashboard : echelle d'edge enrichie (mode xs / n effectif, proche LIVE, priors EARCP)

## Priorite 4  Qualite strategie

- [x] Backtest offline simple (accum_backtest.py : cost-basis IS/OOS committe, §42)
- Journal des signaux ignores
- [x] Indicateurs volume : niveau ancre + biais (concept Unbiased Level Pro)
- [x] Indicateurs pro calculables : momentum, volume profile, Sharpe, sizing risque capital, timing horaire (pro_indicators.py)
- [x] Microstructure (order_flow.py + /orderflow) + contexte macro (macro_context.py + /macro)
- [x] Confluence signal x microstructure x macro branchee dans le scoring (/confluence)
- [x] Statistiques par symbole (stats_report.py + /stats)
- [x] Statistiques long/short (stats_report.py + /stats)
- [x] Ratio TP/SL (stats_report.py + /stats)
- Gestion des signaux ambigus

## Outils externes

Revue curee des sources externes (data, MCP, skills, Polymarket) et plan
d'adoption SAFE : voir [docs/EXTERNAL_TOOLS.md](docs/EXTERNAL_TOOLS.md).
Prochaines adoptions : prediction-mcp (Polymarket, cote PC), module
CVD/order-flow + zones de liquidation, squelette de skill "analyse".

## Interdit (revise §45, puis §67 le 06/07)

Ordres reels UNIQUEMENT via les modules autorises : spot_executor, futures_executor,
et les surfaces bornees §67 (spot_trader, margin_trader, account_transfers, earn_manager
sur le noyau bitget_execute — CLI + --confirm uniquement, jamais de boucle auto).
Jamais de RETRAIT nulle part (cle Trade-only, aucun code de retrait n'existe).
Vente spot libre / marge / virements internes / earn : INTERDITS aux boucles autonomes —
possibles UNIQUEMENT via les surfaces §67 (verrous LIVE armes par decision proprietaire
du 06/07, caps durs par operation et par jour, kill-switch fail-closed, --confirm).
L'accumulation spot, elle, reste achat-seul (on ne vend jamais la poche d'accumulation).
Pas de secrets dans Git.
Pas dactivation can_trade=True sur les agents du cerveau (ils DECIDENT, les executeurs executent).
Pas de depassement des murs durs (50/250, stop -5 %) sans decision proprietaire explicite.
