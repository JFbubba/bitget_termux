"""
accum_backtest.py — backtest COST-BASIS de l'accumulation BTC (§38, §42).

Classement : SAFE. Lecture seule, réseau public sans clé (blockchain.info,
alternative.me), AUCUN ordre, ne modifie AUCUN état du bot.

Pourquoi ce module (au lieu du scratch de §38) : §38 avait validé le sizing par
survente court-terme avec des outils jetables non committés — impossible à
rejouer. Ici l'outillage est COMMITTÉ et testé : c'est le prérequis exigé par
§40 avant toute intégration de Hash Ribbons à l'opportunity_score.

Méthode (métrique honnête de §38) :
  • On simule le DCA quotidien du moteur réel (`opportunity_score` + `dca_amount`,
    mêmes défauts) sur l'historique BTC journalier COMPLET (~2011+).
  • Métrique = AVANTAGE DE PRIX DE REVIENT vs DCA plat : (cb_plat − cb_strat)/cb_plat.
    Le cost basis Σ$/Σbtc est invariant d'échelle -> « à budget égal » est automatique
    (on n'isole QUE le timing/sizing, jamais le fait d'investir plus).
  • Candidat Hash Ribbons : score' = clip01(score + w·f(signal_t)), signal_t calculé
    SANS look-ahead (ribbon au jour t = SMA30/60 du hashrate jusqu'à t inclus).
    Deux formes : "boost" (seule la REPRISE augmente le score — on n'ACHÈTE jamais
    moins à cause du ribbon) et "signed" (la capitulation réduit aussi le score —
    a priori suspect : leçon §38, réduire dans les krachs achète moins au plus bas).
  • Protocole anti-surapprentissage : grille (w × forme) choisie sur IS (70 %
    chronologique), jugée UNE fois sur OOS (30 %) ; robustesse = fraction de plis
    contigus positifs (5 plis) ; le nombre d'essais de la grille est AFFICHÉ.

CLI : python accum_backtest.py
"""

import math
import time

import requests

from config_utils import cfg as _cfg
from numeric_utils import safe_float
from onchain_btc import RIBBON_COURTE, RIBBON_LONGUE, REPRISE_FENETRE, parse_hashrate

PRICE_URL = "https://api.blockchain.info/charts/market-price"
HASHRATE_URL = "https://api.blockchain.info/charts/hash-rate"
FNG_URL = "https://api.alternative.me/fng/"
UA = {"User-Agent": "Mozilla/5.0"}

# Grille candidate (choisie sur IS seulement, jugée une fois sur OOS).
HR_POIDS = (0.1, 0.2, 0.3, 0.5)
HR_FORMES = ("boost", "signed")
WARMUP_J = 120                      # jours avant le 1er achat (RSI/MA/ribbon mûrs)


# ---------- cœurs purs (testables) ----------

def ribbon_signals(valeurs, courte=RIBBON_COURTE, longue=RIBBON_LONGUE,
                   fenetre=REPRISE_FENETRE):
    """PUR. Signal Hash Ribbons PAR JOUR, sans look-ahead : sortie[t] ==
    onchain_btc.hash_ribbons(valeurs[:t+1])["signal"] (équivalence testée), mais en
    UNE passe O(n) (préfixes de sommes) au lieu de O(n³) en rejouant les préfixes.
    Série illisible -> liste de 0.0 (neutre)."""
    serie = [safe_float(v) for v in (valeurs or [])]
    serie = [v for v in serie if v is not None]
    n = len(serie)
    out = [0.0] * n
    try:
        courte, longue = int(courte), int(longue)
    except (TypeError, ValueError):
        return out
    if courte <= 0 or longue <= courte or n == 0:
        return out
    pref = [0.0]
    for v in serie:
        pref.append(pref[-1] + v)
    sc = [None] * n
    sl = [None] * n
    for i in range(n):
        if i + 1 >= courte:
            sc[i] = (pref[i + 1] - pref[i + 1 - courte]) / courte
        if i + 1 >= longue:
            sl[i] = (pref[i + 1] - pref[i + 1 - longue]) / longue
    croix = [False] * n                       # croisement haussier au point i
    for i in range(1, n):
        if None in (sc[i - 1], sl[i - 1], sc[i], sl[i]):
            continue
        croix[i] = sc[i - 1] < sl[i - 1] and sc[i] > sl[i]
    for t in range(n):
        if t + 1 < longue + 5 or sc[t] is None or sl[t] is None:
            continue                          # préfixe trop court -> neutre (0.0)
        debut = max(longue, t + 1 - int(fenetre))
        reprise = any(croix[i] for i in range(debut, t + 1))
        if reprise:
            out[t] = 1.0
        elif sc[t] < sl[t]:
            out[t] = -0.3
    return out


def cost_basis(montants, prix):
    """PUR. Prix de revient moyen = Σ$ dépensés / Σ BTC achetés. None si vide/dégénéré.
    Invariant d'échelle : multiplier tous les montants par c ne change rien -> comparer
    deux stratégies EST une comparaison à budget égal (le timing seul est mesuré)."""
    tot_usd = tot_btc = 0.0
    for a, p in zip(montants, prix):
        a, p = safe_float(a), safe_float(p)
        if a is None or p is None or a <= 0 or p <= 0:
            continue
        tot_usd += a
        tot_btc += a / p
    return (tot_usd / tot_btc) if tot_btc > 0 else None


def avantage_pct(montants, prix):
    """PUR. Avantage de prix de revient (%) vs DCA PLAT sur les mêmes jours/prix :
    (cb_plat − cb_strat)/cb_plat × 100. >0 = la stratégie achète mieux que le plat."""
    cb_s = cost_basis(montants, prix)
    cb_f = cost_basis([1.0] * len(prix), prix)
    if cb_s is None or cb_f is None or cb_f <= 0:
        return None
    return (cb_f - cb_s) / cb_f * 100.0


def score_hr(score, signal, poids, forme):
    """PUR. Mélange du signal Hash Ribbons au score d'opportunité, borné [0,1].
    "boost" : seule la partie POSITIVE (reprise) renforce — on n'achète jamais
    moins à cause du ribbon. "signed" : la capitulation (−0.3) réduit aussi."""
    s = safe_float(signal) or 0.0
    apport = max(s, 0.0) if forme == "boost" else s
    x = (safe_float(score) or 0.0) + float(poids) * apport
    return max(0.0, min(1.0, x))


def simulate_amounts(closes, fg, hr, poids=0.0, forme="boost",
                     warmup=WARMUP_J, st_weight=None, st_window=None, fenetre=200):
    """PUR (déterministe). Rejoue le moteur d'accumulation jour par jour :
    montant_t = dca_amount(score'_t) avec score'_t = score_hr(opportunity_score
    (fenêtre de 200 jours finissant en t — FIDÈLE à la production, où analyze()
    lit `_closes(symbol, limit=200)`), fg[t], hr[t], poids, forme). AUCUN
    look-ahead. Retourne (montants, prix) alignés sur les jours t >= warmup."""
    import accumulation_engine as ae
    stw = 0.30 if st_weight is None else st_weight       # défauts du moteur déployé,
    stk = 24 if st_window is None else st_window         # figés (indépendants de config)
    montants, prix = [], []
    for t in range(int(warmup), len(closes)):
        vue = closes[max(0, t + 1 - int(fenetre)):t + 1]
        s = ae.opportunity_score(vue, fear_greed=fg[t],
                                 st_weight=stw, st_window=stk)["score"]
        s = score_hr(s, hr[t] if t < len(hr) else 0.0, poids, forme)
        montants.append(ae.dca_amount(s, base=10.0, max_mult=5.0))
        prix.append(closes[t])
    return montants, prix


def folds_positifs(montants, prix, n_plis=5):
    """PUR. Robustesse : fraction de plis chronologiques contigus où l'avantage
    vs plat est > 0. Un avantage porté par une seule époque ne généralise pas."""
    n = min(len(montants), len(prix))
    if n < n_plis * 30:
        return {"folds": [], "frac": 0.0}
    taille = n // n_plis
    vals = []
    for k in range(n_plis):
        a, b = k * taille, (k + 1) * taille if k < n_plis - 1 else n
        adv = avantage_pct(montants[a:b], prix[a:b])
        vals.append(round(adv, 3) if adv is not None else None)
    ok = [v for v in vals if v is not None]
    frac = (sum(1 for v in ok if v > 0) / len(ok)) if ok else 0.0
    return {"folds": vals, "frac": round(frac, 3)}


def run_backtest(closes, fg, hashrates, split=0.7):
    """PUR (données fournies). Protocole complet §42 : baseline (moteur actuel)
    vs grille Hash Ribbons — grille CHOISIE sur IS, jugée UNE fois sur OOS,
    robustesse par plis sur TOUTE la période. Retourne un dict rapport."""
    hr = ribbon_signals(hashrates)
    n = len(closes)
    coupe = int(n * float(split))

    def _eval(poids, forme):
        m, p = simulate_amounts(closes, fg, hr, poids, forme)
        k = coupe - WARMUP_J                      # index de coupe dans la série simulée
        return {"poids": poids, "forme": forme,
                "is": avantage_pct(m[:k], p[:k]),
                "oos": avantage_pct(m[k:], p[k:]),
                "plis": folds_positifs(m, p),
                "avantage_total": avantage_pct(m, p)}

    base = _eval(0.0, "boost")                    # poids 0 = moteur ACTUEL (baseline)
    grille = [_eval(w, f) for f in HR_FORMES for w in HR_POIDS]
    # sélection sur IS SEULEMENT (delta vs baseline IS), verdict sur OOS
    meilleur = max(grille, key=lambda g: (g["is"] if g["is"] is not None else -1e9))
    delta_is = (meilleur["is"] - base["is"]) if None not in (meilleur["is"], base["is"]) else None
    delta_oos = (meilleur["oos"] - base["oos"]) if None not in (meilleur["oos"], base["oos"]) else None
    retenu = bool(delta_is is not None and delta_is > 0
                  and delta_oos is not None and delta_oos > 0
                  and meilleur["plis"]["frac"] >= base["plis"]["frac"]
                  and meilleur["plis"]["frac"] >= 0.6)
    return {"n_jours": n, "coupe_is": coupe, "n_essais": len(grille),
            "signal_hr": {"jours_reprise": sum(1 for x in hr if x > 0),
                          "jours_capitulation": sum(1 for x in hr if x < 0)},
            "baseline": base, "grille": grille, "meilleur": meilleur,
            "delta_is": delta_is, "delta_oos": delta_oos, "retenu": retenu}


# ---------- réseau (best-effort, caché) ----------

def _fetch_chart(url, cle_cache, ttl=86400):
    def _fetch():
        r = requests.get(url, params={"timespan": "all", "format": "json",
                                      "sampled": "false"}, headers=UA, timeout=20)
        r.raise_for_status()
        return parse_hashrate(r.json())          # même format {values:[{x,y}]}
    try:
        import runtime_cache as rc
        return rc.get(cle_cache, ttl, _fetch, fallback=[])
    except Exception:
        return []


def fetch_prix_journalier():
    """Prix BTC journalier complet (blockchain.info, ~2009+). [] si injoignable."""
    return _fetch_chart(PRICE_URL, "bt_prix_all")


def fetch_hashrate_journalier():
    """Hashrate BTC journalier complet. [] si injoignable."""
    return _fetch_chart(HASHRATE_URL, "bt_hashrate_all")


def fetch_fng_historique():
    """{jour_unix: valeur} du Fear&Greed (2018+). {} si injoignable."""
    def _fetch():
        r = requests.get(FNG_URL, params={"limit": 0}, headers=UA, timeout=20)
        r.raise_for_status()
        out = {}
        for e in (r.json() or {}).get("data") or []:
            t, v = safe_float(e.get("timestamp")), safe_float(e.get("value"))
            if t is not None and v is not None:
                out[int(t) // 86400] = v
        return out
    try:
        import runtime_cache as rc
        return rc.get("bt_fng_all", 86400, _fetch, fallback={})
    except Exception:
        return {}


def align_series(prix_pts, hash_pts, fng_par_jour):
    """PUR. Aligne prix/hashrate/F&G par JOUR unix. Ne garde que les jours où prix>0
    ET hashrate présent (l'accumulation exige les deux). F&G absent -> None (le
    score dégrade comme en production). Retourne (closes, fg, hashrates)."""
    prix = {p["t"] // 86400: p["v"] for p in (prix_pts or []) if p.get("v")}
    hashr = {p["t"] // 86400: p["v"] for p in (hash_pts or []) if p.get("v")}
    jours = sorted(set(prix) & set(hashr))
    # le cache runtime passe par JSON : les clés int deviennent str -> normalise
    fng_par_jour = {int(float(k)): v for k, v in (fng_par_jour or {}).items()
                    if safe_float(k) is not None}
    closes = [prix[j] for j in jours]
    hs = [hashr[j] for j in jours]
    fg = [fng_par_jour.get(j) for j in jours]
    return closes, fg, hs


# ---------- rapport ----------

def build_report(res):
    """Rapport texte lisible du backtest. PUR."""
    if not res or res.get("erreur"):
        return ("=== BACKTEST COST-BASIS (accumulation) ===\n"
                f"Indisponible : {res.get('erreur', 'données absentes')}. "
                "Aucun ordre. VERDICT: SAFE")
    b, m = res["baseline"], res["meilleur"]
    sig = res["signal_hr"]
    lignes = [
        "=== BACKTEST COST-BASIS (accumulation §42 : Hash Ribbons) ===",
        f"{res['n_jours']} jours · coupe IS/OOS au jour {res['coupe_is']} · "
        f"{res['n_essais']} essais de grille (multiple-testing affiché)",
        f"Ribbon : {sig['jours_reprise']} j de reprise, {sig['jours_capitulation']} j de capitulation",
        "",
        f"Baseline (moteur actuel)     : IS {b['is']:+.3f} % · OOS {b['oos']:+.3f} % · "
        f"plis+ {b['plis']['frac']:.0%} {b['plis']['folds']}",
        f"Meilleur candidat (choisi IS): {m['forme']} w={m['poids']} -> "
        f"IS {m['is']:+.3f} % · OOS {m['oos']:+.3f} % · plis+ {m['plis']['frac']:.0%} {m['plis']['folds']}",
        f"Delta vs baseline            : IS {res['delta_is']:+.3f} pt · OOS {res['delta_oos']:+.3f} pt",
        "",
        "Grille complète (transparence anti-cherry-picking) :",
    ]
    for g in res["grille"]:
        lignes.append(f"  {g['forme']:<7} w={g['poids']:<4} IS {g['is']:+.3f} % · "
                      f"OOS {g['oos']:+.3f} % · plis+ {g['plis']['frac']:.0%}")
    verdict = ("RETENU : le candidat bat la baseline IS ET OOS avec robustesse par plis."
               if res["retenu"] else
               "REJETÉ : pas d'amélioration robuste IS+OOS+plis vs le moteur actuel.")
    lignes += ["", verdict,
               "Backtest lecture seule (aucun état modifié). Aucun ordre. VERDICT: SAFE"]
    return "\n".join(lignes)


def run():
    """Collecte (best-effort) + backtest complet. Retourne le dict rapport ou {erreur}."""
    prix = fetch_prix_journalier()
    hs = fetch_hashrate_journalier()
    fng = fetch_fng_historique()
    closes, fg, hashrates = align_series(prix, hs, fng)
    if len(closes) < WARMUP_J * 3:
        return {"erreur": f"historique insuffisant ({len(closes)} jours alignés)"}
    return run_backtest(closes, fg, hashrates)


def main():
    print(build_report(run()))


if __name__ == "__main__":
    main()
