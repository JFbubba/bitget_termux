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
from config_utils import cfg as _cfg

DEF_FRACTION = 0.5      # Demi-Kelly par défaut
DEF_MAX_FRACTION = 0.25  # plafond dur : jamais > 25 % du capital


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
    0 si edge négatif. PUR si W/R/capital injectés."""
    if W is None or R is None:
        mw, mr, _ = measured_stats()
        W = mw if W is None else W
        R = mr if R is None else R
    k = kelly_fraction(W, R, fraction=fraction, cap=cap)
    capital = account_capital() if capital is None else float(capital)
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
    print(f"W (win rate) = {snap['W']}  ·  R (payoff) = {snap['R']}  ·  n = {snap['n_samples']}")
    print(f"f Kelly complet = {snap['f_full']}  ->  f appliqué (×{snap['fraction']}, cap {snap['cap']}) = {snap['f']}")
    print(f"Edge positif ? {snap['edge_positive']}  ·  {snap['note']}")
    print(f"Capital ≈ ${snap['capital_usdt']}")
    print("Taille recommandée / surface :", json.dumps(snap["recommended_usdt"]))
    if not snap["edge_positive"]:
        print("\n⚠️ Edge mesuré NÉGATIF -> Kelly recommande une taille de 0 sur TOUTES les "
              "surfaces. Ne pas miser tant qu'un edge positif n'est pas démontré.")


if __name__ == "__main__":
    main()
