---
source: package/[12] Lewis, Michael - Flash Boys A Wall Street Revolt.epub
category: canon
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Microstructure & HFT — ce qui survit en crypto »)
---

## Leçon canonique
- **HFT / co-location / front-running** sur l'équité US — ce qui nous concerne :
  - l'**ordre book n'est pas une vérité, c'est un produit** (spoofing, layering).
  - sur Bitget perp, l'analogue = **wash trades + chasse aux liquidations**.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § court : « le book affiche, il ne décrit pas ;
  croiser depth + trades agressifs (CVD) pour estimer le vrai flux ».
- futur agent « microstructure » dans `swarm_brain.py` (déjà mentionné dans
  pdf_arxiv_2512_15720) — exposer un signal de **liquidation hunt** quand un cluster
  de stops est balayé.
