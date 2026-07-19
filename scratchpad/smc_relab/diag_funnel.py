"""diag_funnel.py — entonnoir stage par stage via simulate(funnel=...) (source unique).
Distingue RARETÉ légitime vs BUG. LECTURE SEULE. Usage: diag_funnel.py [SYM] [cfg-mods]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ict_2022 as ict

SYM = sys.argv[1] if len(sys.argv) > 1 else "ETHUSDT"
df15 = ict.load_df(SYM, "15m"); df4 = ict.load_df(SYM, "4H"); dfd = ict.load_df(SYM, "1D")
st4 = ict.htf_state(df4, 50, "4H"); std = ict.htf_state(dfd, 50, "1D")
ts15 = df15["ts"].to_numpy()
bias15, mid15 = ict.map_htf_to_ltf(ts15, st4)
biasD1, _ = ict.map_htf_to_ltf(ts15, std)
cfg = ict.Cfg()
feats = ict.ltf_features(df15, cfg.ltf_swing)
print(f"{SYM} n15={len(df15)}  features: conf_low={len(feats['conf_low'])} "
      f"mss={len(feats['mss'])} fvgs={len(feats['fvgs'])} obs={len(feats['obs'])}")
order = ["sess_bias", "d1", "disc", "mss", "sweep", "fvg_ote", "ob", "retest", "trade"]
for tag, c in (("CANON", ict.Cfg()),
               ("sansOB", ict.Cfg(require_ob=False)),
               ("sansOB_sansD1", ict.Cfg(require_ob=False, align_d1=False)),
               ("coeur(OTE seul)", ict.Cfg(require_ob=False, require_discount=False, align_d1=False))):
    fn = {}
    ict.simulate(SYM, feats, df15, bias15, mid15, biasD1, c, funnel=fn)
    print(f"  {tag:16}: " + " -> ".join(f"{k}={fn.get(k,0)}" for k in order))
