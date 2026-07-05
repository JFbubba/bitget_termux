"""deribit_vol.py — volatilité implicite forward-looking (DVOL) + Variance Risk Premium (LECTURE SEULE).

Classement : SAFE. Réseau public en lecture seule, aucun ordre, aucun secret.
Source sans clé : www.deribit.com — indice DVOL (l'équivalent VIX de BTC/ETH,
agrégé sur le prix des options Deribit) et vol réalisée annualisée.

Complément FORWARD-LOOKING du régime de volatilité du cerveau
(swarm_brain.volatility_regime = ratios de vol historique, backward-looking) :
le DVOL encode ce que le marché d'options PAIE pour s'assurer, donc son
anticipation. Motivation empirique : le VRP (DVOL - vol réalisée) est en
moyenne positif (prime d'assurance vendue par les vendeurs de vol) ; quand il
passe négatif, les options sont bon marché vs le réalisé — marqueur classique
de stress récent (le réalisé a explosé) ou de complaisance des vendeurs. Une
expansion rapide du DVOL (> +10 % en 24 h) accompagne historiquement les
élargissements de range. Advisory RÉGIME uniquement, jamais une direction.

Contrat d'échec (fail-safe) : chaque fetch dégrade vers une valeur neutre
([] ou None) si la source est injoignable — jamais d'exception propagée ; les
cœurs purs tolèrent None / {} / champs manquants et rendent leur neutre.

CLI : python deribit_vol.py
"""

import time

import requests

from config_utils import cfg as _cfg
from numeric_utils import safe_float

DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
RV_URL = "https://www.deribit.com/api/v2/public/get_historical_volatility"
UA = {"User-Agent": "Mozilla/5.0"}

# Seuils de régime sur le NIVEAU du DVOL (vol annualisée, en %).
SEUIL_CALME = 40.0
SEUIL_STRESS = 70.0
# Expansion : pente 24 h du DVOL au-delà de +10 % (le marché re-price la vol).
SEUIL_EXPANSION_PCT = 10.0
PENTE_FENETRE = 24


# ---------- coeurs purs (testables) ----------

def parse_dvol(data):
    """PUR. {"result": {"data": [[ts_ms, o, h, l, close], ...]}} -> [clôtures].

    Ne garde que la clôture (indice 4) de chaque ligne, triée par temps
    croissant. Lignes illisibles / trop courtes / négatives ignorées ;
    None / {} -> [].
    """
    lignes = ((data or {}).get("result") or {}).get("data") or []
    points = []
    for ligne in lignes:
        if not isinstance(ligne, (list, tuple)) or len(ligne) < 5:
            continue
        t = safe_float(ligne[0])
        c = safe_float(ligne[4])
        if t is None or c is None or c < 0:
            continue
        points.append((int(t), c))
    points.sort(key=lambda p: p[0])
    return [c for _t, c in points]


def parse_rv(data):
    """PUR. {"result": [[ts_ms, rv_pct], ...]} -> dernière vol réalisée ou None.

    Deribit publie des points horaires (~16 jours) ; seul le plus récent nous
    intéresse. Lignes illisibles / négatives ignorées ; None / {} -> None.
    """
    lignes = (data or {}).get("result") or []
    points = []
    for ligne in lignes:
        if not isinstance(ligne, (list, tuple)) or len(ligne) < 2:
            continue
        t = safe_float(ligne[0])
        v = safe_float(ligne[1])
        if t is None or v is None or v < 0:
            continue
        points.append((int(t), v))
    if not points:
        return None
    points.sort(key=lambda p: p[0])
    return points[-1][1]


def pente_pct(clotures, n=PENTE_FENETRE):
    """PUR. Variation en % entre clotures[-n] et clotures[-1].

    Série trop courte (< n points lisibles), n invalide (< 2) ou point de
    départ non strictement positif -> None (neutre).
    """
    n = safe_float(n)
    if n is None or int(n) < 2:
        return None
    n = int(n)
    serie = [safe_float(v) for v in (clotures or [])]
    serie = [v for v in serie if v is not None]
    if len(serie) < n:
        return None
    depart, arrivee = serie[-n], serie[-1]
    if depart <= 0:
        return None
    return round((arrivee - depart) / depart * 100.0, 2)


def vrp(dvol_dernier, rv):
    """PUR. Variance Risk Premium en points de vol : DVOL - vol réalisée.

    Négatif = options bon marché vs le réalisé (stress récent ou complaisance
    des vendeurs de vol). Un des deux membres absent / illisible -> None.
    """
    iv = safe_float(dvol_dernier)
    reel = safe_float(rv)
    if iv is None or reel is None:
        return None
    return round(iv - reel, 2)


def regime_vol(niveau, pente):
    """PUR. Régime de vol implicite + drapeau d'expansion.

    niveau < 40 -> "calme", 40-70 -> "normal", >= 70 -> "stress" ;
    None / illisible -> "inconnu". expansion = pente 24 h > +10 % (indépendant
    du niveau : un DVOL calme qui gonfle vite mérite déjà l'attention).
    """
    n = safe_float(niveau)
    p = safe_float(pente)
    expansion = p is not None and p > SEUIL_EXPANSION_PCT
    if n is None:
        return {"regime": "inconnu", "expansion": expansion}
    if n < SEUIL_CALME:
        regime = "calme"
    elif n < SEUIL_STRESS:
        regime = "normal"
    else:
        regime = "stress"
    return {"regime": regime, "expansion": expansion}


# ---------- reseau (best-effort) ----------

def fetch_dvol(devise="BTC", heures=48):
    """Clôtures horaires de l'indice DVOL, chronologiques croissantes, cachées.

    best-effort : [] si la source est injoignable (jamais d'exception).
    48 h par défaut : assez pour la pente 24 points + marge de trous.
    """
    def _fetch():
        fin = int(time.time() * 1000)
        debut = fin - int(heures) * 3600 * 1000
        reponse = requests.get(
            DVOL_URL,
            params={"currency": devise, "resolution": "3600",
                    "start_timestamp": str(debut), "end_timestamp": str(fin)},
            headers=UA, timeout=8)
        reponse.raise_for_status()
        return parse_dvol(reponse.json())

    try:
        import runtime_cache as rc
        return rc.get(f"dvol:{devise}", _cfg("DERIBIT_DVOL_TTL_S", 3600),
                      _fetch, fallback=[])
    except Exception:
        return []


def fetch_vol_realisee(devise="BTC"):
    """Dernière vol réalisée annualisée (%) publiée par Deribit, cachée.

    best-effort : None si la source est injoignable (jamais d'exception).
    """
    def _fetch():
        reponse = requests.get(RV_URL, params={"currency": devise},
                               headers=UA, timeout=8)
        reponse.raise_for_status()
        return parse_rv(reponse.json())

    try:
        import runtime_cache as rc
        return rc.get(f"rv:{devise}", _cfg("DERIBIT_RV_TTL_S", 3600),
                      _fetch, fallback=None)
    except Exception:
        return None


def snapshot(devise="BTC"):
    """Instantané vol implicite d'une devise (niveau, pente, RV, VRP, régime).

    Ne lève jamais : chaque brique dégrade vers son neutre.
    """
    clotures = fetch_dvol(devise) or []
    niveau = safe_float(clotures[-1]) if clotures else None
    pente = pente_pct(clotures)
    rv = fetch_vol_realisee(devise)
    reg = regime_vol(niveau, pente)
    return {
        "niveau": niveau,
        "pente_24h_pct": pente,
        "rv": rv,
        "vrp": vrp(niveau, rv),
        "regime": reg["regime"],
        "expansion": reg["expansion"],
    }


def _num(v, motif="{:.1f}"):
    return motif.format(v) if isinstance(v, (int, float)) else "—"


def build_report(snaps=None):
    """Rapport texte BTC + ETH ; `snaps=None` -> collecte via snapshot()."""
    if snaps is None:
        snaps = {devise: snapshot(devise) for devise in ("BTC", "ETH")}
    lignes = ["=== VOL IMPLICITE DERIBIT (DVOL, l'équivalent VIX crypto) ==="]
    for devise in ("BTC", "ETH"):
        s = snaps.get(devise) or {}
        lignes.append(
            f"{devise} : DVOL {_num(s.get('niveau'))} | "
            f"pente 24h {_num(s.get('pente_24h_pct'), '{:+.1f}')} % | "
            f"RV {_num(s.get('rv'))} | VRP {_num(s.get('vrp'), '{:+.1f}')} pts | "
            f"régime {s.get('regime') or 'inconnu'}"
            f"{' | EXPANSION' if s.get('expansion') else ''}")
    dvol_btc = safe_float((snaps.get("BTC") or {}).get("niveau"))
    dvol_eth = safe_float((snaps.get("ETH") or {}).get("niveau"))
    spread = None
    if dvol_btc is not None and dvol_eth is not None:
        spread = round(dvol_eth - dvol_btc, 2)
    lignes += [
        f"Spread DVOL ETH-BTC : {_num(spread, '{:+.1f}')} pts "
        "(demande de vol relative sur ETH)",
        "",
        "VRP négatif = options bon marché vs réalisé. Advisory régime, pas direction.",
        "Lecture seule. Aucun ordre. VERDICT: SAFE",
    ]
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
