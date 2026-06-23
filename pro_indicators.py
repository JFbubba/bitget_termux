"""
pro_indicators.py — indicateurs "pro traders" purs et testables.

Classement : SAFE (calcul pur, aucune I/O, aucun ordre, aucun secret).

Contient les indicateurs recommandés calculables localement :
  - momentum (Rate of Change)
  - volume_profile (POC + value area)
  - sharpe_ratio (rendements excédentaires / volatilité)
  - risk_based_position_size (le stop protège le CAPITAL, pas la position)
  - trading_sessions (canaux horaires actifs, heure de Bruxelles)

Les indicateurs macro / cross-asset (DXY, VIX, pétrole/inflation, yield curve,
rotation sectorielle XLY/XLP, COT) ne sont PAS calculables ici : ils
nécessitent des flux externes — voir docs/PRO_INDICATORS.md pour les sources
et le plan de branchement (lecture seule).
"""

from datetime import datetime


# ---------- momentum (Rate of Change) ----------

def momentum(values, period=14):
    """Momentum = Rate of Change en %, sur une fenêtre `period`.

    Retourne une liste : pour chaque i >= period, (values[i]/values[i-period]-1)*100.
    Lève ValueError si données insuffisantes ou période invalide.
    """
    if period <= 0:
        raise ValueError(f"momentum: période invalide ({period})")
    if len(values) <= period:
        raise ValueError(
            f"momentum: données insuffisantes ({len(values)} valeurs pour période {period})"
        )
    out = []
    for i in range(period, len(values)):
        base = values[i - period]
        out.append(((values[i] / base) - 1.0) * 100.0 if base else 0.0)
    return out


# ---------- volume profile (POC + value area) ----------

def volume_profile(candles, bins=24, value_area_pct=0.70):
    """Profil de volume : répartit le volume par tranche de prix (close).

    Retourne {poc, value_area_low, value_area_high, total_volume}.
      - poc : prix (centre de tranche) au plus gros volume (Point of Control)
      - value_area_* : bornes de la zone couvrant `value_area_pct` du volume
    Calcul pur. Bougies : {"close", "volume", ...}.
    """
    if bins <= 0:
        raise ValueError(f"volume_profile: bins invalide ({bins})")
    if not candles:
        raise ValueError("volume_profile: aucune bougie fournie")

    prices = [float(c["close"]) for c in candles]
    volumes = [float(c.get("volume", 0.0)) for c in candles]
    low, high = min(prices), max(prices)

    if high == low:
        return {"poc": low, "value_area_low": low, "value_area_high": high,
                "total_volume": sum(volumes)}

    width = (high - low) / bins
    buckets = [0.0] * bins
    for price, volume in zip(prices, volumes):
        idx = int((price - low) / width)
        if idx >= bins:
            idx = bins - 1
        buckets[idx] += volume

    centers = [low + (i + 0.5) * width for i in range(bins)]
    poc_idx = max(range(bins), key=lambda i: buckets[i])

    total = sum(buckets)
    target = total * value_area_pct
    acc = buckets[poc_idx]
    lo_i = hi_i = poc_idx
    while acc < target and (lo_i > 0 or hi_i < bins - 1):
        left = buckets[lo_i - 1] if lo_i > 0 else -1.0
        right = buckets[hi_i + 1] if hi_i < bins - 1 else -1.0
        if right >= left:
            hi_i += 1
            acc += buckets[hi_i]
        else:
            lo_i -= 1
            acc += buckets[lo_i]

    return {
        "poc": centers[poc_idx],
        "value_area_low": centers[lo_i],
        "value_area_high": centers[hi_i],
        "total_volume": total,
    }


# ---------- ratio de Sharpe ----------

def sharpe_ratio(returns, risk_free=0.0, periods_per_year=None):
    """Sharpe = moyenne des rendements excédentaires / volatilité (écart-type).

    `returns` : liste de rendements par période (ex. 0.01 = +1%).
    `periods_per_year` : si fourni, annualise (× racine(periods_per_year)).
    Retourne 0.0 si volatilité nulle. Lève ValueError si < 2 points.
    """
    if len(returns) < 2:
        raise ValueError("sharpe_ratio: au moins 2 rendements requis")
    excess = [r - risk_free for r in returns]
    mean = sum(excess) / len(excess)
    variance = sum((x - mean) ** 2 for x in excess) / (len(excess) - 1)
    std = variance ** 0.5
    if std == 0:
        return 0.0
    sharpe = mean / std
    if periods_per_year:
        sharpe *= periods_per_year ** 0.5
    return sharpe


# ---------- risk management du capital ----------

def risk_based_position_size(capital, risk_percent, entry, stop):
    """Dimensionnement par le RISQUE CAPITAL.

    Principe pro : le stop-loss ne protège pas une position, il protège le
    CAPITAL. On fixe d'abord combien de capital on accepte de perdre
    (risk_percent), puis la taille en découle :
        taille = (capital * risk%) / distance_au_stop

    Retourne {size, risk_amount, distance}. Calcul pur, aucun ordre.
    """
    if capital <= 0:
        raise ValueError("risk_based_position_size: capital doit être > 0")
    if risk_percent <= 0:
        raise ValueError("risk_based_position_size: risk_percent doit être > 0")
    distance = abs(float(entry) - float(stop))
    if distance <= 0:
        raise ValueError("risk_based_position_size: entry et stop doivent différer")
    risk_amount = capital * (risk_percent / 100.0)
    return {"size": risk_amount / distance, "risk_amount": risk_amount, "distance": distance}


# ---------- timing des canaux horaires (heure de Bruxelles) ----------

# (début_min, fin_min, label) en minutes depuis minuit, heure locale Bruxelles.
TRADING_WINDOWS = [
    (9 * 60, 11 * 60, "EU_MORNING"),            # 09:00 - 11:00
    (15 * 60 + 30, 17 * 60, "US_OPEN"),         # 15:30 - 17:00
    (15 * 60 + 30, 16 * 60 + 30, "US_OPEN_PEAK"),  # 15:30 - 16:30 (sous-fenêtre)
    (1 * 60, 2 * 60, "ASIA_LATE"),              # 01:00 - 02:00
]


def trading_sessions(dt):
    """Renvoie les fenêtres horaires actives pour `dt` (heure de Bruxelles).

    `dt` : datetime (l'appelant fournit l'heure de Bruxelles). Retourne la
    liste des labels actifs (vide hors fenêtres).
    """
    if not isinstance(dt, datetime):
        raise ValueError("trading_sessions: datetime attendu")
    minute_of_day = dt.hour * 60 + dt.minute
    return [label for start, end, label in TRADING_WINDOWS if start <= minute_of_day < end]


def in_active_session(dt):
    """True si `dt` (heure de Bruxelles) tombe dans une fenêtre active."""
    return len(trading_sessions(dt)) > 0


def sector_rotation_ratio(xly_price, xlp_price):
    """Ratio rotation sectorielle XLY/XLP (discrétionnaire / staples).

    Ratio élevé / en hausse = appétit pour le risque (risk-on) ; en baisse =
    défensif (risk-off). Prix fournis par une source externe (Yahoo/FMP).
    Calcul pur.
    """
    if xlp_price <= 0:
        raise ValueError("sector_rotation_ratio: xlp_price doit être > 0")
    return float(xly_price) / float(xlp_price)


def cot_net_positioning(long_positions, short_positions):
    """Positionnement net COT (CFTC) : net, net %, biais.

    `long_positions`/`short_positions` : positions ouvertes d'une catégorie
    (ex. large speculators) issues d'un rapport COT cftc.gov. Calcul pur.
    """
    if long_positions < 0 or short_positions < 0:
        raise ValueError("cot_net_positioning: positions négatives invalides")
    total = long_positions + short_positions
    net = long_positions - short_positions
    net_pct = (net / total * 100.0) if total else 0.0
    bias = "LONG" if net > 0 else "SHORT" if net < 0 else "FLAT"
    return {"net": net, "net_pct": net_pct, "bias": bias}


def main():
    print("=== PRO INDICATORS (lecture seule) ===")
    print("Module de calcul pur. Voir docs/PRO_INDICATORS.md.")
    print("Indicateurs calculables: momentum, volume_profile, sharpe_ratio,")
    print("risk_based_position_size, trading_sessions.")
    print("VERDICT: SAFE — aucun ordre, aucun secret.")


if __name__ == "__main__":
    main()
