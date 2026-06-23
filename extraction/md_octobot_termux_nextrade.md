---
source: package/OctoBot on Termux - NexTrade — Documentation complète de session & Prompt Claude Code.md
category: agent-architecture
action: extracted
target: README du repo (déjà aligné), `pc/` si setup, `assistant/` si prompts
---

## Sujet
README **NexTrade** (le nom donné au bot) — bot algo crypto, Bitget, Termux/Android,
Telegram, dashboard Flask, ccxt. **C'est l'ancêtre / la vision** du projet `bitget_termux`.

## Valeur extraite
- **Confirmation d'archi** : EMA 20/50/200, RSI 14, MACD, Bollinger 20, conf
  multi-indicateurs, RR ≥ 1:2, **2 % max** par trade, drawdown 10 % → kill, max 3
  positions, pause macro (FOMC/CPI/NFP), `DRY_RUN=true` par défaut.
- **Stratégies** mentionnées : EMA cross, Bollinger, RSI+MACD, Fibonacci.
- **Pipeline Termux** : pkg → proot-distro Ubuntu → venv → ccxt etc.
- **Telegram commands** stables : `/start /status /prix /portefeuille /trades /stop /aide`.

## Cible d'intégration
- Vérifier que le README du repo `bitget_termux` reflète **toutes** ces règles
  dures (2 %/trade, RR ≥ 2, max 3 positions, DD 10 %, pause macro). Sinon, mise à
  jour à prévoir (hors scope de cette passe).
- `telegram_command_bot.py` — vérifier que la liste de commandes correspond.
- `docs/RESEARCH_NOTES.md` — § « Règles dures NexTrade » directement reprenables.

## Note vie privée
Le fichier mentionne « Jean-François Minet — Entrepreneur indépendant — Liège,
Belgique » dans la section *Auteur*. Pas un secret, mais à savoir si on partage
publiquement le README.
