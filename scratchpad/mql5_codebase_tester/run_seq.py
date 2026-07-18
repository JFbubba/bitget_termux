"""Re-test struct_break en SÉQUENCE ORDONNÉE (CSW→SADF→Chow) vs la MOYENNE simultanée
(struct_break_suite, déjà REJETÉ 0/40). Audit ERR-014. Même panel, même porte."""
import harness as H
from candidates import CANDIDATES

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
        "UNIUSDT", "NVDAUSDT", "QQQUSDT", "XAUUSDT", "XAGUSDT"]


def run(name, h):
    fn, _ = CANDIDATES[name]
    res = H.test_signal(fn, name, SYMS, h=h)
    usable = [c for c in res["configs"] if not c.get("insufficient") and not c.get("degenerate")]
    ics = [c["ic"] for c in usable if c.get("ic") is not None]
    nz = sum(1 for c in usable if c.get("hit") is not None)   # configs avec des votes non-nuls
    ic_med = sorted(ics)[len(ics) // 2] if ics else None
    print(f"[{name} h={h}] configs exploitables {len(usable)} · IC médian {ic_med} · "
          f"n_pass(net taker>0, t>=3) {res['n_pass']}/{len(res['configs'])}")
    return res


print("===== SÉQUENCE ORDONNÉE CSW→SADF→Chow =====")
run("struct_break_sequence", 1)
run("struct_break_sequence", 5)
print("\n===== RAPPEL : MOYENNE SIMULTANÉE (déjà rejetée) =====")
run("struct_break_suite", 1)
print("\n--- détail séquence h=1 ---")
H.print_report(H.test_signal(CANDIDATES["struct_break_sequence"][0], "struct_break_sequence", SYMS, h=1))
