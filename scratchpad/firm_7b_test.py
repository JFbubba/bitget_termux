#!/usr/bin/env python3
"""Test 7b vs 1.5b sur le DÉBAT DE RISQUE de la firme (trading_firm._risk).

Rejoue la séquence RÉELLE du pipeline (run_symbol l.367-369) :
    agressif -> conservateur(voit agg) -> neutre(voit agg ET con)
sur les entrées RÉELLES mises en cache dans .firm_decisions.json.

Mesure, par modèle :
  - taux d'argument VIDE (la pathologie constatée)
  - latence par appel (le VPS n'a ni GPU ni cœurs : c'est peut-être LE verdict)
  - divergence entre les 3 voix (Jaccard sur les mots) — un débat qui n'est qu'un
    écho ne produit aucune information, même si les 3 voix répondent
  - complaisance ("le trader a raison") — la voix ne challenge pas, elle ratifie
  - lean (et si _num tombe sur son défaut 0.0 alors que la voix est muette)

LECTURE SEULE. Aucun ordre, aucun état du bot modifié. Écrit un JSON de résultats.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CACHE = ".firm_decisions.json"
OUT = "scratchpad/firm_7b_results.json"
STOP = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "est", "en", "pour",
        "que", "qui", "dans", "sur", "avec", "pas", "ne", "a", "au", "aux", "ce",
        "cette", "son", "sa", "ses", "il", "elle", "sont", "par", "plus", "mais",
        "d", "l", "n", "s", "y", "the", "of", "and", "to", "is", "are"}


def mots(t):
    return {w for w in re.findall(r"[a-zà-ÿ]+", (t or "").lower()) if w not in STOP and len(w) > 2}


def jaccard(a, b):
    A, B = mots(a), mots(b)
    return len(A & B) / len(A | B) if (A | B) else 0.0


def complaisant(t):
    return bool(re.search(r"trader\s+(a\s+raison|propose)", (t or "").lower()))


def cas_depuis_cache():
    """Reconstruit (symbole, reports, trader) depuis le cache réel."""
    d = json.loads(open(CACHE, encoding="utf-8").read())["by_symbol"]
    cas = []
    for sym, v in d.items():
        tr = dict(v.get("trader") or {})
        # le cache ne persiste que action/reasoning : on recompose les champs que
        # _risk sérialise, à partir de la décision (fidélité de TAILLE du prompt).
        tr.setdefault("direction", v.get("direction", 0.0))
        tr.setdefault("sizing_usdt", v.get("sizing_suggested_usdt", 0.0))
        cas.append((sym, v.get("reports") or {}, tr))
    return cas


def run(modele, cas, timeout_s):
    import trading_firm as tf
    os.environ["FIRM_LLM_LOCAL_MODEL"] = modele
    os.environ["FIRM_LOCAL_TIMEOUT_S"] = str(timeout_s)
    res = []
    for sym, reports, trader in cas:
        # séquence RÉELLE : le neutre voit les deux précédents (prompt le plus long)
        tour = {}
        last_a = last_c = ""
        for profil in ("aggressive", "conservative", "neutral"):
            t0 = time.time()
            try:
                r = tf._risk(profil, trader, reports, last_a, last_c)
            except Exception as e:
                r = {"argument": "", "lean": None, "err": str(e)[:120]}
            dt = time.time() - t0
            arg = r.get("argument", "")
            tour[profil] = {"argument": arg, "lean": r.get("lean"), "s": round(dt, 1),
                            "vide": not arg.strip(), "complaisant": complaisant(arg),
                            "n_mots": len(re.findall(r"\S+", arg))}
            if profil == "aggressive":
                last_a = arg
            elif profil == "conservative":
                last_c = arg
            print(f"  {sym:10s} {profil:13s} {dt:6.1f}s  "
                  f"{'VIDE' if not arg.strip() else str(len(arg))+' car'}"
                  f"{'  [complaisant]' if complaisant(arg) else ''}", flush=True)
        a, c, n = (tour[p]["argument"] for p in ("aggressive", "conservative", "neutral"))
        tour["divergence"] = {
            "agg_vs_con": round(jaccard(a, c), 3),
            "agg_vs_neu": round(jaccard(a, n), 3),
            "con_vs_neu": round(jaccard(c, n), 3),
        }
        res.append({"symbole": sym, "tour": tour})
    return res


def resume(nom, res):
    tours = [t for r in res for t in
             (r["tour"][p] for p in ("aggressive", "conservative", "neutral"))]
    n = len(tours)
    vides = sum(1 for t in tours if t["vide"])
    lat = [t["s"] for t in tours]
    compl = sum(1 for t in tours if t["complaisant"])
    # divergence : seulement sur les tours où les DEUX voix ont parlé
    divs = []
    for r in res:
        tr = r["tour"]
        for k, (p, q) in (("agg_vs_con", ("aggressive", "conservative")),
                          ("agg_vs_neu", ("aggressive", "neutral")),
                          ("con_vs_neu", ("conservative", "neutral"))):
            if not tr[p]["vide"] and not tr[q]["vide"]:
                divs.append(tr["divergence"][k])
    d = {
        "modele": nom, "appels": n,
        "vides": vides, "taux_vide": round(vides / n, 3) if n else None,
        "latence_med_s": round(sorted(lat)[len(lat) // 2], 1) if lat else None,
        "latence_max_s": round(max(lat), 1) if lat else None,
        "complaisants": compl,
        "taux_complaisance_si_parle": round(compl / (n - vides), 3) if n > vides else None,
        "similarite_med_paires_parlantes": round(sorted(divs)[len(divs) // 2], 3) if divs else None,
        "paires_comparees": len(divs),
    }
    return d


if __name__ == "__main__":
    modele = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:1.5b"
    timeout_s = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
    limite = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    cas = cas_depuis_cache()
    if limite:
        cas = cas[:limite]
    print(f"== {modele} == {len(cas)} symboles x 3 voix, timeout {timeout_s}s\n", flush=True)
    t0 = time.time()
    res = run(modele, cas, timeout_s)
    d = resume(modele, res)
    d["duree_totale_s"] = round(time.time() - t0, 1)
    print("\n" + json.dumps(d, ensure_ascii=False, indent=2))
    try:
        tout = json.loads(open(OUT, encoding="utf-8").read())
    except Exception:
        tout = {}
    tout[modele] = {"resume": d, "detail": res}
    open(OUT, "w", encoding="utf-8").write(json.dumps(tout, ensure_ascii=False, indent=2))
    print(f"\n-> {OUT}")
