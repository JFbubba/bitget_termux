# Extraction « package » → repo

> Index des fiches d'extraction issues du dossier Drive `G:/Mon Drive/Trading/package`.
> Source du triage : `docs/DRIVE_TRIAGE.md`. Registre froid : `drive_triage.json`.

Chaque fiche = un fichier (ou un sous-dossier) du `package/` ramené à :
- **catégorie** (rubrique d'analyse)
- **valeur extraite** (1‑3 lignes : ce que c'est, à quoi ça sert chez nous)
- **cible d'intégration** dans ce repo (fichier/agent/doc cible)
- **action** au sens DRIVE_TRIAGE : `learned` / `extracted` / `tool-adapted` / `skipped`

## Légende des catégories

| catégorie | description courte |
|---|---|
| `canon` | grands classiques du trading (livres) — leçon pédagogique unique à extraire |
| `research` | papier de recherche (arXiv, blogs quant) — feature/protocole à reproduire |
| `method` | méthode de marché (Wyckoff, ICT, Volume Profile, chandeliers) — règles concrètes |
| `crypto-onchain` | data on‑chain, memecoin, DEX, sniping, signaux |
| `agent-architecture` | multi‑agent LLM, Aladdin perso, ecosystem design |
| `bitget-tooling` | code Bitget direct (REST, hedge, SL/TP, scanners) |
| `mcp-server` | serveur MCP : utile / déjà couvert / candidat à adapter |
| `strategy-doc` | doc de stratégie (martingale, agressivité, top‑down) |
| `repo-clone` | clone d'un OSS public — référence, pas du code à incorporer |
| `secret-leak` | **CRITIQUE** — clés / tokens / accounts en clair |
| `skip-noise` | scrap HTML, copies dupliquées, screenshots, métadonnées Drive |

## Cibles d'intégration récurrentes

- `docs/RESEARCH_NOTES.md` — cerveau (concepts, features régime/microstructure)
- `swarm_brain.py` — mixture of experts, votes, hedge weights
- `risk_manager.py` / `risk_limits.py` / `position_sizer.py` — guardrails
- `portfolio_scanner.py` / `trade_plan.py` / `decision_engine.py` — pipeline décision
- `macro_context.py` — régime macro
- `order_signal_engine.py` / `preorder_engine.py` / `preorder_approval.py` / `preorder_guard.py` — signaux/pre‑orders
- `paper_*` — paper trading
- `agent_hub.py` / `agent_control.py` / `agent_loop.py` — orchestration
- `assistant/` — LLM (tools, memory, vision)
- `dashboard/` — UI
- `drive_triage.py` / `drive_triage.json` — registre froid

## Fiches

### CRITIQUE — secrets en clair

- [secrets_leak.md](secrets_leak.md) — **rotation immédiate requise**

### Recherche & cerveau (research / canon / method)

#### Déjà tracé dans `drive_triage.json`
- [pdf_arxiv_2511_08571_forecast_to_fill.md](pdf_arxiv_2511_08571_forecast_to_fill.md)
- [pdf_arxiv_2512_15720_orderflow_entropy.md](pdf_arxiv_2512_15720_orderflow_entropy.md)
- [pdf_arxiv_2512_03107_eclipse_skipped.md](pdf_arxiv_2512_03107_eclipse_skipped.md)
- [pdf_factor_drift_oos_sharpe13.md](pdf_factor_drift_oos_sharpe13.md)

#### Méthode (à intégrer)
- [pdf_wyckoff_method.md](pdf_wyckoff_method.md)
- [pdf_wyckoff_strategy_txt.md](pdf_wyckoff_strategy_txt.md)
- [pdf_volume_profile_insiders_guide.md](pdf_volume_profile_insiders_guide.md)
- [pdf_ict_breaker_block.md](pdf_ict_breaker_block.md)
- [txt_smc_9_concepts.md](txt_smc_9_concepts.md)
- [pdf_candlestick_cheatsheet.md](pdf_candlestick_cheatsheet.md)

#### Canon (livres)
- [pdf_trading_in_the_zone_douglas.md](pdf_trading_in_the_zone_douglas.md)
- [pdf_market_wizards.md](pdf_market_wizards.md)
- [pdf_graham_intelligent_investor.md](pdf_graham_intelligent_investor.md)
- [pdf_soros_alchimie_finance.md](pdf_soros_alchimie_finance.md)
- [pdf_dalio_principles.md](pdf_dalio_principles.md)
- [pdf_greenblatt_little_book.md](pdf_greenblatt_little_book.md)
- [pdf_malkiel_random_walk.md](pdf_malkiel_random_walk.md)
- [epub_lewis_flash_boys.md](epub_lewis_flash_boys.md)

#### Autres PDF du sous-dossier `PDF/`
- [pdf_memecoin_sniper_cours.md](pdf_memecoin_sniper_cours.md)
- [pdf_trading_smart_unknown.md](pdf_trading_smart_unknown.md)
- [pdf_beginners_guide_unknown.md](pdf_beginners_guide_unknown.md)
- [pdf_grok_report.md](pdf_grok_report.md)
- [pdf_data_sources_mapping_2026.md](pdf_data_sources_mapping_2026.md)
- [pdf_jasmyne_cdc_arxiv.md](pdf_jasmyne_cdc_arxiv.md)

### Sources signaux / opérationnel

- [pdf_guide_agent_trading_claude_alpaca.md](pdf_guide_agent_trading_claude_alpaca.md)
- [pdf_guide_trading_bot_bitget_android.md](pdf_guide_trading_bot_bitget_android.md)
- [pdf_guide_signaux_telegram.md](pdf_guide_signaux_telegram.md)
- [docx_choisir_canal_telegram.md](docx_choisir_canal_telegram.md)
- [docx_technique_dexscreener_gmgn.md](docx_technique_dexscreener_gmgn.md)
- [docx_smart_money_wallet_tracking.md](docx_smart_money_wallet_tracking.md)

### Agent architecture (multi‑agent, Aladdin perso, écosystèmes)

- [docx_agents_trading_cadre_llm_multiagents.md](docx_agents_trading_cadre_llm_multiagents.md)
- [docx_agent_orchestrateur.md](docx_agent_orchestrateur.md)
- [docx_amelioration_ecosysteme_agents.md](docx_amelioration_ecosysteme_agents.md)
- [docx_ecosysteme_agents_autodidacte.md](docx_ecosysteme_agents_autodidacte.md)
- [docx_synthese_archi_trading_android.md](docx_synthese_archi_trading_android.md)
- [docx_agent_onchain_cahier_conception.md](docx_agent_onchain_cahier_conception.md)
- [folder_aladdin_jasmyne.md](folder_aladdin_jasmyne.md)
- [folder_agent_hub.md](folder_agent_hub.md)
- [folder_agent_matrix.md](folder_agent_matrix.md)
- [folder_ai_trader.md](folder_ai_trader.md)
- [folder_agent_trading_arena.md](folder_agent_trading_arena.md)
- [folder_tradingagents.md](folder_tradingagents.md)

### Stratégies (docx)

- [docx_strategie_agressivite_3sur5.md](docx_strategie_agressivite_3sur5.md)
- [docx_strategie_agressivite_5sur5.md](docx_strategie_agressivite_5sur5.md)
- [docx_strategie_tsla_xau_btc.md](docx_strategie_tsla_xau_btc.md)
- [docx_strategie_martingale.md](docx_strategie_martingale.md)
- [docx_black_protocole.md](docx_black_protocole.md)
- [docx_synthese_renzo.md](docx_synthese_renzo.md)
- [docx_analyse_video_strategie.md](docx_analyse_video_strategie.md)
- [docx_cahier_charges_investingcom.md](docx_cahier_charges_investingcom.md)
- [docx_strategie_fr_mise_en_page.md](docx_strategie_fr_mise_en_page.md)

### Bitget tooling (code Python ≈ 27 fichiers)

- [folder_python_bitget.md](folder_python_bitget.md)
- [folder_bitget_radar.md](folder_bitget_radar.md)
- [folder_bitget_bot_v4_hardened.md](folder_bitget_bot_v4_hardened.md)
- [folder_bitget_skill.md](folder_bitget_skill.md)
- [folder_getagent_strategies.md](folder_getagent_strategies.md)
- [folder_documents_trading.md](folder_documents_trading.md)
- [folder_scratch.md](folder_scratch.md)

### MCP servers

- [folder_mcp_server.md](folder_mcp_server.md)

### Markdown utiles (`Markdown/`)

- [folder_markdown.md](folder_markdown.md)
- [md_octobot_termux_nextrade.md](md_octobot_termux_nextrade.md)
- [md_octobot_termux_short.md](md_octobot_termux_short.md)
- [md_source_acteurs_crypto.md](md_source_acteurs_crypto.md)
- [md_outils_trading_liens.md](md_outils_trading_liens.md)

### Repos OSS clonés (référence seulement)

- [folder_repo_clones.md](folder_repo_clones.md)

### Skip — bruit, doublons, scraps HTML

- [skip_html_scrap_and_assets.md](skip_html_scrap_and_assets.md)
- [skip_screenshots_and_misc.md](skip_screenshots_and_misc.md)
- [skip_gdoc_gsheet_pointers.md](skip_gdoc_gsheet_pointers.md)
- [skip_duplicates.md](skip_duplicates.md)

## Méthode appliquée

1. Inventaire `package/` (221 fichiers + 159 sous-dossiers) à partir du montage Drive Desktop local (`G:/Mon Drive/Trading/package`).
2. Croisement avec `drive_triage.json` pour ne pas réextraire ce qui est déjà tracé.
3. Pour chaque entrée pertinente, une fiche `extraction/<slug>.md` est rédigée :
   titre, type, sujet, valeur, cible, action, notes.
4. Le scrap HTML (≈ 90 .html + autant de `_files/`), les screenshots, les pointeurs
   `.gdoc/.gsheet`, les `desktop.ini` et les doublons sont consolidés dans des fiches
   `skip_*.md` (pas une fiche par fichier — ce serait du bruit).
5. **Hors scope de cette passe** : déplacement / renommage dans le Drive,
   mise à jour de `drive_triage.json`. Seul `extraction/` est touché.
