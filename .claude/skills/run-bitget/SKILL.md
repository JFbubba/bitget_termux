---
name: run-bitget
description: Lance et pilote l'app de façon SÛRE (dashboard lecture seule + CLIs lecture seule), sans jamais déclencher d'ordre réel. À utiliser pour lancer/voir tourner le bot, vérifier l'état, ou tester un changement dans l'app réelle.
---

# /run-bitget — lancer l'app sans toucher au réel

⚠️ **Argent réel sur cette machine, sur DEUX chemins** : accumulation spot armée
(`.env` `ACCUM_AUTONOMOUS_LIVE=1`, `MANDATE_LIVE_ENABLED=True`, `bgc` présent) ET
futures borné §45 (boucle directionnelle + carry). NE JAMAIS lancer ce qui passe par
un chemin d'exécution réel juste pour « voir l'état ».

## À NE PAS faire
- ❌ `python accumulation_engine.py BTCUSDT` -> `main()` -> `run()` -> **achat réel**
  quand armé. (Le garde-fou `.claude/hooks/guard.py` le bloque aussi.)
- ❌ `python futures_auto.py` ou `python carry_auto.py` SANS `--status` -> **CYCLE qui
  peut trader en réel**. La consultation, c'est `--status`.
- ❌ `python spot_executor.py ... --confirm` ou `python futures_executor.py ... --confirm`
  -> ordre réel (les deux sont DRY par défaut, `--confirm` exécute).
- ❌ `bgc ...` avec un verbe d'ordre / transfert / retrait.

## A. Dashboard (lecture seule) — l'app principale
Déjà servi sur `http://127.0.0.1:8787` (sinon : `python dashboard/server.py`).
```bash
curl -s http://127.0.0.1:8787/healthz                                    # -> ok
curl -s -m 90 'http://127.0.0.1:8787/api/state?symbol=BTCUSDT&tf=5m'     # JSON complet
```
⏱ `/api/state` met ~20–30 s à froid (appels réseau) : toujours `-m 90`, pas 30.
Blocs clés : `mode`, `brain` (bias/conviction), `mandate`, `edge_ladder`,
`accumulation` (via `analyze()` lecture seule), `orderflow`, `health`, `futures_live`,
`verrous`, `positions`.

## B. CLIs lecture seule (toutes sortent 0 + VERDICT: SAFE)
```bash
python universe.py        # univers d'analyse (dynamique top-N)
python mandate.py         # politique + état des verrous
python edge_ladder.py     # paliers par agent
python system_health.py   # santé (pipeline pré-ordres : exécution DISABLED attendu)
python stats_report.py    # stats paper TP/SL
python futures_report.py  # futures §45 : boucle, position, equity/stop, PnL bot
python swarm_brain.py BTCUSDT   # consensus du banc 14 agents + voix opt-in (plus lent, réseau)
```

## C. Accumulation en LECTURE SEULE (jamais d'achat)
```bash
python -c "import accumulation_engine as ae, json; print(json.dumps(ae.analyze('BTCUSDT'), default=str, indent=2))"
```
`analyze()` calcule opportunité/premium sans jamais acheter — c'est ce que le dashboard
utilise (`dashboard/server.py`, commentaire « analyze = lecture seule »).

## D. (Optionnel) Prouver que la garde tient — DRY, sans --confirm
```bash
python spot_executor.py --usdt 5     # imprime l'ordre + gardes, n'exécute RIEN (dry)
```
**Ne jamais ajouter `--confirm`.**

## Succès attendu
`/healthz`=ok ; `/api/state` JSON valide (`mode` = "RÉEL spot 2–5$/j · RÉEL futures
borné §45") ; chaque CLI sort 0 + `VERDICT: SAFE` ; `accumulation_real_ledger.json`
inchangé (md5 avant/après identique — aucun ordre déclenché par la consultation).
