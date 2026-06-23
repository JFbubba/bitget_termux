---
source: package/*.html (≈ 90 fichiers) + tous les `* _files/` (≈ 80 dossiers d'assets)
       + `0XFNZE~2.HTM`, `HANSHA~1.HTM`, `SACHIN~1.HTM`, `SIGMAT~1.HTM`,
         `WSOL12~1.HTM` (noms 8.3 Windows — copies tronquées)
category: skip-noise
action: skipped
target: —
---

## Pourquoi skip en bloc

Ce sont des "Save As Webpage, Complete" depuis Chrome / Edge : un `.html` + un
dossier `<nom>_files/` avec CSS/JS/PNG. Caractéristiques :

- **Stale** dès le moment de la sauvegarde.
- **Faible signal** : la page d'origine (live URL) est plus pertinente.
- **Lourd** : un seul export pèse souvent > 1 Mo (avec les assets).
- **Bruit** : pollue le diff de tout outil qui indexe le dossier.

Exemples du dump (non-exhaustif) :
- Docs Anthropic, marketplaces de skills, Capafy, Skills4All, Vincent Flibustier,
  Curated Skills, Claude Skills Directory…
- Tutoriels crypto (Binance Academy, Binance Square, Investing.com, Hyperliquid).
- Pages GitHub de repos (déjà visibles via les URLs).
- Pages MCP market, IBKR Campus, LSEG, FMP, etc.
- `0XFNZE~2.HTM` & co : noms 8.3 = copies Windows tronquées (souvent doublons
  d'autres .html).

## Cible d'intégration
- Aucune. Si un sujet d'une page reste pertinent, **bookmarker l'URL** plutôt
  que garder le `.html` + `_files/` (cf. `md_outils_trading_liens.md`).
- Suggestion (hors scope cette passe) : déplacer tout ce bloc dans
  `package/_html_archive/` côté Drive pour reprendre le contrôle visuel.
