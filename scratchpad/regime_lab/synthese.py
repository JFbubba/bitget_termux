"""synthese.py — lit resultats.json et imprime le tableau compact par TF. Lecture seule."""
import json
from pathlib import Path

d = json.loads((Path(__file__).resolve().parent / "resultats.json").read_text(encoding="utf-8"))
S = d["series"]
TFS = ["5m", "15m", "30m", "1H", "4H", "1D", "1W"]


def g(x, *ks):
    for k in ks:
        if x is None:
            return None
        x = x.get(k) if isinstance(x, dict) else None
    return x


def f(v, p="+.3f"):
    return "  n/a" if v is None else format(v, p)


print("=" * 118)
print("EDGE CONDITIONNEL momentum | flag = hmm2 (haute-vol, causal) | delta_rang = IC_rang(régime1) − IC_rang(régime0)")
print("=" * 118)
h = f"{'série':<12}{'prof.j':>7}{'n_ech':>7}{'chev':>5}{'plis':>5}{'d_rang':>8}{'t':>7}{'d_pears':>9}{'z_alea':>8}{'p_alea':>8}{'IC0rg':>8}{'IC1rg':>8}"
print(h)
print("-" * 118)
for sym in ("BTCUSDT", "ETHUSDT"):
    for tf in TFS:
        r = S.get(f"{sym}_{tf}", {})
        if r.get("statut") != "OK":
            print(f"{sym[:3]+' '+tf:<12}{r.get('profondeur_jours','?'):>7}  {r.get('statut','?')}")
            continue
        hm = g(r, "flags", "hmm2")
        print(f"{sym[:3]+' '+tf:<12}{r['profondeur_jours']:>7.0f}{r['n_echantillons']:>7}"
              f"{r.get('chevauchement_labels',1):>5.0f}{g(hm,'delta_rang','moy') is not None and hm['n_plis_valides'] or 0:>5}"
              f"{f(g(hm,'delta_rang','moy')):>8}{f(g(hm,'delta_rang','t'),'+.2f'):>7}"
              f"{f(g(hm,'delta_p','moy')):>9}{f(hm.get('z_vs_aleatoire'),'+.2f'):>8}"
              f"{f(hm.get('p_empirique'),'.3f'):>8}"
              f"{f(g(hm,'ic0_rang','moy')):>8}{f(g(hm,'ic1_rang','moy')):>8}")
    print("-" * 118)

print("\nPERTINENCE VOL (le flag/vol prédit-il |rendement forward| ?) — moyenne sur plis, t")
print(f"{'série':<12}{'exces_ratio|fwd|hmm2':>22}{'t':>7}{'IC_rang P(haut)|fwd|':>22}{'t':>7}{'IC_rang volEWMA|fwd|':>22}{'t':>7}")
for sym in ("BTCUSDT", "ETHUSDT"):
    for tf in TFS:
        r = S.get(f"{sym}_{tf}", {})
        if r.get("statut") != "OK":
            continue
        pv = r["pertinence_vol"]
        er = pv["exces_ratio_absfwd_hmm2"]
        ph = pv["ic_phaut_absfwd"]
        ve = pv["ic_vol_absfwd"]
        print(f"{sym[:3]+' '+tf:<12}{f(er['moy'],'+.3f'):>22}{f(er['t'],'+.2f'):>7}"
              f"{f(ph['moy'],'+.3f'):>22}{f(ph['t'],'+.2f'):>7}"
              f"{f(ve['moy'],'+.3f'):>22}{f(ve['t'],'+.2f'):>7}")

print("\nAUTRES FLAGS (delta_rang moyen / t) — ruptures & baseline vol_ewma")
print(f"{'série':<12}{'rupt_recent':>16}{'t':>7}{'rupt_age':>14}{'t':>7}{'vol_ewma':>14}{'t':>7}")
for sym in ("BTCUSDT", "ETHUSDT"):
    for tf in TFS:
        r = S.get(f"{sym}_{tf}", {})
        if r.get("statut") != "OK":
            continue
        def cell(fl):
            x = g(r, "flags", fl)
            return f(g(x, "delta_rang", "moy")), f(g(x, "delta_rang", "t"), "+.2f")
        rr = cell("rupt_recent"); ra = cell("rupt_age"); ve = cell("vol_ewma")
        print(f"{sym[:3]+' '+tf:<12}{rr[0]:>16}{rr[1]:>7}{ra[0]:>14}{ra[1]:>7}{ve[0]:>14}{ve[1]:>7}")

co = d.get("coherence", {})
print("\nCOHÉRENCE flags hmm2 (phi) — BTC vs ETH par TF")
for tf, v in co.get("btc_vs_eth", {}).items():
    print(f"  {tf:<5} phi={f(v.get('phi'),'+.3f')}  (n={v.get('n')})")

jr = d.get("journal_1h", {})
print(f"\nJOURNAL CONSENSUS 1H (contrôle, {jr.get('profondeur_journal_jours')} j, 1 bloc) — {jr.get('avertissement','')}")
for sym, v in jr.get("par_symbole", {}).items():
    if "delta_rang" in v:
        print(f"  {sym}: IC_rang global {f(g(v,'ic_global','rang'))} | "
              f"régime0 {f(g(v,'regime_0','rang'))} (n={g(v,'regime_0','n')}) | "
              f"régime1 {f(g(v,'regime_1','rang'))} (n={g(v,'regime_1','n')}) | "
              f"delta_rang {f(v['delta_rang'])}")
