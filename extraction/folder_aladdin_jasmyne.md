---
source: package/Aladdin - Jasmyne/
category: agent-architecture
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Vision Crypto-Aladdin perso »)
---

## Contenu (∼25 fichiers)
- docx multiples : `Aladd.docx`, `Aladdin.docx`, `Aladdin_iyiiu.docx`,
  `NERVA2 brouillon.docx`, `dossier_portefeuille_algorithmique_essaim_black_protocol.docx`,
  `echange_complet_trading_aladdin_jasmyne*.docx`, `info strategie.docx`,
  `Structure_et_Formules_Aladdin_Crypto.docx`,
  `Spécifications et Architecture d'un Crypto-Aladdin Personnel.docx` (+ .md).
- xlsx : `Crypto Aladdin - Architecture et Modèles.xlsx`, `Crypto-Aladdin -
  Modélisation et Risque.xlsx` (+ doublons).
- pdf : `Aladdin _260503_055302.pdf`, `Mapping…2026 Structured Guide.pdf` (doublon
  du `Mapping…2026 — data sources.pdf` racine), `jasmyne_cahier_des_charges_style_arxiv.pdf`.
- pptx : `presentation_aladdin_blackrock_cahier_des_charges-1.pptx` et `-2.pptx`.
- stratégies : `strategie_trading_aladdin_style_agressivite_3_sur_5*.docx` et
  `5_sur_5*.docx` (doublons du root).

## Valeur extraite (consolidée)
- C'est **la même vision** que celle déjà tracée par `pdf_jasmyne_cdc_arxiv.md` :
  un BlackRock-Aladdin personnel pour la crypto (risque portefeuille + agents).
- Beaucoup de **doublons** entre docx et entre versions — vrai contenu utile ≤ 5
  documents distincts.
- Les xlsx contiennent vraisemblablement des **formules** (sizing, risque) à
  comparer avec `position_sizer.py` / `risk_manager.py` — à ouvrir séparément.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § « Vision Crypto-Aladdin perso » + checklist (voir
  `pdf_jasmyne_cdc_arxiv.md`).
- Ouvrir les xlsx en mode **lecture seule** pour extraire les formules
  intéressantes ; ne pas importer le xlsx tel quel dans le repo.
- pptx = matériel de présentation, pas pour le repo.
