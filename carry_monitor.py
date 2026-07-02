"""carry_monitor.py — moniteur PAPER du carry non-directionnel (LECTURE SEULE + journal local).

Classement : SAFE. Réseau public en lecture seule (via derivs_positioning), aucun
ordre, aucun secret. Seule écriture : le journal local `.carry_journal.json`
(gitignoré, cap 500 entrées) pour accumuler l'historique.

Pourquoi : la recherche d'alpha du dépôt (RESEARCH_NOTES §35-38, ~554 signaux) a
montré qu'il n'existe PAS d'edge directionnel robuste. Le cash-and-carry (long
spot + short perpétuel, delta-neutre) est la seule famille de rendement qui n'en
suppose AUCUN : la position encaisse le funding payé par les longs sans parier
sur la direction. Ce module MESURE honnêtement ce rendement (APR brut/net des
frais) par symbole et le journalise ; il n'exécute RIEN — décision humaine
uniquement, et le futures reste paper de jure (§38).

Contrat d'échec : fail-safe -> valeurs None / attrait INCONNU, jamais d'exception.
"""

import json
import os
import time
from pathlib import Path

from config_utils import cfg as _cfg

JOURNAL_FILE = Path(__file__).resolve().parent / ".carry_journal.json"
JOURNAL_CAP = 500
SYMBOLES_REPLI = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
MAX_SYMBOLES = 6

# ---------- cœurs purs (testables) ----------


def apr_brut_pct(funding_hist, intervalle_h=8, fenetre=30):
    """PUR. APR brut du carry en % : moyenne des `fenetre` derniers funding
    (fractions par intervalle) × paiements/an × 100. None si historique vide."""
    if not funding_hist:
        return None
    vals = []
    for v in funding_hist[-int(fenetre):]:
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    if not vals or intervalle_h <= 0:
        return None
    par_an = (24.0 / float(intervalle_h)) * 365.0
    return (sum(vals) / len(vals)) * par_an * 100.0


def apr_net_pct(apr_brut, frais_aller_retour_pct=0.2, horizon_jours=30):
    """PUR. APR net des frais : brut − frais d'entrée+sortie AMORTIS sur l'horizon
    de détention (frais payés une fois, rapportés à l'année : frais × 365/horizon).
    None si brut None ou horizon invalide."""
    if apr_brut is None or horizon_jours is None or horizon_jours <= 0:
        return None
    try:
        return float(apr_brut) - float(frais_aller_retour_pct) * (365.0 / float(horizon_jours))
    except (TypeError, ValueError):
        return None


def attrait(apr_net, seuil_pct=5.0):
    """PUR. Étiquette d'attrait du carry : >= seuil -> ATTRACTIF ; [0, seuil[ ->
    NEUTRE ; < 0 -> NEGATIF ; None -> INCONNU."""
    if apr_net is None:
        return "INCONNU"
    try:
        v = float(apr_net)
    except (TypeError, ValueError):
        return "INCONNU"
    if v >= float(seuil_pct):
        return "ATTRACTIF"
    if v >= 0.0:
        return "NEUTRE"
    return "NEGATIF"


def borner_journal(journal, cap=JOURNAL_CAP):
    """PUR. Garde les `cap` dernières entrées du journal (liste)."""
    if not isinstance(journal, list):
        return []
    return journal[-int(cap):]


# ---------- évaluation (best-effort) ----------


def _symboles(symbols=None):
    """Univers à évaluer, best-effort : universe.symbols() sinon repli statique."""
    if symbols:
        return list(symbols)[:MAX_SYMBOLES]
    try:
        import universe
        syms = universe.symbols()
        if syms:
            return list(syms)[:MAX_SYMBOLES]
    except Exception:
        pass
    return list(SYMBOLES_REPLI)[:MAX_SYMBOLES]


def evaluer(symbols=None):
    """Évalue le carry par symbole (best-effort par symbole, ne lève jamais).
    Retourne [{symbol, funding, apr_brut_pct, apr_net_pct, attrait}]."""
    frais = _cfg("CARRY_FRAIS_ALLER_RETOUR_PCT", 0.2)
    seuil = _cfg("CARRY_SEUIL_APR_PCT", 5.0)
    out = []
    for sym in _symboles(symbols):
        funding, brut, net = None, None, None
        try:
            import derivs_positioning as dp
            snap = dp.fetch_snapshot(sym) or {}
            funding = snap.get("funding")
            hist = dp.fetch_funding_history(sym) or []
            brut = apr_brut_pct(hist, snap.get("funding_interval_h") or 8)
            net = apr_net_pct(brut, frais)
        except Exception:
            pass
        out.append({"symbol": str(sym).upper(), "funding": funding,
                    "apr_brut_pct": round(brut, 2) if brut is not None else None,
                    "apr_net_pct": round(net, 2) if net is not None else None,
                    "attrait": attrait(net, seuil)})
    return out


def journaliser(resultats, min_intervalle_s=3600):
    """Ajoute un instantané au journal local (gitignoré), cap 500, écriture
    atomique (fichier temporaire + os.replace). AUTO-THROTTLÉ : n'append que si
    la dernière entrée a plus de min_intervalle_s (le funding ne change que
    toutes les 8 h — inutile de journaliser à chaque cycle de 5 min).
    Best-effort : ne lève jamais. Retourne True si une entrée a été écrite."""
    try:
        journal = []
        if JOURNAL_FILE.exists():
            try:
                journal = json.loads(JOURNAL_FILE.read_text(encoding="utf-8"))
            except Exception:
                journal = []
        if journal and isinstance(journal[-1], dict):
            dernier_ts = journal[-1].get("ts") or 0
            if time.time() - dernier_ts < min_intervalle_s:
                return False                      # trop récent : throttle
        journal = borner_journal(journal + [{"ts": int(time.time()), "resultats": resultats}])
        tmp = JOURNAL_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(journal, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, JOURNAL_FILE)
        return True
    except Exception:
        return False


# ---------- rapport ----------


def _fmt_funding(x):
    return f"{float(x) * 100:+.4f} %/8h" if x is not None else "n/a"


def _fmt_pct(x):
    return f"{float(x):+.2f} %" if x is not None else "n/a"


def build_report(resultats=None):
    res = resultats if resultats is not None else evaluer()
    lignes = ["=== MONITEUR CARRY (cash-and-carry delta-neutre, PAPER) ==="]
    for r in res:
        lignes.append(f"{r['symbol']:<10} funding {_fmt_funding(r['funding'])} | "
                      f"APR brut {_fmt_pct(r['apr_brut_pct'])} | "
                      f"net {_fmt_pct(r['apr_net_pct'])} | {r['attrait']}")
    lignes.append("APR net = funding moyen 30 périodes annualisé − frais amortis (horizon 30 j).")
    lignes.append("Stratégie mesurée en PAPER uniquement (delta-neutre, long spot + short perp). Aucune exécution.")
    lignes.append("Lecture seule (hors journal local). Aucun ordre. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    res = evaluer()
    journaliser(res)
    print(build_report(res))


if __name__ == "__main__":
    main()
