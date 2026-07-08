"""Remplissage initial du corpus MQL5 (§101). SAFE — GET polis uniquement.

Le flux RSS de mql5.com ne donne que les ~10 derniers articles (titres seuls) :
pour constituer le corpus, on lit `sitemap_articles_en.xml` (autorisé par
robots.txt), on prend les N articles les plus récents et on les ingère via le
pipeline standard (`ingest_url.ingest` — dédup, garde HTTP 200, extraction
parse_html). RE-LANÇABLE pour approfondir : la dédup saute les articles déjà
connus, donc `--n 400` après un premier passage à 200 ajoute les 200 suivants.

    ./data_collector/.venv/bin/python scratchpad/mql5_backfill.py [--n 200]

Puis classer : python3 data_collector/sorter_agent.py
"""
from __future__ import annotations

import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_collector import ingest_url as iu          # noqa: E402
from data_collector import scraper_agent as sc      # noqa: E402

SITEMAP = "https://www.mql5.com/sitemap_articles_en.xml"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def urls_recentes(n):
    """Les n URLs d'articles les plus récentes du sitemap (tri lastmod desc)."""
    req = urllib.request.Request(SITEMAP, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    entrees = []
    for u in root.findall(f"{NS}url"):
        loc = (u.findtext(f"{NS}loc") or "").strip()
        lastmod = (u.findtext(f"{NS}lastmod") or "").strip()
        if loc:
            entrees.append((lastmod, loc))
    entrees.sort(reverse=True)
    return [loc for _, loc in entrees[:n]]


def main():
    n = 200
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    urls = urls_recentes(n)
    print(f"sitemap : {len(urls)} articles retenus (les plus récents)")
    sc.PAUSE_S = 1.0                     # poli : ~2 s/article avec le fetch
    ajoutes = iu.ingest(urls, source="mql5-articles")
    print(f"BACKFILL TERMINÉ : {len(ajoutes)} article(s) ajouté(s)")


if __name__ == "__main__":
    main()
