# smc_relab — ré-test rigoureux du modèle ICT 2022 (top-down + NY killzone)

SCRATCHPAD / LECTURE SEULE / AUCUN ordre. Re-test d'une idée **REJETÉE** (prior
négatif fort, cf. `docs/VERDICTS.md` ligne « SMC / ICT »). N'est PAS un module repo,
n'entre PAS dans `tests_audit.py`. Venv isolé `/root/smc_venv` (ERR-004),
lib `smartmoneyconcepts` (joshyattridge) + `scipy` (installé dans le venv).

## Ce qu'on mesure (la SEULE variante jamais testée)
Deux angles morts identifiés par la recherche du 19/07 :
- **(a) top-down multi-TF STRICT** : biais HTF D1+4H (bos_choch swing=50 +
  premium/discount) → entrée LTF 15m par machine à états causale.
- **(b) filtre de SESSION** : les killzones forex n'ont pas de sens en crypto 24/7 ;
  seule adaptation = fenêtre **NY equity-overlap 08:30-11:00 ET** (gère le DST via
  `America/New_York`), option macro **Silver Bullet 10-11 ET**. PAS de Londres.

Machine à états (causale, sens du biais HTF uniquement) :
`sweep de liquidité → MSS (CHoCH + FVG de displacement) → FVG dans l'OTE 0.62-0.79 →
[confluence OB Unicorn] → ordre LIMIT au repos au bord du FVG → fill au retest`.
Stop structurel sous le sweep ; T1 = extrême opposé (→ break-even), T2 = extension 0.62 ;
gestion 50/50.

## Fichiers
- `ict_2022.py` — moteur : chargement, features SMC avec `available_at` (anti-look-ahead),
  biais HTF causal mappé au 15m par timestamp de CLÔTURE, machine à états, frais, PnL.
- `run_relab.py` — protocole de mesure (grille 48 configs, POOL inter-majors, contrôle
  session ON/OFF, t HAC, Deflated Sharpe, walk-forward OOS, B&H, décompo long/short).
- `diag_funnel.py` — entonnoir stage par stage (rareté vs bug).
- `causality_check.py` — **preuve anti-look-ahead par troncature**.

## Anti-look-ahead (critique)
- `swing_highs_lows` regarde `swing` bougies APRÈS le pivot. On n'utilise chaque pivot
  qu'à `available_at = pivot + swing + stab` (stab = 2·swing : la fonction est STATEFUL
  et reclasse rarement un pivot tardivement — micro look-ahead ~0.03% à lag=swing,
  ramené à ~0% à lag=3·swing, prouvé par `causality_check.py`).
- `bos_choch` : available = max(BrokenIndex, pivot+swing+stab). BrokenIndex/MitigatedIndex/
  Swept/End ne servent JAMAIS de feature à l'instant t — uniquement à dater l'`available_at`.
- HTF→LTF par timestamp de clôture (une bougie 4H/D1 n'est consommée qu'une fois fermée).

## Lancer
```
/root/smc_venv/bin/python causality_check.py     # doit finir "OK — moteur causal"
/root/smc_venv/bin/python run_relab.py           # la mesure + le verdict chiffré
/root/smc_venv/bin/python diag_funnel.py BTCUSDT  # entonnoir (diagnostic)
```

## Critère de déploiement
Edge net **maker**, **OOS**, **B&H-positif**, **DSR > 0.95** sur ≥3 majors.
Sinon → réel-non-tradable, NE PAS relancer. Voir le verdict chiffré dans `run_out.txt`
et la synthèse consignée par le parent dans `docs/VERDICTS.md`.
