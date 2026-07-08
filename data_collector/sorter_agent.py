"""Agent TRIEUR du collecteur de données — Python système, ZÉRO dépendance tierce.

Classement : SAFE (lecture/écriture de fichiers locaux du collecteur uniquement,
AUCUN réseau, AUCUN ordre). Lancement :

    python3 data_collector/sorter_agent.py

Rôle : lire les résultats bruts du scraping (`raw_items.jsonl`, produits par
`scraper_agent.py`), en extraire les MOTS-CLÉS thématiques, et CLASSER chaque
élément dans une catégorie — les catégories sont CRÉÉES par l'agent lui-même au
fil de l'eau, selon les thèmes rencontrés :

  • un élément suffisamment similaire à une catégorie existante (cosinus sur les
    vecteurs de mots-clés ≥ SIM_MIN) la REJOINT — et enrichit son profil ;
  • sinon l'agent CRÉE une nouvelle catégorie, nommée d'après les mots-clés
    dominants de l'élément fondateur (ex. « bitcoin-etf-blackrock »).

Tout est DÉTERMINISTE (pas de LLM, pas d'aléa) : mêmes entrées -> mêmes catégories.
Sorties : `categories.json` (profils des catégories), `sorted_items.jsonl`
(éléments classés), état incrémental `sorter_state.json` (ids déjà triés).
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW_PATH = HERE / "raw_items.jsonl"
CATS_PATH = HERE / "categories.json"
SORTED_PATH = HERE / "sorted_items.jsonl"
STATE_PATH = HERE / "sorter_state.json"

SIM_MIN = 0.18          # similarité cosinus minimale pour rejoindre une catégorie
TOP_K = 12              # mots-clés retenus par élément
PROFIL_MAX = 40         # taille max du profil d'une catégorie (termes les plus lourds)
POIDS_TITRE = 3.0       # les termes du titre pèsent plus que ceux du corps

# Mots vides FR + EN + jargon web (liste courte, volontairement conservatrice).
STOPWORDS = frozenset("""
a about after all also an and are as at be been before but by can could de des du
et for from has have he her his how however if in into is it its la le les more
most new no not now of on or our over s so some than that the their them then
there these they this to under une up was we were what when which while who why
will with would you your vs via amid says said say th its it's dont pas plus sur
au aux ce cette ces son sa ses un pour par est sont avec comme fait faire entre
apres selon deux trois being make makes just other others may might us
""".split())

_TOKEN = re.compile(r"[a-z][a-z0-9\-']{2,}")


def _fold(text):
    """Minuscules + accents retirés (déterministe, indépendant de la locale)."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def keywords(item, top_k=TOP_K):
    """Mots-clés pondérés d'un élément {terme: poids} — titre boosté, mots vides
    exclus. PUR et déterministe (base de la similarité ET du nommage)."""
    poids = Counter()
    for champ, mult in (("title", POIDS_TITRE), ("text", 1.0)):
        for tok in _TOKEN.findall(_fold(item.get(champ, ""))):
            tok = tok.strip("-'")
            if len(tok) >= 3 and tok not in STOPWORDS and not tok.isdigit():
                poids[tok] += mult
    return dict(poids.most_common(top_k))


def _cosine(a, b):
    """Similarité cosinus entre deux dicts {terme: poids} (0.0 si vide)."""
    if not a or not b:
        return 0.0
    dot = sum(w * b[t] for t, w in a.items() if t in b)
    if dot == 0.0:
        return 0.0
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    return dot / (na * nb)


def _nom_categorie(kw, existants):
    """Nom lisible d'une nouvelle catégorie : 3 mots-clés dominants, unicité assurée."""
    base = "-".join(list(kw)[:3]) or "divers"
    nom, i = base, 2
    while nom in existants:
        nom, i = f"{base}-{i}", i + 1
    return nom


def classer(item, categories):
    """Classe UN élément : rejoint la meilleure catégorie (cosinus ≥ SIM_MIN) ou en
    CRÉE une. Renvoie (nom, similarité, créée) et met à jour les profils EN PLACE."""
    kw = keywords(item)
    meilleur, best_sim = None, 0.0
    for nom, cat in categories.items():
        sim = _cosine(kw, cat.get("keywords", {}))
        if sim > best_sim:
            meilleur, best_sim = nom, sim
    if meilleur is not None and best_sim >= SIM_MIN:
        cat = categories[meilleur]
        profil = Counter(cat.get("keywords", {}))
        profil.update(kw)                                   # le thème s'enrichit
        cat["keywords"] = dict(profil.most_common(PROFIL_MAX))
        cat["n_items"] = int(cat.get("n_items", 0)) + 1
        return meilleur, round(best_sim, 3), False
    nom = _nom_categorie(kw, categories)
    categories[nom] = {"keywords": kw, "n_items": 1, "created_ts": int(time.time())}
    return nom, round(best_sim, 3), True


def _read_jsonl(path):
    try:
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows
    except FileNotFoundError:
        return []


def trier():
    """Boucle incrémentale : classe tous les éléments bruts non encore triés."""
    categories = {}
    try:
        categories = json.loads(CATS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        pass
    deja = set()
    try:
        deja = set(json.loads(STATE_PATH.read_text(encoding="utf-8")).get("ids", []))
    except (FileNotFoundError, ValueError):
        pass
    nouveaux, crees = 0, []
    with SORTED_PATH.open("a", encoding="utf-8") as fh:
        for item in _read_jsonl(RAW_PATH):
            iid = item.get("id")
            if not iid or iid in deja:
                continue
            nom, sim, cree = classer(item, categories)
            fh.write(json.dumps({"id": iid, "ts": item.get("ts"),
                                 "source": item.get("source"),
                                 "title": item.get("title"), "url": item.get("url"),
                                 "category": nom, "sim": sim},
                                ensure_ascii=False) + "\n")
            deja.add(iid)
            nouveaux += 1
            if cree:
                crees.append(nom)
    CATS_PATH.write_text(json.dumps(categories, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    STATE_PATH.write_text(json.dumps({"ids": sorted(deja),
                                      "updated_ts": int(time.time())}),
                          encoding="utf-8")
    print(f"Tri : {nouveaux} élément(s) classé(s) · {len(categories)} catégorie(s) "
          f"dont {len(crees)} créée(s)" + (f" : {', '.join(crees)}" if crees else ""))
    for nom, cat in sorted(categories.items(), key=lambda kv: -kv[1].get("n_items", 0)):
        top = ", ".join(list(cat.get("keywords", {}))[:5])
        print(f"  [{cat.get('n_items', 0):3d}] {nom}  ({top})")
    return nouveaux


if __name__ == "__main__":
    sys.exit(0 if trier() >= 0 else 1)
