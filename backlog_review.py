#!/usr/bin/env python3
"""backlog_review.py — revue AUTOMATISÉE du backlog de scripts « en attente ». SAFE, LECTURE SEULE.

Le bot accumule des scripts BÂTIS mais pas (encore) branchés à un consommateur vivant : labos de
mesure, outils à la demande, voix opt-in gated OFF, modules en réserve. Sans cadence, on les OUBLIE
(ERR-013). Ce cron en revoit 1-2 par JOUR (rotation déterministe, curseur persisté) : pour chacun il
rassemble son ÉTAT (câblage via `wiring_audit`, verdict déjà rendu via VERDICTS/LABOS, forme) et
propose une RECOMMANDATION — garder comme outil / ré-mesurer / PROMOUVOIR (classer prédictif vs
méthode/contexte, ERR-016/017, puis câbler) / retirer.

⚠️ BORNE DE SÉCURITÉ (bot ARGENT RÉEL) : ce cron SURFACE et RECOMMANDE ; il ne MODIFIE ni ne câble
AUCUN code. L'analyse profonde (classer/améliorer/optimiser) et l'intégration (installer/tester/
lancer) sont des actes RÉVISÉS qui passent les 3 PORTES — déclenchés par l'alerte, jamais en cron
aveugle. Automatiser la CADENCE (ne rien oublier), pas les changements de code non revus.

CLI :
    python backlog_review.py           # revue du/des item(s) du jour (rotation)
    python backlog_review.py --alert   # + avance le curseur + journalise (pour cron/Telegram)
    python backlog_review.py --all      # liste tout le backlog + son état (consultation)
"""
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, ".backlog_review_state.json")
JOURNAL = os.path.join(ROOT, ".backlog_review_journal.jsonl")
PER_DAY = 2


def _pool():
    """Backlog = modules BÂTIS mais NON consommés (autonomes + réserve), triés. Réutilise wiring_audit
    (source de vérité du câblage). Fail-safe -> []."""
    try:
        import wiring_audit as wa
        c = wa.audit()
        return sorted(set(c.get("standalone", []) + c.get("reserve", [])))
    except Exception:
        return []


def _verdict_of(mod):
    """Le module a-t-il déjà un verdict MESURÉ (VERDICTS/LABOS) ? Court libellé ou None. PUR (I/O doc)."""
    for doc in ("docs/VERDICTS.md", "scratchpad/LABOS.md"):
        try:
            for line in open(os.path.join(ROOT, doc), encoding="utf-8", errors="ignore"):
                if mod in line and any(k in line.upper()
                                       for k in ("REJET", "TRADABLE", "VIVANT", "GARDÉ", "FAIT")):
                    return f"{doc.split('/')[-1]} : {line.strip()[:120]}"
        except Exception:
            continue
    return None


def recommend(mod):
    """(kind, reco) — heuristique PURE sur le source + verdicts. L'acte réel reste RÉVISÉ (3 portes)."""
    try:
        src = open(os.path.join(ROOT, mod + ".py"), encoding="utf-8", errors="ignore").read()
    except Exception:
        src = ""
    v = _verdict_of(mod)
    if "WIRING-RESERVE" in src:
        return ("réserve documentée", "garder en réserve — revisiter si le besoin apparaît")
    if mod.endswith("_lab") or "banc de MESURE" in src:
        return ("labo de mesure", v or "instrument — ré-mesurer si le régime/l'univers a changé")
    if v and "REJET" in v.upper():
        return ("verdict REJETÉ", "garder comme instrument OU retirer ; NE PAS re-tester (double data)")
    if "__main__" in src or "def main(" in src:
        return ("outil à la demande", "garder ; vérifier qu'il est encore utile / pas redondant")
    return ("à évaluer", "classer prédictif vs méthode/contexte (ERR-016/017), mesurer net de frais, décider")


def _cursor(n):
    try:
        return int(json.load(open(STATE)).get("cursor", 0)) % max(1, n)
    except Exception:
        return 0


def review(alert=False):
    pool = _pool()
    if not pool:
        print("backlog vide (rien en attente). Lecture seule. VERDICT: SAFE")
        return
    cur = _cursor(len(pool))
    picks = [pool[(cur + i) % len(pool)] for i in range(min(PER_DAY, len(pool)))]
    print(f"=== BACKLOG REVIEW — {len(pool)} scripts en attente · revue du jour ({len(picks)}) ===")
    cards = []
    for m in picks:
        kind, rec = recommend(m)
        v = _verdict_of(m)
        print(f"  • {m}  [{kind}]")
        if v:
            print(f"      verdict : {v}")
        print(f"      -> {rec}")
        cards.append({"module": m, "kind": kind, "reco": rec, "verdict": v})
    if alert:
        try:
            json.dump({"cursor": (cur + len(picks)) % len(pool)}, open(STATE, "w"))
            with open(JOURNAL, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": int(time.time()), "picks": cards}) + "\n")
        except Exception:
            pass
    print("Revue seule — l'intégration (installer/tester/câbler) passe les 3 portes. VERDICT: SAFE")


def main():
    if "--all" in sys.argv:
        pool = _pool()
        print(f"=== BACKLOG COMPLET ({len(pool)} scripts en attente) ===")
        for m in pool:
            print(f"  {m:30s} [{recommend(m)[0]}]")
        print("Lecture seule, aucun ordre. VERDICT: SAFE")
        return
    review(alert="--alert" in sys.argv)


if __name__ == "__main__":
    main()
