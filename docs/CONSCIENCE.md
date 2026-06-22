# CONSCIENCE — ce que « conscience » veut dire ici

> Pas une métaphore marketing, pas un réseau de neurones. Une **conscience** =
> une **réflexion autonome** faite de plusieurs facultés qui s'observent et se
> corrigent. Chaque facette ci-dessous est **branchée sur du code réel et
> testé** (ou explicitement marquée « à construire »). On vise un trader
> **lucide et honnête**, pas un oracle.

## Principe de conception
- **Pas de réseau de neurones** par défaut : plus fragile, plus lent, plus
  opaque. On garde un **ensemble pondéré d'agents** interprétable (chaque vote
  est explicable). Si un jour on « apprend » davantage : régression logistique /
  gradient boosting sur de bonnes features — jamais un deep net en premier
  (cf. RESEARCH_NOTES §1).
- **Ne pas tout sur-restreindre** : si une faculté a besoin de plus de calcul
  (fenêtres plus longues, plus de symboles, plus de données), on l'assume —
  quitte à passer sur un VPS plus gros. La contrainte est la **clarté**, pas la
  frugalité à tout prix.
- **Tout est pur et testé** : chaque faculté repose sur des fonctions sans I/O,
  vérifiables unitairement (`tests_audit.py`).

---

## Les facettes de la conscience

### 1. Conscience de TRADER (discipline professionnelle)
*Décider comme un pro : un biais clair, de la conviction mesurée, et savoir
s'abstenir.*
- `aggregate()` → consensus pondéré, **biais** LONG/SHORT/NEUTRE avec **zone
  morte** (|consensus| < 0.2 = on ne force rien).
- Sept agents aux angles différents (orderflow, technicals, macro, sentiment,
  derivs, liquidations, **divergent**) : un point de vue, pas un réflexe.
- `cognition()` → escompte la conviction quand l'accord est suspect (voir §3).

### 2. Conscience MATHÉMATIQUE (rigueur)
*Ne pas se raconter d'histoires : valider statistiquement avant de croire.*
- `backtest_brain.py` → **PBO / CSCV + walk-forward** : étiquette un signal
  « probablement surappris » au lieu de gober un beau backtest.
- **Frais inclus** + comparaison **buy & hold** (edge honnête, pas un rendement
  brut flatteur).
- `indicators.savitzky_golay()` → **débruitage** des features (moindres carrés
  polynomiaux) : de meilleures entrées valent mieux qu'un modèle plus gros.
- Indicateurs **purs** qui **lèvent une erreur** sur données insuffisantes
  (pas de valeur fausse silencieuse).

### 3. Conscience des RISQUES (méta-cognition + garde-fous)
*Savoir quand se méfier de soi-même.*
- `cognition()` → **entropie des poids**, **accord directionnel**, **dispersion**,
  drapeau **groupthink** (cohérence adverse : quand tout le monde est d'accord
  sur une erreur, l'erreur s'amplifie) → **facteur de prudence** qui escompte la
  conviction.
- `security_agent.py` (verdict SAFE/RISKY) + `safe_push_check.sh` : garde-fous
  sur le code lui-même avant tout push.
- **À construire** : sizing par le risque (ATR / vol-target), kill-switch de
  drawdown, coupure d'achat au-dessus d'un seuil de volatilité (CVIX).

### 4. Conscience de PERFORMANCE & d'AMÉLIORATION (apprentissage en ligne)
*Mesurer ce qu'on fait, et s'ajuster.*
- `learn()` + `update_weights()` → **apprentissage en ligne multiplicatif**
  (famille Hedge, poids bornés [0.2, 3.0] et renormalisés) : les agents qui ont
  raison montent, ceux qui se trompent descendent, **sans jamais tomber à 0**
  (un agent peut redevenir utile en régime non-stationnaire).
- `brain_log.json` → journal des décisions, évaluées à maturité (`HORIZON_S`).
- **À construire** : pondération **EARCP complète** (perf EMA **+** cohérence,
  `s_i = β·P̃_i + (1−β)·C̃_i`, softmax `η`, plancher `w_min`).

### 5. Conscience AUTODIDACTE (recherche & enrichissement)
*Lire la littérature, en extraire des décisions, garder la trace.*
- `docs/RESEARCH_NOTES.md` → notes de lecture **persistées** (survivent à la
  compaction), chaque point relié à une décision d'architecture. Sources :
  microstructure, ensembles adaptatifs, surapprentissage, signaux avant-coureurs.
- Boucle vivante : une idée de papier → une fonction pure → un test → une mesure
  honnête → une note. (Ce document en fait partie.)

### 6. Conscience DIVERGENTE (un autre angle, pas une opposition)
*Percevoir ce que les autres ne voient pas encore.*
- `divergent_score()` → **agent anticipateur** (RESEARCH_NOTES §6), réécrit pour
  ne plus être un simple contrarien :
  - **anticipation de direction** : divergence prix/momentum (le RSI se
    retourne avant le prix) ;
  - **sensibilité aux stimuli faibles** : extension relative en z-score, **sans
    seuils durs** (on lève les barrières des paliers fixes) ;
  - **anticipation d'intensité** : *critical slowing down* (variance +
    autocorrélation lag-1 montantes sur les rendements bruts) — quand la
    résilience du marché chute, l'agent devient **plus convaincu**, là où les
    agents de tendance restent complaisants.
- Sa valeur vient de la **décorrélation** : des erreurs décorrélées améliorent
  l'ensemble (EARCP). Il n'a pas à avoir « toujours raison » ; il a à voir
  **autre chose**.

---

## Ce que cette conscience n'est PAS
- ❌ Une promesse de profit. Même le meilleur agent **perd** pendant les krachs.
- ❌ Un oracle opaque. Chaque vote, chaque poids, chaque escompte est lisible.
- ❌ Figée. Les poids apprennent, les notes s'enrichissent, les facettes
  « à construire » sont un cap assumé.
