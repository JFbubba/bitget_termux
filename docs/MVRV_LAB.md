# MVRV-Z lab — note de mesure (banc `mvrv_lab.py`)

**Statut : SAFE, lecture seule, défaut OFF, aucun ordre, aucun câblage au cerveau.**
Banc de MESURE du signal on-chain **MVRV Z-score** (valorisation du réseau BTC vs son
coût de base réalisé). Comme `grid_lab` / `vpin_lab` / `mm_lab` : il rejoue l'histoire,
il rapporte des chiffres, il ne trade rien. Un éventuel tilt DCA réel resterait un
opt-in `.env` (`MVRV_TILT_ENABLED`, défaut OFF), décidé par le propriétaire, SOUS les
caps d'accumulation — jamais un signal directionnel futures.

## Source des données — Coin Metrics community, KEYLESS (vérifié 19/07)

GET public en `urllib` stdlib (AUCUNE dépendance tierce, ERR-004), paginé via
`next_page_url`, caché disque (`.mvrv_lab_cache.json`) pour re-run offline. Fail-safe :
réseau KO + pas de cache → verdict `no_data`, jamais de crash.

```
https://community-api.coinmetrics.io/v4/timeseries/asset-metrics
  ?assets=btc&metrics=CapMVRVCur,CapMrktCurUSD,PriceUSD&frequency=1d&start_time=2013-01-01
```

- `CapMVRVCur` = ratio MVRV (gratuit) · `CapMrktCurUSD` = market cap (gratuit) ·
  `PriceUSD` = prix BTC de référence (gratuit) → historique **complet depuis 2013**
  (~4947 jours, ~4 cycles), indispensable pour un signal de cycle.
- `CapRealUSD` (realized cap) est **Pro (403 Forbidden)** → on **DÉRIVE**
  `realized_cap = market_cap / MVRV` (car `CapMVRVCur = market_cap / realized_cap`).
- Cross-check prix : `PriceUSD` vs `candles_history.load("BTCUSDT","1D")` (Bitget) →
  **Spearman 0.9993** sur 2538 jours communs (le prix on-chain suit le tradable).

## Calcul

**MVRV Z-score** = `(market_cap − realized_cap) / std(market_cap)`, numérateur =
`market_cap·(1 − 1/MVRV)`. Deux modes exposés :
- `full` : std sur tout l'échantillon = **définition on-chain classique**, mais
  **non causale** (léger look-ahead d'échelle) → cross-check seulement.
- `expanding` : std cumulée jusqu'à t = **CAUSALE, tradable, sans look-ahead** → c'est
  la version honnête pour l'IC et pour le tilt DCA.

**ERR-001** : le MVRV est calculé **une fois par jour** sur l'état de la chaîne — il
n'existe **pas** de MVRV M1..H4 (natif indisponible, comme la tape M1 pour VPIN).
L'échelle d'un signal de cycle lent = les **horizons forward en jours** : tête {7,14,30},
échelle étendue {1,7,14,30,60,90}.

## Résultats mesurés (BTC 2013-01-01 → 2026-07-18, run du 19/07)

| Mesure | Chiffre | Lecture |
|---|---|---|
| **IC(z, fwd) — expanding (CAUSAL)** | h7 **+0.022** (t 0.56) · h14 +0.014 · h30 +0.011 | **~zéro**, non significatif |
| **IC(z, fwd) — full (non causal)** | h7 **−0.077** (t −2.06) · h14 −0.10 · h30 −0.128 (t −1.64) | réversion de valeur, mais **look-ahead** + t marginal |
| **Directionnel sign(−z)·fwd (exp, h30)** | Sharpe **−0.164** vs B&H **+0.232** | perd, **sous** le buy-and-hold |
| **Deflated Sharpe** (n_trials=6) | **0.002** (seuil 0.95) · E[maxSharpe|H0]=0.053 | **échoue** la déflation |
| **Walk-forward OOS (h30)** | IC train +0.010 → **test −0.034** (t −0.29), Sharpe OOS −0.195 | **signe s'inverse** hors échantillon |
| **Buy-and-hold total** | **+485 804 %** | le hold écrase tout |
| **Tilt DCA vs DCA plat** (budget ÉGAL, z causal) | coût moyen **−30.5 %** (995 $ vs 1433 $), **+44 % BTC** | robuste par sous-période : 2018+ −23 %, 2020+ −16 %, 2022+ −22 % |

## Verdict — HONNÊTE (prior confirmé : beta de cycle)

1. **Comme signal DIRECTIONNEL : MORT.** La version *causale/tradable* (expanding) a un
   IC ≈ 0 (t < 0.6), un Sharpe directionnel **négatif** sous le buy-and-hold, une
   Deflated Sharpe **0.002** (≪ 0.95) et un **walk-forward qui change de signe**. La
   fameuse réversion MVRV n'apparaît **que** dans la normalisation *full-sample*
   (non causale, look-ahead), et même là t ≈ −2 sur seulement ~3-4 cycles.
   → **NE PAS brancher au cerveau / aux futures.**

2. **Comme TILT de coût moyen sur l'accumulation : effet RÉEL mais REDONDANT.** À budget
   égal, acheter plus quand MVRV-Z est bas baisse le coût moyen de **16–30 % vs DCA plat**,
   causal et robuste par sous-période, et les frais ne mordent quasi pas (signal lent).
   MAIS (a) ça **ne bat pas le hold** (accumuler ≠ créer de l'alpha) ; (b) « MVRV bas »
   ≈ « prix déprimé/en drawdown », ce que **`accumulation_engine.opportunity_score`
   capte DÉJÀ** (drawdown 35 % + RSI 25 % + below_ma 20 % + fear 20 %) → l'apport
   MARGINAL du MVRV-Z **au-dessus** du tilt existant est probablement faible et **non
   mesuré ici** ; (c) l'ampleur (16–30 %) est un **beta de cycle** (N≈3-4 creux), pas
   une garantie.

**Bilan** : signal de cycle **lisible** (descripteur de cherté du réseau), **pas** un
edge directionnel, et **redondant** avec le tilt d'opportunité déjà en place côté
accumulation. Prochaine étape possible SI on veut l'exploiter : mesurer l'IC
**incrémental** du MVRV-Z *au-dessus* de `opportunity_score` (orthogonalité), sinon
laisser dormant. Défaut OFF, rien câblé.

## CLI (consultation, lecture seule)
```
python mvrv_lab.py --status          # dernier résultat (aucun réseau)
python mvrv_lab.py --run             # fetch (ou cache) + mesure complète
python mvrv_lab.py --run --no-net    # force le cache disque (offline)
```
Artefacts (dotfiles, à gitignorer) : `.mvrv_lab_cache.json`, `.mvrv_lab_result.json`.
