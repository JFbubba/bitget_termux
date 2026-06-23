---
source: package/strategie_trading_agressivite_5_sur_5.docx (+ `-1.docx` doublon)
       (+ Aladdin variants)
category: strategy-doc
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Profils d'agressivité »)
---

## Sujet
Variante **5/5** (max agressivité) du même cadre — utile pour borner *ce qu'on
n'autorise PAS*.

## Valeur extraite
- Définit la **borne haute** : ce profil n'est PAS souhaité en exploitation, mais
  doit être un **garde-fou** explicite (refus si config trop agressive sauf
  override humain explicite).
- Sert de **test stress** : avec ces params, est-ce que le risk manager refuse
  bien ? bon test à écrire.

## Cible d'intégration
- `config_guard_agent.py` + `risk_manager.py` — ajouter un test qui simule un
  profil 5/5 et vérifie que les limites dures (drawdown cap, max positions)
  bloquent bien avant la ruine.
- `docs/RESEARCH_NOTES.md` — mention dans le § « Profils d'agressivité ».
