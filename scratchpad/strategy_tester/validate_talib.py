"""Valide mon implémentation numpy PURE des indicateurs Wilder contre la RÉFÉRENCE
TA-Lib (talib). Lancer avec le venv : /root/talib_venv/bin/python validate_talib.py

Si l'écart est négligeable, mon ADX/+DI/-DI/ATR/EMA était correct → le faux verdict
d'ADM venait bien de la LOGIQUE simultanée (ERR-014), pas d'un indicateur bogué."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import talib
import candles_history as ch
from adm_strategy import wilder_dmi, ema_full

rows = sorted(ch.load("BTCUSDT", "4H"), key=lambda r: r[0])
a = np.array(rows, float)
h, l, c = a[:, 2], a[:, 3], a[:, 4]

# --- le mien (numpy pur) ---
pDI, mDI, adx, atr = wilder_dmi(h, l, c, 14)
ema = ema_full(c, 200)

# --- référence TA-Lib ---
t_adx = talib.ADX(h, l, c, timeperiod=14)
t_pDI = talib.PLUS_DI(h, l, c, timeperiod=14)
t_mDI = talib.MINUS_DI(h, l, c, timeperiod=14)
t_atr = talib.ATR(h, l, c, timeperiod=14)
t_ema = talib.EMA(c, timeperiod=200)

skip = 320   # on compare après stabilisation du warmup Wilder/EMA


def cmp(name, mine, ref):
    m, r = mine[skip:], ref[skip:]
    ok = np.isfinite(m) & np.isfinite(r)
    m, r = m[ok], r[ok]
    if len(m) == 0:
        print(f"{name:8} : pas de recouvrement"); return
    err = np.abs(m - r)
    rel = err / (np.abs(r) + 1e-9)
    corr = np.corrcoef(m, r)[0, 1]
    print(f"{name:8} : corr={corr:.6f}  err_max={err.max():.4f}  err_moy={err.mean():.5f}  "
          f"err_rel_moy={rel.mean()*100:.3f}%  (n={len(m)})")


print(f"BTC 4H, {len(c)} barres — MON numpy vs TA-Lib {talib.__version__} (comparé après {skip} barres) :")
cmp("+DI", pDI, t_pDI)
cmp("-DI", mDI, t_mDI)
cmp("ADX", adx, t_adx)
cmp("ATR", atr, t_atr)
cmp("EMA200", ema, t_ema)
