"""
kelly.py — dimensionnement par le critère de Kelly (fractionnaire), LECTURE SEULE.

Classement : SAFE. Calcul PUR, aucun ordre. Fournit la fraction optimale de capital à
risquer et le montant USDT correspondant, BORNÉ. Consommé par les exécuteurs §67 (comme
source de taille) et par le dashboard (advisory).

Formule de base :   f = W − (1 − W) / R
  • W = taux de réussite (probabilité, ex. 0.6) ;
  • R = gain moyen / perte moyenne (payoff ratio).

Garde-fous DURS (par conception) :
  • EDGE NÉGATIF -> f = 0. Si W et R ne donnent pas d'espérance positive (f ≤ 0), Kelly
    dit de NE RIEN MISER — on renvoie 0 (jamais de mise à edge négatif, jamais de « pari
    inverse »). C'est le cas des stats mesurées actuelles du bot (edge négatif).
  • KELLY FRACTIONNAIRE : on applique par défaut le DEMI-Kelly (KELLY_FRACTION=0.5) —
    croissance quasi optimale, volatilité/drawdown fortement réduits (cf. littérature).
  • PLAFOND DUR : f ne dépasse jamais KELLY_MAX_FRACTION (défaut 0.25 du capital), même
    si le Full-Kelly le suggère.
  • Le montant est ENSUITE reborné par les caps de la surface (bitget_execute) : Kelly ne
    peut que dimensionner À LA BAISSE dans les murs, jamais les desserrer.

CLI : python kelly.py            (affiche W, R, f et les tailles recommandées)
"""
import math

from config_utils import cfg as _cfg, load_env as _load_env
_load_env()   # .env dès l'import : les knobs env-first ne dépendent pas de l'ordre d'import

DEF_FRACTION = 0.5      # Demi-Kelly par défaut
DEF_MAX_FRACTION = 0.25  # plafond dur : jamais > 25 % du capital
DEF_PRIOR_STRENGTH = 100.0  # poids du prior sceptique (pseudo-trades) du Kelly bayésien §111
DEF_DD_CONF = 0.10      # P(toucher un jour 1−MDD du capital initial) tolérée (Thorp eq. 7.13)
DEF_MDD = 0.20          # mandat de drawdown du bot (mandate.py : MDD ≤ 20 %)


def _knob(name, default):
    import os
    v = os.getenv(name)
    if v is not None:
        try:
            return float(v)
        except ValueError:
            pass
    return float(_cfg(name, default))


def kelly_fraction(W, R, fraction=None, cap=None):
    """Fraction de Kelly (fractionnaire, bornée). Retourne un dict détaillé.

    - f_full : Kelly complet (peut être négatif = pas d'edge) ;
    - f      : fraction APPLIQUÉE = max(0, f_full) × fraction, plafonnée à cap ;
    - edge_positive : W et R donnent-ils une espérance positive ?"""
    fraction = _knob("KELLY_FRACTION", DEF_FRACTION) if fraction is None else fraction
    cap = _knob("KELLY_MAX_FRACTION", DEF_MAX_FRACTION) if cap is None else cap
    try:
        W = float(W)
        R = float(R)
    except (TypeError, ValueError):
        return {"f_full": None, "f": 0.0, "edge_positive": None, "W": None, "R": None,
                "fraction": fraction, "cap": cap, "note": "W/R indisponibles"}
    if R <= 0:
        return {"f_full": None, "f": 0.0, "edge_positive": False, "W": W, "R": R,
                "fraction": fraction, "cap": cap, "note": "R ≤ 0"}
    f_full = W - (1.0 - W) / R
    f = max(0.0, f_full) * fraction          # edge négatif -> 0 ; sinon fractionnaire
    f = min(f, cap)                          # plafond dur
    return {"f_full": round(f_full, 4), "f": round(f, 4),
            "edge_positive": f_full > 0, "W": round(W, 4), "R": round(R, 4),
            "fraction": fraction, "cap": cap,
            "note": "edge négatif -> mise 0" if f_full <= 0 else "edge positif"}


def kelly_general(p, b, a=1.0):
    """Forme GÉNÉRALE de Thorp (§111, deep-research vérifiée) : f* = p/a − (1−p)/b = m/(ab),
    m ≡ bp − aq. `a` = fraction de la mise perdue quand ça perd (a=1 ≡ forme binaire
    W − (1−W)/R), `b` = fraction gagnée quand ça gagne. Pour des trades TP/SL qui ne
    risquent que la distance de SL, f s'interprète en fraction du capital À RISQUE —
    la conversion en notionnel (f/a) est faite par l'exécuteur via la distance de SL. PUR."""
    try:
        p, b, a = float(p), float(b), float(a)
    except (TypeError, ValueError):
        return {"f_full": None, "note": "entrées illisibles"}
    if b <= 0 or a <= 0 or not (0.0 <= p <= 1.0):
        return {"f_full": None, "note": "b/a ≤ 0 ou p hors [0,1]"}
    f_full = p / a - (1.0 - p) / b
    return {"f_full": round(f_full, 6), "p": p, "b": b, "a": a,
            "edge_positive": f_full > 0}


def kelly_bayes(wins, losses, R, prior_strength=None):
    """Kelly BAYÉSIEN (Chu–Wu–Swartz 2018, eq. 15 — §111) adapté aux cotes asymétriques :
    prior Beta centré sur le BREAK-EVEN p0 = 1/(1+R) (prior « marché efficient » : edge nul
    a priori — l'adaptation du Beta(50,50) du papier, centré 0.5, aux paris R ≠ 1), moyenne
    postérieure p̂ = (wins + k·p0)/(n + k), et f0 = Kelly binaire évalué à p̂ — NUL dès que
    p̂ ≤ p0. Remplace le plug-in brut ×0,5 : le shrink est piloté par n (peu de données ->
    p̂ ≈ p0 -> mise ≈ 0 ; beaucoup -> converge vers le plug-in). PUR. Sans données (n=0),
    p̂ = p0 exactement -> mise 0 : pas de pari sans preuve."""
    k = _knob("KELLY_PRIOR_STRENGTH", DEF_PRIOR_STRENGTH) if prior_strength is None else float(prior_strength)
    try:
        wins, losses, R = float(wins), float(losses), float(R)
    except (TypeError, ValueError):
        return {"f0": 0.0, "note": "entrées illisibles -> mise 0"}
    if R <= 0 or wins < 0 or losses < 0 or k <= 0:
        return {"f0": 0.0, "note": "R ≤ 0 ou compte/prior invalide -> mise 0"}
    n = wins + losses
    p0 = 1.0 / (1.0 + R)                       # probabilité de break-even des cotes R
    p_post = (wins + k * p0) / (n + k)         # moyenne postérieure Beta(k·p0, k·(1−p0))
    f0 = (p_post - (1.0 - p_post) / R) if p_post > p0 else 0.0
    return {"f0": round(max(0.0, f0), 6), "p_post": round(p_post, 4), "p0": round(p0, 4),
            "n": int(n), "prior_strength": k, "R": round(R, 4),
            "note": ("posterior ≤ break-even -> mise 0" if f0 <= 0
                     else f"posterior {p_post:.3f} > break-even {p0:.3f}")}


def dd_fraction(mdd=None, conf=None):
    """Fraction c dérivée du MANDAT de drawdown (Thorp eq. 7.13 — §111) : sous c·f*,
    P(toucher un jour x = 1−mdd du capital INITIAL) = x^(2/c−1) ; on résout c pour que
    cette probabilité ≤ conf : c = 2/(1 + ln(conf)/ln(1−mdd)), écrêté (0, 1]. Remplace le
    0,5 ad hoc par une fraction dérivée du mandat MDD 20 % (c ≈ 0,18 à conf 10 %). LIMITES
    (rapport) : chute depuis le capital initial, PAS pic-à-creux ; approximation continue,
    queues crypto -> confiance nominale. Le kill-switch et la halte MDD restent les murs. PUR."""
    mdd = _knob("KELLY_MDD", DEF_MDD) if mdd is None else float(mdd)
    conf = _knob("KELLY_DD_CONF", DEF_DD_CONF) if conf is None else float(conf)
    if not (0.0 < mdd < 1.0) or not (0.0 < conf < 1.0):
        return 1.0                              # paramètres invalides -> neutre (pas de resserrage)
    x = 1.0 - mdd
    denom = 1.0 + math.log(conf) / math.log(x)
    if denom <= 0:                              # conf si lâche que full Kelly suffit
        return 1.0
    return min(1.0, 2.0 / denom)


def kelly_empirical(returns, cap=None, grid=400):
    """Kelly EMPIRIQUE (§111) : argmax_f Σ log(1+f·r) sur la distribution RÉELLE des
    R-multiples/retours par trade (sorties partielles, ambigus, frais compris) — la voie
    sûre du rapport quand les issues ne sont pas binaires (le E[log] direct, PAS
    l'approximation par moments, réfutée 0-3). f borné par `cap` et par la ruine
    (f < 1/|min r|). Retourne f (0 si aucun f ne donne une croissance > 0). PUR."""
    from numeric_utils import safe_float
    rs = [x for x in (safe_float(r) for r in (returns or [])) if x is not None and math.isfinite(x)]
    if not rs:
        return 0.0
    cap = _knob("KELLY_MAX_FRACTION", DEF_MAX_FRACTION) if cap is None else float(cap)
    lo = min(rs)
    f_hi = min(cap, 0.999 / abs(lo)) if lo < 0 else cap
    if f_hi <= 0:
        return 0.0
    best_f, best_g = 0.0, 0.0
    for i in range(1, int(grid) + 1):
        f = f_hi * i / grid
        try:
            g = sum(math.log1p(f * r) for r in rs)
        except ValueError:
            continue
        if g > best_g:
            best_f, best_g = f, g
    return round(best_f, 6)


def live_stats():
    """(wins, losses, R, n…) mesurés sur les FILLS RÉELS du bot (futures_report : cache
    600 s, bornés au premier ordre réel). Les stats LIVE priment sur le paper (Thorp,
    §111 : « systems that worked may be … based on data mining » — supposer l'edge vrai
    INFÉRIEUR à l'edge mesuré, a fortiori paper). Best-effort -> None (fail-open)."""
    try:
        import futures_auto as fa
        import futures_report as fr
        debut = fr.premier_ordre_reel_ts(fa._executor_events())
        if not debut:
            return None
        # group_by_order (revue §111, défaut 3) : n = ORDRES agrégés, pas fills bruts —
        # sinon les remplissages partiels gonflent n et diluent le prior trop vite.
        prof = fr.payoff_profile(fr.fetch_fills(), depuis_ts=debut, group_by_order=True)
        n = int(prof.get("n") or 0)
        if not n:
            return None
        R = prof.get("payoff")
        note = None
        if R is None:
            # tout-gagnants (revue §111, défaut 4) : payoff indéfini. NE PAS se débrancher
            # (fail-open = garde fixe seule PILE quand le posterior est au plus haut) :
            # R=1 conservateur — on ne suppose pas que les gros gains persistent.
            R, note = 1.0, "aucune perte au registre -> R=1 conservateur"
        out = {"wins": int(round(float(prof.get("win_rate") or 0.0) * n)), "n": n,
               "R": float(R), "expectancy": prof.get("expectancy"),
               "t_stat": prof.get("t_stat"), "shape": prof.get("shape"),
               "source": "ordres réels agrégés (futures_report, group_by_order)"}
        out["losses"] = n - out["wins"]
        if note:
            out["note"] = note
        return out
    except Exception:
        return None


def futures_risk_pct(n_slots=None):
    """CALCULATEUR DE MISE de la boucle directionnelle (§111) : % d'equity à RISQUER par
    trade = Kelly bayésien (stats LIVE) × fraction drawdown (mandat MDD) ÷ n_slots —
    budget Kelly UNIQUE partagé entre positions quasi-corrélées (rapport : à ρ→1 chaque
    position reçoit 1/n du Kelly mono-actif ; 3 fractions indépendantes sur-parieraient le
    beta commun ~3×). Retourne (risk_pct, detail) :
      • risk_pct > 0 : fraction à passer (en %) à la garde risque de l'exécuteur —
        l'appelant fait min() avec la garde fixe (réducteur-seulement) ;
      • risk_pct = 0 : Kelly dit NE PAS MISER (posterior ≤ break-even) — l'appelant
        s'abstient d'ouvrir et ne passe JAMAIS 0 à l'exécuteur (0 y = garde désactivée) ;
      • None : stats indisponibles -> fail-open, la garde fixe reste seule."""
    ls = live_stats()
    if not ls:
        return None, {"note": "stats live indisponibles -> garde fixe seule (fail-open)"}
    kb = kelly_bayes(ls["wins"], ls["losses"], ls["R"])
    c = dd_fraction()
    slots = max(1, int(n_slots or 1))
    f = min(kb.get("f0") or 0.0, _knob("KELLY_MAX_FRACTION", DEF_MAX_FRACTION))
    f_trade = f * c / slots
    detail = {"live": ls, "bayes": kb, "dd_fraction": round(c, 4), "n_slots": slots,
              "f_trade": round(f_trade, 6), "risk_pct": round(100.0 * f_trade, 4)}
    return round(100.0 * f_trade, 4), detail


def bet_fraction():
    """Fraction de mise « meilleure connaissance » pour les surfaces spot/marge et le CLI :
    bayésien sur stats LIVE × fraction drawdown si disponibles, sinon repli plug-in paper
    demi-Kelly (legacy, marqué comme tel). Réseau best-effort. Champs compat : f, f_full, note."""
    ls = live_stats()
    if ls:
        kb = kelly_bayes(ls["wins"], ls["losses"], ls["R"])
        c = dd_fraction()
        f = min((kb.get("f0") or 0.0) * c, _knob("KELLY_MAX_FRACTION", DEF_MAX_FRACTION))
        return {"f": round(f, 6), "f_full": kb.get("f0"), "source": "bayes-live",
                "bayes": kb, "dd_fraction": round(c, 4), "live": ls,
                "note": f"bayésien LIVE ({kb.get('note')}) × c_dd {c:.3f}"}
    W, R, n = measured_stats()
    k = kelly_fraction(W, R)
    k = dict(k, source="paper-plugin", n=n,
             note=k.get("note", "") + " · repli PAPER plug-in (stats live indisponibles)")
    return k


def measured_stats():
    """(W, R) MESURÉS depuis le journal d'outcomes (stats_report). Best-effort (None)."""
    try:
        import stats_report as sr
        s = sr.compute_stats(sr.load_rows())
        wr = s.get("win_rate")
        R = s.get("tp_sl_ratio")
        W = (wr / 100.0) if wr is not None else None
        return W, R, s.get("total")
    except Exception:
        return None, None, None


def account_capital():
    """Capital de référence pour le sizing (USDT), best-effort : valeur spot + equity
    futures. Défaut prudent KELLY_CAPITAL_DEFAULT si indisponible."""
    cap = 0.0
    got = False
    try:
        import real_positions as rp
        snap = rp.snapshot()
        cap += float((snap.get("totals") or {}).get("spot_usdt") or 0.0)
        got = True
    except Exception:
        pass
    try:
        import futures_report as fr
        eq = (fr.snapshot() or {}).get("equity_usdt")
        if eq:
            cap += float(eq)
            got = True
    except Exception:
        pass
    return cap if got and cap > 0 else _knob("KELLY_CAPITAL_DEFAULT", 100.0)


def recommended_usdt(per_op_cap, W=None, R=None, capital=None, fraction=None, cap=None):
    """Montant USDT recommandé = f × capital, REBORNÉ par le cap/opération de la surface.
    0 si edge négatif. PUR si W/R/capital injectés (legacy plug-in) ; sans injection,
    pipeline §111 : bayésien sur stats LIVE × fraction drawdown, repli paper plug-in."""
    capital = account_capital() if capital is None else float(capital)
    if W is None and R is None and fraction is None and cap is None:
        k = bet_fraction()                       # bayes-live ou repli paper (marqué)
        raw = float(k.get("f") or 0.0) * capital
        return round(min(raw, float(per_op_cap)), 2), k
    if W is None or R is None:
        mw, mr, _ = measured_stats()
        W = mw if W is None else W
        R = mr if R is None else R
    k = kelly_fraction(W, R, fraction=fraction, cap=cap)
    raw = k["f"] * capital
    return round(min(raw, float(per_op_cap)), 2), k


def snapshot(per_op_caps=None, capital=None, W=None, R=None, n=None):
    """Vue complète pour le dashboard : W, R, Kelly, capital, et taille recommandée par
    surface (rebornée par chaque cap/opération). LECTURE SEULE.

    Optimisation : `capital`, `W`, `R` peuvent être INJECTÉS (le dashboard les a déjà —
    real_positions/futures pour le capital, stats pour W/R) -> évite de re-fetcher (le
    coût de kelly passait de ~4 s à ~0). Sinon calculés en interne (CLI)."""
    if W is None or R is None:
        mw, mr, mn = measured_stats()
        W = mw if W is None else W
        R = mr if R is None else R
        n = mn if n is None else n
    k = kelly_fraction(W, R)
    capital = account_capital() if capital is None else float(capital)
    caps = per_op_caps or {"spot": 10.0, "margin": 10.0, "futures": 50.0}
    reco = {}
    for surface, c in caps.items():
        reco[surface] = round(min(k["f"] * capital, float(c)), 2)
    return {"W": k["W"], "R": k["R"], "f_full": k["f_full"], "f": k["f"],
            "edge_positive": k["edge_positive"], "fraction": k["fraction"], "cap": k["cap"],
            "capital_usdt": round(capital, 2), "n_samples": n, "note": k["note"],
            "recommended_usdt": reco}


def main():
    import json
    snap = snapshot()
    print("=== CRITÈRE DE KELLY (fractionnaire, borné) ===")
    print(f"W (win rate) = {snap['W']}  ·  R (payoff) = {snap['R']}  ·  n = {snap['n_samples']}  [PAPER]")
    print(f"f Kelly complet = {snap['f_full']}  ->  f appliqué (×{snap['fraction']}, cap {snap['cap']}) = {snap['f']}")
    print(f"Edge positif ? {snap['edge_positive']}  ·  {snap['note']}")
    print(f"Capital ≈ ${snap['capital_usdt']}")
    print("Taille recommandée / surface :", json.dumps(snap["recommended_usdt"]))
    if not snap["edge_positive"]:
        print("\n⚠️ Edge PAPER NÉGATIF -> plug-in legacy : mise 0 sur toutes les surfaces.")
    # §111 : le CALCULATEUR réel (bayésien stats LIVE × fraction drawdown ÷ budget corrélé)
    slots = int(_cfg("FUTURES_AUTO_MAX_POSITIONS", 3))
    pct, det = futures_risk_pct(n_slots=slots)
    print("\n=== CALCULATEUR DE MISE §111 (bayésien LIVE × c_dd ÷ budget corrélé) ===")
    if pct is None:
        print("Stats live indisponibles -> fail-open (garde fixe FUTURES_RISK_PCT_PER_TRADE seule).")
    else:
        ls, kb = det["live"], det["bayes"]
        print(f"Fills réels : n={ls['n']} · wins={ls['wins']} · R={ls['R']:.2f} · forme {ls.get('shape')}")
        print(f"Bayes (prior break-even {kb.get('p0')}, k={kb.get('prior_strength'):.0f}) : "
              f"posterior {kb.get('p_post')} -> f0={kb.get('f0')}")
        print(f"× c_dd {det['dd_fraction']} (mandat MDD, Thorp 7.13) ÷ {det['n_slots']} slots corrélés "
              f"-> RISQUE/TRADE = {pct} % d'equity")
        if pct <= 0:
            print("-> Kelly dit NE PAS MISER (posterior ≤ break-even) : la boucle s'abstient d'ouvrir.")


if __name__ == "__main__":
    main()
