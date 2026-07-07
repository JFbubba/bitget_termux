"""
backup_registres.py — sauvegarde HORS-VPS des registres irremplaçables. SAFE.

§60 : le code vit sur GitHub, mais les registres RÉELS (ledgers, journaux,
hit-rates, décisions) ne vivaient QUE sur ce VPS — une panne disque = perte de
tout l'historique d'argent réel. Chaque nuit : archive tar.gz des fichiers
irremplaçables, CHIFFRÉE (AES-256-CBC, PBKDF2, passphrase BACKUP_PASSPHRASE du
.env — à conserver AUSSI hors-VPS par le propriétaire), envoyée en DOCUMENT sur
le Telegram du propriétaire (déjà câblé, hors-VPS, taille garde-fou 45 Mo).

Restauration :
    openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE \\
        -in registres_YYYYMMDD.tar.gz.enc | tar xz

Lecture seule sur l'état du bot (n'écrit que l'archive temporaire). AUCUN ordre.
CLI : python backup_registres.py [--dry]   (--dry : archive sans envoi)
"""

import os
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
# IRREMPLAÇABLES uniquement (l'historique de bougies data_history/ se re-télécharge)
FICHIERS = [
    "accumulation_ledger.json", "accumulation_real_ledger.json",
    "futures_real_ledger.json", "futures_auto_journal.jsonl",
    "trading_real_ledger.json",                  # surfaces §67 (spot/marge/virements/earn)
    ".alt_carry_journal.jsonl", ".alt_carry_state.json",   # moisson de funding §82-90
    ".liquidity_journal.jsonl",                  # gestion de liquidité §76/§91
    ".trades_archive.jsonl",                     # archive des round-trips §89
    ".overlay_votes.jsonl",                      # votes des voix opt-in + ombre NN §77/§89
    "brain_hitrates.json", "brain_weights.json",
    "brain_log.json", "brain_log_history.jsonl",
    "validation_report.json", "market_timing_history.jsonl",
    "carry_journal.jsonl", ".futures_pos_state.json",
    "knowledge.json", "pending_orders.json", "paper_positions.json",
    "data_history/FUNDING_BTCUSDT.json",
]
TAILLE_MAX = 45 * 1024 * 1024                 # garde-fou Telegram (50 Mo API)


def fichiers_presents(racine=None, noms=None):
    """Chemins EXISTANTS parmi les irremplaçables. PUR (injecte racine/noms)."""
    racine = Path(racine or RACINE)
    out = []
    for n in noms or FICHIERS:
        p = racine / n
        if p.exists() and p.is_file():
            out.append(p)
    return out


def archiver(chemins, dest_tgz):
    """tar.gz des chemins (noms relatifs à la racine). Retourne la taille."""
    with tarfile.open(dest_tgz, "w:gz") as tar:
        for p in chemins:
            tar.add(p, arcname=str(Path(p).relative_to(RACINE)))
    return Path(dest_tgz).stat().st_size


def chiffrer(src, dest_enc, passphrase):
    """AES-256-CBC + PBKDF2 via openssl (présent sur le VPS). Lève si échec."""
    env = dict(os.environ, BACKUP_PASSPHRASE=passphrase)
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
                    "-in", str(src), "-out", str(dest_enc),
                    "-pass", "env:BACKUP_PASSPHRASE"],
                   check=True, env=env, capture_output=True)
    return Path(dest_enc).stat().st_size


def dechiffrer(src_enc, dest, passphrase):
    """Inverse de chiffrer (utilisé par le test d'aller-retour)."""
    env = dict(os.environ, BACKUP_PASSPHRASE=passphrase)
    subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                    "-in", str(src_enc), "-out", str(dest),
                    "-pass", "env:BACKUP_PASSPHRASE"],
                   check=True, env=env, capture_output=True)
    return Path(dest).stat().st_size


def _secrets():
    try:
        from dotenv import load_dotenv
        load_dotenv(RACINE / ".env")
    except Exception:
        pass
    return (os.getenv("BACKUP_PASSPHRASE"), os.getenv("TELEGRAM_BOT_TOKEN"),
            os.getenv("TELEGRAM_CHAT_ID"))


def envoyer_telegram(chemin, token, chat_id, legende):
    """Envoie l'archive en document Telegram. Lève si échec (le timer alerte)."""
    import requests
    with open(chemin, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                          data={"chat_id": chat_id, "caption": legende},
                          files={"document": (Path(chemin).name, f)}, timeout=120)
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError(f"telegram sendDocument: {r.text[:120]}")


def run(dry=False, now=None):
    now = time.time() if now is None else now
    passphrase, token, chat_id = _secrets()
    if not passphrase:
        return "BACKUP_PASSPHRASE absente du .env — sauvegarde IMPOSSIBLE. VERDICT: SAFE"
    chemins = fichiers_presents()
    if not chemins:
        return "aucun registre à sauvegarder. VERDICT: SAFE"
    jour = time.strftime("%Y%m%d", time.gmtime(now))
    with tempfile.TemporaryDirectory() as tmp:
        tgz = Path(tmp) / f"registres_{jour}.tar.gz"
        enc = Path(tmp) / f"registres_{jour}.tar.gz.enc"
        brut = archiver(chemins, tgz)
        taille = chiffrer(tgz, enc, passphrase)
        if taille > TAILLE_MAX:
            return (f"archive {taille // 1024 // 1024} Mo > garde-fou 45 Mo — "
                    "NON envoyée (élaguer FICHIERS). VERDICT: SAFE")
        if dry:
            return (f"[dry] {len(chemins)} fichiers · {brut // 1024} Ko bruts -> "
                    f"{taille // 1024} Ko chiffrés. VERDICT: SAFE")
        envoyer_telegram(enc, token, chat_id,
                         f"🗄 Sauvegarde registres {jour} — {len(chemins)} fichiers, "
                         f"{taille // 1024} Ko chiffrés (AES-256). Déchiffrement : "
                         "openssl enc -d -aes-256-cbc -pbkdf2 + BACKUP_PASSPHRASE.")
        return (f"sauvegarde envoyée sur Telegram : {len(chemins)} fichiers, "
                f"{taille // 1024} Ko chiffrés. VERDICT: SAFE")


def main():
    import sys
    print(run(dry="--dry" in sys.argv))


if __name__ == "__main__":
    main()
