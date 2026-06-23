"""
confluence_score.py — confluence d'un signal avec la microstructure + la macro.

Classement : SAFE (advisory, aucun ordre, aucun secret).

But : dire si la MICROSTRUCTURE (déséquilibre de carnet, CVD, biais volume) et
le CONTEXTE MACRO (régime risk-on/off) sont D'ACCORD avec la direction d'un
signal (LONG/SHORT). C'est une aide à la décision en LECTURE SEULE : le module
ne génère aucun ordre et ne modifie pas le moteur de signaux.

La fonction confluence_score() est PURE et testée. assess() ajoute le fetch
réseau (order-flow Bitget + macro FRED) et dégrade proprement.

CLI : python confluence_score.py SYMBOL SIDE   (ex. BTCUSDT LONG)
"""

import sys


def confluence_score(side, book_imbalance=None, cvd=None, macro_regime=None, volume_bias=None):
    """Score de confluence (pur). Retourne {side, score, label, components}.

    side : "LONG"/"SHORT". Pour un LONG, une pression acheteuse (imbalance>0,
    cvd>0, biais>0, RISK_ON) est ALIGNÉE (+1 chacune) ; l'inverse est DIVERGENTE
    (-1). Pour un SHORT, c'est miroir. Les entrées None sont ignorées.
    """
    side = str(side).upper()
    if side in ("LONG", "BUY"):
        direction = 1
    elif side in ("SHORT", "SELL"):
        direction = -1
    else:
        raise ValueError(f"confluence_score: side invalide ({side})")

    components = []
    score = 0

    def add(name, value_direction):
        nonlocal score
        if value_direction == 0:
            components.append((name, "neutre", 0))
            return
        delta = 1 if value_direction == direction else -1
        score += delta
        components.append((name, "aligné" if delta > 0 else "divergent", delta))

    if book_imbalance is not None:
        add("carnet (imbalance)", 1 if book_imbalance > 0.05 else -1 if book_imbalance < -0.05 else 0)
    if cvd is not None:
        add("CVD (tape)", 1 if cvd > 0 else -1 if cvd < 0 else 0)
    if volume_bias is not None:
        add("biais volume", 1 if volume_bias > 0 else -1 if volume_bias < 0 else 0)
    if macro_regime is not None:
        regime = str(macro_regime).upper()
        add("macro régime", 1 if regime == "RISK_ON" else -1 if regime == "RISK_OFF" else 0)

    if score >= 3:
        label = "FORTE CONFLUENCE"
    elif score >= 1:
        label = "ALIGNÉ"
    elif score == 0:
        label = "MIXTE"
    elif score >= -2:
        label = "DIVERGENT"
    else:
        label = "CONTRE-SIGNAL"

    return {"side": side, "score": score, "label": label, "components": components}


def assess(symbol, side, depth=20):
    """Confluence en conditions réelles : order-flow Bitget + régime macro."""
    import bitget_market_data as bmd
    import macro_context as mc

    snap = bmd.market_snapshot(symbol, depth=depth)
    macro = mc.macro_snapshot()
    result = confluence_score(
        side,
        book_imbalance=snap.get("book_imbalance"),
        cvd=snap.get("cvd"),
        macro_regime=macro.get("regime"),
    )
    return {"symbol": symbol, "side": side, "snapshot": snap, "macro": macro, "confluence": result}


def build_report(assessment):
    conf = assessment["confluence"]
    lines = [
        f"=== CONFLUENCE {assessment['symbol']} {conf['side']} (lecture seule) ===",
        f"Verdict : {conf['label']} (score {conf['score']:+d})",
        "",
    ]
    for name, status, delta in conf["components"]:
        lines.append(f"  {name:<22} {status} ({delta:+d})")
    lines.append("")
    lines.append("Aide à la décision uniquement. Aucun ordre réel. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        print("Usage: python confluence_score.py SYMBOL SIDE   (ex. BTCUSDT LONG)")
        raise SystemExit(2)
    symbol, side = sys.argv[1].upper(), sys.argv[2].upper()
    print(build_report(assess(symbol, side)))


if __name__ == "__main__":
    main()
