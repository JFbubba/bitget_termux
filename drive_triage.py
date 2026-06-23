"""
drive_triage.py — répertoire de triage des fichiers Google Drive (« trading/package »).

Classement : SAFE (logique pure + I/O sur un JSON local ; aucun réseau, aucun ordre).

POURQUOI : le dossier Drive « package » est un fourre-tout (docs, sources, PDF,
skills, projets entamés…). Pour l'analyser sans se perdre et sans rien retraiter
deux fois, on tient un RÉPERTOIRE :
  • savoir si un fichier est DÉJÀ traité (vérifier avant de confirmer « traité ») ;
  • détecter les DOUBLONS — par SUJET (éviter de réextraire deux fois la même chose)
    et par HASH de contenu (fichiers identiques) ;
  • suivre un COMPTEUR fichiers/dossiers traités / total.

Le registre vit dans le REPO (versionné, fiable, modifiable en place). Le serveur
Drive est éphémère ici et sans outil de mise à jour en place : impossible d'y tenir
un journal vivant.

Schéma d'une entrée :
  id            identifiant Drive (clé d'unicité)
  title         titre du fichier
  type          pdf | code | doc | sheet | image | archive | folder | other
  folder        chemin parent lisible (ex. "package/Wyckoff")
  subject       sujet normalisé (ex. "wyckoff", "orderflow", "bitget-api")
  relevant      bool|None — pertinent pour notre projet ?
  duplicate_of  id d'une entrée déjà couvrant ce sujet/contenu, sinon None
  action        learned | extracted | tool-adapted | skipped | pending
  status        "traité" | "à-faire"
  sha1          empreinte du contenu (optionnel) pour les doublons exacts
  notes         résumé court de l'analyse / ce qui a été extrait
  ts            horodatage ISO
"""

import hashlib
import json
import re
import time
from pathlib import Path

REGISTRY_FILE = Path(__file__).resolve().parent / "drive_triage.json"
PACKAGE_FOLDER_ID = "16fYrJsQcVAKU9kasZ9-GZ4gV5EIAtxmX"  # Drive: trading/package

VALID_ACTIONS = ("learned", "extracted", "tool-adapted", "skipped", "pending")


def new_registry(source="trading/package", folder_id=PACKAGE_FOLDER_ID):
    return {"source": source, "folder_id": folder_id, "updated": _now_iso(),
            "totals": {"declared_total": None, "declared_folders": None},
            "entries": []}


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def load(path=REGISTRY_FILE):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return new_registry()


def save(reg, path=REGISTRY_FILE):
    reg["updated"] = _now_iso()
    Path(path).write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- helpers purs ----------

def norm_subject(s):
    """Normalise un sujet : minuscules, accents simplifiés, tirets. Pur."""
    s = (s or "").strip().lower()
    s = (s.replace("é", "e").replace("è", "e").replace("ê", "e").replace("à", "a")
         .replace("ç", "c").replace("ï", "i").replace("ô", "o").replace("û", "u"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def sha1_of(data):
    """Empreinte SHA-1 d'un texte ou d'octets. Pur."""
    if isinstance(data, str):
        data = data.encode("utf-8", errors="ignore")
    return hashlib.sha1(data).hexdigest()


def index_by_id(reg):
    return {e["id"]: e for e in reg.get("entries", []) if e.get("id")}


def get(reg, file_id):
    return index_by_id(reg).get(file_id)


def is_processed(reg, file_id=None, title=None):
    """Vrai si un fichier (par id, sinon par titre) est déjà au statut « traité »."""
    for e in reg.get("entries", []):
        if file_id and e.get("id") == file_id:
            return e.get("status") == "traité"
        if title and not file_id and e.get("title") == title:
            return e.get("status") == "traité"
    return False


def upsert(reg, entry):
    """Insère/mets à jour une entrée (clé = id). Mise à jour = fusion des champs
    fournis SEULEMENT (ne clobbe pas status/action existants) ; nouvelle entrée =
    défauts appliqués (action=pending, status=à-faire)."""
    provided = {k: v for k, v in entry.items() if v is not None}
    if provided.get("subject"):
        provided["subject"] = norm_subject(provided["subject"])
    entries = reg.setdefault("entries", [])
    for i, e in enumerate(entries):
        if e.get("id") and e.get("id") == provided.get("id"):
            merged = dict(e)
            merged.update(provided)          # ne fusionne que ce qui est fourni
            merged["ts"] = _now_iso()
            entries[i] = merged
            return merged
    new = dict(provided)                     # nouvelle entrée : défauts
    new.setdefault("ts", _now_iso())
    new.setdefault("action", "pending")
    new.setdefault("status", "à-faire")
    entries.append(new)
    return new


def subject_duplicates(reg, subject, exclude_id=None):
    """Entrées PERTINENTES déjà enregistrées sur le MÊME sujet (anti-doublon). Pur."""
    sub = norm_subject(subject)
    out = []
    for e in reg.get("entries", []):
        if e.get("id") == exclude_id:
            continue
        if e.get("subject") == sub and e.get("relevant"):
            out.append(e)
    return out


def hash_duplicates(reg, sha1, exclude_id=None):
    """Entrées au MÊME contenu (doublons exacts par SHA-1). Pur."""
    return [e for e in reg.get("entries", [])
            if e.get("sha1") == sha1 and e.get("id") != exclude_id]


def counters(reg):
    """Compteurs : traités / total, dossiers, pdfs, pertinents, par action. Pur."""
    entries = reg.get("entries", [])
    seen = len(entries)
    processed = sum(1 for e in entries if e.get("status") == "traité")
    folders = sum(1 for e in entries if e.get("type") == "folder")
    pdfs = sum(1 for e in entries if e.get("type") == "pdf")
    relevant = sum(1 for e in entries if e.get("relevant") is True)
    by_action = {}
    for e in entries:
        a = e.get("action", "pending")
        by_action[a] = by_action.get(a, 0) + 1
    totals = reg.get("totals", {})
    return {
        "seen": seen, "processed": processed, "pending": seen - processed,
        "folders": folders, "pdfs": pdfs, "relevant": relevant,
        "by_action": by_action,
        "declared_total": totals.get("declared_total"),
        "declared_folders": totals.get("declared_folders"),
    }


def summary_md(reg):
    """Rapport lisible (Markdown) du registre. Pur."""
    c = counters(reg)
    tot = c["declared_total"]
    head = f"{c['processed']}/{tot}" if tot else f"{c['processed']}/{c['seen']} (total à confirmer)"
    lines = [
        f"# Triage Drive — {reg.get('source', '?')}",
        f"_maj {reg.get('updated', '?')}_",
        "",
        f"- **Fichiers traités** : {head}",
        f"- Dossiers vus : {c['folders']} · PDF vus : {c['pdfs']} · pertinents : {c['relevant']}",
        f"- Par action : " + (", ".join(f"{k}={v}" for k, v in sorted(c['by_action'].items())) or "—"),
        "",
        "| statut | type | titre | sujet | pertinent | action | doublon | notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in reg.get("entries", []):
        rel = "✓" if e.get("relevant") else ("✗" if e.get("relevant") is False else "?")
        dup = (e.get("duplicate_of") or "")[:8]
        notes = (e.get("notes") or "").replace("|", "/")[:60]
        lines.append(f"| {e.get('status','?')} | {e.get('type','?')} | {e.get('title','?')[:40]} "
                     f"| {e.get('subject','')} | {rel} | {e.get('action','')} | {dup} | {notes} |")
    return "\n".join(lines)


def main():
    import sys
    reg = load()
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        key = sys.argv[2]
        done = is_processed(reg, file_id=key) or is_processed(reg, title=key)
        print(f"{'TRAITÉ' if done else 'NON TRAITÉ'} : {key}")
    else:
        print(summary_md(reg))


if __name__ == "__main__":
    main()
