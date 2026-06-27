---
name: run-bitget
description: Lance et pilote l'app de facon SURE (dashboard lecture seule + CLIs lecture seule), sans jamais declencher d'achat reel. A utiliser pour lancer/voir tourner le bot, verifier l'etat, ou tester un changement dans l'app reelle.
---

# /run-bitget — lancer l'app sans toucher au reel

⚠️ **Argent reel sur cette machine.** L'accumulation autonome est armee (`.env`
`ACCUM_AUTONOMOUS_LIVE=1`, `MANDATE_LIVE_ENABLED=True`, `bgc` present). NE JAMAIS lancer
ce qui passe par le chemin d'achat reel juste pour « voir l'etat ».

## A NE PAS faire
- ❌ `python accumulation_engine.py BTCUSDT` -> `main()` -> `run()` -> **achat reel**
  quand arme. (Le garde-fou `.claude/hooks/guard.py` le bloque aussi.)
- ❌ `python spot_executor.py ... --confirm` -> achat reel.
- ❌ `bgc ...` avec un verbe d'ordre / transfert / retrait.

## A. Dashboard (lecture seule) — l'app principale
Deja servi sur `http://127.0.0.1:8787` (sinon : `python dashboard/server.py`).
```bash
curl -s http://127.0.0.1:8787/healthz                              # -> ok
curl -s 'http://127.0.0.1:8787/api/state?symbol=BTCUSDT&tf=5m'     # JSON complet
```
Blocs cles : `mode`, `brain` (bias/conviction), `mandate`, `edge_ladder`,
`accumulation` (via `analyze()` lecture seule), `orderflow`, `health`.

## B. CLIs lecture seule (toutes finissent VERDICT: SAFE)
```bash
python universe.py        # univers d'analyse
python mandate.py         # politique + etat des verrous
python edge_ladder.py     # paliers par agent
python system_health.py   # sante (execution reelle = DISABLED attendu)
python stats_report.py    # stats paper TP/SL
python swarm_brain.py BTCUSDT   # consensus des 11 agents (plus lent, reseau)
```

## C. Accumulation en LECTURE SEULE (jamais d'achat)
```bash
python -c "import accumulation_engine as ae, json; print(json.dumps(ae.analyze('BTCUSDT'), default=str, indent=2))"
```
`analyze()` calcule opportunite/premium sans jamais acheter (c'est ce que le dashboard
utilise, server.py:239).

## D. (Optionnel) Prouver que la garde tient — DRY, sans --confirm
```bash
python spot_executor.py --usdt 5     # imprime l'ordre + gardes, n'execute RIEN (dry:true)
```
**Ne jamais ajouter `--confirm`.**

## Succes attendu
`/healthz`=ok ; `/api/state` JSON valide (`mode` = "PAPER futures · ...") ; chaque CLI
sort 0 + `VERDICT: SAFE` ; `accumulation_real_ledger.json` inchange (aucun ordre).
