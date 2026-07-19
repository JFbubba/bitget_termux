#!/usr/bin/env python3
"""wiring_audit.py — audit de CÂBLAGE / ACTIVATION du bot (anti-ERR-013). SAFE, LECTURE SEULE.

Vérifie que CHAQUE module top-level est dans un de ces états :
  • CONSOMMÉ  : importé par un chemin de PRODUCTION (hors tests_audit / scratchpad / soi-même) ;
  • ACTIVÉ    : lancé par un cron ou un service/timer systemd ;
  • AUTONOME  : outil/labo runnable (`__main__`) exécuté à la demande — légitime ;
  • ORPHELIN  : module-BIBLIOTHÈQUE (pas de `__main__`) importé NULLE PART -> risque ERR-013
    (construit + testé, portes vertes, mais jamais branché à un consommateur vivant).

Complète le watchdog (carte de fraîcheur de 17 artefacts CURÉS, §61) qui ne couvre PAS
l'exhaustivité des modules : le watchdog dit « rien d'aveugle » sur SA liste, pas « tout est câblé ».
AUCUN ordre, AUCUN secret, LECTURE SEULE (grep/crontab/systemctl en subprocess, fail-safe).

CLI :
    python wiring_audit.py            # rapport complet (consommés / activés / outils / ORPHELINS)
    python wiring_audit.py --alert    # concis (pour /lance-correction & cron)
"""
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP = {"tests_audit", "wiring_audit"}


def _cron_service_modules():
    """Modules `.py` référencés par le crontab OU un unit systemd bitget-*. Fail-safe -> set()."""
    mods = set()
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
        mods |= set(re.findall(r"([a-z_][a-z0-9_]+)\.py", cron))
    except Exception:
        pass
    try:
        svc = subprocess.run(["bash", "-lc", "systemctl cat 'bitget-*' 2>/dev/null"],
                             capture_output=True, text=True, timeout=15).stdout
        mods |= set(re.findall(r"([a-z_][a-z0-9_]+)\.py", svc))
    except Exception:
        pass
    return mods


def _importer_map():
    """{module: set(fichiers de PROD qui l'importent)}. UN SEUL passage regex sur TOUS les *.py de
    prod (RÉCURSIF : top-level + dashboard/ + data_collector/ + qml_prototype/… — dashboard/server.py
    est un gros importeur), en excluant scratchpad et tests_audit. Remplace ~200 grep subprocess ->
    quasi instantané, MÊME couverture que l'ancien `grep -r`. Fail-safe -> {}."""
    imp = {}
    rx = re.compile(r"\bfrom\s+([a-z_][a-z0-9_]*)\s+import|\bimport\s+([a-z_][a-z0-9_]*)")
    for p in glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True):
        rel = os.path.relpath(p, ROOT)
        if rel.startswith("scratchpad" + os.sep) or os.path.basename(p) == "tests_audit.py":
            continue
        base = os.path.basename(p)[:-3]
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for mo in rx.finditer(txt):
            imp.setdefault(mo.group(1) or mo.group(2), set()).add(base)
    return imp


def classify(has_importer, activated, has_main):
    """PUR. Catégorie d'un module depuis ses 3 signaux de vie."""
    if has_importer:
        return "consumed"
    if activated:
        return "activated"
    if has_main:
        return "standalone"
    return "orphan"


def audit():
    """Classe tous les modules top-level. Retourne {catégorie: [modules]}. Un module qui SERAIT
    orphelin mais porte le marqueur `WIRING-RESERVE` (réserve ASSUMÉE, documentée) est classé
    'reserve' (accepté), pas 'orphan' (dormant accidentel = vrai risque ERR-013)."""
    activated = _cron_service_modules()
    imp = _importer_map()
    cats = {"consumed": [], "activated": [], "standalone": [], "reserve": [], "orphan": []}
    for p in sorted(glob.glob(os.path.join(ROOT, "*.py"))):
        m = os.path.basename(p)[:-3]
        if m in SKIP:
            continue
        try:
            src = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        has_importer = bool(imp.get(m, set()) - {m})     # importé par un AUTRE module de prod
        cat = classify(has_importer, m in activated, "__main__" in src)
        if cat == "orphan" and "wiring-reserve" in src.lower():
            cat = "reserve"
        cats[cat].append(m)
    return cats


def main():
    alert = "--alert" in sys.argv
    c = audit()
    orphans = c["orphan"]
    if alert:
        print(f"WIRING: {len(orphans)} orphelin(s) biblio"
              + ((" : " + ", ".join(orphans)) if orphans else " — tout câblé/activé/autonome/réserve"))
    else:
        print("=== WIRING AUDIT (câblage/activation, anti-ERR-013, lecture seule) ===")
        print(f"  CONSOMMÉS (importés en prod)   : {len(c['consumed'])}")
        print(f"  ACTIVÉS (cron/systemd)         : {len(c['activated'])}")
        print(f"  AUTONOMES (outils/labos CLI)   : {len(c['standalone'])}")
        print(f"  RÉSERVE (marquée WIRING-RESERVE) : {len(c['reserve'])}"
              + ((" -> " + ", ".join(c['reserve'])) if c['reserve'] else ""))
        print(f"  ⚠ ORPHELINS (biblio non consommée) : {len(orphans)}")
        for m in orphans:
            print(f"      - {m}")
        if not orphans:
            print("  -> aucun module-bibliothèque dormant. Tout est câblé, activé, autonome ou réserve.")
    print("Lecture seule, aucun ordre. VERDICT: SAFE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
