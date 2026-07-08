"""Bloc « collecte de données » du digest quotidien (§101, suite 2). SAFE.

Classement : SAFE — lecture seule des artefacts locaux du collecteur
(`sorted_items.jsonl`, `categories.json`), AUCUN réseau, AUCUN ordre. Le digest
de 07:00 y gagne une vue de ce que les deux agents (scraper + trieur) ont
ramassé et classé sur les dernières 24 h : volume, catégories touchées,
nouvelles catégories, et les thèmes dominants illustrés par leur dernier titre.

`resume()` est PURE (testable) ; `bloc()` est le chargeur fail-safe pour
`daily_digest.build_message` ([] si artefacts absents/corrompus — un bloc qui
casse ne prive jamais des autres).
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SORTED_PATH = HERE / "sorted_items.jsonl"
CATS_PATH = HERE / "categories.json"

FENETRE_S = 86_400      # la fenêtre du digest : 24 h
TOP_CATS = 4            # catégories dominantes affichées
TITRE_MAX = 70          # troncature des titres (le digest reste compact)


def resume(items, categories, now, fenetre_s=FENETRE_S, top=TOP_CATS):
    """PUR. Lignes du bloc digest à partir des éléments TRIÉS et des profils de
    catégories — [] si rien de collecté dans la fenêtre. items : [{ts, title,
    category, ...}] ; categories : {nom: {n_items, created_ts, ...}}."""
    recents = [i for i in (items or [])
               if i.get("category") and (now - float(i.get("ts") or 0)) <= fenetre_s]
    if not recents:
        return []
    par_cat = Counter(i["category"] for i in recents)
    nouvelles = sum(1 for meta in (categories or {}).values()
                    if (now - float(meta.get("created_ts") or 0)) <= fenetre_s)
    lignes = [f"\n📡 Collecte 24 h : {len(recents)} élément(s) · "
              f"{len(par_cat)} catégorie(s) touchée(s)"
              + (f" · {nouvelles} créée(s)" if nouvelles else "")]
    for cat, n in par_cat.most_common(top):
        titre = next((i.get("title") or "" for i in reversed(recents)
                      if i["category"] == cat), "")
        lignes.append(f"  {cat} ×{n} — {titre[:TITRE_MAX]}")
    return lignes


def bloc(now=None):
    """Chargeur FAIL-SAFE pour le digest : lit les artefacts locaux et rend les
    lignes du bloc ([] si indisponibles — jamais d'exception)."""
    try:
        items = []
        for ligne in SORTED_PATH.read_text(encoding="utf-8").splitlines()[-5000:]:
            try:
                items.append(json.loads(ligne))
            except Exception:
                continue
        cats = json.loads(CATS_PATH.read_text(encoding="utf-8"))
        return resume(items, cats, now if now is not None else time.time())
    except Exception:
        return []


if __name__ == "__main__":
    print("\n".join(bloc()) or "(rien de collecté sur 24 h)")
