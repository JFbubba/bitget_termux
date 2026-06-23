---
source: package/Markdown/ (∼48 fichiers .md)
category: agent-architecture / strategy-doc / crypto-onchain (mixte)
action: extracted (consolidé)
target: docs/RESEARCH_NOTES.md (selon le sujet de chaque .md)
---

## Contenu (extrait, ∼48 .md)
- **Agents** : `AGENTS.md`, `agent.md`, `agent_defi.md`, `agent_security.md`,
  `agent_tax_be.md`, `agent_trading.md`, `_Agent Orchestrateur .md`,
  `HERMES_SKILL1.md`, `bitget_skill.md`.
- **Aladdin / Nerva** : `Aladd.md`, `NERVA2 brouillon.md`, `Nerva 1.md`,
  `Amélioration Écosystème Agents IA.md`.
- **Contexte** : `CRYPTO_CONTEXT.md`, `CRYPTO_DEFI_CONTEXT.md`,
  `Acteurs Clés Du Monde De La Finance Et De La Crypto En 2026.md`,
  `acteurs finance.md`.
- **Stratégies** : `Stratégie _ Martingale.md`, `Synthese_Conversation_Renzo_Protocol.md`,
  `Synthèse Architecture Trading Android.md`, `conversation_strategie_trading_bitget*.md`.
- **Memecoin / on-chain** : `Smart Money Wallet Tracking*.md`, `meme coin.md`,
  `meme pool.md`, `crypto pour enfants.md`.
- **Outils** : `bitget_dashboard.md`, `outils-trading-tries.md`,
  `prompt-tradingagents-fable5*.md`,
  `script-python-final-collecte-analyse-et-génération-de-signaux-de-trading-crypto.md`.
- **Algo / Quant** : `algo.md`, `alch.md`, `alchemy.md`, `gravia.md`, `gestion-de-patrimoine-crypto-…institutionnels-et-baleines.md`.
- **Misc** : `Guide Obsidian.md`, `RESUME_SESSION_2026-05-07.md`,
  `compass_artifact_wf-…_text_markdown.md`, `info strategie.md`, `noeuds val.md`,
  `zennbot.md`.

## Valeur extraite (méthode)
- Beaucoup de **doublons** avec les `.docx` racine (mêmes contenus exportés en md).
- Le **vrai signal** est dans :
  - `agent_defi.md`, `agent_security.md`, `agent_tax_be.md`,
    `agent_trading.md` — design d'agents spécialisés ;
  - `prompt-tradingagents-fable5*.md` — prompts d'agents (ressource précieuse pour
    `assistant/` si on construit un agent généraliste) ;
  - `script-python-final-collecte-analyse-et-génération-de-signaux-de-trading-crypto.md`
    — squelette de pipeline ;
  - `gestion-de-patrimoine-crypto-théorie-algorithmes-et-stratégies-pour-les-institutionnels-et-baleines.md`
    — long-form quant-portfolio (à fouiller).

## Cible d'intégration
- Plutôt qu'une fiche par .md (du bruit), traiter chaque famille **groupée** :
  - agents → consolider dans `docs/RESEARCH_NOTES.md` § agents spécialisés (defi,
    security, tax-be, trading) avec, pour chacun, 5 lignes : rôle, outils, garde-fous.
  - prompts fable5 → si on construit un agent généraliste, partir de ce template.
  - script collecte/analyse → cross-check avec `journal_scanner.py`.
- Doublons des .docx déjà fichés ici → ignorer.
