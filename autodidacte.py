"""autodidacte.py — agent AUTO-AMÉLIORANT / AUTODIDACTE.

Classement : SAFE (lecture seule, aucun ordre, aucun secret, aucune écriture d'état de
trading). Réalise concrètement la « Conscience AUTODIDACTE » (docs/CONSCIENCE.md §5) et
le bras « code/méthode » de l'auto-amélioration (docs/AGENT_ERRORS.md), en complément du
§68 qui, lui, améliore le TRADING. Deux bras :

  1. AUTOCORRECTEUR — lit docs/AGENT_ERRORS.md et exécute les contrôles AUTOMATISABLES sur
     le dépôt (ex. ERR-001 : une liste de timeframes qui n'est pas l'échelle complète).
     Signale les récurrences pour revue. Les contrôles de jugement (ERR-002/003) sont
     listés en « revue manuelle » (honnête : on ne prétend pas les automatiser).

  2. AUTODIDACTE — croise le SAVOIR ingéré (knowledge_base) avec ce que le laboratoire a
     réellement MESURÉ/promu (strategies_out/) -> backlog des idées connues NON testées,
     matière de la boucle « idée -> fonction pure -> test -> mesure honnête -> note ».

CLI : python autodidacte.py [--alert]   (--alert -> résumé Telegram best-effort).
Cron hebdo possible. Fonctions pures testables (aucune I/O si texte injecté).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FULL_LADDER = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
_TF = re.compile(r"""['"](\d+[mhdwMHDW])['"]""")
_CFGLINE = re.compile(r"(tfs?|timeframe|granular|ladder|gran)", re.I)


def _logical_lines(text):
    """PUR. Fusionne les lignes physiques en lignes LOGIQUES : tant que les
    parenthèses/crochets/accolades sont déséquilibrés, on continue (littéraux
    multi-lignes). -> (ligne_de_début, texte_fusionné). Heuristique (compte aussi les
    brackets dans les chaînes, acceptable pour des lignes de config)."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        start, buf = i + 1, lines[i]
        depth = sum(buf.count(c) for c in "([{") - sum(buf.count(c) for c in ")]}")
        while depth > 0 and i + 1 < len(lines):
            i += 1
            buf += " " + lines[i]
            depth += sum(lines[i].count(c) for c in "([{") - sum(lines[i].count(c) for c in ")]}")
        yield start, buf
        i += 1


def incomplete_tf_lists(text):
    """PUR (ERR-001). Assignations de timeframes MULTI mais INCOMPLÈTES (≥2 et <8 TF de
    l'échelle). Retourne [(ligne_no, tfs_trouvés, manquants)]. Reconstitue les littéraux
    MULTI-LIGNES. Advisory : ne flague qu'une assignation config-like (contient '=' ET un
    mot-clé tfs/timeframe/granular). Une justification `# tf-ladder-ok` supprime le flag
    (cas opérationnel légitime : confluence MTF, granularité par âge, etc.)."""
    phys = text.splitlines()
    suppr = {i for i, l in enumerate(phys, 1) if "tf-ladder-ok" in l}   # nº de ligne annotée
    out = []
    for ln, logical in _logical_lines(text):
        if "=" not in logical or not _CFGLINE.search(logical):
            continue
        if "tf-ladder-ok" in logical or ln in suppr or (ln - 1) in suppr:  # même ligne OU au-dessus
            continue
        toks = {t.lower() for t in _TF.findall(logical)}
        ladder = {t for t in toks if t in FULL_LADDER}
        if 2 <= len(ladder) < len(FULL_LADDER):
            out.append((ln, sorted(ladder, key=FULL_LADDER.index),
                        [t for t in FULL_LADDER if t not in ladder]))
    return out


def scan_repo_tf(root=None):
    """Applique incomplete_tf_lists à tous les .py du dépôt. -> [{file, line, tfs, missing}].
    Best-effort ; ignore les fichiers illisibles et ce module lui-même."""
    root = Path(root or ROOT)
    findings = []
    for p in sorted(root.glob("*.py")):
        if p.name in ("autodidacte.py", "tests_audit.py"):
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for ln, tfs, miss in incomplete_tf_lists(txt):
            findings.append({"file": p.name, "line": ln, "tfs": tfs, "missing": miss})
    return findings


def knowledge_backlog():
    """Idées connues (knowledge_base) vs stratégies réellement mesurées/promues
    (strategies_out/). Best-effort {}. Backlog = savoir non encore confronté au lab."""
    out = {"n_knowledge": 0, "n_promues": 0, "categories": []}
    try:
        import knowledge_base as kb
        entries = kb.query() if hasattr(kb, "query") else []
        out["n_knowledge"] = len(entries) if entries else 0
        cats = {}
        for e in entries or []:
            c = (e.get("category") if isinstance(e, dict) else None) or "?"
            cats[c] = cats.get(c, 0) + 1
        out["categories"] = sorted(cats.items(), key=lambda x: -x[1])[:8]
    except Exception:
        pass
    try:
        out["n_promues"] = len(list((ROOT / "strategies_out").glob("*.py")))
    except Exception:
        pass
    return out


def snapshot():
    """État LECTURE SEULE de l'auto-amélioration. {tf_findings, backlog, errors_actives}."""
    out = {"tf_findings": [], "backlog": {}, "n_errors_journal": 0, "note": ""}
    try:
        out["tf_findings"] = scan_repo_tf()
    except Exception as e:
        out["note"] += f"scan_tf KO ({type(e).__name__}) "
    out["backlog"] = knowledge_backlog()
    try:
        txt = (ROOT / "docs" / "AGENT_ERRORS.md").read_text(encoding="utf-8")
        out["n_errors_journal"] = len(re.findall(r"^## ERR-\d+", txt, re.M))
    except Exception:
        pass
    return out


def build_report(s=None):
    s = snapshot() if s is None else s
    L = ["=== AUTODIDACTE / AUTO-AMÉLIORATION (lecture seule) ==="]
    tf = s["tf_findings"]
    L.append(f"\n— AUTOCORRECTEUR : ERR-001 (échelle de timeframes) —")
    if tf:
        L.append(f"  ⚠ {len(tf)} liste(s) de TF incomplète(s) à revoir :")
        for f in tf[:12]:
            L.append(f"    {f['file']}:{f['line']} = {f['tfs']}  (manque : {', '.join(f['missing'])})")
    else:
        L.append("  OK — aucune liste de timeframes incomplète détectée dans le dépôt.")
    L.append("  ERR-002/003 : revue de JUGEMENT (holistique-d'abord, vérifier-avant-d'affirmer) "
             "— non automatisable, à repasser à la main lors des analyses.")
    b = s["backlog"]
    L.append(f"\n— AUTODIDACTE : savoir vs mesure —")
    L.append(f"  knowledge_base : {b.get('n_knowledge', 0)} fiches "
             f"({', '.join(f'{c}:{n}' for c, n in b.get('categories', []))})")
    L.append(f"  stratégies promues au lab (strategies_out/) : {b.get('n_promues', 0)}")
    L.append(f"\nJournal d'erreurs : {s['n_errors_journal']} entrée(s) actives (docs/AGENT_ERRORS.md).")
    L.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(L)


def main():
    import sys
    s = snapshot()
    print(build_report(s))
    if "--alert" in sys.argv[1:] and s["tf_findings"]:
        try:
            import telegram_notifier as tn
            tn.send_message(f"🎓 AUTODIDACTE — {len(s['tf_findings'])} liste(s) de timeframes "
                            "incomplète(s) à revoir (ERR-001). Détail : python autodidacte.py")
        except Exception:
            pass


if __name__ == "__main__":
    main()
