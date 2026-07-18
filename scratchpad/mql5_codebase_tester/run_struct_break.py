"""Test du candidat 'structural break' (AFML Ch.17) — protocole ERR-002 :
la SUITE holistique d'abord, puis décomposition en composants pour l'attribution,
échelle TF complète (ERR-001) × 5 symboles cross-asset, net de frais, porte §77.
Contrôle de robustesse : suite à h=5 (les ruptures se jouent sur plusieurs barres).
Journalise un verdict consolidé dans verdicts.jsonl. Lecture seule."""
import json, time
from pathlib import Path
import harness as H
from candidates import CANDIDATES

LAB = Path(__file__).resolve().parent
JOURNAL = LAB / "verdicts.jsonl"
# PANEL DIVERSIFIÉ (10 symboles / 7 secteurs, profondeur >=6/8 TF) — évite le biais
# crypto-L1 corrélé. L1: BTC/ETH/SOL · paiement: XRP · meme: DOGE · DeFi: UNI ·
# action US: NVDA · indice US: QQQ · or: XAU · argent: XAG.
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
        "UNIUSDT", "NVDAUSDT", "QQQUSDT", "XAUUSDT", "XAGUSDT"]
SRC = "Feature Engineering for ML (Part 9): Structural Break Tests in Python (AFML Ch.17)"


def run(name, h=1):
    fn, _ = CANDIDATES[name]
    t0 = time.time()
    res = H.test_signal(fn, name, SYMS, h=h)
    res["_sec"] = round(time.time() - t0, 1)
    res["_h"] = h
    H.print_report(res)
    usable = [c for c in res["configs"] if not c.get("insufficient") and not c.get("degenerate")]
    ics = [c["ic"] for c in usable if c.get("ic") is not None]
    print(f"   ({res['_sec']}s · {len(usable)} configs exploitables · "
          f"IC médian {sorted(ics)[len(ics)//2] if ics else None} · "
          f"n_pass {res['n_pass']})\n")
    return res


print("========== SUITE HOLISTIQUE (testée EN PREMIER — ERR-002) ==========")
suite = run("struct_break_suite", h=1)

print("========== DÉCOMPOSITION (attribution) ==========")
comps = {n: run(n, h=1) for n in ["csw_cusum", "sadf_dir", "chow_dir"]}

print("========== ROBUSTESSE — SUITE à h=5 ==========")
suite_h5 = run("struct_break_suite", h=5)


def summ(res):
    usable = [c for c in res["configs"] if not c.get("insufficient") and not c.get("degenerate")]
    ics = [c["ic"] for c in usable if c.get("ic") is not None]
    return {"n_configs": len(usable), "n_pass": res["n_pass"],
            "ic_median": (sorted(ics)[len(ics) // 2] if ics else None),
            "ic_min": (min(ics) if ics else None), "ic_max": (max(ics) if ics else None)}


all_res = {"struct_break_suite_h1": suite, "struct_break_suite_h5": suite_h5, **comps}
n_pass_total = sum(r["n_pass"] for r in all_res.values())
# porte de verdict : au moins qq configs franchissent net-de-frais t>=3, pas 1 isolée
verdict = "EDGE" if suite["n_pass"] >= max(2, len(suite["configs"]) // 8) else "REJETÉ"
rec = {
    "candidat": "struct_break_suite",
    "source_mql5": SRC,
    "symbols": SYMS, "h_teste": [1, 5], "protocole": "ERR-002 (suite d'abord) + ERR-001 (échelle TF complète)",
    "verdict": verdict,
    "n_pass_suite_h1": suite["n_pass"], "n_configs_suite_h1": len(suite["configs"]),
    "resume": {k: summ(v) for k, v in all_res.items()},
    "note": ("tests d'AFML Ch.17 (CSW/SADF/Chow) lus en signal directionnel (construction du "
             "testeur ; l'article les donne comme FEATURES ML). Porte : net taker>0 ET t>=3."),
}
with JOURNAL.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

print("========== VERDICT CONSOLIDÉ ==========")
print(json.dumps(rec, ensure_ascii=False, indent=1))
print(f"\n-> {verdict} · journalisé dans verdicts.jsonl")
