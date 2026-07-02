"""carry_agent.py — agent CARRY du cerveau : positionnement dérivés contrarian (LECTURE SEULE).

Classement : SAFE. Réseau public en lecture seule (via derivs_positioning), aucun
ordre, aucun secret.

Pourquoi : quand le positionnement devient extrême (funding très positif, foule de
comptes très long, perp en premium marqué sur le spot), le côté surpeuplé PAYE le
portage et fournit le carburant des squeezes — historiquement, ces extrêmes se
résolvent contre la foule. L'agent FADE donc les extrêmes de positionnement.
Famille de données ORTHOGONALE à la recherche négative du dépôt (RESEARCH_NOTES
§36-37 n'a balayé que des dérivés de bougies ; funding/ratio L/S/basis n'y étaient
pas). Contrairement à l'agent `derivs` (contrarian 1D sur le funding agrégé seul),
celui-ci combine trois dimensions et le z-score HISTORIQUE du funding.

Contrat d'échec : fail-safe -> vote nul/confiance nulle, jamais d'exception
propagée au cerveau. Confiance PLAFONNÉE à 0.6 (humilité : signal jamais validé
à l'étalon — l'EARCP et le chemin 2/3 de la validation jugeront sur pièces).
"""

# ---------- cœur pur (testable) ----------

FUNDING_EXTREME = 0.0005    # 0.05 %/8h : funding extrême (annualisé ~55 %)
CONF_MAX = 0.6              # plafond d'humilité


def _clamp(x, lo=-1.0, hi=1.0):
    """PUR. Borne x dans [lo, hi]."""
    return max(lo, min(hi, x))


def _zscore(historique, courant):
    """PUR. z-score du funding courant vs historique (écart-type population,
    stdlib). None si données insuffisantes (<10 points valides) ou sigma ~0."""
    if courant is None or not historique:
        return None
    vals = []
    for v in historique:
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    if len(vals) < 10:
        return None
    try:
        import statistics
        mu = statistics.fmean(vals)
        sigma = statistics.pstdev(vals)
        if sigma <= 1e-12:
            return None
        return (float(courant) - mu) / sigma
    except (TypeError, ValueError):
        return None


def _foule(ls_ratio):
    """PUR. Foule long/short dans [-1, 1] (recodé localement : le cœur ne dépend
    d'aucun module). ratio 1.0 -> 0 ; >=2.5 -> +1 (troupeau très long) ;
    <=0.4 -> -1 ; continu entre : clamp((r-1)/1.5) côté long,
    -clamp((1/r-1)/1.5) côté court. None/illisible/<=0 -> 0.0."""
    try:
        r = float(ls_ratio)
    except (TypeError, ValueError):
        return 0.0
    if r <= 0:
        return 0.0
    if r >= 1.0:
        return _clamp((r - 1.0) / 1.5, 0.0, 1.0)
    return -_clamp((1.0 / r - 1.0) / 1.5, 0.0, 1.0)


def signal(funding_hist, funding_courant, ls_ratio, basis_pct):
    """Cœur PUR du vote contrarian : fade les extrêmes de positionnement.

    - c_funding = -clamp(z/2.5), renforcé de 50 % si |funding courant| >= 0.05 %/8h
      (extrême absolu), puis re-clampé ;
    - c_foule = -foule(ls_ratio) * 0.8 (troupeau très long -> penche short) ;
    - c_basis = -clamp(basis_pct/0.5) * 0.4 (perp premium marqué = euphorie long) ;
    - vote = clamp(0.5·c_funding + 0.35·c_foule + 0.15·c_basis), poids renormalisés
      sur les composantes DISPONIBLES si le z est incalculable ;
    - confidence = min(0.6, |vote|·1.2).
    PUR, déterministe, aucune I/O."""
    z = _zscore(funding_hist, funding_courant)
    hist_ok = z is not None
    if not hist_ok and ls_ratio is None:
        return {"vote": 0.0, "confidence": 0.0, "note": "données insuffisantes"}

    composantes = []                                # [(poids, valeur)]
    if hist_ok:
        c_funding = -_clamp(z / 2.5)
        try:
            if funding_courant is not None and abs(float(funding_courant)) >= FUNDING_EXTREME:
                c_funding = _clamp(c_funding * 1.5)  # extrême absolu : renforce
        except (TypeError, ValueError):
            pass
        composantes.append((0.5, c_funding))
    f = _foule(ls_ratio)
    if ls_ratio is not None:
        composantes.append((0.35, -f * 0.8))
    if basis_pct is not None:
        try:
            composantes.append((0.15, -_clamp(float(basis_pct) / 0.5) * 0.4))
        except (TypeError, ValueError):
            pass
    poids_total = sum(p for p, _ in composantes)
    if poids_total <= 0:
        return {"vote": 0.0, "confidence": 0.0, "note": "données insuffisantes"}
    vote = _clamp(sum(p * v for p, v in composantes) / poids_total)
    conf = min(CONF_MAX, abs(vote) * 1.2)
    z_txt = f"{z:+.1f}" if z is not None else "n/a"
    b_txt = f"{float(basis_pct):+.2f}%" if basis_pct is not None else "n/a"
    return {"vote": round(vote, 3), "confidence": round(conf, 3),
            "note": f"carry z={z_txt} foule={f:+.2f} basis={b_txt}"}


# ---------- adaptateurs (best-effort) ----------

def analyze(symbol="BTCUSDT", ttl=300):
    """Analyse live cachée, best-effort : fallback neutre si la source est
    injoignable (jamais d'exception)."""
    sym = str(symbol or "BTCUSDT").upper()

    def _fetch():
        import derivs_positioning as dp
        snap = dp.fetch_snapshot(sym) or {}
        hist = dp.fetch_funding_history(sym) or []
        return signal(hist, snap.get("funding"), snap.get("ls_ratio"),
                      snap.get("basis_pct"))
    try:
        import runtime_cache as rc
        return rc.get(f"carry:{sym}", ttl, _fetch,
                      fallback={"vote": 0.0, "confidence": 0.0, "note": "n/a"})
    except Exception:
        return {"vote": 0.0, "confidence": 0.0, "note": "n/a"}


def agent(symbol="BTCUSDT"):
    """Adaptateur essaim : {vote, confidence, note}. Best-effort."""
    a = analyze(symbol)
    return {"vote": a.get("vote", 0.0), "confidence": a.get("confidence", 0.0),
            "note": a.get("note", "n/a")}


# ---------- rapport ----------

def build_report(symbol="BTCUSDT"):
    a = analyze(symbol)
    return (f"=== AGENT CARRY (positionnement dérivés) — {str(symbol).upper()} ===\n"
            f"Vote : {a.get('vote', 0.0):+.3f} | confiance : {a.get('confidence', 0.0):.3f}\n"
            f"Détail : {a.get('note', 'n/a')}\n"
            "Contrarian sur les extrêmes de positionnement (funding, foule L/S, basis).\n"
            "Lecture seule. Aucun ordre. VERDICT: SAFE")


def main():
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(build_report(symbol))


if __name__ == "__main__":
    main()
