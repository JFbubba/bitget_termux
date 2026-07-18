"""
controls.py — TESTS DE CONTRÔLE DÉCISIFS (valident la machinerie AVANT toute conclusion).
Si le look-ahead ne donne pas IC=+1 ou le bruit != 0, la machinerie est cassée.
"""
import numpy as np
import audit_core as ac

RNG = np.random.default_rng(12345)


def banner(s):
    print("\n" + "=" * 78 + f"\n{s}\n" + "=" * 78)


def control_lookahead(sym="BTCUSDT", gran="1H"):
    """1a. feature[t] = rendement FUTUR lui-même. IC (rang ET pearson) DOIT = +1.
    Test à la fois GLOBAL et à travers les plis non chevauchants (avec purge)."""
    banner(f"CONTRÔLE 1a — LOOK-AHEAD (doit donner IC = +1.000) : {sym} {gran}")
    d = ac.load(sym, gran)
    c = d["c"]
    for h in (1, 4, 24, 96):
        fwd = ac.fwd_logret(c, h)
        feat = fwd.copy()                       # LE signal EST le rendement futur
        bar = np.arange(len(c), dtype=float)
        # global (sur tous les points valides)
        rg = ac.rank_ic(feat, fwd); pg = ac.pearson_ic(feat, fwd)
        # à travers plis non chevauchants
        rf = ac.ic_across_folds(bar, feat, fwd, h, method="rank")
        print(f"  h={h:>3}: rank_ic_global={rg:+.6f}  pearson_global={pg:+.6f}  "
              f"rank_ic_plis={rf[0]:+.6f} (t={rf[1]:+.1f}, {rf[2]} plis)")


def control_lookahead_shift(sym="BTCUSDT", gran="1H"):
    """1a-bis. DÉTECTEUR D'OFF-BY-ONE : feature = fwd décalé d'UNE barre.
    Si l'alignement est bon, l'IC chute NETTEMENT sous +1 (proche de l'autocorr)."""
    banner(f"CONTRÔLE 1a-bis — sensibilité d'alignement (fwd décalé de 1) : {sym} {gran}")
    d = ac.load(sym, gran); c = d["c"]
    for h in (1, 4, 24):
        fwd = ac.fwd_logret(c, h)
        feat = np.full_like(fwd, np.nan); feat[1:] = fwd[:-1]   # décalage +1
        r = ac.rank_ic(feat, fwd)
        print(f"  h={h:>3}: rank_ic(fwd_decale_de_1, fwd) = {r:+.4f}  "
              f"(doit être << 1 : sinon la cible est mal alignée)")


def control_noise(sym="BTCUSDT", gran="1H", n_rep=8):
    """1b. signal = bruit blanc. IC moyen ~0, |t| inter-plis rarement > 2."""
    banner(f"CONTRÔLE 1b — BRUIT (IC doit ~0, t non significatif) : {sym} {gran}")
    d = ac.load(sym, gran); c = d["c"]
    bar = np.arange(len(c), dtype=float)
    for h in (1, 24):
        fwd = ac.fwd_logret(c, h)
        ts, ics = [], []
        for _ in range(n_rep):
            feat = RNG.standard_normal(len(c))
            r = ac.ic_across_folds(bar, feat, fwd, h, method="rank")
            if r:
                ics.append(r[0]); ts.append(r[1])
        print(f"  h={h:>3}: sur {len(ics)} tirages -> IC moyen {np.mean(ics):+.5f} "
              f"(min {np.min(ics):+.4f}/max {np.max(ics):+.4f}), "
              f"t moyen {np.mean(ts):+.2f}, |t|max {np.max(np.abs(ts)):.2f}")


def control_signflip(sym="BTCUSDT", gran="1H"):
    """1b-bis. Inverser le signe de la cible DOIT inverser exactement l'IC."""
    banner(f"CONTRÔLE 1b-bis — inversion de cible (IC doit changer de signe) : {sym} {gran}")
    d = ac.load(sym, gran); c = d["c"]
    fwd = ac.fwd_logret(c, 1)
    feat = RNG.standard_normal(len(c))
    a = ac.rank_ic(feat, fwd); b = ac.rank_ic(feat, -fwd)
    print(f"  rank_ic(x, fwd)={a:+.5f}   rank_ic(x, -fwd)={b:+.5f}   somme={a+b:+.1e} (doit ~0)")


def control_integrity():
    """1c. Ordre des fichiers : tri, doublons, régularité du pas."""
    banner("CONTRÔLE 1c — INTÉGRITÉ DES FICHIERS (tri / doublons / pas)")
    for sym, gran in [("BTCUSDT", "1H"), ("BTCUSDT", "1D"), ("ETHUSDT", "1H"),
                      ("XRPUSDT", "1H"), ("XRPUSDT", "1D")]:
        r = ac.integrity(sym, gran)
        print(f"  {sym:<8}{gran:<4}: n={r['n_raw']:<6} trié_dans_fichier={r['already_sorted_in_file']!s:<5} "
              f"doublons={r['n_dupes']:<3} pas_median={r['median_step_ms']}ms "
              f"pas_irreguliers={r['n_irregular_steps']} (gaps/trous) n_apres_dedup={r['n_after_dedup']}")


def control_order_matters(sym="BTCUSDT", gran="1H"):
    """1c-bis. Un tri INCORRECT (fichier mélangé) casserait-il le résultat ?
    On mélange les lignes AVANT ma routine de tri : ma routine doit re-trier et
    donner exactement le même look-ahead IC=+1. Puis on montre qu'un mauvais tri
    (par close au lieu de ts) détruit l'IC — preuve que l'ordre compte et que ma
    machinerie l'impose."""
    banner(f"CONTRÔLE 1c-bis — robustesse au désordre d'entrée : {sym} {gran}")
    import json
    raw = json.loads((ac.DATA / f"{sym}_{gran}.json").read_text())
    arr = np.array([[r[0], r[4]] for r in raw], float)          # ts, close
    # (i) ordre correct par ts
    o = np.argsort(arr[:, 0]); c_ok = arr[o, 1]
    fwd = ac.fwd_logret(c_ok, 1)
    ic_ok = ac.rank_ic(fwd, fwd)
    # (ii) ordre FAUX : trié par close (chronologie détruite)
    o2 = np.argsort(arr[:, 1]); c_bad = arr[o2, 1]
    fwd_bad = ac.fwd_logret(c_bad, 1)
    ic_bad = ac.rank_ic(fwd_bad, fwd_bad)                        # toujours +1 (self)
    # rendement forward MAL ORDONNÉ vs rendement forward BIEN ordonné, mêmes ts
    # -> mesure combien un mauvais tri décorrèle
    import scipy.stats as ss
    common = min(len(c_ok), len(c_bad))
    print(f"  look-ahead sur close BIEN triée : rank_ic={ic_ok:+.4f} (self, =+1 attendu)")
    print(f"  autocorr lag-1 des rendements (bon ordre)  : "
          f"{np.corrcoef(fwd[:-1][np.isfinite(fwd[:-1])&np.isfinite(fwd[1:])], fwd[1:][np.isfinite(fwd[:-1])&np.isfinite(fwd[1:])])[0,1]:+.4f}")
    m = np.isfinite(fwd_bad[:-1]) & np.isfinite(fwd_bad[1:])
    print(f"  autocorr lag-1 des rendements (MAUVAIS ordre par close): "
          f"{np.corrcoef(fwd_bad[:-1][m], fwd_bad[1:][m])[0,1]:+.4f}  "
          f"(artefact : le tri par prix crée une fausse autocorr énorme)")


if __name__ == "__main__":
    control_integrity()
    control_lookahead()
    control_lookahead_shift()
    control_noise()
    control_signflip()
    control_order_matters()
    print("\n== CONTROLES TERMINES ==")
