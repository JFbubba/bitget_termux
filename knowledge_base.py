"""
knowledge_base.py — base de connaissances issue du tri Drive (`extraction/`),
interrogeable par les agents et par strategy_lab. SAFE (lecture seule, aucun ordre).

« Ajouter le dossier trié à la base de données » : chaque fiche `extraction/*.md`
(frontmatter `source/category/action/target` + corps = valeur extraite) est
chargée dans une base interrogeable, persistée en `knowledge.json` pour SURVIVRE à
la suppression éventuelle de `extraction/`.

Usage par un agent :
    import knowledge_base as kb
    kb.rules_for("volume_profile")   # règles extraites sur un sujet
    kb.query(category="method")      # toutes les méthodes
"""

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXTRACTION_DIR = ROOT / "extraction"
KB_FILE = ROOT / "knowledge.json"


def _parse_fiche(path):
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return {"id": path.stem,
            "category": meta.get("category"), "action": meta.get("action"),
            "target": meta.get("target"), "source": meta.get("source"),
            "body": body.strip()}


def build(extraction_dir=EXTRACTION_DIR, out=KB_FILE):
    """Construit la base depuis les fiches `extraction/*.md` et la persiste. SAFE."""
    entries = []
    for p in sorted(Path(extraction_dir).glob("*.md")):
        if p.name == "INDEX.md":
            continue
        try:
            entries.append(_parse_fiche(p))
        except Exception:
            pass
    kb = {"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "count": len(entries), "entries": entries}
    Path(out).write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")
    return kb


def load(path=KB_FILE):
    """Charge la base ; reconstruit depuis `extraction/` si le json est absent."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        if EXTRACTION_DIR.exists():
            return build()
        return {"count": 0, "entries": []}


def query(category=None, action=None, contains=None, kb=None):
    """Filtre les fiches par catégorie / action / sous-chaîne (id ou corps). Pur."""
    kb = kb or load()
    out = []
    for e in kb.get("entries", []):
        if category and e.get("category") != category:
            continue
        if action and e.get("action") != action:
            continue
        if contains and contains.lower() not in (str(e.get("id", "")) + str(e.get("body", ""))).lower():
            continue
        out.append(e)
    return out


def rules_for(subject, kb=None):
    """Fiches pertinentes pour un sujet (un agent consulte les règles extraites :
    ex. 'volume_profile', 'smc', 'martingale', 'wyckoff'). Pur."""
    return query(contains=subject, kb=kb)


def categories(kb=None):
    """Inventaire {catégorie: nombre}. Pur."""
    kb = kb or load()
    out = {}
    for e in kb.get("entries", []):
        c = e.get("category") or "?"
        out[c] = out.get(c, 0) + 1
    return out


def main():
    kb = build()
    print(f"knowledge.json : {kb['count']} fiches")
    for c, n in sorted(categories(kb).items(), key=lambda kv: -kv[1]):
        print(f"  {c:20} {n}")


if __name__ == "__main__":
    main()
