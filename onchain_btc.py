"""onchain_btc.py — santé on-chain Bitcoin : Hash Ribbons, congestion mempool, difficulté (LECTURE SEULE).

Classement : SAFE. Réseau public en lecture seule, aucun ordre, aucun secret.
Sources sans clé : api.blockchain.info (hashrate) et mempool.space (frais
recommandés, ajustement de difficulté).

Première source ON-CHAIN du dépôt. Motivation empirique : les Hash Ribbons
(SMA30/SMA60 du hashrate journalier) datent la capitulation puis la reprise
des mineurs ; historiquement, la reprise a coïncidé avec les creux majeurs de
BTC (déc. 2018, mars 2020, fin 2022) — un des signaux d'ACCUMULATION lente les
mieux documentés, PAS une prédiction court terme. Les frais mempool mesurent
la congestion (demande d'espace bloc) et l'ajustement de difficulté confirme
la tendance du hashrate. Advisory pur : aucun module n'est tenu de le suivre.

Contrat d'échec (fail-safe) : chaque fetch dégrade vers une valeur neutre
([] ou {}) si la source est injoignable — jamais d'exception propagée ; les
cœurs purs tolèrent None / {} / champs manquants et rendent leur neutre.

CLI : python onchain_btc.py
"""

import time

import requests

from config_utils import cfg as _cfg
from numeric_utils import safe_float

HASHRATE_URL = "https://api.blockchain.info/charts/hash-rate"
FRAIS_URL = "https://mempool.space/api/v1/fees/recommended"
DIFF_URL = "https://mempool.space/api/v1/difficulty-adjustment"
UA = {"User-Agent": "Mozilla/5.0"}

# Fenêtres canoniques des Hash Ribbons et fenêtre de fraîcheur de la reprise.
RIBBON_COURTE = 30
RIBBON_LONGUE = 60
REPRISE_FENETRE = 14


# ---------- coeurs purs (testables) ----------

def sma(valeurs, n):
    """PUR. Moyenne simple des `n` derniers éléments ; None si insuffisant.

    indicators.py centralise ema/rsi/atr mais n'expose pas de moyenne simple :
    ceci est un complément, pas une redéfinition. Une entrée illisible (None,
    texte non numérique) dans la fenêtre rend None (pas de moyenne partielle).
    """
    n = safe_float(n)
    if n is None or int(n) <= 0:
        return None
    n = int(n)
    valeurs = list(valeurs or [])
    if len(valeurs) < n:
        return None
    total = 0.0
    for v in valeurs[-n:]:
        x = safe_float(v)
        if x is None:
            return None
        total += x
    return total / n


def hash_ribbons(valeurs, courte=RIBBON_COURTE, longue=RIBBON_LONGUE):
    """PUR. Hash Ribbons (capitulation / reprise des mineurs) sur le hashrate.

    - capitulation : SMA courte < SMA longue au dernier point (les mineurs
      débranchent, le hashrate décroche) ;
    - reprise : croisement haussier (SMA courte repasse au-dessus de la SMA
      longue) survenu dans les `REPRISE_FENETRE` derniers points, juste après
      une phase de capitulation — le point d'entrée historique du signal ;
      les deux SMA sont calculées sur TOUTE la série pour dater le croisement ;
    - signal dans [-1, +1] : reprise -> +1.0 (meilleur timing d'accumulation
      historique), capitulation en cours -> -0.3 (patience), sinon 0.0.

    Série trop courte (< longue + 5), illisible ou paramètres invalides ->
    tout None / False / 0.0 (neutre).
    """
    neutre = {"sma_courte": None, "sma_longue": None,
              "capitulation": False, "reprise": False, "signal": 0.0}
    try:
        courte, longue = int(courte), int(longue)
    except (TypeError, ValueError):
        return neutre
    if courte <= 0 or longue <= courte:
        return neutre
    serie = [safe_float(v) for v in (valeurs or [])]
    serie = [v for v in serie if v is not None]
    if len(serie) < longue + 5:
        return neutre

    # SMA glissantes sur toute la série (préfixes) — n ~ 180, coût négligeable.
    n = len(serie)
    sc = [sma(serie[:i + 1], courte) for i in range(n)]
    sl = [sma(serie[:i + 1], longue) for i in range(n)]
    if sc[-1] is None or sl[-1] is None:
        return neutre

    capitulation = sc[-1] < sl[-1]

    reprise = False
    debut = max(longue, n - REPRISE_FENETRE)
    for i in range(debut, n):
        if None in (sc[i - 1], sl[i - 1], sc[i], sl[i]):
            continue
        # Croisement haussier : point précédent en capitulation, point courant au-dessus.
        if sc[i - 1] < sl[i - 1] and sc[i] > sl[i]:
            reprise = True
            break

    if reprise:
        signal = 1.0
    elif capitulation:
        signal = -0.3
    else:
        signal = 0.0
    return {"sma_courte": sc[-1], "sma_longue": sl[-1],
            "capitulation": capitulation, "reprise": reprise, "signal": signal}


def congestion(frais_rapide):
    """PUR. Congestion mempool dans [0, 1] à partir du tarif « rapide » (sat/vB).

    Forme fermée : congestion(f) = clip( racine((f - 2) / 198), 0, 1 ).
    Ancrages : f <= 2 sat/vB -> 0.0 (mempool vide), f = 50 -> ~0.49 (chargé),
    f >= 200 -> 1.0 (saturé). La racine écrase le haut de plage : passer de
    2 à 50 sat/vB dit plus sur la demande que passer de 150 à 200.
    None / illisible -> 0.0 (neutre).
    """
    f = safe_float(frais_rapide)
    if f is None:
        return 0.0
    ratio = (f - 2.0) / 198.0
    if ratio <= 0.0:
        return 0.0
    if ratio >= 1.0:
        return 1.0
    return round(ratio ** 0.5, 4)


def parse_hashrate(data):
    """PUR. {"values": [{"x": unix_s, "y": TH/s}]} -> [{"t", "v"}] trié croissant.

    Entrées illisibles ou négatives ignorées ; None / {} -> [].
    """
    points = []
    for point in (data or {}).get("values") or []:
        if not isinstance(point, dict):
            continue
        t = safe_float(point.get("x"))
        v = safe_float(point.get("y"))
        if t is None or v is None or v < 0:
            continue
        points.append({"t": int(t), "v": v})
    points.sort(key=lambda p: p["t"])
    return points


def parse_frais(data):
    """PUR. {fastestFee, halfHourFee, hourFee, economyFee} -> clés françaises.

    Chaque tarif devient un int (sat/vB) ou None si absent / illisible / négatif.
    """
    data = data if isinstance(data, dict) else {}

    def _entier(cle):
        v = safe_float(data.get(cle))
        return int(v) if v is not None and v >= 0 else None

    return {"rapide": _entier("fastestFee"), "demi_heure": _entier("halfHourFee"),
            "heure": _entier("hourFee"), "eco": _entier("economyFee")}


def parse_difficulte(data):
    """PUR. {difficultyChange, progressPercent, remainingBlocks} -> dict français.

    variation_pct : variation estimée du prochain ajustement (% ; négatif =
    hashrate en retrait). Champs absents / illisibles -> None.
    """
    data = data if isinstance(data, dict) else {}
    blocs = safe_float(data.get("remainingBlocks"))
    return {"variation_pct": safe_float(data.get("difficultyChange")),
            "progression_pct": safe_float(data.get("progressPercent")),
            "blocs_restants": int(blocs) if blocs is not None and blocs >= 0 else None}


def etat_ribbon(ribbon):
    """PUR. Libellé humain de l'état du ribbon (tolère {} / clés manquantes)."""
    ribbon = ribbon or {}
    if ribbon.get("reprise"):
        return "REPRISE (croisement haussier récent — zone d'accumulation historique)"
    if ribbon.get("capitulation"):
        return "CAPITULATION (mineurs sous pression — patience)"
    if ribbon.get("sma_courte") is None:
        return "INDISPONIBLE (série trop courte ou source muette)"
    return "NÉANT (ribbon sain, pas de signal)"


# ---------- reseau (best-effort) ----------

def fetch_hashrate(timespan="6months"):
    """Série journalière du hashrate BTC (TH/s), chronologique croissante, cachée.

    best-effort : [] si la source est injoignable (jamais d'exception).
    ~180 points sur 6 mois : assez pour SMA30/60 + détection du croisement.
    """
    def _fetch():
        reponse = requests.get(
            HASHRATE_URL,
            params={"timespan": timespan, "format": "json", "sampled": "true"},
            headers=UA, timeout=8)
        reponse.raise_for_status()
        return parse_hashrate(reponse.json())

    try:
        import runtime_cache as rc
        return rc.get("onchain_hashrate", _cfg("ONCHAIN_HASHRATE_TTL_S", 21600),
                      _fetch, fallback=[])
    except Exception:
        return []


def fetch_frais():
    """Frais recommandés mempool.space (sat/vB), cachés.

    best-effort : {} si la source est injoignable (jamais d'exception).
    """
    def _fetch():
        reponse = requests.get(FRAIS_URL, headers=UA, timeout=8)
        reponse.raise_for_status()
        return parse_frais(reponse.json())

    try:
        import runtime_cache as rc
        return rc.get("onchain_frais", _cfg("ONCHAIN_FRAIS_TTL_S", 1800),
                      _fetch, fallback={})
    except Exception:
        return {}


def fetch_difficulte():
    """Prochain ajustement de difficulté (mempool.space), caché.

    best-effort : {} si la source est injoignable (jamais d'exception).
    """
    def _fetch():
        reponse = requests.get(DIFF_URL, headers=UA, timeout=8)
        reponse.raise_for_status()
        return parse_difficulte(reponse.json())

    try:
        import runtime_cache as rc
        return rc.get("onchain_diff", _cfg("ONCHAIN_DIFF_TTL_S", 21600),
                      _fetch, fallback={})
    except Exception:
        return {}


def snapshot():
    """Instantané on-chain complet (hashrate + ribbons + frais + difficulté).

    Ne lève jamais : chaque brique dégrade vers son neutre.
    """
    serie = fetch_hashrate() or []
    valeurs = [p.get("v") for p in serie if isinstance(p, dict)]
    frais = fetch_frais() or {}
    age_j = None
    if serie and isinstance(serie[-1], dict) and serie[-1].get("t"):
        age_j = round(max(0.0, (time.time() - serie[-1]["t"]) / 86400.0), 1)
    return {
        "hashrate_ths": valeurs[-1] if valeurs else None,
        "points": len(valeurs),
        "age_dernier_point_j": age_j,
        "ribbon": hash_ribbons(valeurs),
        "frais": frais,
        "congestion": congestion(frais.get("rapide")),
        "difficulte": fetch_difficulte() or {},
    }


def _human(n):
    if n is None:
        return "—"
    for unite in ("", "K", "M", "G"):
        if abs(n) < 1000:
            return f"{n:.1f}{unite}"
        n /= 1000.0
    return f"{n:.1f}T"


def _num(v, motif="{:.1f}"):
    return motif.format(v) if isinstance(v, (int, float)) else "—"


def build_report(snap=None):
    """Rapport texte lisible ; `snap=None` -> collecte via snapshot()."""
    snap = snapshot() if snap is None else snap
    ribbon = snap.get("ribbon") or {}
    frais = snap.get("frais") or {}
    diff = snap.get("difficulte") or {}
    lignes = [
        "=== ON-CHAIN BTC (blockchain.info + mempool.space) ===",
        f"Hashrate : {_human(snap.get('hashrate_ths'))} TH/s "
        f"({snap.get('points', 0)} points journaliers, dernier il y a "
        f"{_num(snap.get('age_dernier_point_j'))} j)",
        f"Ribbon   : SMA30 {_human(ribbon.get('sma_courte'))} | "
        f"SMA60 {_human(ribbon.get('sma_longue'))} -> {etat_ribbon(ribbon)}",
        f"Signal accumulation : {_num(ribbon.get('signal'), '{:+.1f}')} (dans [-1, +1], advisory lent)",
        f"Frais    : rapide {_num(frais.get('rapide'), '{}')} | 30min {_num(frais.get('demi_heure'), '{}')} | "
        f"1h {_num(frais.get('heure'), '{}')} | eco {_num(frais.get('eco'), '{}')} sat/vB "
        f"-> congestion {_num(snap.get('congestion'), '{:.2f}')} / 1.00",
        f"Difficulté : variation estimée {_num(diff.get('variation_pct'), '{:+.2f}')} % | "
        f"progression époque {_num(diff.get('progression_pct'), '{:.1f}')} % | "
        f"blocs restants {_num(diff.get('blocs_restants'), '{}')}",
        "",
        "Signal de creux de cycle (accumulation lente), jamais un timing court terme.",
        "Lecture seule. Aucun ordre. VERDICT: SAFE",
    ]
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
