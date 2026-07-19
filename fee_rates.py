"""
fee_rates.py — helper CENTRAL des frais EFFECTIFS du compte Bitget. LECTURE SEULE. SAFE.

Classement : SAFE (lecture seule). Le module ne fait QUE des GET signés de CONSULTATION
(taux de frais du compte + option de déduction BGB), délégués au signeur read-only audité
`real_positions._signed_get` (clé Bitget = Trade only, jamais de retrait). Aucun verbe
d'écriture, aucun placement, aucune annulation, aucun mouvement de fonds. Best-effort partout.

But (docs/BITGET_REFERENCE.md §1b — « source autoritative des frais = l'API, pas le scraping ») :
centraliser la lecture des frais RÉELS plutôt que des constantes en dur éparses, pour que les
labos/plans de coûts s'auto-ajustent au tier VIP et à la déduction BGB du compte.

Trois faits câblés ici :
  • `GET /api/v2/common/trade-rate` (businessType ∈ {spot, mix, margin}) renvoie MES taux
    maker/taker réels (VIP + BGB déjà appliqués par Bitget), en fractions ;
  • BGB = SPOT SEULEMENT, remise −20 % (10 → 8 bps) — MAIS elle n'est active que si l'option
    est ON *ET* que le réservoir BGB est approvisionné : toggle ON + solde vide = remise
    INACTIVE (vérifié live 19/07, fills spot payés en BTC à ~10 bps réservoir vide) ;
  • Futures = maker 2 / taker 6 bps, JAMAIS de BGB.

FAIL-SAFE ABSOLU : toute erreur réseau / parse / valeur aberrante retombe sur les défauts en
dur (état actuel du bot). Aucune exception ne remonte, aucun blocage. Cache TTL pour ne pas
solliciter l'API à chaque appel (le plancher de spread MM tourne chaque cycle).

Défauts en dur retenus = taux VIP0 vérifiés live (§1b) : la direction fail-safe SPOT suppose
PAS de remise BGB (frais plus élevés = calcul d'edge plus prudent).

CLI (consultation) : python fee_rates.py
"""
from __future__ import annotations

import time


# --- constantes / défauts fail-safe (= valeurs en dur actuelles du bot) ----------------
CACHE_TTL_S = 3600.0            # cache mémoire : 1 h suffit (le tier ne bouge pas en séance)
BGB_DUST = 0.05                 # seuil poussière BGB : au-dessous, réservoir vide -> remise OFF
DEFAULT_SYMBOL = "BTCUSDT"
_MAX_FRACTION = 0.01            # garde-fou magnitude : un taux > 100 bps est aberrant -> fallback

# taux VIP0 vérifiés live (docs/BITGET_REFERENCE.md §1b), en FRACTIONS
_FALLBACK_RATES = {
    "spot":   {"maker": 0.0010, "taker": 0.0010},   # 10 / 10 bps
    "mix":    {"maker": 0.0002, "taker": 0.0006},   # 2 / 6 bps (futures USDT-M)
    "margin": {"maker": 0.0010, "taker": 0.0010},
}
_FALLBACK_SPOT_BPS = 10.0                            # spot par côté, SANS remise BGB
_FALLBACK_FUTURES_BPS = {"maker": 2.0, "taker": 6.0}

# --- cache TTL (mémoire process) -------------------------------------------------------
_CACHE = {}
_K_BGB = ("bgb_effective",)


def _cache_get(key):
    ent = _CACHE.get(key)
    if not ent:
        return None
    ts, val = ent
    if (time.time() - ts) > CACHE_TTL_S:
        _CACHE.pop(key, None)
        return None
    return val


def _cache_put(key, val):
    _CACHE[key] = (time.time(), val)


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# --- I/O LECTURE SEULE (délégation au signeur audité) ----------------------------------
def _signed_get(path, params=None):
    """GET signé LECTURE SEULE via le signeur audité de `real_positions` (jamais un verbe
    d'écriture). Lève sur erreur ; les fonctions publiques enveloppent en fail-safe."""
    import real_positions as rp
    return rp._signed_get(path, params)


# --- fonctions PURES (testables sans réseau) -------------------------------------------
def _parse_trade_rate(data):
    """PUR. Champ 'data' de /common/trade-rate -> {'maker','taker'} en fractions, ou None
    si illisible / aberrant (garde-fou de magnitude : 0 <= taux <= 1 %)."""
    row = data[0] if isinstance(data, (list, tuple)) and data else data
    if not isinstance(row, dict):
        return None
    maker = _num(row.get("makerFeeRate"), default=-1.0)
    taker = _num(row.get("takerFeeRate"), default=-1.0)
    for v in (maker, taker):
        if v < 0 or v > _MAX_FRACTION:
            return None
    return {"maker": maker, "taker": taker}


def _effective_spot_bps(list_bps, bgb_effective):
    """PUR. bps SPOT par côté EFFECTIF : `list_bps` = taux listé (VIP inclus) par côté ;
    la remise BGB −20 % ne s'applique QUE si `bgb_effective`.
    Ex : _effective_spot_bps(10, True) = 8.0 ; _effective_spot_bps(10, False) = 10.0."""
    base = _num(list_bps, default=_FALLBACK_SPOT_BPS)
    if base <= 0:
        base = _FALLBACK_SPOT_BPS
    return round(base * 0.8, 4) if bgb_effective else round(base, 4)


def _bgb_effective(toggle_on, bgb_balance, dust_bgb=BGB_DUST):
    """PUR. La remise BGB est EFFECTIVE si et seulement si l'option est ON *ET* le solde
    BGB spot dépasse la poussière. Le toggle seul ne suffit PAS (réservoir vide = OFF)."""
    try:
        return bool(toggle_on) and float(bgb_balance) > float(dust_bgb)
    except (TypeError, ValueError):
        return False


# --- lecteurs BGB (I/O read-only) ------------------------------------------------------
def _bgb_toggle_on():
    """Option « payer les frais en BGB » ON ? via /spot/account/deduct-info (GET signé
    read-only). Lève sur erreur (appelant fail-safe)."""
    data = _signed_get("/api/v2/spot/account/deduct-info")
    row = data[0] if isinstance(data, (list, tuple)) and data else data
    return isinstance(row, dict) and str(row.get("deduct", "")).strip().lower() == "on"


def _bgb_spot_balance():
    """Solde BGB spot (available+frozen+locked) via le lecteur de compte read-only existant
    (`bitget_balance_reader.get_spot_assets`). Lève sur erreur (appelant fail-safe)."""
    import bitget_balance_reader as br
    resp = br.get_spot_assets("BGB")
    if not isinstance(resp, dict) or resp.get("code") != "00000":
        raise RuntimeError("solde BGB illisible")
    total = 0.0
    for r in resp.get("data") or []:
        if str(r.get("coin", "")).upper() != "BGB":
            continue
        total += _num(r.get("available")) + _num(r.get("frozen")) + _num(r.get("locked"))
    return total


# --- API publique ----------------------------------------------------------------------
def trade_rate(business_type, symbol=DEFAULT_SYMBOL):
    """Taux maker/taker EFFECTIFS du compte via /api/v2/common/trade-rate (VIP + BGB déjà
    appliqués côté Bitget). Retourne {'maker': fraction, 'taker': fraction}.
    FAIL-SAFE ABSOLU : toute erreur réseau/parse/aberration -> défauts en dur du business_type."""
    bt = str(business_type or "").lower()
    fallback = dict(_FALLBACK_RATES.get(bt, _FALLBACK_RATES["spot"]))
    key = ("trade_rate", bt, str(symbol).upper())
    cached = _cache_get(key)
    if cached is not None:
        return dict(cached)
    rate = fallback
    try:
        data = _signed_get("/api/v2/common/trade-rate",
                           {"symbol": str(symbol).upper(), "businessType": bt})
        parsed = _parse_trade_rate(data)
        if parsed is not None:
            rate = parsed
    except Exception:
        rate = fallback
    _cache_put(key, rate)
    return dict(rate)


def bgb_deduction_effective(toggle_on=None, bgb_balance=None, dust_bgb=BGB_DUST):
    """True SEULEMENT SI l'option BGB est ON *ET* le solde BGB spot > poussière.
    C'est LE point clé : toggle ON + réservoir vide = False (remise −20 % INACTIVE).
    `toggle_on` / `bgb_balance` sont injectables pour des tests hermétiques (chemin PUR).
    FAIL-SAFE : toute erreur -> False (on suppose PAS de remise = frais plus prudents)."""
    if toggle_on is not None and bgb_balance is not None:
        return _bgb_effective(toggle_on, bgb_balance, dust_bgb)   # chemin PUR injecté
    cached = _cache_get(_K_BGB)
    if cached is not None:
        return cached
    try:
        eff = _bgb_effective(_bgb_toggle_on(), _bgb_spot_balance(), dust_bgb)
    except Exception:
        eff = False
    _cache_put(_K_BGB, eff)
    return eff


def spot_fee_bps():
    """Frais SPOT effectif par côté en bps (accumulation, listing-hype, MM spot).
    = trade_rate('spot').maker × 1e4, puis × 0.8 si la déduction BGB est EFFECTIVE.
    FAIL-SAFE : 10.0 bps (ou 8.0 si BGB effectif)."""
    bgb = bgb_deduction_effective()
    base = _num(trade_rate("spot").get("maker")) * 1e4
    if base <= 0:
        base = _FALLBACK_SPOT_BPS
    return _effective_spot_bps(base, bgb)


def futures_fee_bps():
    """Frais FUTURES par côté en bps {'maker': 2.0, 'taker': 6.0} via trade_rate('mix').
    La déduction BGB ne s'applique JAMAIS au futures. FAIL-SAFE : défauts en dur 2 / 6."""
    rate = trade_rate("mix")
    maker = _num(rate.get("maker")) * 1e4
    taker = _num(rate.get("taker")) * 1e4
    if maker <= 0 or taker <= 0:
        return dict(_FALLBACK_FUTURES_BPS)
    return {"maker": round(maker, 4), "taker": round(taker, 4)}


def main():
    print("=== FRAIS EFFECTIFS DU COMPTE (fee_rates.py — LECTURE SEULE) ===")
    bgb = bgb_deduction_effective()
    print(f"Déduction BGB effective (option ON + réservoir) : {bgb}")
    print(f"Spot   (par côté)   : {spot_fee_bps():.4f} bps")
    fut = futures_fee_bps()
    print(f"Futures (par côté)  : maker {fut['maker']:.4f} / taker {fut['taker']:.4f} bps")
    for bt in ("spot", "mix"):
        r = trade_rate(bt)
        print(f"trade-rate[{bt:>4}] : maker={r['maker']} taker={r['taker']}")


if __name__ == "__main__":
    main()
