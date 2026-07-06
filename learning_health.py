"""
learning_health.py — moniteur de SANTÉ de la boucle d'apprentissage (§68). SAFE, lecture seule.

La boucle EARCP « apprend » chaque minute, mais son signal de base (hit-rate) est
DÉCORRÉLÉ de la prédictivité réelle (IC live) — corrélation de rang ~0, parfois
inversée. Le correctif IC-align (§68) réaligne la cible sur l'IC. Ce moniteur VÉRIFIE
que le correctif tient : il mesure la corrélation de rang entre les POIDS APPRIS et
l'IC live. Si elle décroche (les poids n'anticipent plus la prédictivité), il ALERTE
(Telegram, best-effort). Il rapporte aussi la décorrélation hit-rate↔IC (cause racine).

Aucun ordre, aucune écriture d'état de trading. CLI : python learning_health.py [--alert]
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORR_MIN = 0.2          # sous ce seuil, les poids n'anticipent plus l'IC -> alerte


def _load_env():
    """Charge le fichier d'environnement (le service systemd n'a pas d'EnvironmentFile)
    pour refléter l'état LIVE des verrous (BRAIN_IC_ALIGN, ...). Best-effort."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass


def rank_corr(a, b):
    """Corrélation de rang de Spearman entre deux dicts {clé: valeur}, sur les clés
    communes. PUR. None si < 3 clés communes."""
    common = [k for k in a if k in b and a[k] is not None and b[k] is not None]
    n = len(common)
    if n < 3:
        return None
    ra = {k: i for i, k in enumerate(sorted(common, key=lambda k: a[k]))}
    rb = {k: i for i, k in enumerate(sorted(common, key=lambda k: b[k]))}
    dsq = sum((ra[k] - rb[k]) ** 2 for k in common)
    return round(1.0 - 6.0 * dsq / (n * (n * n - 1)), 3)


def snapshot():
    """État de santé de l'apprentissage. LECTURE SEULE.
      - corr_weight_ic : corrélation de rang POIDS APPRIS ↔ IC live (doit être POSITIVE) ;
      - corr_hitrate_ic : corrélation hit-rate ↔ IC (cause racine, ~0 = signal cassé) ;
      - ic_align : le correctif est-il armé ? ; healthy : corr_weight_ic ≥ seuil."""
    _load_env()
    out = {"corr_weight_ic": None, "corr_hitrate_ic": None, "ic_align": None,
           "healthy": None, "n_agents": 0, "note": ""}
    try:
        import live_ic_audit as lia
        ic = {a["agent"]: a["ic"] for a in lia.snapshot(3600).get("agents", []) if a.get("ic") is not None}
    except Exception:
        out["note"] = "IC live indisponible"
        return out
    import os
    try:
        import swarm_brain as sb
        weights = {k: v for k, v in sb.load_weights().items() if k in ic}
    except Exception:
        out["note"] = "poids indisponibles"
        return out
    v = (os.getenv("BRAIN_IC_ALIGN") or "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        out["ic_align"] = True
    elif v in ("0", "false", "off", "no"):
        out["ic_align"] = False
    else:                                       # ni env : lit le défaut config
        try:
            from config_utils import cfg
            out["ic_align"] = bool(cfg("BRAIN_IC_ALIGN", 0))
        except Exception:
            out["ic_align"] = None
    hr = {}
    try:
        hr = {k: v for k, v in json.loads((ROOT / "brain_hitrates.json").read_text()).items() if k in ic}
    except Exception:
        pass
    out["corr_weight_ic"] = rank_corr(weights, ic)
    out["corr_hitrate_ic"] = rank_corr(hr, ic) if hr else None
    out["n_agents"] = len(weights)
    cw = out["corr_weight_ic"]
    out["healthy"] = (cw is not None and cw >= CORR_MIN)
    if cw is None:
        out["note"] = "corrélation non calculable (données insuffisantes)"
    elif out["healthy"]:
        out["note"] = f"poids alignés sur l'IC (corr {cw:+.2f})"
    else:
        out["note"] = (f"ALERTE : poids DÉSALIGNÉS de l'IC (corr {cw:+.2f} < {CORR_MIN}) — "
                       f"le correctif IC-align ne compense pas"
                       + ("" if out["ic_align"] else " (BRAIN_IC_ALIGN est OFF !)"))
    return out


def check_and_alert():
    """Calcule la santé et ALERTE Telegram si désaligné. Retourne le snapshot."""
    s = snapshot()
    if s.get("healthy") is False:
        try:
            import telegram_notifier as tn
            tn.send_message(
                "⚠️ SANTÉ APPRENTISSAGE — " + s["note"]
                + f"\n· corr poids↔IC {s['corr_weight_ic']}"
                + f"\n· corr hit-rate↔IC {s['corr_hitrate_ic']} (cause racine)"
                + f"\n· IC-align {'ARMÉ' if s['ic_align'] else 'OFF'}")
        except Exception:
            pass
    return s


def main():
    import sys
    s = check_and_alert() if "--alert" in sys.argv else snapshot()
    print("=== SANTÉ DE L'APPRENTISSAGE (§68, lecture seule) ===")
    print(f"corr POIDS APPRIS ↔ IC : {s['corr_weight_ic']}  (doit être ≥ {CORR_MIN})")
    print(f"corr hit-rate ↔ IC     : {s['corr_hitrate_ic']}  (~0 = signal EARCP de base cassé)")
    print(f"IC-align (correctif)   : {'ARMÉ' if s['ic_align'] else 'OFF'}  ·  agents {s['n_agents']}")
    print(f"Verdict : {'SAIN' if s['healthy'] else 'ALERTE'} — {s['note']}")
    print("Lecture seule. Aucun ordre. VERDICT: SAFE")


if __name__ == "__main__":
    main()
