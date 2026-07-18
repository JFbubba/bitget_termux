"""Catalogue des candidats de la code base mql5. LECTURE SEULE.

NOTE (2026-07-08) : la section /code de mql5.com REFUSE le fetch (anti-bot :
HTTP/2 PROTOCOL_ERROR via scrapling, RemoteDisconnected via urllib, chromium
absent pour StealthyFetcher). Or pour RÉIMPLÉMENTER en Python, les ARTICLES sont
une meilleure source que la code base brute : ils décrivent la LOGIQUE (formules)
d'un indicateur/stratégie, réutilisable ; le .mq5 serait du code non exécutable et
non audité (ligne rouge). Le catalogue s'appuie donc sur le corpus d'ARTICLES déjà
ingéré (data_collector, flux mql5-articles) — même finalité, source plus riche.

Si /code redevient accessible, réactiver le fetch RSS ici (fallback conservé).
"""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data_collector" / "raw_items.jsonl"
OUT = Path(__file__).resolve().parent / "catalog.json"


def ingest():
    items = {}
    for line in RAW.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        if "mql5" not in (d.get("source", "") + d.get("url", "")):
            continue
        iid = d.get("id")
        if not iid or iid in items:
            continue
        text = re.sub(r"\s+", " ", d.get("text", "") or "").strip()
        items[iid] = {"id": iid, "title": (d.get("title") or "").strip(),
                      "desc": text[:600], "url": d.get("url", "")}
    OUT.write_text(json.dumps(list(items.values()), ensure_ascii=False, indent=1))
    print(f"catalogue (source: articles mql5) : {len(items)} items -> {OUT.name}")
    return len(items)


if __name__ == "__main__":
    ingest()
