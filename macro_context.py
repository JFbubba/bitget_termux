"""
macro_context.py — contexte macro risk-on / risk-off (LECTURE SEULE).

Classement : SAFE (aucun ordre, aucun secret).

Fournit une couche de CONTEXTE au-dessus des signaux crypto :
  - VIX (peur actions)            -> FRED série VIXCLS
  - courbe des taux 2s10s         -> FRED série T10Y2Y (inversion = stress)
  - dollar (DXY proxy)            -> FRED série DTWEXBGS (dollar fort = vent contraire)

Source : FRED (Federal Reserve), export CSV PUBLIC sans clé :
  https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIE>

La logique de régime (compute_risk_regime) est PURE et testée. Le fetch réseau
dégrade proprement (None) si une série est indisponible.

CLI : python macro_context.py
"""

import requests

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
HEADERS = {"User-Agent": "Mozilla/5.0 (bitget-termux macro_context, read-only)"}


# ---------- parseur pur ----------

def parse_fred_csv(text):
    """Parse un CSV FRED -> liste de (date, valeur float). Ignore les '.'/vides."""
    rows = []
    lines = text.strip().splitlines()
    for line in lines[1:]:  # saute l'entête
        parts = line.split(",")
        if len(parts) < 2:
            continue
        date, raw = parts[0].strip(), parts[1].strip()
        if raw in ("", "."):
            continue
        try:
            rows.append((date, float(raw)))
        except ValueError:
            continue
    return rows


def latest_value(rows):
    """Dernière valeur d'une liste (date, valeur) ou None."""
    return rows[-1][1] if rows else None


# ---------- logique de régime (PURE, testable) ----------

def compute_risk_regime(vix=None, yield_2s10s=None, dxy_change_pct=None):
    """Détermine un régime RISK_ON / RISK_OFF / NEUTRE. Fonction pure.

    Heuristique :
      VIX  < 20 -> +1 (calme) ; 20-25 -> -1 ; >= 25 -> -2 (peur)
      2s10s >= 0 -> +1 (normale) ; < 0 -> -1 (inversion = stress)
      DXY change > +0.5% -> -1 (vent contraire) ; < -0.5% -> +1 (favorable)
    score > 0 = RISK_ON, < 0 = RISK_OFF, 0 = NEUTRE.
    """
    score = 0
    notes = []

    if vix is not None:
        if vix >= 25:
            score -= 2
            notes.append(f"VIX {vix:.1f} élevé (peur)")
        elif vix >= 20:
            score -= 1
            notes.append(f"VIX {vix:.1f} modéré")
        else:
            score += 1
            notes.append(f"VIX {vix:.1f} bas (calme)")

    if yield_2s10s is not None:
        if yield_2s10s < 0:
            score -= 1
            notes.append(f"courbe 2s10s inversée ({yield_2s10s:.2f}, stress)")
        else:
            score += 1
            notes.append(f"courbe 2s10s normale ({yield_2s10s:.2f})")

    if dxy_change_pct is not None:
        if dxy_change_pct > 0.5:
            score -= 1
            notes.append(f"DXY +{dxy_change_pct:.2f}% (vent contraire)")
        elif dxy_change_pct < -0.5:
            score += 1
            notes.append(f"DXY {dxy_change_pct:.2f}% (favorable)")

    regime = "RISK_ON" if score > 0 else "RISK_OFF" if score < 0 else "NEUTRE"
    return {"regime": regime, "score": score, "notes": notes}


# ---------- fetch réseau (impur, dégrade en None) ----------

def fetch_fred_series(series_id):
    """Télécharge une série FRED en CSV (sans clé). Lève en cas d'échec réseau."""
    response = requests.get(FRED_CSV.format(series_id=series_id), headers=HEADERS, timeout=15)
    response.raise_for_status()
    return parse_fred_csv(response.text)


def _safe_series(series_id):
    try:
        return fetch_fred_series(series_id)
    except Exception:
        return []


def macro_snapshot():
    """Instantané macro + régime risk-on/off. Dégrade proprement si data absente."""
    vix = latest_value(_safe_series("VIXCLS"))
    yield_2s10s = latest_value(_safe_series("T10Y2Y"))

    dxy_rows = _safe_series("DTWEXBGS")
    dxy_change = None
    if len(dxy_rows) >= 2:
        last = dxy_rows[-1][1]
        ref = dxy_rows[-6][1] if len(dxy_rows) >= 6 else dxy_rows[0][1]
        if ref:
            dxy_change = (last / ref - 1.0) * 100.0

    oil = latest_value(_safe_series("DCOILWTICO"))  # WTI, contexte inflation/énergie

    regime = compute_risk_regime(vix, yield_2s10s, dxy_change)
    return {
        "vix": vix,
        "yield_2s10s": yield_2s10s,
        "dxy_change_pct": dxy_change,
        "oil_wti": oil,
        "regime": regime["regime"],
        "score": regime["score"],
        "notes": regime["notes"],
    }


def build_report(snap):
    def fmt(v, suffix=""):
        return "n/a" if v is None else f"{v:.2f}{suffix}"
    lines = [
        "=== MACRO CONTEXT (lecture seule) ===",
        f"VIX          : {fmt(snap['vix'])}",
        f"Courbe 2s10s : {fmt(snap['yield_2s10s'])}",
        f"DXY (var.)   : {fmt(snap['dxy_change_pct'], '%')}",
        f"Pétrole WTI  : {fmt(snap.get('oil_wti'))}",
        f"RÉGIME       : {snap['regime']} (score {snap['score']:+d})",
    ]
    for note in snap["notes"]:
        lines.append(f"  - {note}")
    lines.append("")
    lines.append("Mode: lecture seule. Aucun ordre réel. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    print(build_report(macro_snapshot()))


if __name__ == "__main__":
    main()
