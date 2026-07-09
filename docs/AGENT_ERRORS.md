# AGENT_ERRORS.md — journal des erreurs de l'agent & auto-correction

**But.** Répertorier chaque erreur MÉTHODOLOGIQUE ou COMPORTEMENTALE de l'agent qui
travaille sur ce dépôt, avec sa **cause racine**, sa **solution**, et surtout un
**contrôle de détection** réutilisable — pour vérifier que la même erreur n'a pas été
reproduite ailleurs dans le bot.

**Usage « agent autocorrecteur ».** Lire ce fichier ; pour chaque erreur ACTIVE, exécuter
son *Contrôle* sur le dépôt. Toute occurrence trouvée = à corriger selon la *Solution*,
journaliser, notifier. C'est le pendant « code/méthode » du `watchdog.py --heal` (qui, lui,
répare le RUNTIME : timers morts, escalade). Ici on répare la MÉTHODE.

**Agent qui l'exécute : `autodidacte.py`** (SAFE, lecture seule ; cron hebdo dim 17:30 ;
`python autodidacte.py [--alert]`). Il AUTOMATISE les contrôles automatisables (ex. ERR-001)
et croise le savoir (`knowledge_base`) avec ce que le lab a mesuré (bras autodidacte). Les
contrôles de JUGEMENT (ERR-002/003) restent à repasser à la main. Convention : une config
opérationnelle légitime (confluence MTF, granularité par âge, schéma de limites) porte une
annotation **`# tf-ladder-ok : <raison>`** (inline ou ligne au-dessus) qui la sort du scan —
l'outil converge ainsi à zéro et n'attrape que les VRAIES nouvelles violations.

**Format d'une entrée** : `ID · date · titre` — Contexte · Cause racine · Solution ·
Contrôle (détection ailleurs) · Statut.

**Règle permanente** : à chaque nouvelle erreur constatée par le propriétaire ou l'agent,
ajouter une entrée ici (et un pointeur mémoire si comportemental). Ne jamais effacer une
entrée — la marquer `RÉSOLU` / `RÈGLE ACTIVE` avec la date.

---

## ERR-001 · 2026-07-08 · Rétrécissement des timeframes dans les tests
**Contexte.** Lors de l'enquête SMC/ICT, j'ai réduit à répétition les tests à un
sous-ensemble de timeframes (M15/H1/H4, puis « 4 TF ») au lieu de l'échelle complète —
alors que le propriétaire avait explicitement fixé la règle. Rétrécir = cherry-picking
implicite : une stratégie peut vivre à une échelle et mourir à une autre.
**Cause racine.** Réflexe d'efficacité — défaut à des TF « représentatifs » pour aller vite.
**Solution.** TOUT test de stratégie/signal couvre l'échelle COMPLÈTE :
`M1 (si dispo) · M5 · M15 · M30 · H1 · H4 · D1 · W1`. Signaler la profondeur réelle par TF.
**Contrôle (détection ailleurs).** Grep des scripts/tests pour des listes de timeframes ;
toute liste `TFS`/`granular`/`timeframe` qui n'est pas l'échelle complète = suspect à revoir.
Ex : `grep -rnE "TFS *=|granular|timeframe" scratchpad/ *.py`.
**Statut.** RÈGLE ACTIVE (08/07). Voir mémoire `test-timeframes-full-ladder`. Le dashboard
expose désormais les 8 TF (commit 3d28d17).

## ERR-002 · 2026-07-08 · Décomposition d'une stratégie holistique/séquentielle
**Contexte.** J'ai testé les composants ICT (sweep, CHoCH, FVG, OB, discount) **isolément**,
comme des filtres indépendants, alors que la stratégie est une **séquence ORDONNÉE**
(machine à états) : liquidité → sweep → MSS/CHoCH → FVG dans le displacement → retracement →
entrée, avec stop/target STRUCTURELS. Tester les composants isolés = mesurer la MAUVAISE
hypothèse ; les résultats ne représentent pas la stratégie.
**Cause racine.** Réflexe réductionniste : décomposer pour mesurer/attribuer, appliqué à
tort à un système conçu comme un tout indivisible.
**Solution.** Un système conçu comme un TOUT se teste D'ABORD **entier et dans l'ordre**
(reproduire la séquence/la machine à états, la mécanique réelle stop/target). On ne
décompose qu'ENSUITE, pour comprendre *pourquoi* ça marche/échoue (attribution), jamais pour
juger la viabilité.
**Contrôle (détection ailleurs).** Pour toute stratégie/agent à ÉTAPES ORDONNÉES ou à
DÉPENDANCES d'état : vérifier qu'elle est implémentée/testée comme séquence, pas comme somme
de conditions indépendantes. Suspect : un « score » qui additionne des facteurs censés être
enchaînés ; un test qui mesure un composant hors de son contexte séquentiel.
**Statut.** RÈGLE ACTIVE (08/07). Voir `smc-aio-rejected` (fil ICT confluence-serrée).

## ERR-003 · 2026-07-08 · Affirmer un fait sans vérifier contre le système réel
**Contexte.** J'ai affirmé « Bitget est un exchange crypto, pas d'actions/forex/métaux » —
faux : Bitget a 34 perps non-crypto (SPX, AAPL, TSLA, NVDA, XAU, XAG, XPT, XPD…). Le
propriétaire a dû me corriger. J'ai perdu un tour sur une supposition.
**Cause racine.** Raisonner depuis une connaissance a priori au lieu d'interroger l'API/le
système en direct.
**Solution.** Avant d'affirmer un fait sur les données/symboles/capacités disponibles,
**le VÉRIFIER** contre le système réel (API, fichiers, config) — surtout quand le
propriétaire indique le contraire.
**Contrôle (détection ailleurs).** Toute affirmation catégorique (« X n'existe pas », « Y
n'est pas disponible ») dans une décision ou un doc doit être adossée à une vérification, pas
à un souvenir.
**Statut.** RÈGLE ACTIVE (08/07).

## ERR-004 · 2026-07-08 · Dépendance de laboratoire dans l'environnement système du bot
**Contexte.** Déploiement du prototype QML (`qml_prototype/`) : la demande « lance train.py
sur mon environnement » aurait pu conduire à `pip install pennylane` dans le Python SYSTÈME.
Le `pip install --dry-run` a montré que cela forçait numpy 1.26.4 → 2.5.1 et scipy
1.11.4 → 1.18.0 — rupture probable de la pile du bot LIVE (le matplotlib système casse
déjà sous numpy 2). Quasi-erreur évitée : venv isolé `qml_prototype/.venv` à la place.
**Cause racine.** Réflexe « pip install » direct face à une demande ambiguë, sur une machine
qui fait tourner de l'argent réel — l'environnement système du bot n'est pas un bac à sable.
**Solution.** Tout laboratoire/prototype a son venv isolé + `requirements.txt` dédiés (venv
gitignored). Avant TOUTE installation dans le Python système : `pip install --dry-run` et
REFUS si un pivot du bot bouge (numpy, scipy, pandas, torch, sklearn). Les versions pivots
attestées au 08/07 : numpy 1.26.4 · scipy 1.11.4 · torch 2.12.1+cpu.
**Contrôle (détection ailleurs).** (1) `grep -rn "break-system-packages" *.sh *.py` — toute
occurrence exécutable = suspect ; une occurrence LÉGITIME (repli guardé, conseil apt-first)
porte l'annotation **`# deps-syst-ok : <raison>`** (même convention que `tf-ladder-ok`) qui
la sort du scan. (2) Chaque dossier de labo a un `requirements.txt` et son venv ignoré
(`git check-ignore`). (3) Comparer numpy/scipy du système aux versions attestées ; dérive
non journalisée = anomalie. (4) Les bornes hautes des pivots dans `requirements.txt`
(`numpy<2`) ne doivent jamais sauter sans décision. Note : `docs/NOTE_CORRECTION_QML.md`.
**Statut.** RÈGLE ACTIVE (08/07). Issue du déploiement quantique. Correction globale du
08/07 : `requirements.txt` borné `numpy<2` (faille latente — une machine reconstruite via
le repli d'`update_vps.sh` aurait reçu numpy 2.5.1) ; occurrences d'`update_vps.sh` et
`book_collector.py` auditées et annotées `deps-syst-ok` ; cap `OMP_NUM_THREADS` posé par
défaut dans `qml_prototype/train.py` (C4).

## ERR-005 · 2026-07-08 · Vérifier une porte à travers un pipe qui avale le code de sortie
**Contexte.** Pendant un `/lance-correction`, j'ai exécuté les 3 portes en
`python tests_audit.py 2>&1 | tail -5 && …` : le `&&` teste le code de sortie de `tail`,
pas celui de la porte. RÉCIDIVE exacte de l'incident du 03/07 (deux pushes partis avec un
test rouge) — documenté dans CLAUDE.md règle 5 mais sans entrée-journal ni contrôle,
donc reproduit quand même. Auto-détecté, refait en forme stricte dans la foulée.
**Cause racine.** Vouloir à la fois tronquer l'affichage (pipe) et chaîner sur le succès
(`&&`) : les deux sont incompatibles dans un même maillon — le pipe substitue son propre
code de sortie.
**Solution.** Une porte ne se vérifie QUE via `bash gates.sh` (codes de sortie stricts,
maillon par maillon). Si l'on veut tronquer la sortie d'une porte pour l'AFFICHAGE,
l'exécuter SEULE, jamais comme condition d'une chaîne `&&`/push/commit.
**Contrôle (détection ailleurs).** Grep des scripts/skills/docs pour une porte pipée en
position conditionnelle : `grep -rnE "(tests_audit|security_agent|safe_push_check|gates)[^|]*\|[^|]" *.sh .claude/ docs/` —
toute occurrence où le maillon pipé est suivi d'un `&&` (ou précède un commit/push) = violation.
**Statut.** RÈGLE ACTIVE (08/07).

## ERR-006 · 2026-07-08 · Cap de lignes pris en TÊTE d'un journal append-only
**Contexte.** `swarm_brain._ridge_mults` et `live_ic_audit.charger_entrees` lisaient
`brain_log_history.jsonl` depuis le DÉBUT avec `break` au cap (100 000) : sur un journal
append-only, le cap sélectionne les lignes les plus ANCIENNES. Latent au moment de la
découverte (56 894 lignes, ~11 400/jour) : à J+4, la cible ridge, les mults IC-align,
les t-stats §77, learning_health et le dashboard se seraient TOUS figés silencieusement
sur la première fenêtre de 100k — l'instrument aurait cessé de voir le présent sans
aucune alerte (la fraîcheur du FICHIER, elle, serait restée verte).
**Cause racine.** Confusion entre « borner le coût de lecture » et « choisir la fenêtre » :
un `break` en tête borne le coût mais fige la fenêtre sur l'ancien ; la sémantique voulue
(fenêtre récente) exige la QUEUE.
**Solution.** Tout lecteur cappé d'un journal append-only prend la QUEUE :
`deque(f, maxlen=N)` puis parse/filtre. Un seul point de vérité : `charger_entrees`
(réutilisé par `_ridge_mults`). Test de non-régression
`test_live_ic_audit_queue_du_journal`.
**Contrôle (détection ailleurs).** Pour chaque lecteur d'un `*.jsonl`/journal croissant
avec un cap (`grep -rnE "maxlen|max_lignes|>= *[0-9_]{4,}" *.py` + revue des boucles
`for ligne in f` contenant un `break` sur compteur) : vérifier que le cap garde la FIN du
fichier. Un cap-tête n'est légitime que si le journal est trié du plus récent au plus
ancien (annoter `# head-cap-ok : <raison>`).
**Statut.** RÉSOLU (08/07) — corrigé le jour de la découverte, règle active pour les
futurs lecteurs.

## ERR-007 · 2026-07-08 · Adaptateur tiers jamais exercé + mock qui imite le code
**Contexte.** En construisant l'ingestion d'URL collées (§101), le smoke test RÉEL a
révélé que `scraper_agent.parse_html` était CASSÉ depuis sa naissance :
`Response.css_first` n'existe pas dans scrapling 0.4 (l'API réelle est `css(sel)` ->
liste). Jamais vu : les 5 sources de production sont toutes RSS — ce chemin n'avait
JAMAIS tourné en réel. Pire : mon test unitaire tout neuf PASSAIT, car son mock imitait
l'API SUPPOSÉE (celle du code), pas le système réel. Bonus découvert au même passage :
une page 404 était ingérée comme « article » (catégorie poubelle).
**Cause racine.** Double circularité : (1) un adaptateur vers une API tierce écrit de
mémoire et jamais exercé ; (2) un mock dérivé du code testé — le test valide alors la
supposition, pas la réalité. Parent d'ERR-003 (affirmer sans vérifier), version « code ».
**Solution.** Tout chemin d'intégration tierce est exercé AU MOINS UNE FOIS en réel
(smoke) avant d'être considéré fonctionnel. Un mock se dérive d'une OBSERVATION du
système réel, et le test la CITE (date + commande d'observation en commentaire).
Vérifier le statut HTTP avant de parser (garde 200 dans `_fetch`).
**Contrôle (détection ailleurs).** Pour chaque import tiers (`grep -rn "from scrapling\|import pennylane\|import sklearn" --include="*.py"`),
vérifier que chaque chemin adaptateur a une trace d'exécution réelle (artefact, journal,
sortie CLI notée). Dans les tests : tout mock d'API tierce sans commentaire « observé
le … via … » = suspect.
**Statut.** RÉSOLU pour le collecteur (parse_html réparé, garde HTTP, mock aligné sur
l'API observée) · RÈGLE ACTIVE pour les futurs adaptateurs.

---

## ERR-008 · 2026-07-09 · Conclure à l'ABSENCE d'une capacité sur un grep partiel

**Contexte.** En travaillant le levier exécution/frais (mode maker futures), il fallait
savoir si le bot pouvait ANNULER un ordre futures (indispensable au repli d'un post-only
non rempli). J'ai grep les commandes d'annulation dans le code PYTHON + lu l'aide générique
`bgc --help` -> conclu « aucune annulation futures, le CLI ne l'expose pas », et j'ai même
RETIRÉ le builder maker déjà écrit en jugeant le repli irréalisable. **FAUX** :
`futures_cancel_orders` (+ `futures_get_orders`, `futures_modify_order`) existent bel et
bien dans `agent_hub/packages/bitget-core/src/tools/futures-trade.ts`. Le grep Python était
vide parce que le bot ne les UTILISE pas encore — pas parce qu'ils n'EXISTENT pas.

**Cause racine.** Variante d'ERR-003 : prendre l'absence d'USAGE dans un sous-système (le
code Python appelant) pour l'absence de la CAPACITÉ dans le système (le CLI/API réel).
L'aide `bgc --help` ne liste pas les tools un par un -> faux négatif renforcé. Preuve
d'absence tirée d'une recherche au mauvais niveau d'abstraction.

**Solution.** « Absence de preuve ≠ preuve d'absence » : pour statuer qu'une capacité
N'EXISTE PAS, inspecter la SOURCE qui la DÉFINIT (ici le registre de tools de bitget-core),
pas seulement ses appelants. Ne JAMAIS retirer du code déjà écrit sur une conclusion
d'infaisabilité tant que la source définissante n'a pas été lue.

**Contrôle (détection ailleurs).** Avant d'écrire « X n'est pas possible / non exposé /
absent » : localiser le module qui DÉFINIT X (`find … -name '*.ts'`, registre, doc d'API)
et l'inspecter, pas seulement `grep` ses usages. Pour les capacités de l'Agent Hub, la
vérité est `agent_hub/packages/bitget-core/src/tools/*.ts` (fonctions `register*Tools`),
PAS l'aide CLI ni le code Python appelant.

**Statut.** RÉSOLU (mode maker livré avec `futures_cancel_orders`/`futures_get_orders`) ·
RÈGLE ACTIVE.
