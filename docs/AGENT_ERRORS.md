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

---

## ERR-009 · 2026-07-09 · Test « ancré sur le réel » mais sur le MAUVAIS endpoint (faux-vert)

**Contexte.** Le poll du mode maker lit l'état d'un ordre via `futures_get_orders --orderId`
qui route vers `/api/v2/mix/order/detail`. Suite à ERR-007 j'avais « ancré » le test de
parsing sur une observation réelle… mais celle de `--status history` (`/orders-history`),
dont le schéma DIFFÈRE (`status` vs `state`). Les 3 portes étaient VERTES alors que le chemin
réellement emprunté (`/detail`) n'était validé NULLE PART, et le mock du dépôt (`FuturesOrder`)
n'a aucun champ de quantité remplie. Un `/code-review` xhigh a levé le trou (parmi des bugs de
double-position dans la garde anti-doublon).

**Cause racine.** « Ancrer sur une observation réelle » (ERR-007) ne suffit pas si
l'observation porte sur un endpoint/chemin DIFFÉRENT de celui que le code appelle. Un test
vert sur un schéma voisin ≠ un test du vrai chemin. Ici le code lisait `state OR status` : le
mock à `status` passait, masquant que `/detail` renvoie `state`.

**Solution.** Le mock/ancrage doit provenir de l'EXACT appel que le code fait en prod (même
endpoint, mêmes params). Vérifié le 09/07 : `/detail` exige `--symbol` (sinon `data=None`) et
renvoie `state`+`baseVolume` ; le test ré-ancré dessus.

**Contrôle (détection ailleurs).** Pour tout test qui « ancre » un parsing d'API : confirmer
que la commande/endpoint OBSERVÉ est IDENTIQUE à celui appelé par le code testé (même
sous-commande, mêmes flags). Un mock utilisant un champ que le code lit via un `OR` de repli,
alors que l'endpoint réel renvoie l'autre champ, est un faux-vert.

**Statut.** RÉSOLU (test ré-ancré sur `/detail` réel ; `_order_fill_state` lit `state`+
`baseVolume` via `hub._read`) · RÈGLE ACTIVE.

---

## ERR-010 · 2026-07-09 · Instrument de lecture affichant un cap d'une AUTRE couche à la place du mur d'exécution

**Contexte.** `etat_effectif.py` (créé le 08/07 POUR consolider les verrous et tuer le piège
des caps éparpillés, cf. `verrous-env-vs-config`) affichait sous « CAPS DURS (murs) :
futures » la valeur `MAX_TOTAL_NOTIONAL_USDT = 300` — le cap notionnel de PORTEFEUILLE
(couche `risk_limits`), PAS le mur cumulé futures. Le mur d'exécution futures réel est
`FUT_ABS_MAX_GROSS_USDT = 250` (effectif **200** via `_capped("FUTURES_REAL_MAX_GROSS_USDT"=200, 250)`),
appliqué fail-closed dans `guards()`. Un lecteur (humain/agent) croyait donc le mur cumulé
futures à 300 alors qu'il est 200/250. **Sécurité INTACTE** (guards applique bien 200/250) ;
seul l'INSTRUMENT DE LECTURE trompait — ironie : l'outil censé être la source de vérité
reproduisait une variante du piège qu'il devait tuer. De même le per-trade affiché lisait
`MAX_POSITION_USD` (50) au lieu du cap effectif `FUTURES_REAL_MAX_PER_TRADE_USDT` (50) : même
valeur par coïncidence, donc pas trompeur mais mal sourcé (fragile si l'un des deux bouge).
**Cause racine.** Afficher un cap en le lisant depuis une variable config HOMONYME/voisine
(d'une autre couche de risque) au lieu de la SOURCE qui l'APPLIQUE (le module d'exécution).
Parent d'ERR-003/ERR-008 : supposer qu'une variable nommée « notionnel total » EST le mur
futures, sans vérifier quelle constante `guards()` applique réellement.
**Solution.** Tout instrument de lecture (etat_effectif, dashboard, verrous) affiche les
caps/murs en les lisant à la SOURCE qui les APPLIQUE — ici les constantes `FUT_ABS_MAX_*`
et la fonction `_capped` de `futures_executor` — jamais une variable config d'une autre
couche. Fix : `etat_effectif` importe `FUT_ABS_MAX_PER_TRADE/GROSS_USDT` + `_capped` et
affiche le cap EFFECTIF (50/200) ET le mur (50/250) ; le cap portefeuille 300 est affiché
séparément et étiqueté « couche risk_limits ».
**Contrôle (détection ailleurs).** Pour tout affichage de cap/mur d'exécution, vérifier
qu'il provient de la constante/fonction du module qui l'APPLIQUE, pas d'une variable config
homonyme : `grep -rnE "MAX_TOTAL_NOTIONAL_USDT|MAX_POSITION_USD" --include=*.py dashboard/ *.py`
dans un contexte d'AFFICHAGE = suspect. Une string de mur codée en dur (ex.
`dashboard/server.py:231` « futures 50/250 $ ») est tolérable SI la valeur = les murs absolus
réels, mais fragile — à re-vérifier si un mur bouge (annoter `# mur-hardcode-ok : <raison>`).
**Statut.** RÉSOLU (etat_effectif.py corrigé le 09/07, 3 portes vertes 465/465 · SAFE ·
SAFE PUSH OK) · RÈGLE ACTIVE. Cas toléré signalé : `dashboard/server.py:231` (murs 50/250 en dur, valeur juste).

---

## ERR-011 · 2026-07-10 · Déterminer un succès d'exécution sur un champ de réponse non garanti par l'API

**Contexte.** Le chemin taker futures (`_submit_taker`) concluait le succès via
`_order_id_from(out) is not None`. Or Bitget REMPLIT parfois un `limit_ioc` en renvoyant
`data:{clientOid, orderId:null}` (ordre identifié par le clientOid, ABSENT des fills). Le
durcissement vers l'extraction stricte de l'orderId a introduit un FAUX NÉGATIF : 2 ordres
RÉELLEMENT remplis (HYPE/XRP le 07-09) journalisés `FUTURES_REAL_FAILED`. Trouvé non par
relecture de code mais en MESURANT l'état réel (drill-down dashboard : compter les `orderId:null`),
puis en croisant avec les fills (les 2 « échecs » avaient des round-trips clos avec PnL réalisé).
**Cause racine.** Supposer un INVARIANT d'API (« un ordre exécuté renvoie toujours un orderId »)
sans le vérifier contre le comportement réel. Variante d'ERR-003/ERR-009 appliquée à une
détermination succès/échec : le champ choisi comme preuve de succès n'est pas présent sur TOUS
les chemins de succès, et aucun test ne couvrait le cas `orderId:null`-mais-rempli.
**Solution.** Une détermination succès/échec ne repose jamais sur la seule présence d'un champ
dont l'API ne garantit pas la présence sur tous les succès. Distinguer TROIS issues : succès net
(preuve positive) · rejet EXPLICITE (code d'erreur) · AMBIGU (ni l'un ni l'autre) — et pour
l'ambigu, RÉCONCILIER avec l'état réel (fills/position) avant de conclure, jamais défaut à
« échec ». Un test couvre explicitement le cas ambigu.
**Contrôle (détection ailleurs).** Pour chaque `executed`/`success = <présence d'un champ de
réponse>` dans un module d'exécution (`grep -rnE "executed|success" *executor*.py`), vérifier que
le champ est présent sur TOUS les succès réels (probe API) OU qu'une réconciliation couvre
l'ambiguïté. Les 3 chemins d'exécution sont désormais réconciliés : spot (`7604105`), maker
(`f313f59`), taker (`7e15ae1`).
**Statut.** RÉSOLU (`7e15ae1`, chemin taker réconcilié par les fills — 3 portes vertes 516/516) ·
RÈGLE ACTIVE. Voir mémoire `revue-chemin-argent-fixes`.


## ERR-012 · 2026-07-17 · Juger la VIE d'une boucle sur un journal ÉVÉNEMENTIEL (dédupliqué) au lieu d'un battement per-cycle

**Contexte.** Le 14/07 à 12:08, le watchdog a posé le kill-switch (DOWN×3 → escalade) et
halté le trading réel ~3 j — pour RIEN. `evaluate()` jugeait la vie du scan sur la fraîcheur
de `signals_journal.csv` : or ce fichier est ÉVÉNEMENTIEL (dédupliqué — une ligne seulement
pour un signal NOUVEAU). Dès 11:25, les signaux émis (WLD/ZEC/LIT/EDGE…) sont restés
identiques cycle après cycle → 0 ligne ajoutée → mtime figé >30 min (seuil `2×interval`)
ALORS QUE le scan tournait (la carte de fraîcheur des 17 artefacts affichait « 17/17 frais »
à l'instant de l'escalade). Faux DOWN → faux positif. Aucune perte (portefeuille intact, le
stop −5 % a veillé tout du long) ; le fail-safe a SUR-réagi, il n'a pas déraillé.
**Cause racine.** Confondre « le module a produit un ÉVÉNEMENT récemment » avec « le module
TOURNE ». Un journal événementiel/dédupliqué se fige légitimement quand rien de neuf ne se
produit — il ne prouve PAS l'arrêt. La preuve de vie doit être un artefact écrit
INCONDITIONNELLEMENT à chaque cycle. Aggravant : l'instrument correct existait déjà (la carte
de fraîcheur §61, `artefacts_figes`) mais ne nourrissait qu'une ALERTE, jamais le VERDICT.
**Solution.** Le verdict de vie s'appuie sur un BATTEMENT per-cycle (`SCAN_HEARTBEAT` =
`brain_log.json` + history, écrits à chaque cycle du cerveau ; `heartbeat_fresh`, ANY-fresh).
Artefacts choisis PROPRES : on EXCLUT ceux qui tournent PENDANT une halte (`.runtime_cache.json`
multi-writer, `.stop_guardian_heartbeat.json`) — ils masqueraient une vraie mort. Le journal
événementiel reste une corroboration POSITIVE (OR) ; DOWN seulement si AUCUNE source récente.
Vrai positif (cœur ET journal figés → DOWN) préservé et testé.
**Contrôle (détection ailleurs).** Pour tout signal de LIVENESS/fraîcheur (`grep -rnE
"st_mtime|fresh|figé|stale|périmé" *.py`), vérifier que la source est un artefact écrit à
CHAQUE cycle SANS condition (pas un journal événementiel/dédupliqué, pas un fichier partagé
avec un autre process, pas un heartbeat qui survit à la halte du module surveillé). Un
watchdog/fail-safe ne conclut à la mort que sur le silence d'un battement INCONDITIONNEL.
**Statut.** RÉSOLU (`eef1f63`, 3 portes vertes 518/518 · vérifié en live : cycle watchdog
13:32 → RUNNING? avec battement frais ; reprise du trading réel confirmée) · RÈGLE ACTIVE.
Le contrôle a resservi le 17/07 : **même pattern dans la carte de fraîcheur** — l'entrée
`strategies_out` jugeait la vie du lab sur le mtime du DOSSIER (événementiel : ne bouge que sur
PROMOTION, rare par conception) → figé alors que le lab tournait (alerte chronique 5 min).
Corrigé : `strategy_lab.write_run_stamp()` écrit `strategies_out/.last_run` à CHAQUE run réussi
et le watchdog surveille ce STAMP ; un crash/data-indispo ne stampe pas → figé → vrai positif
conservé (le crash silencieux du run cron de jeudi 16/07 a d'ailleurs été rendu diagnosticable
en ajoutant `>> ~/strategy_lab.log 2>&1` à sa ligne cron). Voir mémoire `watchdog-liveness-heartbeat`.

## ERR-013 · 2026-07-18 · Feature construite + testée mais jamais CONSOMMÉE en production (module dormant)

**Contexte.** Vérification du câblage (18/07) : `taker_flow.py` (Volume Delta REST /
taker-buy-sell) et `bitget_flows.py` (whale/fund net flow) — features orderflow écrites la
veille, chacune avec ses tests dans `tests_audit.py` — n'étaient importées par AUCUN module de
PRODUCTION (dashboard, brain, cron). En live elles renvoyaient pourtant des données réelles
(`taker_delta(BTCUSDT)` → cvd/bias ; `whale_net` → cumul/bias). Construites, testées, vertes aux
portes… et mortes : invisibles au cockpit, ne nourrissant aucune mesure. Idem `listing_hype`
(sim DRY vivant, cron 10 min) dont le bilan round-trips/PnL n'était affiché nulle part.
**Cause racine.** Le cycle « écrire le module → écrire son test → portes vertes → cocher fait »
s'arrête à la couverture de test. Un test qui importe le module MASQUE le fait que rien d'autre
ne l'importe : la porte passe, le module est « couvert », mais il n'est branché à aucun
consommateur vivant. **Couverture de test ≠ intégration au système.** Un artefact n'existe pour
le bot que si un chemin de production (dashboard/brain/cron/boucle) le lit.
**Solution.** Après avoir construit une feature destinée à être consommée (signal, indicateur,
mesure), VÉRIFIER qu'un module de production l'importe. Ici : `taker_delta`/`whale_net` branchés
au bloc `_orderflow_signals` du dashboard (MESURE, aucun vote — banc intact) ; `listing_hype.dry_report()`
au bloc `_methodes` ; `listing_hype.enabled()` (env-first `LISTING_HYPE_LIVE`) pour l'état armé.
**Contrôle (détection ailleurs).** Pour un module applicatif à fonctions publiques, lister ses
importateurs hors tests : `grep -rl "import <mod>" --include=*.py | grep -vE "tests_audit|scratchpad|^\./<mod>\.py"`.
Résultat VIDE ⇒ module DORMANT → décision consciente : le brancher (dashboard/brain/cron) OU
documenter pourquoi il est en réserve (labo, voix gated OFF en attente d'armement — légitime).
Le contrôle SIGNALE, il ne condamne pas : un feature-flag OFF ou un labo de mesure sont des
dormants voulus ; l'erreur est le dormant OUBLIÉ, cru actif.
**Statut.** RÉSOLU (`d9ec12d`, 3 portes vertes 559/559 · vérifié en live : `/api/state` expose
`methodes.listing_hype`, `orderflow_signals.taker_delta`, `orderflow_signals.whale_net`) · RÈGLE ACTIVE.

## ERR-014 · 2026-07-18 · Tester une stratégie SÉQUENTIELLE (machine à états) comme un ET de conditions INSTANTANÉES

**Contexte.** Test de la stratégie ADM/DMI‑ADX de Wilder (collée par le propriétaire). Je l'ai
modélisée comme un booléen unique évalué à la barre du croisement : `croisement +DI/−DI FRAIS ET
ADX>25 ET ADX montant ET EMA200`. Résultat : ~0 trade sur 1D, et j'ai conclu que la règle était
« auto‑contradictoire » et la stratégie REJETÉE. **Faux.** Le propriétaire a corrigé : « c'est
leur INTERACTION dans le temps qui fait la stratégie ; cherche la vraie mécanique ». Le vrai
système de Wilder est une **machine à états** : le croisement ARME un signal (règle du croisement),
on note le **point extrême** de la barre de croisement, et on n'ENTRE qu'à une barre ULTÉRIEURE
qui franchit ce point (**Extreme Point Rule**) ; l'ADX (retardé) est une **porte de régime vérifiée
à l'ENTRÉE**, pas au croisement. Recodé ainsi (`adm_wilder.py`), le système trade normalement
(23 trades/1D vs 0). Verdict final inchangé (pas d'alpha — c'est du beta long, cf. `VERDICTS.md`)
mais pour une raison RÉELLE, révélée seulement par la bonne méthode.
**Cause racine.** J'ai aplati une dimension TEMPORELLE en une condition simultanée. Deux conditions
peuvent être vraies à des MOMENTS différents (le croisement à t, l'ADX qui remonte à t+k) et JAMAIS
à la même barre — les exiger ensemble crée une contradiction ARTIFICIELLE qui ne prouve rien sur la
stratégie, seulement sur ma modélisation. Signe d'alerte que j'ai ignoré : « la condition A ne se
déclenche jamais avec la condition B » (0 sur 1D) aurait dû me faire suspecter un décalage temporel,
pas conclure à un défaut de la stratégie. Prolonge ERR‑002 (tester le TOUT d'abord) : le « tout »
inclut la SÉQUENCE, pas seulement l'ensemble des conditions.
**Solution.** Avant de tester une stratégie, identifier si elle est SÉQUENTIELLE (signal qui arme →
confirmation → entrée décalée → sortie/reverse = machine à états) ou vraiment instantanée. Si
séquentielle : l'implémenter en machine à états avec état persistant, PAS en `ET` de booléens à une
barre. Vérifier la mécanique RÉELLE à la source (livre/doc de l'auteur) avant de coder — ne pas
inférer la règle d'un pseudocode approximatif. **2e apprentissage (couplé) :** pour un système
DIRECTIONNEL à forte exposition, benchmarker contre **buy‑and‑hold** (Sharpe + drawdown + split
long/short) — un gros rendement brut en marché haussier est souvent du BETA capturé, pas un alpha ;
un PnL ~100 % côté long = capacité prédictive nulle.
**Contrôle (détection ailleurs).** Auditer chaque test de stratégie/signal passé et répondre : (1)
la logique testée a‑t‑elle une séquence temporelle (arme→confirme→entre) écrasée en condition
simultanée ou en IC contemporain ? (2) un backtest à ~0 trade / une condition « jamais vraie avec
une autre » a‑t‑il été lu comme un verdict plutôt que comme un signe de mismodélisation ? (3) un
système directionnel exposé a‑t‑il été jugé sur le rendement brut sans benchmark buy‑and‑hold
(alpha vs beta) ? Toute réponse « oui » ⇒ re‑tester avec machine à états + benchmark.
**Statut.** RÉSOLU pour ADM (`adm_wilder.py`, verdict corrigé `VERDICTS.md`) · RÈGLE ACTIVE.
**Audit des méthodes passées (18/07, 3 agents lecture seule)** : 1 seul faux‑rejet potentiel =
**SMC/AIO** (la stratégie la plus séquentielle, rejetée sur confluence contemporaine / composants
isolés sans backtest état‑machine ni B&H → `VERDICTS.md` reclassé « à revérifier », re‑test à faire).
Réserves mineures : (a) `strategy_tester/metrics.py` n'avait PAS de benchmark buy‑and‑hold →
DURCI (fonction `buy_and_hold()` + verdicts `beats_bh_*`/split long‑short branchés dans `compute()`,
`report.py`, `run.py`) ; (b) `struct_break_suite` testé en moyenne simultanée (légitime car AFML =
features parallèles ; re‑tester en séquence seulement si l'ordre CSW→SADF→Chow porte l'info —
décision proprio) ; (c) prospectif : `mql5_codebase_tester/harness.py` ne teste que de l'instantané
→ tout futur EA SÉQUENTIEL doit passer par le moteur événementiel, pas par le harness IC. Tout le
reste (12 signaux/prédicteurs en IC forward, 7 classiques avec edge‑vs‑B&H déjà exigé, labos de
sortie path‑based déflatés) = LÉGITIME, méthode adaptée à la nature du test.
**Re‑tests des 2 suspects séquentiels (18/07, décision proprio « les tester ensemble/en séquence »)** :
(1) **SMC/ICT** re‑codé en machine à états CAUSALE (`smc_ict.py`, causalité vérifiée par troncature) →
rejet CONFIRMÉ (PF méd 0,64‑0,72, Sharpe méd ~−0,5, PnL long ET short négatifs, ne bat pas le B&H) ;
(2) **struct_break** re‑testé en SÉQUENCE ordonnée CSW→SADF→Chow (`struct_break_sequence`) → l'ordre
FLIP l'IC de −0,02 (contrarien) à +0,02 (momentum) — l'interaction change bien la nature du signal,
confirmant l'intuition proprio — mais 0/80 net de frais, edge mangé par les frais. **Bilan ERR‑014 :
le défaut méthodo était RÉEL (2 stratégies séquentielles mal testées) mais une fois corrigé, AUCUNE
ne révèle d'edge caché — corriger la méthode a rendu les DIAGNOSTICS justes (beta vs alpha, momentum
vs contrarien), pas les edges gagnants. Le mur des frais reste le facteur dominant.**
**Ré-audit ÉLARGI (18/07, demande proprio « fais tout »)** : (a) les 14 agents du banc cartographiés
→ 13 votent en INSTANTANÉ (légitime, IC forward adapté) ; SEUL `agent_structure` (`swarm_brain.py:297`)
porte la séquence SMC/ICT compressée en confluence contemporaine → mais c'est SMC, déjà re-testé
(`smc_ict.py`) = pas de gain net → banc gelé §62 justifié. (b) deep-research 102-agents (17/07)
auditée : n'a RIEN backtesté (raisonnement web) → hors périmètre ERR-014 ; liste des pistes non
persistée. (c) SMC re-testé en modèle COMPLET (target structurel + entrée OTE discount) : edge brut
RÉEL mais LOCALISÉ (majors 4H), ne généralise pas net de frais. (d) indicateurs Wilder validés vs
TA-Lib (corr 1,0, venv `/root/talib_venv`). (e) **DERNIER angle du nouveau method — l'INTERACTION,
pas seulement la séquence** : le nouveau method corrige aussi l'analyse des indicateurs pris
INDIVIDUELLEMENT. Le rejet « réversion 7 signaux » (`VERDICTS.md`) reposait sur l'IC de CHAQUE signal
SÉPARÉ (chacun < frais). Re-testé en INTERACTION (`scratchpad/audit_indep/interaction_test.py` :
confluence K‑parmi‑7 + slow‑momentum/fast‑reversion arXiv:2105.13727, backtest événementiel net de
frais, échelle TF complète, cross‑secteur, benchmark B&H, K balayé) → **0/500 config forte, médiane
net_sharpe <0 sur TOUS les TF, gross≈0** aux extrêmes de confluence → l'interaction ne franchit pas
les frais, aucun edge caché (les 7 signaux sont des proxys colinéaires de « a monté »). **BILAN : le
défaut ERR-014 était réel et reproduit plusieurs fois (séquences ADM/SMC/struct_break ET analyse
individuelle des signaux de réversion), mais ne cachait AUCUN alpha — corriger la méthode affine le
diagnostic, le mur des frais + l'exécution maker restent les seuls vrais leviers.** RÉ-AUDIT CLOS
(angles SÉQUENTIEL et INDIVIDUEL tous deux couverts et mesurés).
**Extension MODÈLE JOINT (18/07, demande proprio « teste les rejets + les 102 agents en interaction »).**
Au-delà des re-tests unitaires, on a réuni les indicateurs des labos rejetés ET des pistes du backlog
§104 (la campagne ~102 agents) dans des MODÈLES JOINTS non linéaires (RandomForest + Ridge, WF purgé,
net frais, contrôle SHUFFLE) pour laisser leurs INTERACTIONS créer le signal : (i) geometric_v2 vecteur
complet (`scratchpad/geometric_v2_lab/interaction_geom.py`, 44 configs, net méd −1,19 bps) ; (ii) GLOBAL =
réversion 7 + gates de régime + momentum cross-sectionnel #8 (`scratchpad/audit_indep/global_interaction.py`,
12 configs POOLED cross-sectionnel, net méd −3,24 bps). Dans les DEUX : IC OOS ≈ shuffle, net < frais.
**Piège méthodo repéré et neutralisé** : le seuil automatique a d'abord flaggé 2-3 « pistes » à 1D/4H
long-horizon — mais n minuscule (534/432 vs médiane 2792) + signes INCOHÉRENTS cross-symbole (1D h4 :
ETH +140 / SOL +117 / XRP −42 bps) = le piège « daily-pas-intraday » des 102 agents, reproduit LIVE →
correctement rejeté en exigeant n suffisant + cohérence cross-symbole (leçon : un « hit » du modèle joint
n'est réel que s'il est cohérent cross-symbole ET hors petit échantillon daily). **CONCLUSION : la méthode
interaction, poussée jusqu'au modèle joint de TOUTES les familles, ne révèle AUCUN alpha caché — cohérent
avec le bilan §104 (edge réversion réel ~−0,04 IC mais < frais) et avec les modèles DÉJÀ-joints Darts/TimesFM
(qui combinent tout en interne et échouent pareil). Le mur des frais + l'exécution maker restent les seuls
leviers. Le nouveau method a rendu les DIAGNOSTICS justes, pas des edges gagnants.**
**Ré‑audit LENTILLE MAKER + specs COMPLÉTÉES (18/07 soir, demande proprio « analyse en ensemble pas isolé ;
cherche des infos sur le net pour compléter chaque agent avant de ré‑analyser »).** Deux failles réelles
trouvées AVANT de re‑juger (2 sous‑agents de recherche web) : (1) **specs incomplètes** — `supertrend` en ATR
SMA au lieu de **Wilder/RMA** (écart canonique TradingView) ; surtout le **momentum cross‑sectionnel mal
construit** (rang 8‑barres SANS skip → aux TF intraday capte du REVERSAL, signe inversé ; Jegadeesh‑Titman =
skip‑1, Dobrynskaya crypto = momentum ~2‑3 sem puis flip reversal >1 mois) ; (2) tous les rejets jugés à frais
**taker** seulement, jamais sous la lentille **maker** (le levier documenté). Corrigé (`signals_v2.py` :
SuperTrend Wilder + formation skip‑1 + lead‑lag seesaw ; `joint_v2.py`, `fee_sweep.py`, `geom_fee_sweep.py`,
`exit_fee_sweep.py`, `global_interaction_funding.py`). **Résultat** : sur specs canoniques ET sous maker ET avec
shuffle/déflation, aucune famille intraday ne révèle d'edge robuste (réversion 0/config même à 0 frais ; joint V2
ne bat jamais le shuffle ; funding ΔIC ~0 ; geometric = artefacts). **3ᵉ apprentissage — les OUTILS génèrent des
FAUX POSITIFS que seule la discipline attrape** : (a) `geom_fee_sweep` a flaggé 8 « pistes » = toutes des
artefacts (net +75‑106 bps/BARRE, long‑horizon, signes incohérents cross‑symbole, null shuffle SE≈0,1) ;
(b) `orderflow_lab/ic_measure.py` imprime « EDGE plausible (maker) » sur n≈25 barres (|IC| 0,3‑0,56 = bruit) ;
(c) `exit_calibration` best‑de‑grille « positif à maker » = déflaté ≤0 (sur‑testing) → **la convention RÉELLE des
sorties est négative MÊME à 0 frais** (corrige la mémoire « @4 bps bascule positif »). Filtre requis désormais :
un « hit » n'est réel que s'il **bat le shuffle de marge, survit à la déflation, est cohérent cross‑symbole, a une
magnitude sensée, et tient en HOLDOUT temporel**. **À DURCIR** : `ic_measure.py` (exiger significativité +
cohérence) et le filtre « strong » de `geom_fee_sweep`/`interaction_geom` (trop faible quand le null shuffle a
SE≈0,1 aux longs horizons). **4ᵉ apprentissage — appliquer la méthode ENSEMBLE à la BONNE ÉCHELLE a fait émerger
la SEULE vraie piste** : le momentum cross‑sectionnel **1D** (tri long‑short sur tout l'univers, skip‑1, L=21≈3 sem)
donne +16,9 bps/j net maker (Sharpe 0,89, t 2,35), survit shuffle+déflation, est **market‑neutral** (corr −0,06),
**culmine à L=21 puis redescend** (momentum Dobrynskaya, pas beta) — mais **holdout OOS MARGINAL** (2e moitié
t=1,28) + L instable → **lead réel, pas déployable**, à valider en **walk‑forward à L glissant** (`docs/VERDICTS.md`,
ligne « momentum cross‑sectionnel 1D »). L'analyse par‑indicateur et les joints intraday l'avaient manqué : elle
n'apparaît qu'en traitant l'univers comme un ENSEMBLE cross‑actifs, à l'échelle daily. **WALK‑FORWARD FAIT
(18/07)** : L sélectionné OOS sur train glissant → maker **t=1,62** (+13,4 bps/j), taker t=1,04 ; L fixe 14 j
t=1,12 → **NON significatif OOS** (le t=2,35 plein‑échantillon était gonflé par la sélection in‑sample de L).
Réel, market‑neutral, théorie‑cohérent MAIS sub‑seuil → **VIVANT, pas déployable** ; seul levier = univers
élargi (12→~40 coins = puissance, pas p‑hacking). **5ᵉ apprentissage** : une sélection de paramètre in‑sample
gonfle le t‑stat ; seul le walk‑forward (paramètre choisi OOS) donne le t honnête. **UNIVERS ÉLARGI FAIT
(12→46 coins)** : plein‑échantillon renforcé (t 2,35→2,9) MAIS walk‑forward OOS reste **t=1,51 maker / 0,80
taker** → effet RÉEL mais trop faible pour être tradable seul → **CLASSÉ réel‑non‑tradable**. 6ᵉ apprentissage :
élargir l'univers renforce le plein‑échantillon (puissance in‑sample) sans forcément rescaper l'OOS — un effet
peut être réel ET rester sub‑seuil en effet‑taille.

## ERR-015 · 2026-07-19 · Re-coder / re-mesurer ce qui existe déjà (contexte éphémère + ancrage sur le 1er fichier trouvé)

**Contexte.** Tâche SMC/ICT : j'ai grep `price_action.py`, y ai trouvé FVG/market_structure, et
j'ai ANCRÉ dessus en supposant que c'était tout l'existant. J'ai conçu — et commencé à construire —
un nouveau module, alors que `smc.py` existait déjà : un agrégateur ICT COMPLET (FVG/sweep/ChoCh/
BPR/killzone/PO3/SMT + setup) DÉJÀ câblé au dashboard. Il n'a surfacé que quand un agent de
cartographie a interrogé **graphify**. Même classe d'erreur : re-mesurer une idée DÉJÀ rejetée
(double data inutile — ex. re-tester SMC comme edge alors que `VERDICTS.md` le donne net-négatif).
**Cause racine.** Mon contexte d'agent est ÉPHÉMÈRE (je repars sans le dépôt « en tête » chaque
session). Face à une tâche « ajoute X », j'ancre sur le premier fichier que je trouve et je suppose
qu'il borne l'existant. Les index anti-gaspillage EXISTENT déjà — graphify (graphe de tout le code),
`docs/VERDICTS.md`, `scratchpad/LABOS.md`, la mémoire — mais je ne les consulte pas SUR LE CONCEPT,
en PREMIER. Ce n'est pas un outil manquant, c'est une discipline ratée.
**Solution.** `prior_art.py` — un réflexe UNIQUE `python prior_art.py "<concept>"` qui interroge d'un
coup graphify + symboles def/class + VERDICTS + LABOS + mémoire, et rend un verdict (EXISTE DÉJÀ /
DÉJÀ TESTÉ / rien trouvé). + sous-agent read-only `prior-art-scout` (accès lecture à tout le bot,
aucun Edit/Write). + intégré à `/lance-correction`. À lancer AVANT de concevoir tout module/labo/voix.
**Contrôle (détection ailleurs).** Avant de construire quoi que ce soit de neuf :
`python prior_art.py "<le concept>"`. « ⚠ CODE EXISTANT » ⇒ ÉTENDRE le module, ne pas le re-coder ;
« ⚠ DÉJÀ MESURÉ/REJETÉ » ⇒ lire le verdict avant de re-tester. graphify reste la source précise
(communauté/nœuds) ; le scan de symboles est un filet de secours.
**Statut.** RÉSOLU (`prior_art.py` + `prior-art-scout` + `/lance-correction`, 4 tests, 3 portes vertes)
· RÈGLE ACTIVE.

## ERR-016 · 2026-07-19 · Mesurer un outil de RECONNAISSANCE de structure / d'aide à l'EXÉCUTION comme un signal directionnel PRÉDICTIF (IC)

**Contexte.** SMC/ICT : j'ai mesuré l'IC DIRECTIONNELLE de `smc_shadow` (le biais smc prédit-il le
rendement forward) sur plusieurs régimes → IC≈0 → « aucun edge ». Le propriétaire a corrigé : **SMC
n'est PAS un indicateur prédictif ; c'est la RECONNAISSANCE d'un processus structurel détectable — il
dit OÙ on est dans le mouvement pour bien PLACER ses ordres.** On ne demande pas à un FVG/OTE/BPR/pool
de liquidité de crier « achète », mais « prix en discount, près d'un pool, après un sweep → limit ICI,
stop LÀ ». Mesuré comme un prédicteur directionnel, un outil de placement rend forcément un « no edge »
qui répond à la MAUVAISE question.
**Cause racine.** Réflexe de tester TOUT signal comme une prédiction directionnelle (IC vs rendement
forward). Mais certains modules sont des aides au CONTEXTE / à la LOCALISATION / à l'EXÉCUTION, pas des
prédicteurs. Leur valeur est dans le PLACEMENT des ordres (où poser le limit, qualité de fill, markout,
sélection adverse), pas dans la direction. La lentille IC appliquée à un outil de reconnaissance
GARANTIT un faux « rejeté ». (Le dashboard SMC — carte des zones pour placer — était, lui, le BON usage.)
**Solution.** Avant de mesurer un module, CLASSER son intention : (a) prédicteur directionnel → IC/
rendement forward net de frais ; (b) reconnaissance / exécution / contexte → mesurer la QUALITÉ
D'EXÉCUTION (taux de fill, markout, slippage, sélection adverse) CONDITIONNÉE à ce contexte, pas une IC
directionnelle. Pour SMC, le test aligné est : « placer un limit MAKER au bord d'un FVG/OTE/niveau de
session donne-t-il de meilleurs fills / markout qu'un placement naïf ? » — pile sur le SEUL levier réel
du bot (exécution/frais, cf. mémoire `exec-fees-lever`).
**Contrôle (détection ailleurs) — RUBRIQUE de différenciation (reproductible, pas au feeling).**
Classer CHAQUE module de mesure par la NATURE de sa sortie, via 4 questions :
  1. **Type de sortie** : une DIRECTION signée à trader (long/short + conviction) ⇒ prédicteur.
     Un NIVEAU de prix / une ZONE / une PHASE / un ÉTAT de régime / un label ⇒ contexte.
  2. **Nomme-t-il une direction, ou un lieu/état ?** « achète » ⇒ prédicteur ; « on est en discount,
     près d'un pool, vol haute, killzone Londres » ⇒ contexte/exécution/timing.
  3. **Usage humain** : « j'entre parce qu'il dit long » ⇒ prédicteur ; « il dit OÙ je suis → je place
     mon limit ici / j'attends / je réduis la taille » ⇒ contexte.
  4. **Évaluation naturelle** : corrélation au rendement forward (IC) ⇒ prédicteur ; amélioration
     CONDITIONNELLE (meilleur fill/markout, moindre sélection adverse, meilleur risk-adjusted d'une
     stratégie existante QUAND ce contexte tient) ⇒ contexte/exécution/sizing.
Verdict de la rubrique : **prédicteur** → IC / rendement net de frais. **contexte/exécution** → qualité
de PLACEMENT (fill, markout, slippage, adverse selection). **risque/sizing** → z-score → taille, pas IC.
NE JAMAIS rendre un « rejeté » sur une IC directionnelle pour un outil de contexte/exécution/risque.
Exemples de bonne classification déjà faite : `geometric_agent` (reclassé descripteur de RISQUE→sizing,
pas edge) ; `regime_lab` (régime = variable de CONDITIONNEMENT du consensus, pas prédicteur seul).
**Statut.** RECONNU (correction propriétaire 19/07) · dashboard SMC = bon usage. `smc_execution_lab.py` a
été construit pour mesurer l'edge d'EXÉCUTION du SMC — mais **CETTE construction est elle-même une instance
d'ERR-017** (on ne mesure pas l'edge d'une méthode) : ce qui en reste VALIDE = le résultat d'un SIGNAL de
placement concret (limit maker au bord FVG/OTE ≈/pire que naïf), PAS un verdict sur « SMC ». Voir ERR-017. · RÈGLE ACTIVE.

## ERR-017 · 2026-07-19 · Attendre/mesurer un EDGE d'une MÉTHODE (l'edge est une propriété d'un SIGNAL, pas d'un cadre)

**Contexte.** Après le reframe SMC (ERR-016 « reconnaissance, pas prédiction »), j'ai construit
`smc_execution_lab.py` pour mesurer l'edge d'EXÉCUTION du SMC (markout des fills à la structure).
Le propriétaire a re-corrigé : **mesurer/attendre un edge d'une MÉTHODE est aussi une erreur — l'edge
est une réponse d'un SIGNAL, pas d'une méthode.** SMC est une MÉTHODE (un cadre pour organiser la
perception et reconnaître la structure) ; lui demander un edge — directionnel OU exécution — est une
erreur de CATÉGORIE. J'avais juste déplacé la mauvaise question (IC → markout) sans voir qu'aucune des
deux ne s'applique à une méthode.
**Cause racine.** Réflexe de tout réduire à « y a-t-il un edge ? » (IC, markout, rendement net). Mais
un EDGE est une propriété d'un **SIGNAL** : un déclencheur PRÉCIS, testable, à espérance mesurable. Une
**MÉTHODE** (SMC, Wyckoff, chartisme) est un CADRE — elle n'« a » pas d'edge, elle organise la
perception, situe le contexte, oriente où regarder et comment exécuter. Demander un edge à un cadre
force un test qui répond toujours « non » et rate le point.
**Solution.** Distinguer 3 natures AVANT de choisir la mesure : (a) **SIGNAL** (déclencheur testable)
→ se juge par EDGE net de frais (IC / markout / rendement) ; (b) **MÉTHODE / reconnaissance** (cadre)
→ se juge par CORRECTION : reconnaît-elle juste, de façon consistante et CAUSALE, et organise-t-elle
utilement le contexte/l'exécution ? PAS d'edge attendu ; (c) **RISQUE / descripteur** → z-score →
sizing. Pour obtenir un edge « issu de » SMC, il faut DÉFINIR un signal précis DANS le cadre SMC et
mesurer CE signal — jamais « SMC » en bloc. Étend ERR-016 : ERR-016 disait « ne mesure pas un outil de
placement à l'IC directionnelle » ; ERR-017 ajoute « ne mesure pas non plus l'EDGE d'une méthode, en
aucune lentille — une méthode se VÉRIFIE (fait-elle son travail), un signal se MESURE (a-t-il un edge) ».
**Contrôle (détection ailleurs).** Pour tout module : d'abord « SIGNAL ou MÉTHODE/cadre ? ». Si MÉTHODE
→ interdiction de conclure « rejeté (pas d'edge) » ; la bonne analyse est « travaille-t-elle et
signale-t-elle CORRECTEMENT ? » (reconnaissance juste, causale, consistante). L'edge ne se mesure QUE
sur des signaux définis. Un « labo » qui teste l'edge d'un cadre entier (SMC, Wyckoff) pose déjà la
mauvaise question — reformuler en un signal concret, ou en une vérification de correction.
**Statut.** RECONNU (correction propriétaire 19/07) · étend ERR-016 · RÈGLE ACTIVE.

## ERR-018 · 2026-07-20 · Poser un levier et supposer qu'il a PRIS EFFET (levier lu par `_cfg` config-seule au lieu de `_knob` env-prioritaire)

**Contexte.** Test du modèle 7b pour la firme (§105). Sachant que le VPS n'a que 7,9 Go et fait
tourner des boucles argent, j'ai lancé le test avec `LLM_AGENT_KEEPALIVE=2m` en variable
d'environnement pour que le modèle de 4,6 Go soit relâché vite. Le levier a été **silencieusement
ignoré** : `llm_agent._call_local` lisait `_cfg("LLM_AGENT_KEEPALIVE", "30m")` — `_cfg` lit
**config.py seul**, pas l'environnement. Le 7b a campé 4,6 Go pendant 30 min, ne laissant que
1,2 Go libres, pendant que les crons `futures_auto` (:10/:25/:40/:55) tournaient. Découvert par
hasard en lisant `ollama ps` (« UNTIL : 29 minutes from now »), pas par une vérification.
**Cause racine.** DEUX conventions coexistent dans le dépôt pour lire un réglage :
`_knob(name, default)` = **.env PRIORITAIRE** puis config (tous les verrous opérationnels), et
`_cfg(name, default)` = **config.py SEUL**. Elles sont indiscernables au point d'appel. J'ai
supposé la convention `_knob` (la dominante) sans la vérifier, et j'ai surtout **supposé l'effet
au lieu de l'observer**. Cousin de `verrous-env-vs-config` (mémoire) et de ERR-010 : croire un
réglage actif parce qu'on l'a écrit quelque part.
**Solution.** (1) `llm_agent._keepalive()` passe par `_knob` (env prioritaire), testé. (2) Règle
générale : **un levier posé se VÉRIFIE par son effet observable**, jamais par le fait de l'avoir
posé — ici `ollama ps` AVANT de lancer un run long, comme on vérifie l'état runtime réel d'un
verrou avec `_load_env()` puis lecture (et non `cfg()` à froid).
**Contrôle (détection ailleurs).** `grep -n "_cfg(\"" *.py` sur tout réglage à vocation
**opérationnelle** (armement, timeout, taille, résidence mémoire, périmètre) : s'il est lu par
`_cfg` et non `_knob`, il n'est PAS pilotable par `.env` — soit c'est voulu (constante de
constitution), soit c'est un piège. Et avant tout run coûteux/long sous contrainte de ressource :
observer l'état réel (`ollama ps`, `free -m`, `--status`) plutôt que de faire confiance au levier.
**Statut.** CORRIGÉ (levier + test) · RÈGLE ACTIVE.

## ERR-019 · 2026-07-20 · Un TEST a écrit dans un journal de PRODUCTION (cas « dégénéré » qui n'en était pas)

**Contexte.** Découvert en cherchant l'origine d'un vote daté de **1970** dans `.overlay_votes.jsonl`.
16 lignes `sentiment_shadow` y portent `ts=0`. Elles ne viennent d'aucun cron ni d'aucun incident :
elles viennent de **mon propre test**. Livrant `variant_shadows.py` (§variantes-mesurées, commit
`5255d89`), j'avais écrit le garde-fou `assert vs.cycle(symbols=[], now=0) == 0` — « liste de
symboles vide → 0 ligne journalisée ». Or le driver faisait `syms = symbols or WATCH` : **une liste
vide est falsy**, donc `[] or WATCH` = `WATCH`. Le test n'a pas exercé un cas dégénéré, il a lancé un
**cycle complet réel** : appels réseau Bitget sur 8 symboles, et 8 lignes appendées dans le journal
d'ombre **de production**, horodatées `ts=0` puisque je passais `now=0` pour la déterminisme. Deux
exécutions avant correction → 16 lignes. J'ai ensuite corrigé l'assertion (`isinstance(vs.WATCH, list)
and callable(vs.cycle)`) **sans jamais nettoyer ce que le test avait écrit**, et sans me demander s'il
avait écrit quelque part.
**Cause racine.** DEUX défauts qui se composent, et c'est la composition qui fait mal :
(1) `x or DEFAULT` sur une **collection** transforme « vide » en « tout » — l'exact inverse du cas
qu'on croit tester ; le garde-fou testait la valeur la plus dangereuse en croyant tester la plus
inoffensive. (2) Surtout : `cycle()` n'avait **aucun point d'injection du chemin de journal** (`OVERLAY`
= constante de module), donc rien ne pouvait empêcher un test de toucher l'artefact réel. Comparer à
`news_agent.cycle(overlay_path=...)`, dont le test écrit dans un `TemporaryDirectory` : même famille de
module, même risque, mais l'injection rend la faute *impossible*. La discipline seule ne protège pas —
la structure, oui.
**Conséquence (pourquoi ce n'est pas cosmétique).** La voix a été RETIRÉE 1 h plus tard (commit
`3c67950`, mesure = aucun gain), mais ses 56 votes ont survécu dans le journal, dont 16 faux. Le
`promotion_board` affichait encore `sentiment_shadow · n 56 · progression 100 %` — une voix **sans
aucun producteur dans le dépôt**, présentée comme prête à franchir la barre des 50 votes. Même famille
que §107/§107b (firm_shadow) : une population morte qui progresse vers une promotion.
**Solution.** (1) Epoch posé sur `sentiment_shadow` dans `voice_epochs.json` à l'heure du retrait
(1784523695) → les 56 votes écartés, **et le compte affiché** dans le rapport d'audit
(`sentiment_shadow −56`) : jamais de filtrage silencieux. (2) Règle : **tout module qui écrit un
artefact partagé expose le chemin en paramètre** (`overlay_path=`, `chemin=`) et son test l'injecte
vers un `TemporaryDirectory`. (3) Un test qui affirme « ne fait rien » doit vérifier **l'absence
d'effet** (taille/mtime du journal avant/après), pas seulement une valeur de retour.
**Contrôle (détection ailleurs).** Deux greps, à passer ensemble :
`grep -nE "^\s*\w+ = (symbols|syms|items|rows|targets|liste) or [A-Z_]+" *.py` — chaque occurrence est
un piège si un appelant peut légitimement passer une collection vide (au 20/07 : `smc_execution_lab.py:218`,
`vpin_lab.py:389`, tous deux écrivant dans un fichier de lab DÉDIÉ, pas dans un journal partagé → sans
gravité, mais à ne pas laisser dériver). Puis, dans `tests_audit.py`, lister les appels de cycle de
production (`\w+\.(cycle|main|run)\(`) et exiger pour chacun soit une injection de chemin, soit un gate
prouvé OFF avec assertion de no-op (au 20/07 : `na.cycle` → injecte `overlay_path`, ✅ ; `tf.cycle` →
`FIRM_ENABLED=0` + `assert == 0`, ✅).
**Statut.** CORRIGÉ (epoch posé, voix disparue du board et de l'audit) · RÈGLE ACTIVE.

**RÉCIDIVE le 2026-07-20, ~2 h après avoir écrit cette entrée — et elle corrige la leçon.**
En livrant le journal des refus §67 (`bitget_execute.record_refusal`), j'ai appliqué scrupuleusement
ma propre solution : mes 5 nouveaux tests injectaient `be.REFUSALS` vers un `TemporaryDirectory`.
Insuffisant. J'avais ajouté une écriture dans un chemin **déjà exercé par des tests PRÉEXISTANTS**
(`test_margin_trader_rejects_bad_type`, `test_account_transfers_allowlist_blocks_external`,
`test_earn_manager_action_validation`, `test_spot_trader_off_by_default_and_args`, + mm) — écrits
des semaines plus tôt, ils ne pouvaient pas deviner qu'ils devaient se protéger. Résultat :
**203 lignes de `'bogus'` / `'external_wallet'` dans le journal de production**, soit 29 passages
du harnais × 7 tests produisant un refus. Découvert par `/lance-correction`, pas par moi.
**Ce que la récidive apprend.** (a) Mon contrôle initial était trop étroit : je cherchais des
**timestamps** suspects (l'incident `sentiment_shadow` était daté de 1970), or ici l'horodatage
était parfaitement légitime et c'est le **contenu** qui trahissait. Un contrôle calqué sur la
signature d'un incident passé ne détecte que cet incident-là. (b) Surtout : « injecter le chemin
dans le test » ne protège que les tests qu'on écrit soi-même. La faute vit dans les **tests déjà
là**, donc la protection doit être **globale et antérieure**, pas locale.
**Solution (v2, structurelle).** Redirection UNIQUE en tête de `tests_audit.py`, dans le volet
« tests hermétiques » qui existait déjà pour `.env` : `_rediriger_artefacts()` pointe tout journal
à écriture par effet de bord vers un tmpdir de suite. Plus
`test_aucune_ecriture_dans_un_journal_de_production` qui **échoue si un journal pointe encore sur
la racine du dépôt** pendant les tests — donc si un module futur en ajoute un sans l'inscrire.
Vérifié : après un passage complet, le journal de production est ABSENT. Les 203 lignes ont été
purgées (100 % artefacts de test, 0 évènement réel — contrairement au registre d'argent
`FUTURES_REAL_FAILED`, qu'on ne réécrit jamais).
**Contrôle (v2).** Après tout ajout d'une écriture de fichier dans un chemin de production :
`grep` les tests qui exercent ce chemin **avant** de committer, et inscrire le journal dans
`_rediriger_artefacts()`. Le test d'enforcement fait le reste. Généralisation : ne jamais juger la
propreté d'un artefact sur la seule signature d'un incident passé — inspecter le CONTENU.

## ERR-020 · 2026-07-20 · Corriger un mode de défaillance sur UN chemin sans traiter son chemin SYMÉTRIQUE

**Contexte.** Le 07-09, deux ordres d'OUVERTURE réellement remplis ont été journalisés FAILED :
Bitget répond parfois `data:{orderId:null}` sans code d'erreur. J'ai construit
`_confirm_futures_open_fill()` — re-poll des fills, match par symbole + côté + `tradeSide` + fenêtre
temporelle — et le faux négatif a disparu. **À l'ouverture seulement.** Le branchement portait
`if not rejet_definitif and not order.get("reduce")`, excluant explicitement les réductions. Le
2026-07-20, la MÊME réponse ambiguë est arrivée sur deux **fermetures** (HYPEUSDT 05:56, BANKUSDT
15:07) : journalisées `FUTURES_REAL_FAILED` « position à vérifier » alors que les fills de l'exchange
montrent les deux remplies INTÉGRALEMENT (0,22/0,22 et 85/85, positions ensuite à plat).
**Cause racine.** J'ai corrigé le cas que j'avais OBSERVÉ, pas le mode de défaillance. La réponse
ambiguë est une propriété de **l'API**, pas de la direction de l'ordre : elle frappe donc les deux
phases. En n'instrumentant qu'une moitié, j'ai laissé l'autre produire des faux négatifs pendant
11 jours. C'est la **deuxième occurrence du même geste le même jour** : §107b — le `promotion_board`
honorait l'epoch de voix pour l'IC mais recomptait les votes en contournant le filtre. Motif commun :
**une correction appliquée au point où le symptôme a été vu, au lieu de tous les points où sa cause
peut s'exprimer.**
**Solution.** Noyau unique `_confirm_futures_fill(order, phase)` paramétré par la phase, et deux
enveloppes `_confirm_futures_open_fill` / `_confirm_futures_close_fill` ; le branchement choisit la
phase au lieu d'exclure les réductions. Relevé réel encodé : pour une fermeture, Bitget rend
`side` = DIRECTION DE LA POSITION (un short s'ouvre en `sell open` ET se ferme en `sell close`) — le
mapping de côté est donc identique aux deux phases, seul `tradeSide` s'inverse. Au passage,
`price_avg` est passé de 2 à 8 décimales : l'arrondi écrasait le prix des alts sous le dollar
(BANK 0,2798 → 0,28) dans un registre d'ARGENT. 5 tests TDD (rouges d'abord), dont la rejouabilité des
deux cas réels du 20/07 contre les vrais fills → tous deux confirmés INTÉGRAL.
**Sens de l'erreur préservé.** On ne déclare soldé qu'après avoir VU le fill de fermeture : un faux
positif ferait croire une position fermée alors qu'elle est ouverte. Filet de dernier ressort inchangé :
`flatten_all`/`futures_auto` relisent `positions_ouvertes()` à chaque tick — l'autorité finale est le
livre, jamais ce drapeau. Un rejet EXPLICITE ne déclenche aucune réconciliation (testé).
**Contrôle (détection ailleurs).** Devant toute garde/réconciliation/instrument corrigé, énumérer les
chemins où la MÊME cause peut s'exprimer avant de clore : ouverture ↔ fermeture, achat ↔ vente,
IC ↔ comptage, spot ↔ futures ↔ marge, entrée ↔ sortie. Un `and not <cas>` dans une correction est le
drapeau rouge : il dit « je n'ai pas traité ce cas » — soit c'est motivé en commentaire, soit c'est un
trou. `grep -nE "and not .*\.get\(|if not .*reduce|only|seulement" ` sur les chemins d'argent.
**Statut.** CORRIGÉ (noyau symétrique + 5 tests, cas réels rejoués) · RÈGLE ACTIVE.

## ERR-021 · 2026-07-20 · Modifier hors-ligne un fichier que des DÉMONS VIVANTS détiennent et réécrivent

**Contexte.** Après avoir corrigé §108 (la télémétrie d'auto-réparation quitte le registre d'argent),
j'ai voulu récupérer immédiatement les 612 places déjà occupées : migration des anciennes entrées
vers le nouveau canal, puis réécriture du registre sans elles. Exécution nickel — sauvegarde
préalable, migration vérifiée 612/612, réécriture atomique, contrôle « aucune perte sur les familles
non-télémétrie », 388 évènements restants, 612 places libérées. **Et trente secondes plus tard le
fichier était revenu à 1000 évènements, 0 marqueur de migration.**
**Cause racine.** `stop_guardian.py` tourne en **démon permanent** (visible dans `ps`, démarré le
10/07). Il lit le registre, le garde, et le réécrit en entier (lecture-modification-écriture). Ma
version a été écrasée par la sienne, plus ancienne. Je n'ai pas vérifié *qui détenait le fichier*
avant de le modifier — j'ai raisonné comme si le dépôt était au repos alors que le bot tourne en
continu. Ironie utile : j'avais décrit ce danger EXACT deux heures plus tôt en concevant le journal
des refus (« le journal d'argent s'écrit en lecture-modification-écriture -> une écriture de refus
pourrait écraser un `record()` concurrent »), et je l'ai quand même fait.
**Dégâts : AUCUN**, par chance de conception. La migration écrivait d'abord dans le canal neuf
(append-only, non détenu) et n'effaçait qu'ensuite ; l'écrasement a donc restauré l'état d'origine
sans rien détruire — les 612 lignes existent aux deux endroits. Un ordre inverse (effacer puis
écrire) aurait perdu 612 entrées.
**Solution.** Ne PAS réessayer : le correctif de CODE suffit — la télémétrie n'entrant plus, les
anciennes entrées s'évacuent d'elles-mêmes par le plafond FIFO (~3-4 j au débit actuel). Une
migration immédiate n'apportait que de la vitesse, contre un risque sur le journal d'argent.
**Contrôle (détection ailleurs).** Avant toute modification hors-ligne d'un artefact partagé :
`ps aux | grep -E "<module>|python3"` pour lister les démons vivants, et se demander **qui d'autre
écrit ce fichier**. Si un processus long le détient : soit passer par le module lui-même (qui
sérialise), soit arrêter le service, soit — le plus souvent — **ne rien faire** et laisser la
rotation opérer. Corollaire général : un fichier réécrit en entier par plusieurs processus n'a pas
de modification « hors-ligne » sûre. Et quand une migration est malgré tout nécessaire : **écrire la
destination AVANT d'effacer la source**, jamais l'inverse.
**Statut.** RECONNU (aucun dégât, migration abandonnée volontairement) · RÈGLE ACTIVE.
