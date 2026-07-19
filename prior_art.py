#!/usr/bin/env python3
"""prior_art.py — check ANTI-DOUBLON à lancer AVANT de construire quoi que ce soit. SAFE.

LECTURE SEULE, PUR (aucun ordre, aucun secret, aucun réseau sauf le subprocess graphify local).
Réflexe UNIQUE « ça existe déjà / ça a déjà été testé ? » qui interroge d'un coup les 5 sources
de vérité anti-gaspillage du dépôt :
  1. CODE — graphify (graphe de tout le dépôt) + symboles `def`/`class` + docstrings de modules ;
  2. VERDICTS (`docs/VERDICTS.md`) — idées DÉJÀ mesurées / rejetées (ne pas re-tester) ;
  3. LABOS (`scratchpad/LABOS.md`) — labos existants + leur verdict ;
  4. MÉMOIRE de l'agent (MEMORY.md + fichiers) — faits déjà consignés ;
  5. SAVOIR & ERREURS (`docs/SAVOIR.md`, `docs/AGENT_ERRORS.md`).

Corrige ERR-015 : contexte d'agent ÉPHÉMÈRE -> on ancre sur le 1er fichier trouvé et on re-code un
module qui existait déjà (ex. `smc.py` « découvert » après avoir failli le dupliquer ; re-mesure
d'idées déjà rejetées = double data inutile). À lancer sur le CONCEPT avant tout module/labo/voix.

CLI : python prior_art.py "<concept ou mots-clés>"     (ex. python prior_art.py "SMC ICT killzone")
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_STOP = {"the", "and", "pour", "avec", "dans", "une", "des", "les", "sur", "est", "qui",
         "que", "par", "sans", "aux", "son", "ses", "via", "new", "add", "make"}


def tokens(concept):
    """PUR. Concept -> mots-clés normalisés (minuscules, ≥3 lettres, hors mots vides), uniques."""
    out, seen = [], set()
    for w in re.findall(r"[a-zA-Zéèêàùçûôî]{3,}", str(concept).lower()):
        if w in _STOP or w in seen:
            continue
        seen.add(w); out.append(w)
    return out


def _subwords(name):
    """PUR. Découpe un identifiant en SOUS-MOTS (underscore + camelCase). Ex.
    fair_value_gaps -> {fair,value,gaps} ; changeOfCharacter -> {change,of,character}."""
    out = set()
    for part in re.split(r"[_\W]+", name):
        for w in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", part) or [part]:
            if w:
                out.add(w.lower())
    return out


def scan_symbols(pytext, toks):
    """PUR. `def`/`class` dont un SOUS-MOT du nom ÉGALE un mot-clé (pas une sous-chaîne — évite
    « value » ∈ « validation »). Indice fort de code existant."""
    hits = []
    for m in re.finditer(r"^\s*(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", pytext, re.M):
        if _subwords(m.group(2)) & set(toks):
            hits.append((m.group(1), m.group(2)))
    return hits


def scan_lines(text, toks, max_hits=6):
    """PUR. Lignes contenant ≥1 mot-clé (avec n° de ligne). Cappé pour rester lisible."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if any(t in low for t in toks):
            out.append((i, line.strip()[:160]))
            if len(out) >= max_hits:
                break
    return out


def code_matches(toks, max_files=12):
    """Scan des *.py du dépôt : symboles def/class matchant + 1re ligne du docstring si elle matche."""
    res = []
    for p in sorted(ROOT.glob("*.py")):
        if p.name in ("prior_art.py", "tests_audit.py"):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        syms = scan_symbols(txt, toks)
        doc = ""
        dm = re.search(r'^\s*(?:#!.*\n)?"""(.*?)"""', txt, re.S)
        if dm:
            dlow = dm.group(1).lower()
            if sum(1 for t in set(toks) if t in dlow) >= 2:      # ≥2 mots-clés -> signal fort
                doc = dm.group(1).strip().splitlines()[0][:120]
        if syms or doc:
            res.append((p.name, [s[1] for s in syms][:6], doc))
        if len(res) >= max_files:
            break
    return res


def graphify_matches(concept, timeout=30):
    """Interroge graphify (graphe de TOUT le dépôt). Renvoie les lignes NODE (fichier:fonction).
    FAIL-SAFE : [] si graphify absent / erreur / timeout."""
    try:
        out = subprocess.run(["graphify", "query", str(concept)], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=timeout)
        lines = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.startswith("NODE ")]
        return lines[:12]
    except Exception:
        return []


def _doc(path, toks, label):
    p = ROOT / path
    if not p.exists():
        return (label, path, [])
    try:
        return (label, path, scan_lines(p.read_text(encoding="utf-8", errors="ignore"), toks))
    except Exception:
        return (label, path, [])


def memory_matches(toks):
    """Best-effort : mémoire de l'agent (~/.claude/projects/*/memory/). FAIL-SAFE si absente."""
    hits = []
    try:
        for mem in glob.glob(os.path.expanduser("~/.claude/projects/*/memory/MEMORY.md")):
            for i, line in scan_lines(Path(mem).read_text(encoding="utf-8", errors="ignore"), toks):
                hits.append((i, line))
    except Exception:
        pass
    return hits[:6]


def report(concept, use_graphify=True):
    """Assemble le rapport (dict) : code/graphify/verdicts/labos/savoir/mémoire + verdict heuristique."""
    toks = tokens(concept)
    code = code_matches(toks)
    gr = graphify_matches(concept) if use_graphify else []
    verdicts = _doc("docs/VERDICTS.md", toks, "VERDICTS (déjà mesuré/rejeté)")
    labos = _doc("scratchpad/LABOS.md", toks, "LABOS")
    savoir = _doc("docs/SAVOIR.md", toks, "SAVOIR")
    errs = _doc("docs/AGENT_ERRORS.md", toks, "AGENT_ERRORS")
    mem = memory_matches(toks)
    code_exists = bool(code or gr)
    already_tested = bool(verdicts[2] or labos[2])
    if code_exists and already_tested:
        verdict = "⚠ EXISTE DÉJÀ (code) ET DÉJÀ TESTÉ — ÉTENDRE/lire le verdict, NE PAS re-coder ni re-mesurer"
    elif code_exists:
        verdict = "⚠ CODE EXISTANT — ÉTENDRE le module existant, ne pas le re-coder"
    elif already_tested:
        verdict = "⚠ DÉJÀ MESURÉ/REJETÉ — lire le verdict AVANT de re-tester (double data)"
    else:
        verdict = "rien trouvé — construction probablement nouvelle (vérifier quand même le contexte)"
    return {"concept": concept, "tokens": toks, "code": code, "graphify": gr,
            "docs": [verdicts, labos, savoir, errs], "memory": mem, "verdict": verdict}


def _print(r):
    print(f"=== PRIOR ART — « {r['concept']} »  (mots-clés : {', '.join(r['tokens']) or '—'}) ===")
    print("\n[1] CODE EXISTANT (symboles def/class + docstrings) :")
    if r["code"]:
        for fn, syms, doc in r["code"]:
            tag = (" · ".join(syms)) or doc
            print(f"  • {fn}  {tag}")
    else:
        print("  (aucun symbole matchant)")
    print("\n[1b] GRAPHIFY (graphe de tout le dépôt) :")
    for ln in r["graphify"] or ["  (graphify indisponible ou aucun nœud)"]:
        print(f"  {ln}" if ln.startswith("  ") else f"  {ln}")
    for label, path, hits in r["docs"]:
        print(f"\n[2] {label} ({path}) :")
        if hits:
            for i, line in hits:
                print(f"  L{i}: {line}")
        else:
            print("  (aucune occurrence)")
    print("\n[3] MÉMOIRE de l'agent (MEMORY.md) :")
    if r["memory"]:
        for i, line in r["memory"]:
            print(f"  L{i}: {line}")
    else:
        print("  (aucune occurrence)")
    print(f"\n>>> VERDICT : {r['verdict']}")
    print("Lecture seule, aucun ordre. VERDICT: SAFE")


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    if not args:
        print(__doc__.split("CLI :")[-1].strip())
        print("\nDonne un concept. Lecture seule. VERDICT: SAFE")
        return
    _print(report(" ".join(args)))


if __name__ == "__main__":
    main()
