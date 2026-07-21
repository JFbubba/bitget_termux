# SAVOIR.md — bibliothèque de connaissances du bot (constituée le 03/07/2026, §56)

Savoir externe VÉRIFIÉ et croisé avec nos propres mesures. Chaque acquis porte son
« implication pour le bot ». Règle de la maison : un savoir sans implication
actionnable ou sans source n'entre pas ici.

---

## 1. Agrégation d'experts : le « forecast combination puzzle »

**Acquis** (Stock & Watson 2004 ; Timmermann et al., IJoF 2012 ; UCR WP 2025) :
la moyenne À POIDS ÉGAUX des prévisionnistes bat presque toujours les poids
« optimaux » estimés — l'erreur d'ESTIMATION des poids détruit plus de valeur
que l'optimisation n'en crée. Le gain des poids égaux vient de la variance
évitée, au prix d'un biais minime. Robuste à la mauvaise spécification et aux
changements de régime.

**Croisement avec nos mesures** : c'est EXACTEMENT la saga §51 — cinq mécanismes
d'auto-amplification poussaient un agent au clamp 3.0 sans pouvoir prédictif ;
le mécanisme corrigé (hit-rates exogènes, bornes absolues, lissage 10 %) fait
précisément ce que la littérature recommande : des poids proches de 1.0 qui ne
s'écartent que sur preuve durable.

**Implication** : ne JAMAIS revenir à des poids agressifs. Si un futur audit
montre les poids collés aux bornes [0.2, 3.0] sans support d'IC live, la bonne
réponse est PLUS de shrinkage vers 1.0, pas moins. La sophistication de
pondération est un piège mesuré par 20 ans de littérature.

---

## 2. Tendance vs réversion selon l'horizon (arXiv:2501.16772, Zurich 2025)

*(Synthèse détaillée du papier — voir section dédiée en fin de document.)*

**Croisement avec nos mesures** : notre fait stylisé §35-38 (réversion à courte
échelle) + le verdict 6 ans §55 (savant/geometric positifs sur la durée quand
l'année seule les condamnait) s'inscrivent dans ce cadre : le SIGNE d'un signal
momentum/réversion dépend de l'échelle de temps et du régime.

---

## 3. « Slow momentum, fast reversion » (arXiv:2105.13727, Oxford-Man)

**Acquis** : les stratégies momentum souffrent aux retournements ; combiner un
momentum LENT avec une réversion RAPIDE (détection de points de rupture)
améliore le profil. C'est indépendamment la forme de notre geometric v2 (§48 :
réversion 8 barres + tendance 32 barres qualifiée), que le replay 6 ans a
validée (+0.032) après que l'année seule l'avait condamnée.

**Implication** : garder la structure bi-échelle de geometric ; toute future
retouche doit préserver la séparation lent/rapide.

---

## 4. Discipline anti-cherry-picking (arXiv:2504.10914, Machina Capital)

**Acquis** : le Sharpe d'une stratégie de tendance suit une formule théorique en
fonction du paramètre du signal — les « pics » de backtest hors de cette courbe
sont du bruit sélectionné. Corollaire pratique : un paramètre choisi doit être
sur un PLATEAU de performance, jamais un pic isolé.

**Croisement** : notre pratique (plateau de fenêtre 56-72 pour savant §49,
barre multi-fenêtres §48-55, porte profonde §54) est alignée ; la déflation DSR
du xs (§41) aussi.

**Implication** : à chaque calibrage, tracer la performance en fonction du
paramètre et exiger un plateau — jamais adopter un maximum ponctuel.

---

## 5. Funding des perpétuels : mécanique et régimes

**Acquis** (Ackerer-Hugonnier-Jermann, Mathematical Finance 2026 ; arXiv:2506.08573 ;
données The Block/MacroMicro) :
- le funding est LE mécanisme d'ancrage du perp au spot ; la fonction de
  CLAMPING (bornage du taux) est la cause principale des déviations
  persistantes prix perp / spot ;
- régimes typiques : base « calme » ≈ 0.01 %/8h (~11 % APR), euphorie 0.03 %+
  (~33 % APR et au-delà), marchés baissiers : négatif (les shorts paient) ;
- le carry cash-and-carry est essentiellement une MOISSON D'EUPHORIE : sa
  rentabilité se concentre dans les phases de levier long excessif ;
- volumes perp 2025 : ~62 T$ (Binance ~29 %, OKX/Bybit ~21 % chacun) — la
  liquidité perp domine le spot.

**Croisement** : notre seuil d'entrée carry 5 % APR (hystérésis sortie 2 %) est
bien calé : il ne déclenche qu'au-dessus du régime calme. L'APR actuel ~3.8 %
= NEUTRE correct — le carry attend sa saison, il ne dort pas par erreur.

**Implication** : quand l'historique de funding s'accumulera dans nos journaux
(bills contract_settle_fee §46), passer le seuil d'un niveau ABSOLU à un
PERCENTILE de son historique propre. Ne pas « forcer » le carry en régime calme.

---

## 6. Structure de marché crypto 2026 : l'ère des ETF et des cascades

**Acquis** (Amberdata 2026 ; The Block ; presse spécialisée) :
- les flux d'ETF spot BTC sont devenus l'acheteur/vendeur MARGINAL dominant :
  1.7 G$ d'entrées en janvier 2026 -> spike ~97k ; sorties de mai -> drawdown ;
- cascades de liquidations récentes : 10/10/2025 = 2.3 G$ liquidés en un jour
  (86 % des longs, record historique) ; février 2026 = 2.56 G$ sur carnets
  minces ; le dé-levier cumulé ~31 G$ ;
- la part institutionnelle (CME) croît -> à terme, carnets plus profonds et
  cascades moins violentes, mais PAS encore : les carnets minces amplifient.

**Implication** : (a) nos agents liquidations/derivs gardent leur pertinence —
mais leur IC live mesuré est NÉGATIF (§51) : détecter une cascade n'est pas la
même chose que la trader ; (b) IDÉE DE SOURCE : les flux d'ETF BTC quotidiens
(données publiques) seraient un input marché-large pour l'agent flows — à
évaluer comme chantier (chemin 3, market-timing §39).

---

## 7. Sizing sous queues lourdes : Kelly fractionnaire et vol-targeting

**Acquis** :
- Kelly PLEIN est un plafond théorique jamais praticable : l'erreur
  d'estimation (arXiv:2508.18868) et les queues lourdes (Taleb,
  arXiv:2001.10488 : les moments empiriques sont peu fiables en préasymptotique)
  imposent une FRACTION — ½ Kelly est le standard, ¼ conservateur ;
- le vol-targeting fonctionne mais son coût de turnover se réduit en LISSANT
  l'estimateur de vol (arXiv:2212.07288) ; contrôle adaptatif : 2603.01298 ;
- le levier LUI-MÊME fabrique les queues lourdes et la vol clusterisée
  (Farmer et al., arXiv:0908.1555) : les cascades sont endogènes.

**Croisement** : nos 10 $/trade fixes ≈ Kelly ultra-fractionnaire — correct à
notre échelle. Le GARCH du mandat existe pour le vol-targeting.

**Implication** : le jour où les caps montent (décision propriétaire), sizing =
vol-target avec estimateur LISSÉ, plafonné à ~¼ Kelly ; jamais de sizing
agressif sur des moments estimés en queues lourdes.

---

## 8. Synthèse du papier Zurich (2501.16772, Safari & Schmidhuber) — tendance/réversion, minutes -> décennies

**Le résultat central** (14 ans de tick data + 30 ans journalier + 330 ans mensuel,
24 contrats, PAS de crypto) — la carte des régimes par horizon de tendance :

| Horizon | Régime |
|---|---|
| < ~30 min | RÉVERSION (mais non universelle, artefact tick size en partie, non rentable après coûts) |
| quelques heures -> ~2 ans | TENDANCE — pic du momentum à **6-12 mois** |
| > ~2 ans | RÉVERSION des tendances faibles (cycles économiques), persistance des séculaires |

**Le modèle** : R(t+1) = a + b·φ + c·φ³, où φ = t-statistique de la tendance
(moyenne pondérée des rendements normalisés, poids n·e^(−2n/T)). b = persistance
(dépend de T, pic 3-12 mois), c < 0 = force de réversion (≈ constant sur T).
Journalier 1990-2020 : b=+1.29 % (t=3.0), c=−0.62 % (t=2.7), R²adj ~4 bp en
AGRÉGEANT 10 horizons — juste assez pour les Sharpe ~1 des trend-followers.

**Règles pratiques extraites** :
1. Momentum : lookback jours -> 2 ans, optimum 6-12 mois ; agréger ~10 horizons
   (une seule échelle = signal noyé, 1 bp vs 4 bp).
2. SUR-EXTENSION quantifiée : E(r) = bφ + cφ³ n'est pas monotone — espérance
   max à φ* ≈ 0.8-1.3 (selon horizon), NULLE à φ ≈ 1.4-2.2, négative au-delà :
   « by the time a trend has become so obvious that everybody can see it in a
   price chart, it is already over ». Ne jamais chasser une tendance de
   t-stat > ~1.5.
3. L'edge momentum S'ÉRODE : b décroît depuis les années 90, b -> 0 estimé
   entre 2010 et 2030 (97.5 % de confiance). Dimensionner les attentes.
4. Universalité valable seulement 1 h ≤ T ≤ ~1 an, actifs traditionnels.

**Croisement honnête avec NOS mesures** : notre horizon de trading (8 h, lookback
8-32 barres 1h) est à la LISIÈRE basse de leur régime de tendance — et nos
mesures crypto y trouvent de la RÉVERSION (§35-38, 4 confirmations), là où leurs
actifs traditionnels tendent déjà. Crypto n'est PAS dans leur univers : marché
24/7, levier retail, cascades — la transposition directe est interdite ; c'est
NOTRE replay 6 ans qui fait foi pour nos actifs.

**Implications pour le bot — chantiers MESURÉS le jour même (§57)** :
- momentum LENT (φ Zurich, T=90/180/270 j, bougies 1D, 6 ans, 4 symboles,
  horizons 7/30 j) : **NO-GO en crypto** — T=180j au mieux +0.026 (t 1.3,
  bruit), T=270j SIGNIFICATIVEMENT contrarian (−0.042, t −2.0). La carte des
  horizons ne se transpose pas : la crypto 2020-2026 casse ses tendances
  longues (flips de régime violents). Cohérent avec leur caveat (crypto absent,
  b -> 0) ;
- cap de sur-extension |φ|>1.5 : ne sauve pas le signal quotidien (mesuré) ;
  geometric (32 barres 1h) laissé INTACT — pas de retouche sans gain mesuré ;
- l'agrégation MULTI-HORIZONS reste l'acquis le plus solide (écho du
  combination puzzle §1) — c'est déjà l'architecture du cerveau (14 agents).

---

## 9. Market making HFT : les principes Virtu Financial (ajouté le 07/07/2026, §94)

**Le savoir** (prospectus IPO + rapports annuels Virtu, synthèse propriétaire) :
Virtu est un teneur de marché non-directionnel : cotations passives bid/ask
simultanées, capture de micro-écarts sur des volumes colossaux (5,3 M trades/jour
en 2014), ~51-52 % de trades gagnants seulement — mais 1 seule journée perdante
sur 1 278 (loi des grands nombres + neutralité). Piliers : (1) NON-DIRECTIONNEL
— toute exposition est immédiatement adossée/fermée, le profit vient du spread,
jamais de la tendance ; (2) CONTRÔLE D'INVENTAIRE strict (taille notionnelle
plafonnée, exposition réduite automatiquement aux seuils) ; (3) GESTION DU RISQUE
multicouche — contrôles pré-négociation qui VERROUILLENT la stratégie sur
anomalie (reset manuel requis), limites par modèle, surveillance temps réel
mark-to-market, comités indépendants ; (4) diversification 235+ places, 36 pays,
aucune zone >30 % des revenus ; (5) technologie propriétaire bout-en-bout
(latence milliseconde, 24 h/24 sans intervention humaine). Limites connues :
compression des spreads (concurrence HFT), dépendance totale à la techno (un bug
= pertes immédiates), régulation (l'AMF a sanctionné Madison Tyler en 2015 pour
arbitrage cross-plateformes trompeur — la frontière manipulation est proche),
adverse selection (besoin de ML pour la détecter).

**Ce qui NE se transpose PAS chez nous** : la vitesse (REST retail = secondes,
pas microsecondes — on PERD la course à la file d'attente), la colocation, le
rebate maker des bourses actions, l'échelle. Un retail qui « copie Virtu »
naïvement fournit de la liquidité STALE : il se fait cueillir par plus rapide
que lui (adverse selection structurelle). Réf. académique du cadre d'inventaire :
Avellaneda & Stoikov (2008) — déjà noté « exigeant » dans simons_agent.py.

**Implications pour le bot (§94 — market_maker.py, transposition HONNÊTE)** :
- market making LENT et post-only STRICT : jamais preneur, spread cible JAMAIS
  sous les frais aller-retour (2×fee+buffer = 23 bps par défaut) — sous ce
  plancher, chaque aller-retour PERD par construction ;
- prix théorique = 0.70×microprice + 0.30×mid ; réservation glissée CONTRE
  l'inventaire (Avellaneda-Stoikov simplifié, décalage borné au demi-spread) ;
- l'équivalent retail du « verrouillage » Virtu : gardes pré-cotation
  fail-closed (carnet illisible/disloqué, premium cross-exchange = notre
  détection d'adverse selection minimale via fair_price §44, warm-up de vol),
  stop local journalier du module, kill-switch global, murs de surface ;
- mesure-d'abord (§45) : DRY par défaut (MM_AUTO=0), le journal .mm_journal.jsonl
  mesure le spread capturable AVANT tout armement — l'edge du MM retail lent
  n'est PAS acquis, il doit être PROUVÉ sur nos fills.

---


## 10. Diversité d'un comité de LLM : elle vient des DONNÉES, pas des rôles (mesuré le 20/07/2026, §106)

**Acquis (mesuré sur ce bot, pas lu).** Dans un comité multi-agents LLM, donner à plusieurs
voix des INSTRUCTIONS DE RÔLE différentes (haussier/baissier, agressif/neutre/conservateur)
sur un CONTEXTE IDENTIQUE ne produit AUCUNE diversité : les voix rendent le même texte
(similarité de Jaccard **1,00**, y compris entre deux rôles explicitement adversaires). En
revanche, différencier les voix par leurs **DONNÉES D'ENTRÉE** (chaque analyste reçoit des
blocs distincts : prix/orderflow, sentiment/funding, macro, on-chain) produit une divergence
franche (similarité **0,00**, étendue de biais 0,50).

**Mécanisme.** Un persona est une contrainte FAIBLE : elle est noyée par le contexte partagé,
qui domine la génération. Une entrée différente est une contrainte FORTE : elle change ce
qu'il y a à dire. La taille du modèle module l'effet (un 7b redescend à 0,22 de similarité
entre personas) mais ne l'annule pas — et un modèle assez gros pour tenir un rôle ne tient
pas dans le budget latence/RAM de ce VPS (§105).

**Implication opérationnelle.** (1) Ne jamais construire un « débat » ou un « comité »
d'agents dont la seule différence est le prompt de rôle — c'est un écho qui COMPTE PLUSIEURS
FOIS le même avis et fabrique une fausse confiance (ici, cela triple-pondérait le trader et
polluait la mesure d'ombre). (2) Pour obtenir de la vraie diversité : donner des DONNÉES
différentes, des horizons différents, ou des méthodes différentes — pas des personnalités.
(3) Contrôle systématique avant de croire un comité : mesurer la similarité texte-à-texte
entre les voix ; deux voix adversaires qui se ressemblent à ≥0,8 invalident l'étage.

## 11. Ingénierie d'exécution : les invariants d'un moteur production (Nautilus Trader — ajouté le 21/07/2026)

**Acquis (lu, et recoupé avec nos propres incidents).** Les moteurs d'exécution de qualité
production (référence : Nautilus Trader — parité recherche→live, cœur déterministe, design
crash-only) convergent sur six invariants (1–4 : Nautilus Trader ; 5–6 : recoupés le même
jour d'un bundle d'architecture multi-agents, trié anti-doublon) :

1. **L'exchange est la SOURCE DE VÉRITÉ.** Au démarrage on RÉCONCILIE : l'état local est
   régénéré/aligné depuis la venue (mass status), jamais l'inverse. Un ordre orphelin se résout
   par une requête CIBLÉE à la venue AVANT d'être marqué rejeté/annulé.
2. **Machine à états d'ordre avec états AMBIGUS explicites.** SUBMITTED → ACCEPTED →
   PARTIALLY_FILLED → FILLED/CANCELED/REJECTED, plus les états in-flight (PENDING_UPDATE,
   PENDING_CANCEL). Un submit jamais acquitté reste « in-flight » : on interroge la venue
   (seuil ~5 s, N tentatives) et on ne résout REJECTED qu'ensuite — jamais par supposition.
   Corollaire anti-double-annulation : EXCLURE PENDING_CANCEL des filtres d'annulation.
3. **Journal write-ahead / event sourcing.** Chaque événement qui change l'état est persisté
   AVANT son handler → recovery et replay possibles après crash.
4. **Résilience mécanique.** Retry à backoff exponentiel + JITTER, circuit breaker, timeouts —
   du code, pas de la discipline.
5. **La parité recherche→live est un HARNAIS, pas un slogan.** On REJOUE une session live
   ENREGISTRÉE à travers le moteur de recherche : même entrée → même décision, exactement ;
   toute divergence est un bug P0, jamais un « détail d'arrondi ». Condition pratique : la
   logique de signal en fonctions PURES (pas d'I/O, pas d'horloge système — le temps est
   INJECTÉ), paramètres en config, sizing séparé du signal.
6. **Réconciliation CONTINUE avec taxonomie des écarts.** Un écart interne↔exchange n'est
   jamais « de l'arrondi » ; il se CLASSE : timing (ordre in-flight → se résout seul,
   documenter), modèle de frais/funding (→ corriger le modèle), fill manqué (→ bug
   d'exécution, escalader), INEXPLIQUÉ (→ condition de HALTE : on n'ouvre plus tant que
   l'écart n'est pas expliqué).

**Implication pour ce bot.** Nos incidents ont déjà fait converger le code vers (1) et (2) par
la douleur : ERR-008 double-position, §109 « accepté ≠ rempli », réconciliation
`accum_reconcile`, « `sl` affiché = intention, pas exchange ». Le fait nouveau est que c'est un
PATTERN standard et complet, pas une série de rustines : toute nouvelle surface d'exécution
(§67) doit NAÎTRE avec ces 4 invariants au lieu de les apprendre par incident. Chaînon manquant
identifié chez nous : la confirmation temps réel par le canal WS PRIVÉ `orders`
(BITGET_REFERENCE §8f) à la place du polling. Deux chaînons de plus (invariants 5-6) : nos
réconciliations (`accum_reconcile`, `futures_report`) constatent en best-effort mais ne
CLASSENT pas les écarts et aucun écart inexpliqué n'est aujourd'hui une condition de halte ;
et il n'existe pas de harnais de rejeu live→recherche (`live_ic_audit` mesure l'IC des voix,
pas la parité décisionnelle) — porté au backlog (PRIORITÉ 1).

## 12. Cadre fiscal belge des plus-values crypto (2026) — factuel, PAS un conseil (ajouté le 21/07/2026)

**Acquis.** Depuis le **1er janvier 2026**, la Belgique taxe les plus-values d'actifs financiers
(crypto incluse) à **10 %** dans le régime de gestion « en bon père de famille ». Mais la
qualification peut être REQUALIFIÉE : **revenus divers à 33 %** (gestion spéculative), voire
**revenus professionnels jusqu'à ~50 %** — et les critères qui accélèrent la requalification
sont précisément le profil de ce bot : **automatisation, levier, fréquence**. Le droit belge ne
fixe pas de seuils chiffrés ; la qualification est une question de fait (comptable,
éventuellement ruling SDA). MiCA, lui, laisse le trading pour compte propre d'un particulier
HORS périmètre CASP : pas d'agrément requis pour ce bot.

**Implication opérationnelle.** (1) Hypothèse de travail prudente : tant que le bot trade
automatiquement, avec levier et fréquence, raisonner en régime **33 %** et **provisionner les
gains nets en conséquence** — le PnL « net de frais » du bot n'est PAS le PnL net du
propriétaire. (2) Le registre exportable des trades (déjà en place : registres + backups
chiffrés quotidiens) est la matière première de toute déclaration ou défense — le conserver
intègre. (3) Avant toute montée significative de volume/notional : consulter un comptable
belge ; un ruling SDA peut figer la qualification. Ces trois points sont FACTUELS et ne
constituent pas un conseil fiscal.

## Traçabilité

Constitué le 03/07/2026 (§56 des RESEARCH_NOTES). Sources primaires citées par
section. Méthode : recherche web + arXiv ciblée sur les questions OUVERTES du
système (pondération d'experts, régimes, funding, structure de marché, sizing),
lecture intégrale du papier pivot par agent dédié, croisement systématique avec
nos propres mesures (§35-55). Prochaine révision : quand une question nouvelle
se pose — pas de collecte sans usage.
