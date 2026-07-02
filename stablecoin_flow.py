"""stablecoin_flow.py — flux de capitaux via l'offre de stablecoins (LECTURE SEULE).

Classement : SAFE. Réseau public en lecture seule, aucun ordre, aucun secret.
Source sans clé : stablecoins.llama.fi (DefiLlama). Endpoint jamais branché
jusqu'ici : defi_data.py ne lit que le TVL par chaîne instantané — ceci ne le
doublonne pas, on suit ici l'OFFRE de stablecoins et sa dynamique.

Motivation empirique : l'offre totale de stablecoins mesure les liquidités en
attente sur le marché crypto (« dry powder »). Une expansion = du capital frais
entre (mint net), historiquement un vent favorable large (croissance quasi
ininterrompue 2020-2021 pendant le bull) ; une contraction = les liquidités
refluent (burn net), régime de repli (contraction continue 2022-2023 pendant
le bear). Signal de RÉGIME marché-large et lent — jamais une prédiction par
symbole. Advisory pur : aucun module n'est tenu de le suivre.

Contrat d'échec (fail-safe) : chaque fetch dégrade vers une valeur neutre
([] ou {}) si la source est injoignable — jamais d'exception propagée ; les
cœurs purs tolèrent None / {} / champs manquants et rendent leur neutre
(None ou signal 0.0).

CLI : python stablecoin_flow.py
"""

import math
import time

import requests

from config_utils import cfg as _cfg
from numeric_utils import safe_float

SERIE_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
MAJEURS_URL = "https://stablecoins.llama.fi/stablecoins"
UA = {"User-Agent": "Mozilla/5.0"}

# Les deux stablecoins dominants (~85 % de l'offre) : leur mint/burn mensuel
# raconte l'essentiel du flux.
MAJEURS = ("USDT", "USDC")

# Échelles empiriques du signal : ±0.5 % sur 7 j et ±2 % sur 30 j sont des
# mouvements notables de l'offre (tanh y vaut ~±0.76, proche de la saturation).
ECHELLE_7J = 0.5
ECHELLE_30J = 2.0

# Au-delà de 1.5 jour d'écart entre le point trouvé et la cible, la série ne
# couvre pas la fenêtre demandée : on refuse de calculer une fausse variation.
TOLERANCE_S = 86400.0 * 1.5


# ---------- coeurs purs (testables) ----------

def _pegged(valeur):
    """PUR. Champ DefiLlama tantôt nombre, tantôt {"peggedUSD": x} -> float|None."""
    if isinstance(valeur, dict):
        valeur = valeur.get("peggedUSD")
    return safe_float(valeur)


def parse_serie(data):
    """PUR. [{"date": "1511913600", "totalCirculating": {"peggedUSD": x}}, ...]
    -> [(int unix_s, float total_usd)] chronologique croissant, SANS le dernier point.

    Le champ `date` est une STRING de secondes unix. Seul totalCirculating.peggedUSD
    est lu (offre libellée USD ; les autres pegs sont marginaux). Le dernier point
    est le jour EN COURS, partiel : on l'exclut pour ne comparer que des jours clos.
    Tolère None / [] / entrées malformées (ignorées, jamais d'exception).
    """
    points = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        ts = safe_float(item.get("date"))
        val = _pegged(item.get("totalCirculating"))
        if ts is None or val is None:
            continue
        points.append((int(ts), float(val)))
    points.sort(key=lambda p: p[0])
    return points[:-1]


def parse_majeurs(data):
    """PUR. {"peggedAssets": [{symbol, circulating, ...}]} -> offres USDT/USDC.

    Rend toujours {"USDT": {...}, "USDC": {...}} avec les clés actuel /
    prev_semaine / prev_mois (float|None). circulating* est tantôt un nombre,
    tantôt un dict {"peggedUSD": x} : _pegged tolère les deux. Symbole absent
    ou data illisible -> valeurs None (jamais d'exception).
    """
    sortie = {sym: {"actuel": None, "prev_semaine": None, "prev_mois": None}
              for sym in MAJEURS}
    if not isinstance(data, dict):
        return sortie
    for actif in data.get("peggedAssets") or []:
        if not isinstance(actif, dict):
            continue
        sym = actif.get("symbol")
        if sym in sortie:
            sortie[sym] = {
                "actuel": _pegged(actif.get("circulating")),
                "prev_semaine": _pegged(actif.get("circulatingPrevWeek")),
                "prev_mois": _pegged(actif.get("circulatingPrevMonth")),
            }
    return sortie


def variation_pct(serie, jours):
    """PUR. Variation % entre le point à ~jours*86400 s du dernier et le dernier.

    Ne suppose PAS un pas parfaitement régulier : on cherche le point (hors
    dernier) dont l'horodatage est le PLUS PROCHE de la cible
    `dernier_ts - jours*86400`. None si la série est trop courte : moins de
    2 points valides, ou point le plus proche à plus de TOLERANCE_S de la cible
    (la série ne couvre pas la fenêtre). Base <= 0 ou entrées illisibles
    ignorées -> None plutôt qu'une fausse valeur. Accepte tuples ou listes
    (le cache disque JSON rend des listes).
    """
    jours = safe_float(jours)
    if jours is None or jours <= 0:
        return None
    points = []
    for p in serie or []:
        try:
            ts, val = safe_float(p[0]), safe_float(p[1])
        except (TypeError, IndexError, KeyError):
            continue
        if ts is None or val is None:
            continue
        points.append((ts, val))
    if len(points) < 2:
        return None
    points.sort(key=lambda q: q[0])
    dernier_ts, dernier_val = points[-1]
    cible = dernier_ts - jours * 86400.0
    ts_base, base = min(points[:-1], key=lambda q: abs(q[0] - cible))
    if abs(ts_base - cible) > TOLERANCE_S:
        return None
    if base <= 0:
        return None
    return (dernier_val - base) / base * 100.0


def signal_flux(pct7, pct30):
    """PUR. Signal de flux borné [-1, +1] : >0 = expansion, <0 = contraction.

    0.6*tanh(pct7/0.5) + 0.4*tanh(pct30/2.0). Échelles empiriques : ±0.5 % sur
    7 j et ±2 % sur 30 j = mouvements notables de l'offre (tanh sature au-delà) ;
    le court terme pèse plus (0.6) car le mint/burn récent mène le régime.
    Les deux None -> 0.0 (neutre). Un seul None -> seule l'autre composante,
    avec son poids renormalisé à 1.
    """
    pct7, pct30 = safe_float(pct7), safe_float(pct30)
    if pct7 is None and pct30 is None:
        return 0.0
    if pct30 is None:
        s = math.tanh(pct7 / ECHELLE_7J)
    elif pct7 is None:
        s = math.tanh(pct30 / ECHELLE_30J)
    else:
        s = 0.6 * math.tanh(pct7 / ECHELLE_7J) + 0.4 * math.tanh(pct30 / ECHELLE_30J)
    return max(-1.0, min(1.0, s))


def pct_mensuel(entree):
    """PUR. {"actuel", "prev_mois"} -> variation % sur 1 mois ; None si illisible.

    Sert au mint/burn net mensuel d'un stablecoin majeur. Tolère None / {} /
    non-dict / base <= 0 -> None.
    """
    if not isinstance(entree, dict):
        return None
    actuel = safe_float(entree.get("actuel"))
    prev = safe_float(entree.get("prev_mois"))
    if actuel is None or prev is None or prev <= 0:
        return None
    return (actuel - prev) / prev * 100.0


# ---------- reseau (best-effort) ----------

def fetch_serie_totale():
    """Série journalière de l'offre totale de stablecoins (USD), cachée.

    best-effort : [] si la source est injoignable (jamais d'exception).
    [(int unix_s, float total_usd)] chronologique croissant, SANS le dernier
    point (jour en cours, partiel). ~3100 points depuis 2017, ok à TTL 6 h.
    """
    def _fetch():
        reponse = requests.get(SERIE_URL, headers=UA, timeout=8)
        reponse.raise_for_status()
        serie = parse_serie(reponse.json())
        # garde-fou : aucun point daté au-delà de demain (horodatage fantaisiste)
        horizon = time.time() + 86400.0
        return [(t, v) for (t, v) in serie if t <= horizon]

    try:
        import runtime_cache as rc
        return rc.get("stable_serie", _cfg("STABLE_SERIE_TTL_S", 21600),
                      _fetch, fallback=[])
    except Exception:
        return []


def fetch_majeurs():
    """Offres actuelles / -7 j / -30 j des stablecoins majeurs, cachées.

    best-effort : {} si la source est injoignable (jamais d'exception).
    {"USDT": {"actuel", "prev_semaine", "prev_mois"}, "USDC": {...}}.
    Réponse ~500 Ko (tous les pegs) : ok à TTL 6 h, une seule tentative.
    """
    def _fetch():
        reponse = requests.get(MAJEURS_URL, params={"includePrices": "false"},
                               headers=UA, timeout=8)
        reponse.raise_for_status()
        return parse_majeurs(reponse.json())

    try:
        import runtime_cache as rc
        return rc.get("stable_majeurs", _cfg("STABLE_MAJEURS_TTL_S", 21600),
                      _fetch, fallback={})
    except Exception:
        return {}


def snapshot():
    """Instantané complet du flux stablecoins. Ne lève jamais (briques fail-safe)."""
    serie = fetch_serie_totale() or []
    pct7 = variation_pct(serie, 7)
    pct30 = variation_pct(serie, 30)
    total = None
    if serie:
        try:
            total = safe_float(serie[-1][1])
        except (TypeError, IndexError, KeyError):
            total = None
    majeurs = fetch_majeurs()
    if not isinstance(majeurs, dict):
        majeurs = {}
    return {
        "total_mds": round(total / 1e9, 1) if total is not None else None,
        "pct_7j": pct7,
        "pct_30j": pct30,
        "signal": signal_flux(pct7, pct30),
        "usdt_pct_mois": pct_mensuel(majeurs.get("USDT")),
        "usdc_pct_mois": pct_mensuel(majeurs.get("USDC")),
    }


def _num(v, motif="{:+.2f}"):
    return motif.format(v) if isinstance(v, (int, float)) else "—"


def build_report(snap=None):
    """Rapport texte lisible ; `snap=None` -> collecte via snapshot()."""
    snap = snapshot() if snap is None else snap
    lignes = [
        "=== FLUX STABLECOINS (DefiLlama) ===",
        f"Offre totale (jours clos) : {_num(snap.get('total_mds'), '{:.1f}')} Mds$",
        f"Variation : 7 j {_num(snap.get('pct_7j'))} % | 30 j {_num(snap.get('pct_30j'))} %",
        f"Signal de flux : {_num(snap.get('signal'))} (dans [-1, +1] ; >0 = expansion "
        "= liquidités entrantes, <0 = contraction = repli)",
        f"Mint/burn net 1 mois : USDT {_num(snap.get('usdt_pct_mois'))} % | "
        f"USDC {_num(snap.get('usdc_pct_mois'))} %",
        "",
        "Signal de RÉGIME marché-large (dry powder), jamais une prédiction par symbole.",
        "Lecture seule. Aucun ordre. VERDICT: SAFE",
    ]
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
