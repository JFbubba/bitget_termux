---
source: package/Synthèse Architecture Trading Android.docx
category: agent-architecture
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Contraintes Android »), `pc/` ou `deploy/`
---

## Sujet
Synthèse d'une **architecture trading sur Android** (Termux), contraintes et
choix techniques.

## Valeur extraite
- Contraintes : pas de daemon système, batterie, killer process Android,
  proot-distro pour avoir un Linux complet.
- Recommandations : **task-keeper** (script qui relance après kill), logs dans
  une zone persistante (pas en `/tmp`), backup périodique via Drive Desktop.
- **Pertinent pour nous** : c'est exactement le terrain de jeu du repo (cf. nom
  `bitget_termux`).

## Cible d'intégration
- Si pas déjà fait, ajouter à `pc/` (ou `deploy/`) un md `android-termux.md`
  consolidant ces points + nos commandes actuelles.
- `docs/RESEARCH_NOTES.md` — § court « contraintes Android » (kill, batterie,
  persistance) à respecter.
