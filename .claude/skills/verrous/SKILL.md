---
name: verrous
description: État EFFECTIF de tous les verrous d'exécution du bot (armé/paper + SOURCE .env vs config) et recommandation MESURÉE de ce qui pourrait passer ON/OFF. À utiliser pour « qu'est-ce qui est en OFF qui peut passer en ON ? », « qu'est-ce qui est armé ? », « état des verrous », « quels leviers sont actifs ? ».
---

# /verrous — état effectif des verrous + recommandation mesurée

Répond en un coup à la question récurrente de l'audit 22/07 (« qu'est-ce qui est
OFF qui peut passer en ON ? »). S'appuie sur l'outil existant
`verrous_effectifs.py` (SAFE, lecture seule, vraie logique `.env OR config` —
piège ERR-018 documenté dans la fiche mémoire verrous-env-vs-config).

## Procédure

### 1. État brut
```bash
python verrous_effectifs.py
```
Montre chaque verrou avec sa valeur EFFECTIVE et sa SOURCE (.env / config /
défaut). Ne jamais déduire un état d'un grep de config seul.

### 2. Lecture structurée
Regrouper en trois familles :
- **Armé réel** : ce qui trade/agit vraiment aujourd'hui.
- **OFF armable** : verrous à défaut OFF dont l'infrastructure est prête
  (surfaces §67, voix opt-in, MM_AUTO, gates de sizing…).
- **OFF verrouillé par verdict** : ce que les mesures interdisent d'armer
  (cf. fiches « Verdicts de mesure » — ex. FIRM_RISK_DEBATE, porte d'edge).

### 3. Recommandation MESURÉE (jamais d'armement direct)
Pour chaque « OFF armable », une ligne : la MESURE qui justifierait de l'armer
(ex. IC d'ombre ≥ seuil, N trades de preuve, coût mesuré) et où elle en est
(live_ic_audit, voice_shadow_measure, exit_calibration…). Pas de mesure → pas de
recommandation.

### 4. Rappels non négociables
- Les MURS ABSOLUS et le stop −5 % ne sont PAS des verrous : hors sujet ici.
- Un ARMEMENT reste un acte séparé : commit isolé si via dépôt, journalisé +
  notifié Telegram si via .env (§92) — jamais dans la foulée de ce skill.
