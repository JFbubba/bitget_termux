"""
holdout_registry.py — registre d'USAGE du holdout profond (hygiène anti-contamination).

Classement : SAFE. Lecture/écriture d'UN JSON local borné (`holdout_usage.json`,
gitignoré). AUCUN ordre, aucun réseau, ne touche jamais au trading.

Pourquoi : le holdout PROFOND (candles_history 6 ans, porte §54 / replay_annuel) ne
devrait s'ouvrir qu'UNE fois par version de code — chaque consultation supplémentaire
de la MÊME version « dépense » le holdout : le verdict suivant est contaminé par ce
qu'on a appris à la consultation précédente (backtest overfitting, López de Prado).
Ce registre CONSIGNE chaque consultation et expose un drapeau `contamine` par
(quoi, version). PUREMENT OBSERVATIONNEL : aucun code ne le lit pour bloquer quoi que
ce soit — l'armer en porte serait un commit isolé.

Fail-safe ABSOLU : `consigner` ne lève JAMAIS (le registre ne doit jamais casser la
validation qui le consigne) ; `statut` rend {} sur toute erreur.

Chemin INJECTABLE (paramètre `chemin` ou env HOLDOUT_LEDGER) : un test n'écrit JAMAIS
dans le registre de production (ERR-019).

CLI (lecture seule) : python holdout_registry.py --status
"""

import json
import os
import time
from pathlib import Path

MAX_ENTREES = 500                                    # borne dure du journal (FIFO)


def _chemin(chemin=None):
    """Chemin du registre : paramètre > env HOLDOUT_LEDGER > défaut à côté du module."""
    if chemin:
        return Path(chemin)
    env = os.environ.get("HOLDOUT_LEDGER", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "holdout_usage.json"


def _version_git():
    """Commit court du dépôt, best-effort ('inconnue' si git indisponible)."""
    try:
        import subprocess
        res = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=str(Path(__file__).resolve().parent))
        v = (res.stdout or "").strip()
        return v if res.returncode == 0 and v else "inconnue"
    except Exception:
        return "inconnue"


def consigner(quoi, version=None, periode="", note="", chemin=None):
    """Appende {ts, quoi, version, periode, note} au registre (borné aux MAX_ENTREES
    dernières entrées, écriture atomique .tmp -> replace). version=None -> commit
    court git best-effort. NE LÈVE JAMAIS : retourne True si écrit, False sinon."""
    try:
        p = _chemin(chemin)
        try:
            entrees = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(entrees, list):
                entrees = []
        except Exception:
            entrees = []                              # registre absent/corrompu -> repart
        entrees.append({"ts": int(time.time()), "quoi": str(quoi),
                        "version": str(version) if version else _version_git(),
                        "periode": str(periode), "note": str(note)})
        entrees = entrees[-MAX_ENTREES:]
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(entrees, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception:
        return False                                  # best-effort : jamais bloquant


def statut(chemin=None):
    """Lit le registre et rend {(quoi, version): {"consultations": n, "contamine":
    bool, "dernier_ts": ts}}. contamine=True si la MÊME version a été consultée
    plus d'une fois (le holdout ne s'ouvre qu'une fois par version). Lecture seule,
    ne lève jamais ({} si registre absent/illisible)."""
    try:
        entrees = json.loads(_chemin(chemin).read_text(encoding="utf-8"))
        if not isinstance(entrees, list):
            return {}
    except Exception:
        return {}
    out = {}
    for e in entrees:
        try:
            cle = (str(e.get("quoi", "?")), str(e.get("version", "?")))
        except Exception:
            continue
        d = out.setdefault(cle, {"consultations": 0, "contamine": False, "dernier_ts": 0})
        d["consultations"] += 1
        d["contamine"] = d["consultations"] > 1
        try:
            d["dernier_ts"] = max(d["dernier_ts"], int(e.get("ts", 0) or 0))
        except (TypeError, ValueError):
            pass
    return out


def main():
    """CLI lecture seule : --status (défaut)."""
    st = statut()
    if not st:
        print("holdout_registry : aucun usage consigné. Lecture seule. VERDICT: SAFE")
        return
    print("=== REGISTRE D'USAGE DU HOLDOUT PROFOND (lecture seule) ===")
    for (quoi, version), d in sorted(st.items(), key=lambda kv: -kv[1]["dernier_ts"]):
        drapeau = ("⚠️ CONTAMINÉ (>1 consultation de cette version)"
                   if d["contamine"] else "ok (1 consultation)")
        quand = time.strftime("%Y-%m-%d %H:%M", time.gmtime(d["dernier_ts"]))
        print(f"  {quoi:<18} @{version:<10} consultations={d['consultations']:<3} "
              f"dernier={quand}Z  {drapeau}")
    print("Observationnel : aucun blocage, aucun ordre. VERDICT: SAFE")


if __name__ == "__main__":
    main()
