"""Ingestion PONCTUELLE d'URL(s) collées par le propriétaire (§101). SAFE.

Le geste : le propriétaire colle un ou plusieurs liens dans la conversation ;
l'agent lance cet outil (venv du collecteur — ERR-004, scrapling n'existe que
là), puis le TRIEUR (Python système). Chaque page rejoint le même pipeline que
la collecte quotidienne : mêmes conventions (id/dédup/normalisation, fonctions
RÉUTILISÉES de `scraper_agent`), même journal brut, mêmes catégories.

    ./data_collector/.venv/bin/python data_collector/ingest_url.py URL [URL ...]
    python3 data_collector/sorter_agent.py     # classement (à chaîner ensuite)

Détection automatique : un flux RSS/Atom est moissonné (jusqu'à MAX_PAR_SOURCE
éléments) ; une page article donne UN élément (titre + paragraphes). GET poli
uniquement, fail-safe par URL (une URL morte ne casse pas les autres).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))            # racine du dépôt (import qualifié)

# Import QUALIFIÉ (même objet-module que les tests/le dashboard — un import de
# tête créerait un DOUBLE du module et les monkeypatchs ne s'appliqueraient pas).
from data_collector import scraper_agent as sc  # noqa: E402 — conventions PARTAGÉES

SOURCE_COLLE = "colle-proprio"                  # marque les éléments collés à la main


def _est_flux(body):
    """PUR. Vrai si le corps ressemble à un flux RSS/Atom (et pas à une page HTML)."""
    tete = (body or "").lstrip()[:500].lower()
    return ("<rss" in tete) or ("<feed" in tete) or tete.startswith("<?xml")


def ingest(urls, source=SOURCE_COLLE):
    """Récupère chaque URL, normalise, DÉDUPLIQUE et appende au journal brut.
    Retourne la liste des éléments ajoutés (fail-safe par URL)."""
    known = sc._known_ids()
    ajoutes = []
    with sc.RAW_PATH.open("a", encoding="utf-8") as fh:
        for url in urls:
            page = sc._fetch(url)
            if page is None:
                continue
            body = sc._raw_body(page)
            items = (sc.parse_rss(body, source) if _est_flux(body)
                     else sc.parse_html(page, url, source))
            fresh = [it for it in items if it["id"] not in known]
            for it in fresh:
                it["ts"] = int(time.time())
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
                known.add(it["id"])
            ajoutes.extend(fresh)
            print(f"  {url[:70]} : {len(items)} lu(s), {len(fresh)} nouveau(x)")
            if len(urls) > 1:
                time.sleep(sc.PAUSE_S)
    return ajoutes


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a.startswith("http")]
    if not args:
        print("usage : ingest_url.py URL [URL ...]")
        sys.exit(2)
    res = ingest(args)
    print(f"Ingestion : {len(res)} élément(s) ajouté(s) -> {sc.RAW_PATH.name}"
          " (lancer sorter_agent.py pour classer)")
    sys.exit(0)
