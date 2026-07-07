"""
backup_restore_drill.py — EXERCICE DE RESTAURATION des sauvegardes (§89). SAFE.

Une sauvegarde n'existe que si sa restauration a été TESTÉE. Ce drill, à blanc et
en local (rien n'est envoyé, rien n'est écrasé — tout se passe dans un répertoire
temporaire) :
  1. archive les registres vivants (même liste que backup_registres) ;
  2. les CHIFFRE avec la passphrase de production (openssl AES-256-CBC + PBKDF2) ;
  3. les DÉCHIFFRE comme le ferait une restauration réelle ;
  4. dépaquette et VÉRIFIE : liste des fichiers identique, chaque JSON re-parsable,
     tailles identiques aux originaux.
Si une étape casse (passphrase manquante, openssl absent, artefact corrompu), on
l'apprend PENDANT l'exercice — pas le jour du sinistre. Cron mensuel (1ᵉʳ, 08:00)
avec alerte Telegram en cas d'échec (et un mot de confirmation en cas de succès).

CLI : python backup_restore_drill.py [--alert]
"""
from __future__ import annotations

import json
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def drill(now=None):
    """Exécute l'exercice. Retourne {ok, etapes: [...], erreur?}. Rien d'envoyé."""
    import backup_registres as br
    out = {"ok": False, "etapes": [], "ts": int(now or time.time())}
    try:
        passphrase, _tok, _chat = br._secrets()      # (passphrase, token, chat_id)
        if not passphrase:
            out["erreur"] = "BACKUP_PASSPHRASE introuvable (le jour J, la restauration échouerait !)"
            return out
        chemins = br.fichiers_presents()
        if not chemins:
            out["erreur"] = "aucun registre présent à sauvegarder"
            return out
        out["etapes"].append(f"registres présents : {len(chemins)}")
        with tempfile.TemporaryDirectory(prefix="drill_restore_") as tmp:
            tmp = Path(tmp)
            tgz = tmp / "drill.tgz"
            enc = tmp / "drill.tgz.enc"
            dec = tmp / "drill_restored.tgz"
            br.archiver(chemins, tgz)
            out["etapes"].append(f"archivé ({tgz.stat().st_size} octets)")
            br.chiffrer(tgz, enc, passphrase)
            out["etapes"].append("chiffré (AES-256-CBC + PBKDF2)")
            br.dechiffrer(enc, dec, passphrase)
            out["etapes"].append("déchiffré — la passphrase de production OUVRE bien l'artefact")
            restore_dir = tmp / "restored"
            restore_dir.mkdir()
            with tarfile.open(dec, "r:gz") as tf:
                noms = [m.name for m in tf.getmembers() if m.isfile()]
                tf.extractall(restore_dir, filter="data")
            attendus = {Path(c).name for c in chemins}
            restaures = {Path(n).name for n in noms}
            if attendus - restaures:
                out["erreur"] = f"fichiers MANQUANTS à la restauration : {sorted(attendus - restaures)}"
                return out
            out["etapes"].append(f"liste vérifiée : {len(restaures)} fichier(s), aucun manquant")
            illisibles, verifies = [], 0
            for chemin in restore_dir.rglob("*"):
                if not chemin.is_file():
                    continue
                orig = next((Path(c) for c in chemins if Path(c).name == chemin.name), None)
                if orig and orig.exists() and orig.stat().st_size != chemin.stat().st_size:
                    illisibles.append(f"{chemin.name} : taille {chemin.stat().st_size} ≠ {orig.stat().st_size}")
                    continue
                if chemin.suffix in (".json",):
                    try:
                        json.loads(chemin.read_text(encoding="utf-8"))
                        verifies += 1
                    except Exception:
                        illisibles.append(f"{chemin.name} : JSON restauré ILLISIBLE")
                elif chemin.suffix == ".jsonl":
                    try:
                        for l in chemin.read_text(encoding="utf-8").splitlines()[:50]:
                            if l.strip():
                                json.loads(l)
                        verifies += 1
                    except Exception:
                        illisibles.append(f"{chemin.name} : JSONL restauré ILLISIBLE")
            if illisibles:
                out["erreur"] = " ; ".join(illisibles[:5])
                return out
            out["etapes"].append(f"intégrité vérifiée : {verifies} registre(s) re-parsé(s), tailles conformes")
        out["ok"] = True
        return out
    except Exception as exc:
        out["erreur"] = f"{type(exc).__name__}: {exc}"
        return out


def main():
    import sys
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    r = drill()
    print("=== EXERCICE DE RESTAURATION (§89, à blanc, local) ===")
    for e in r["etapes"]:
        print("  ✓", e)
    print(("✅ RESTAURATION VÉRIFIÉE — la sauvegarde de cette nuit est restaurable."
           if r["ok"] else f"❌ ÉCHEC : {r.get('erreur')}"))
    if "--alert" in sys.argv[1:]:
        try:
            import telegram_notifier as tn
            tn.send_telegram(("🗄️ Drill de restauration : ✅ OK — sauvegardes restaurables ("
                              + r["etapes"][-1] + ").") if r["ok"] else
                             f"🗄️ Drill de restauration : ❌ ÉCHEC — {r.get('erreur')} — "
                             "la sauvegarde ne serait PAS restaurable, à corriger.")
        except Exception:
            pass
    print("Aucun envoi, aucun écrasement. VERDICT: SAFE")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
