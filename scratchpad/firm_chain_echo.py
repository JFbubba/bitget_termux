#!/usr/bin/env python3
"""La firme produit-elle de l'INFORMATION, ou chaque étage répète-t-il la précédente ?

Le débat de risque est déjà jugé (§105 : écho, gaté OFF). Reste la question de fond,
soulevée par le propriétaire : le juge cloud rendait un verdict identique mot pour mot
au trader. Si TOUTE la chaîne est un écho, `firm_shadow` ne mesure rien — et il
accumulerait des mois de données fantômes avant qu'on s'en aperçoive.

Mesure sur le cache RÉEL (aucun appel LLM) :
  1. BULL vs BEAR — ils sont ADVERSAIRES PAR CONSTRUCTION. Une similarité élevée
     signifie que l'étage de débat est cassé au même titre que celui du risque.
  2. Écho de chaîne — plan.rationale -> trader.reasoning -> verdict.thesis.
  3. Les analystes pilotent-ils la sortie ? (corrélation biais moyen -> direction finale)

LECTURE SEULE.
"""
import json
import re
import statistics

CACHE = ".firm_decisions.json"
STOP = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "est", "en", "pour",
        "que", "qui", "dans", "sur", "avec", "pas", "ne", "au", "aux", "ce", "cette",
        "son", "sa", "ses", "il", "elle", "sont", "par", "plus", "mais", "ont", "bien",
        "cela", "ces", "leur", "aussi", "the", "of", "and", "to", "is", "are", "for"}


def mots(t):
    return {w for w in re.findall(r"[a-zà-ÿ]+", (t or "").lower()) if w not in STOP and len(w) > 2}


def jac(a, b):
    A, B = mots(a), mots(b)
    return len(A & B) / len(A | B) if (A | B) else None


def ligne(nom, vals, seuil, sens):
    vals = [v for v in vals if v is not None]
    if not vals:
        print(f"  {nom:34s} n/a")
        return
    med = statistics.median(vals)
    verdict = "ÉCHO" if (med >= seuil) else "ok"
    print(f"  {nom:34s} médiane {med:.2f}  (n={len(vals)})  -> {verdict}   [{sens}]")


def main():
    d = json.loads(open(CACHE, encoding="utf-8").read())["by_symbol"]
    print(f"=== CHAÎNE DE LA FIRME — {len(d)} symboles (cache réel) ===\n")

    bb, pt, tv, pv = [], [], [], []
    paires_bb = []
    for s, v in d.items():
        deb = v.get("debate", {}) or {}
        bull, bear = deb.get("bull", ""), deb.get("bear", "")
        plan = (deb.get("plan") or {}).get("rationale", "")
        trad = (v.get("trader") or {}).get("reasoning", "")
        verd = (v.get("risk") or {}).get("verdict", "")
        j = jac(bull, bear)
        if j is not None and bull.strip() and bear.strip():
            bb.append(j)
            paires_bb.append((s, j))
        if plan.strip() and trad.strip():
            pt.append(jac(plan, trad))
        if trad.strip() and verd.strip():
            tv.append(jac(trad, verd))
        if plan.strip() and verd.strip():
            pv.append(jac(plan, verd))

    print("1) ÉTAGE DE DÉBAT — bull vs bear (ADVERSAIRES par construction)")
    ligne("bull vs bear", bb, 0.5, "haut = débat cassé")
    for s, j in sorted(paires_bb, key=lambda x: -x[1]):
        marque = "  <-- quasi-identiques" if j >= 0.8 else ""
        print(f"       {s:10s} {j:.2f}{marque}")

    print("\n2) ÉCHO DE CHAÎNE (chaque étage répète-t-il le précédent ?)")
    ligne("plan -> trader", pt, 0.5, "haut = trader répète le plan")
    ligne("trader -> verdict final", tv, 0.5, "haut = juge répète le trader")
    ligne("plan -> verdict final", pv, 0.5, "haut = juge répète le plan")

    print("\n3) LES ANALYSTES PILOTENT-ILS LA SORTIE ?")
    xs, ys = [], []
    for s, v in d.items():
        biais = [r["bias"] for r in (v.get("reports") or {}).values()
                 if r and r.get("bias") is not None]
        if not biais:
            continue
        m = sum(biais) / len(biais)
        xs.append(m)
        ys.append(float(v.get("direction") or 0.0))
        print(f"       {s:10s} biais moyen {m:+.3f}  ->  direction {v.get('direction'):+.3f}")
    if len(xs) >= 3:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        vx = sum((a - mx) ** 2 for a in xs) ** 0.5
        vy = sum((b - my) ** 2 for b in ys) ** 0.5
        r = cov / (vx * vy) if vx and vy else 0.0
        print(f"\n  corrélation biais analystes -> direction finale : r = {r:+.2f} (n={len(xs)})")
        print("  (r élevé = la chaîne LLM ne fait que relayer la moyenne des analystes ;"
              "\n   r faible = les étages ajoutent quelque chose... ou du bruit)")


if __name__ == "__main__":
    main()
