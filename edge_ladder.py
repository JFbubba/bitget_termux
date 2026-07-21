"""
edge_ladder.py — l'ÉCHELLE D'EDGE par agent (promotion paper -> réel).

Classement : SAFE. Pur / lecture seule, AUCUN ordre. Généralise la « porte d'edge »
du mandat à TOUS les agents du cerveau : chaque agent reçoit un PALIER selon son
edge mesuré (DSR déflaté + taille d'échantillon + Sharpe hors-échantillon) lu dans
`validation_report.json` (produit par la validation T5). C'est le mécanisme « par
paliers, agent par agent » : un agent ne devient éligible au RÉEL qu'au palier LIVE.

Paliers :
  • LIVE      : edge REPLAY (DSR≥seuil, n≥min, OOS>0) ET edge LIVE confirme -> eligible reel
  • PROBATION : DSR ≥ 0.50 ET n ≥ 30                      -> prometteur, reste paper
  • PAPER     : DSR ≥ 0.10                                 -> neutre, paper
  • NEGATIVE  : sinon                                      -> bridé (prior faible)

Porte CPCV (armable, CPCV_GATE — .env OR config, défaut OFF) : LIVE exige EN PLUS que la
distribution d'IC OOS multi-chemins (champ `cpcv` du rapport, cpcv_diagnostic §54) ne soit
pas FRAGILE — un walk-forward mono-chemin peut « valider » un artefact de chemin (démonstration
backlog : p10 ≈ −0.000 sur 45 chemins là où le WF simple validait). Fail-open sur absence de
mesure (même philosophie que _annuel_ok) ; RÉDUCTEUR-SEULEMENT : ne promeut jamais, ne fait
que retenir une promotion.

Cohérent avec `mandate.futures_live_allowed` (même critère LIVE). Les priors de poids
sont ADVISORY : ils n'écrasent pas l'apprentissage EARCP, ils le bornent/orientent —
branchés dans swarm_brain._apply_edge_priors (adoucis prior**alpha, débrayables).
"""

import json
from pathlib import Path

REPORT_FILE = Path(__file__).resolve().parent / "validation_report.json"

TIERS = ("LIVE", "PROBATION", "PAPER", "NEGATIVE")
_PRIOR = {"LIVE": 1.5, "PROBATION": 1.0, "PAPER": 0.6, "NEGATIVE": 0.3}


from config_utils import cfg as _cfg
from config_utils import env_flag as _env_flag


def _load(report=None):
    if report is not None:
        return report
    try:
        return json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _live_confirms(live_row, min_n=None, min_ic_t=None):
    """L'edge sur les VOTES REELS (section 'live' du rapport) confirme-t-il l'agent :
    echantillon suffisant ET IC significatif ? PUR. Conservateur : pas de ligne live
    -> False (aucune promotion LIVE sans preuve sur les votes reellement emis)."""
    if not live_row:
        return False
    min_n = int(_cfg("MANDATE_LIVE_MIN_SAMPLES", 60) if min_n is None else min_n)
    min_t = float(_cfg("MANDATE_LIVE_MIN_IC_T", 2.0) if min_ic_t is None else min_ic_t)
    return (int((live_row or {}).get("n", 0) or 0) >= min_n
            and float((live_row or {}).get("ic_t", 0) or 0) >= min_t)


def _live_row(rep, agent):
    """Ligne 'live' (votes reels) d'un agent dans le rapport, ou None. PUR."""
    for r in ((rep or {}).get("live", {}) or {}).get("agents", []):
        if str(r.get("agent")) == str(agent):
            return r
    return None


def _replay_passes(row, dsr_min=None, min_n=None):
    """L'agent bat-il l'edge REPLAY (backtest) : DSR ≥ seuil ET n ≥ min ET OOS > 0 ? PUR."""
    dsr_min = float(_cfg("MANDATE_FUTURES_DSR_MIN", 0.90) if dsr_min is None else dsr_min)
    min_n = int(_cfg("MANDATE_FUTURES_MIN_SAMPLES", 120) if min_n is None else min_n)
    dsr = float((row or {}).get("dsr", 0) or 0)
    n = int((row or {}).get("n", 0) or 0)
    oos = (row or {}).get("oos_sharpe")
    oos = float(oos) if oos is not None else 0.0
    return dsr >= dsr_min and n >= min_n and oos > 0


def _cpcv_row(rep, agent):
    """Ligne CPCV d'un agent dans le champ `cpcv` du rapport, ou None. PUR."""
    return ((((rep or {}).get("cpcv", {}) or {}).get("agents", {}) or {}).get(str(agent)))


def _cpcv_ok(cpcv_row):
    """Porte CPCV multi-chemins. Désarmée (CPCV_GATE off, défaut) -> transparente.
    Armée : bride le LIVE si la distribution d'IC OOS est FRAGILE (ic_p10 ≤ 0 OU
    frac_neg > CPCV_MAX_FRAC_NEG). FAIL-OPEN : diagnostic absent, champs manquants ou
    < CPCV_MIN_PATHS chemins -> transparente (on bride sur preuve, pas sur absence
    de mesure — même philosophie que _annuel_ok)."""
    if not _env_flag("CPCV_GATE", False):
        return True
    if not isinstance(cpcv_row, dict):
        return True
    try:
        n = int(cpcv_row.get("n_chemins", 0) or 0)
    except (TypeError, ValueError):
        return True
    if n < int(_cfg("CPCV_MIN_PATHS", 30)):
        return True
    p10, fneg = cpcv_row.get("ic_p10"), cpcv_row.get("frac_neg")
    if p10 is None or fneg is None:
        return True
    try:
        return float(p10) > 0.0 and float(fneg) <= float(_cfg("CPCV_MAX_FRAC_NEG", 0.10))
    except (TypeError, ValueError):
        return True


def _annuel_ok(row):
    """Robustesse ANNUELLE (§54). PUR. Un agent dont l'IC sur UN AN d'historique est
    NÉGATIF est un artefact de régime possible : pas de LIVE. FAIL-OPEN : sans
    mesure annuelle (historique absent), la porte est transparente — on bride sur
    preuve, pas sur absence de mesure."""
    an = (row or {}).get("annuel")
    if not isinstance(an, dict) or an.get("ic") is None:
        return True
    return float(an["ic"]) > 0.0


def tier_of(row, live_row=None, dsr_min=None, min_n=None, cpcv_row=None):
    """Palier d'un agent. PUR. LIVE exige l'edge REPLAY (DSR/n/OOS) ET la confirmation
    sur les VOTES REELS (live) ET la robustesse ANNUELLE (§54 : pas de promotion
    d'un artefact de régime) ET la porte CPCV si armée (pas de promotion d'un artefact
    de CHEMIN) ; replay seul -> PROBATION (prometteur, reste paper)."""
    if _replay_passes(row, dsr_min, min_n):
        return ("LIVE" if (_live_confirms(live_row) and _annuel_ok(row)
                           and _cpcv_ok(cpcv_row))
                else "PROBATION")            # live/annuel/cpcv pas (encore) confirmés
    dsr = float((row or {}).get("dsr", 0) or 0)
    n = int((row or {}).get("n", 0) or 0)
    if dsr >= 0.50 and n >= 30:
        return "PROBATION"
    if dsr >= 0.10:
        return "PAPER"
    return "NEGATIVE"


def live_pending(row, live_row=None, dsr_min=None, min_n=None, cpcv_row=None):
    """L'agent bat-il le REPLAY mais PAS (encore) la confirmation live ? PUR.
    True = « à une confirmation live près du palier LIVE » : purement informatif (observabilité),
    ne donne AUCUN droit réel. Sert à voir qui approche du réel sans qu'aucun verrou ne bouge."""
    return bool(_replay_passes(row, dsr_min, min_n)
                and not (_live_confirms(live_row) and _annuel_ok(row)
                         and _cpcv_ok(cpcv_row)))


def agent_tier(agent, report=None):
    """Palier d'un agent nommé (NEGATIVE si absent du rapport). PUR."""
    rep = _load(report)
    for row in rep.get("ranking", []):
        if str(row.get("agent")) == str(agent):
            return tier_of(row, _live_row(rep, agent), cpcv_row=_cpcv_row(rep, agent))
    return "NEGATIVE"


def all_tiers(report=None):
    """{agent: palier} pour tous les agents du rapport. PUR."""
    rep = _load(report)
    return {row.get("agent"): tier_of(row, _live_row(rep, row.get("agent")),
                                      cpcv_row=_cpcv_row(rep, row.get("agent")))
            for row in rep.get("ranking", [])}


def weight_prior(agent, report=None):
    """Prior de poids ADVISORY selon le palier (borne/oriente EARCP). PUR."""
    return _PRIOR[agent_tier(agent, report)]


def weight_priors(report=None):
    """{agent: prior ADVISORY} pour les agents PRÉSENTS dans le rapport. PUR.

    Deux sources d'évidence, toutes deux bornées par _PRIOR :
      • palier replay (section 'ranking') -> prior du palier ;
      • dérate LIVE : un IC significativement NÉGATIF sur les votes réels
        (n ≥ MANDATE_LIVE_MIN_SAMPLES, ic_t ≤ −MANDATE_LIVE_MIN_IC_T) plafonne le
        prior à NEGATIVE — l'évidence CONTRE un agent compte autant que l'évidence
        pour (symétrique de _live_confirms).
    Un agent ABSENT du rapport n'a AUCUNE entrée : le cerveau le traite neutre
    (×1.0) — on ne bride pas faute de mesure, on bride sur preuve. (≠ agent_tier,
    qui répond NEGATIVE pour un absent : là c'est une PORTE de promotion au réel,
    fail-closed par construction.)"""
    rep = _load(report)
    out = {}
    for row in rep.get("ranking", []):
        a = str(row.get("agent"))
        out[a] = _PRIOR[tier_of(row, _live_row(rep, a), cpcv_row=_cpcv_row(rep, a))]
    min_n = int(_cfg("MANDATE_LIVE_MIN_SAMPLES", 60))
    min_t = float(_cfg("MANDATE_LIVE_MIN_IC_T", 2.0))
    for r in (rep.get("live", {}) or {}).get("agents", []):
        a = str(r.get("agent"))
        try:
            n, ic_t = int(r.get("n", 0) or 0), float(r.get("ic_t", 0) or 0)
        except (TypeError, ValueError):
            continue
        if n >= min_n and ic_t <= -min_t:
            out[a] = min(out.get(a, 1.0), _PRIOR["NEGATIVE"])
    return out


def live_agents(report=None):
    """Agents au palier LIVE -> seuls éligibles au RÉEL. PUR."""
    return [a for a, t in all_tiers(report).items() if t == "LIVE"]


def build_report(report=None):
    rep = _load(report)
    ranking = rep.get("ranking", [])
    if not ranking:
        return ("=== ÉCHELLE D'EDGE (par agent) ===\n"
                "Aucun rapport de validation encore (lance brain_validation.py).\n"
                "Aucun agent éligible au réel. VERDICT: SAFE")
    rows = []
    for row in ranking:
        agent = row.get("agent")
        lr = _live_row(rep, agent)
        cr = _cpcv_row(rep, agent)
        rows.append((agent, tier_of(row, lr, cpcv_row=cr),
                     live_pending(row, lr, cpcv_row=cr)))
    order = {t: i for i, t in enumerate(TIERS)}
    rows.sort(key=lambda r: order.get(r[1], 9))
    lines = ["=== ÉCHELLE D'EDGE (par agent) ==="]
    for agent, t, pending in rows:
        suffix = "  ← replay OK, confirmation live en attente" if pending else ""
        lines.append(f"  {agent:<12} {t:<10} (prior ×{_PRIOR[t]}){suffix}")
    live = [a for a, t, _ in rows if t == "LIVE"]
    pend = [a for a, _, p in rows if p]
    lines.append(f"Éligibles RÉEL (palier LIVE) : {', '.join(live) if live else 'aucun'}")
    if pend:
        lines.append(f"À une confirmation live près : {', '.join(pend)} "
                     "(replay OK ; manque échantillon/IC sur les votes réels)")
    lines.append("Promotion par edge mesuré. Lecture seule, aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
