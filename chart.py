"""
chart.py — rendu d'un graphique (bougies + indicateurs) depuis les données Bitget.

Classement : SAFE (analyse, aucun ordre, aucun secret). Génère une image que le
bot envoie sur Telegram → plus besoin de screenshots, et le fichier est RÉÉCRIT à
chaque appel dans /tmp (aucune accumulation dans tes dossiers).

Nécessite matplotlib (sur le VPS : apt install -y python3-matplotlib).
matplotlib est importé paresseusement (le module s'importe sans).

CLI : python chart.py SYMBOL [granularity]   (ex. BTCUSDT 1H)
"""

import sys

import indicators
import technicals


def render(symbol, granularity="15m", limit=120, out=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    candles = technicals.fetch_candles(symbol, granularity, limit)
    if not candles:
        raise RuntimeError("aucune bougie reçue")
    out = out or f"/tmp/bitget_chart_{symbol}_{granularity}.png"

    closes = [c["close"] for c in candles]
    n = len(candles)
    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#0d0d0d")
    for a in (ax, axv):
        a.set_facecolor("#0d0d0d")
        a.tick_params(colors="#888", labelsize=8)
        a.grid(color="#1a1a1a", linewidth=0.5)
        for spine in a.spines.values():
            spine.set_color("#222")

    for i, c in enumerate(candles):
        up = c["close"] >= c["open"]
        col = "#3fb950" if up else "#f85149"
        ax.plot([i, i], [c["low"], c["high"]], color=col, linewidth=0.7)
        body_low = min(c["open"], c["close"])
        body_h = abs(c["close"] - c["open"]) or max((c["high"] - c["low"]) * 0.02, 1e-9)
        ax.add_patch(plt.Rectangle((i - 0.3, body_low), 0.6, body_h, color=col))
        axv.bar(i, c["volume"], color=col, width=0.7, alpha=0.6)

    vw = technicals.vwap(candles)
    if vw:
        ax.plot([0, n - 1], [vw, vw], color="#d29922", lw=1.0, ls="--", label=f"VWAP {vw:.0f}")
    for period, color in ((20, "#58a6ff"), (50, "#bc8cff")):
        try:
            e = indicators.ema(closes, period)
            ax.plot(range(period - 1, n), e, color=color, lw=1.0, label=f"EMA{period}")
        except Exception:
            pass
    vp = technicals.volume_profile(candles)
    if vp and vp.get("poc"):
        ax.plot([0, n - 1], [vp["poc"], vp["poc"]], color="#888", lw=0.8, ls=":", label=f"POC {vp['poc']:.0f}")

    ax.legend(loc="upper left", fontsize=7, facecolor="#111", edgecolor="#222", labelcolor="#ccc")
    ax.set_title(f"{symbol}  {granularity}  ·  close {closes[-1]}", color="#ddd", fontsize=10)
    axv.set_ylabel("vol", color="#888", fontsize=8)
    plt.tight_layout()
    plt.savefig(out, dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def main():
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    granularity = sys.argv[2] if len(sys.argv) > 2 else "15m"
    print("Chart écrit :", render(symbol, granularity))


if __name__ == "__main__":
    main()
