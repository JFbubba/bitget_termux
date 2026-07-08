# AGENT_ERRORS.md — journal des erreurs de l'agent & auto-correction

**But.** Répertorier chaque erreur MÉTHODOLOGIQUE ou COMPORTEMENTALE de l'agent qui
travaille sur ce dépôt, avec sa **cause racine**, sa **solution**, et surtout un
**contrôle de détection** réutilisable — pour vérifier que la même erreur n'a pas été
reproduite ailleurs dans le bot.

**Usage « agent autocorrecteur ».** Lire ce fichier ; pour chaque erreur ACTIVE, exécuter
son *Contrôle* sur le dépôt. Toute occurrence trouvée = à corriger selon la *Solution*,
journaliser, notifier. C'est le pendant « code/méthode » du `watchdog.py --heal` (qui, lui,
répare le RUNTIME : timers morts, escalade). Ici on répare la MÉTHODE.

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
