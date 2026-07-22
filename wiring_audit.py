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
    python wiring_audit.py --write    # + sérialise wiring_report.json (badge dashboard)
"""
import ast
import glob
import json
import os
import re
import subprocess
import sys
import time

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
    """{module: set(fichiers de PROD qui l'importent)}. Parse l'AST de TOUS les *.py de prod
    (RÉCURSIF : top-level + dashboard/ + data_collector/ + qml_prototype/… — dashboard/server.py est
    un gros importeur), en excluant scratchpad et tests_audit. L'AST (vs regex) gère les imports en
    virgule (`import a, b`) ET ignore les imports cités dans commentaires/docstrings/chaînes -> pas
    de faux orphelin ni de dormant masqué. Un fichier non-parsable est ignoré. Fail-safe -> {}."""
    imp = {}
    for p in glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True):
        rel = os.path.relpath(p, ROOT)
        if rel.startswith("scratchpad" + os.sep) or os.path.basename(p) == "tests_audit.py":
            continue
        base = os.path.basename(p)[:-3]
        try:
            tree = ast.parse(open(p, encoding="utf-8", errors="ignore").read())
        except Exception:
            continue                                   # fichier syntaxiquement invalide -> ignoré
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:               # `import a, b, c` -> chaque nom
                    imp.setdefault(alias.name.split(".")[0], set()).add(base)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:     # absolu seulement (ignore les `from . import`)
                    imp.setdefault(node.module.split(".")[0], set()).add(base)
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
        if cat == "orphan" and "WIRING-RESERVE" in src:   # tag EXACT (pas une sous-chaîne lowercase)
            cat = "reserve"
        cats[cat].append(m)
    return cats


def write_report(cats, chemin=None):
    """Sérialise le résultat d'audit() en artefact JSON pour le badge « câblage » du
    dashboard (audit frictions 22/07 : triple « tout est câblé ? » en une session).
    Chemin INJECTABLE (ERR-019 : un test ne doit jamais écrire l'artefact de prod)."""
    chemin = chemin or os.path.join(ROOT, "wiring_report.json")
    rep = {"ts": time.time(),
           "counts": {k: len(v) for k, v in cats.items()},
           "orphans": list(cats.get("orphan") or []),
           "reserve": list(cats.get("reserve") or []),
           "ok": not cats.get("orphan")}
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False)
    os.replace(tmp, chemin)  # écriture atomique (le dashboard lit en concurrence)
    return chemin


def main():
    alert = "--alert" in sys.argv
    c = audit()
    orphans = c["orphan"]
    if "--write" in sys.argv:
        write_report(c)
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
