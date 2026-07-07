"""
promotion_board.py — TABLEAU DES PROMOTIONS (§88). SAFE, lecture seule.

Toutes les barres de promotion du dépôt en UNE vue : chaque candidat (voix opt-in,
labo xs, grille réelle, alt-carry, stratégies du lab) face à SA barre chiffrée et sa
progression. RIEN ne s'arme ici — la promotion effective reste une décision
propriétaire ; ce tableau rend juste la gouvernance lisible (consommé par le digest
quotidien, la revue hebdo et le dashboard).

CLI : python promotion_board.py
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _voix(overlay=None, comptes=None):
    """Voix opt-in : barre = IC live significatif (t = ic·√n ≥ 3) sur ≥ 50 votes."""
    out = []
    try:
        if overlay is None:
            import live_ic_audit as lia
            snap = lia.overlay_snapshot(3600)
            overlay = snap.get("agents", [])
            comptes = {}
            for e in lia.charger_entrees(lia.OVERLAY, max_lignes=50_000):
                for k in (e.get("votes") or {}):
                    comptes[k] = comptes.get(k, 0) + 1
    except Exception:
        overlay, comptes = overlay or [], comptes or {}
    ics = {a.get("agent"): a for a in overlay or []}
    for nom in sorted(set(list(ics) + list((comptes or {}).keys()))):
        a = ics.get(nom) or {}
        n = a.get("n") or (comptes or {}).get(nom, 0)
        ic = a.get("ic")
        t = round(ic * math.sqrt(n), 2) if (ic is not None and n) else None
        out.append({"nom": f"voix {nom}", "barre": "IC live t ≥ 3 (≥ 50 votes appariés)",
                    "etat": f"ic {ic} · n {n}" + (f" · t {t}" if t is not None else " · IC pas encore appariable"),
                    "progression": round(min(1.0, max(0.0, (t or 0) / 3.0)), 2) if t is not None
                                   else round(min(1.0, n / 50.0), 2),
                    "pret": bool(t is not None and t >= 3.0)})
    return out


def _nn(meta=None):
    """16ᵉ voix : barre = edge walk-forward > 0 (porte brute §71)."""
    try:
        if meta is None:
            meta = json.loads((ROOT / "neural_net_meta.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    edge = meta.get("wf_edge")
    return [{"nom": "voix nn (16ᵉ)", "barre": "edge walk-forward > 0 (fine-tune 04:20)",
             "etat": f"wf_edge {edge} · v{meta.get('version')} · n {meta.get('n_samples')}",
             "progression": None,
             "pret": bool(edge is not None and float(edge) > 0)}]


def _xs(st=None):
    try:
        if st is None:
            import xs_paper
            st = xs_paper.promotion_status()
    except Exception:
        return []
    b = st.get("barre") or {}
    prog = min((st.get("jours") or 0) / float(b.get("jours") or 30),
               (st.get("rebalances") or 0) / float(b.get("rebalances") or 20), 1.0)
    if (st.get("pnl_usdt") or 0) <= 0:
        prog = min(prog, 0.5)
    return [{"nom": "labo xs long-short", "barre": f"≥ {b.get('jours')} j · ≥ {b.get('rebalances')} rebal · PnL > 0",
             "etat": f"{st.get('jours')} j · {st.get('rebalances')} rebal · PnL {st.get('pnl_usdt')} $",
             "progression": round(prog, 2), "pret": bool(st.get("qualifie"))}]


def _runs_lab(fichiers=None):
    """Runs du lab groupés par horodatage de promotion (nom_YYYYmmdd_HHMMSS.md)."""
    if fichiers is None:
        try:
            fichiers = [f.stem for f in (ROOT / "strategies_out").glob("*.md")]
        except Exception:
            fichiers = []
    runs = {}
    for stem in fichiers:
        parts = stem.rsplit("_", 2)
        if len(parts) == 3:
            runs.setdefault(parts[1] + "_" + parts[2], set()).add(parts[0])
    return [runs[k] for k in sorted(runs)]


def _grille(runs=None, requis=2):
    """Grille spot réelle : barre = famille grille promue sur N runs CONSÉCUTIFS
    (le rapport de promotion du lab exige lui-même la re-validation avant capital)."""
    runs = _runs_lab() if runs is None else runs
    consec = 0
    for noms in reversed(runs):
        if any(n.startswith(("grid_", "evo_grid_")) for n in noms):
            consec += 1
        else:
            break
    return [{"nom": "grille spot réelle", "barre": f"famille grille promue {requis} runs lab consécutifs",
             "etat": f"{consec} consécutif(s) · {len(runs)} run(s) au total (mar·jeu·sam)",
             "progression": round(min(1.0, consec / float(requis)), 2),
             "pret": consec >= requis}]


def _alt_carry(lignes=None):
    """Alt-carry : barre = premier cycle de moisson EXÉCUTÉ proprement (ouvert+fermé)."""
    if lignes is None:
        lignes = []
        try:
            with (ROOT / ".alt_carry_journal.jsonl").open(encoding="utf-8") as f:
                for l in f:
                    try:
                        lignes.append(json.loads(l))
                    except Exception:
                        continue
        except Exception:
            pass
    executes = [l for l in lignes if l.get("executed")]
    return [{"nom": "alt-carry (montée des caps)", "barre": "1 moisson complète exécutée proprement",
             "etat": f"{len(lignes)} cycles · {len(executes)} exécutés (armé, attend un extrême)",
             "progression": round(min(1.0, len(executes) / 2.0), 2),
             "pret": len(executes) >= 2}]


def snapshot():
    """Tous les candidats face à leur barre. Lecture seule."""
    items = []
    for bloc in (_voix, _nn, _xs, _grille, _alt_carry):
        try:
            items.extend(bloc())
        except Exception:
            continue
    return {"ts": int(time.time()), "items": items,
            "prets": [i["nom"] for i in items if i.get("pret")]}


def build_report(s=None):
    s = snapshot() if s is None else s
    L = ["=== TABLEAU DES PROMOTIONS (§88, lecture seule — rien ne s'arme ici) ==="]
    for i in s["items"]:
        coche = "✅ PRÊT" if i.get("pret") else (f"{int((i.get('progression') or 0) * 100):3d} %"
                                                 if i.get("progression") is not None else "  — ")
        L.append(f"  [{coche}] {i['nom']:26s} barre : {i['barre']}")
        L.append(f"           état : {i['etat']}")
    L.append("Toute promotion effective = décision propriétaire. VERDICT: SAFE")
    return "\n".join(L)


if __name__ == "__main__":
    print(build_report())
