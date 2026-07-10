"""Agent SCRAPER du collecteur de données — à exécuter dans le venv du collecteur.

Classement : SAFE (lecture seule web : GET uniquement, AUCUN ordre, AUCUN secret).

ERR-004 : `scrapling` est une dépendance TIERCE — elle vit UNIQUEMENT dans le venv
isolé `data_collector/.venv` (jamais dans le Python système du bot). Lancement :

    ./data_collector/.venv/bin/python data_collector/scraper_agent.py

Rôle : lire `sources.json` (flux RSS / pages HTML publiques crypto), récupérer les
éléments via scrapling (Fetcher), normaliser {id, ts, source, url, title, text,
published}, DÉDUPLIQUER contre l'existant, et ajouter au journal brut
`raw_items.jsonl`. L'agent TRIEUR (`sorter_agent.py`, Python système, zéro dépendance)
lit ensuite ce journal et classe par thèmes. Politesse : pause entre sources, timeout,
plafond d'éléments par source (pas d'aspirateur).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES_PATH = HERE / "sources.json"
RAW_PATH = HERE / "raw_items.jsonl"
MAX_PAR_SOURCE = 20
PAUSE_S = 1.5
TIMEOUT_S = 25

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean(text):
    """Texte plat : balises HTML retirées, entités basiques, espaces normalisés."""
    if not text:
        return ""
    text = _TAGS.sub(" ", str(text))
    for ent, ch in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")):
        text = text.replace(ent, ch)
    return _WS.sub(" ", text).strip()


def _item_id(url, title):
    """Identifiant stable d'un élément (dédup) : sha1 de l'URL (ou du titre)."""
    base = (url or "") + "|" + (title or "")
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
    return hashlib.sha1(base.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:16]


def _strip_boilerplate(title):
    """Retire le suffixe de site répété d'un <title> HTML (« Titre - MQL5 Articles »
    -> « Titre »). Sans lui, un boilerplate identique sur chaque page (pesé ×3 par le
    trieur) crée une similarité ARTIFICIELLE qui agglutine tout un domaine dans une
    seule catégorie (constaté le 08/07 : 85/101 articles MQL5). PUR. Garde-fous : ne
    coupe que sur «  -  »/«  |  » (séparateurs entourés d'espaces, pas un tiret
    interne), suffixe court (≤ 30 car) et reste substantiel (≥ 15 car)."""
    for sep in (" | ", " - ", " — "):
        if sep in title:
            tete, _, queue = title.rpartition(sep)
            if len(queue) <= 30 and len(tete) >= 15:
                return tete.strip()
    return title


def _known_ids():
    """Ids déjà collectés (scan du journal brut existant — collecte incrémentale)."""
    ids = set()
    try:
        for line in RAW_PATH.read_text(encoding="utf-8").splitlines():
            try:
                ids.add(json.loads(line).get("id"))
            except ValueError:
                continue
    except FileNotFoundError:
        pass
    return ids


def _fetch(url):
    """GET via scrapling. Fail-safe : None si erreur OU statut HTTP ≠ 200 —
    sinon une page 404/403 devient un faux « article » (catégorie poubelle,
    constaté le 08/07 avec un 404 Decrypt ingéré comme contenu)."""
    try:
        from scrapling.fetchers import Fetcher
        page = Fetcher.get(url, timeout=TIMEOUT_S, stealthy_headers=True)
        statut = getattr(page, "status", 200)
        if statut != 200:
            print(f"  ! fetch KO (HTTP {statut}): {url}")
            return None
        return page
    except Exception as exc:                     # noqa: BLE001 — une source ne casse pas la collecte
        print(f"  ! fetch KO ({type(exc).__name__}): {url}")
        return None


def _raw_body(page):
    """Corps brut de la réponse (pour parser le XML RSS en stdlib — les parseurs
    HTML mutilent les balises <link> des flux RSS)."""
    for attr in ("body", "html_content", "text"):
        v = getattr(page, attr, None)
        if v:
            return v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)
    return str(page)


def parse_rss(xml_text, source_name):
    """Éléments d'un flux RSS/Atom -> liste de dicts normalisés (sans réseau, PUR)."""
    out = []
    try:
        xml_text = xml_text[xml_text.index("<"):]          # strip BOM/préambule
        root = ET.fromstring(xml_text)
    except (ValueError, ET.ParseError):
        return out
    ns_atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{ns_atom}entry")
    for it in items[:MAX_PAR_SOURCE]:
        def _t(tag, it=it):
            return (it.findtext(tag) or it.findtext(f"{ns_atom}{tag}") or "").strip()
        link = _t("link")
        if not link:                                        # Atom : <link href="..."/>
            el = it.find(f"{ns_atom}link")
            link = (el.get("href") or "").strip() if el is not None else ""
        title = _clean(_t("title"))
        if not title:
            continue
        out.append({"id": _item_id(link, title), "source": source_name,
                    "url": link, "title": title,
                    "text": _clean(_t("description") or _t("summary"))[:2000],
                    "published": _t("pubDate") or _t("updated")})
    return out


def parse_html(page, url, source_name, cap_texte=2000):
    """Page HTML générique -> un élément (titre + paragraphes) via scrapling.
    API RÉELLE scrapling 0.4 (constatée le 08/07, ERR-007) : Response.css(sel)
    -> liste Selectors indexable ; css_first N'EXISTE PAS sur Response."""
    try:
        titres = page.css("title::text")
        title = _strip_boilerplate(_clean(str(titres[0]) if titres else ""))
        paras = " ".join(str(p) for p in page.css("p::text")[:60])
        if not title:
            return []
        return [{"id": _item_id(url, title), "source": source_name, "url": url,
                 "title": title, "text": _clean(paras)[:cap_texte], "published": ""}]
    except Exception:                            # noqa: BLE001 — fail-safe par source
        return []


def enrichir_texte(items, source_name, seuil=200, cap_texte=3000):
    """SUIVI DE LIENS (opt-in par source, clé « suivre_liens ») : certains flux ne
    livrent que le titre (mql5 : description vide) — pour chaque NOUVEL élément au
    texte maigre, GET poli de sa page et extraction parse_html. Fail-safe par
    élément (page morte -> le titre seul reste). Ne touche qu'aux éléments FRAIS :
    le coût réseau reste borné par MAX_PAR_SOURCE/jour."""
    for it in items:
        if len(it.get("text") or "") >= seuil or not it.get("url"):
            continue
        time.sleep(PAUSE_S)
        page = _fetch(it["url"])
        if page is None:
            continue
        art = parse_html(page, it["url"], source_name, cap_texte=cap_texte)
        if art and art[0].get("text"):
            it["text"] = art[0]["text"]
    return items


def collect():
    cfg = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    known = _known_ids()
    added = 0
    with RAW_PATH.open("a", encoding="utf-8") as fh:
        for src in cfg.get("sources", []):
            name, url = src.get("name", "?"), src.get("url", "")
            page = _fetch(url)
            if page is None:
                continue
            if src.get("type") == "rss":
                items = parse_rss(_raw_body(page), name)
            else:
                items = parse_html(page, url, name)
            fresh = [it for it in items if it["id"] not in known]
            if src.get("suivre_liens"):
                fresh = enrichir_texte(fresh, name)
            for it in fresh:
                it["ts"] = int(time.time())
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
                known.add(it["id"])
            added += len(fresh)
            print(f"  {name}: {len(items)} lus, {len(fresh)} nouveaux")
            time.sleep(PAUSE_S)
    print(f"Collecte terminée : {added} nouvel(aux) élément(s) -> {RAW_PATH.name}")
    return added


if __name__ == "__main__":
    sys.exit(0 if collect() >= 0 else 1)
