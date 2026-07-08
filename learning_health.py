"""
learning_health.py — moniteur de SANTÉ de la boucle d'apprentissage (§68). SAFE, lecture seule.

La boucle EARCP « apprend » chaque minute, mais son signal de base (hit-rate) est
DÉCORRÉLÉ de la prédictivité réelle (IC live) — corrélation de rang ~0, parfois
inversée. Le correctif IC-align (§68) réaligne la cible sur l'IC. Ce moniteur VÉRIFIE
que le correctif tient : il mesure la corrélation de rang entre les POIDS APPRIS et
l'IC live. Si elle décroche (les poids n'anticipent plus la prédictivité), il ALERTE
(Telegram, best-effort). Il rapporte aussi la décorrélation hit-rate↔IC (cause racine).

Aucun ordre, aucune écriture d'état de trading (seul un fichier de déduplication
d'ALERTES est écrit — `.learning_health_alert_state.json`, gitignored).
CLI : python learning_health.py [--alert]
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORR_MIN = 0.2          # sous ce seuil, les poids n'anticipent plus l'IC -> alerte
ETAT_ALERTE = ROOT / ".learning_health_alert_state.json"
RAPPEL_S = 24 * 3600    # une tension §96 peut persister des JOURS : rappel au plus 1×/jour


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


def overweight_negatifs(weights, pic, seuil_poids=1.0, t_max=-2.0):
    """PUR. Garde NON-CIRCULAIRE (§96) : liste des agents SUR-pondérés (poids > seuil,
    au-dessus de la moyenne ~1) ET significativement NÉGATIFS dans la métrique qui pilote
    le SIZING — le PEARSON IC (t ≤ t_max). weights : {agent: poids} ; pic : {agent:
    (pearson_ic, pearson_t)}. On utilise le PEARSON, pas le Rank IC (qui diffère de signe
    pour ~5 agents, §96), car c'est lui que la cible ridge optimise. Triés du plus négatif."""
    sus = []
    for k, w in (weights or {}).items():
        p, pt = (pic or {}).get(k, (None, None))
        if w is not None and w > seuil_poids and p is not None and pt is not None and pt <= t_max:
            sus.append({"agent": k, "poids": round(float(w), 2),
                        "pearson_ic": round(float(p), 4), "pearson_t": round(float(pt), 1)})
    sus.sort(key=lambda s: s["pearson_t"])
    return sus


def snapshot():
    """État de santé de l'apprentissage. LECTURE SEULE.
      - corr_weight_ic : corrélation de rang POIDS APPRIS ↔ IC live (doit être POSITIVE) ;
      - corr_hitrate_ic : corrélation hit-rate ↔ IC (cause racine, ~0 = signal cassé) ;
      - ic_align : le correctif est-il armé ? ; healthy : corr_weight_ic ≥ seuil."""
    _load_env()
    out = {"corr_weight_ic": None, "corr_hitrate_ic": None, "ic_align": None,
           "healthy": None, "n_agents": 0, "note": "", "overweight_negatifs": []}
    try:
        import live_ic_audit as lia
        agents = lia.snapshot(3600).get("agents", [])
        ic = {a["agent"]: a["ic"] for a in agents if a.get("ic") is not None}
        # §96 : Pearson IC (pondéré-magnitude ≈ PnL) par agent — base de la garde NON-circulaire.
        pic = {a["agent"]: (a.get("pic"), a.get("pic_t")) for a in agents if a.get("pic") is not None}
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
    # §82 : quand la cible RIDGE (§78) est armée, les poids DIVERGENT de l'IC individuel
    # PAR CONSTRUCTION (le ridge pénalise la redondance corrélée : sentiment/macro
    # descendent malgré leur IC). L'alignement se juge alors contre la CIBLE ACTIVE
    # (les mults ridge) — sinon le moniteur crie au décrochage précisément quand le
    # mécanisme fonctionne. Repli : cible IC (comportement historique).
    out["cible"] = "ic"
    out["corr_weight_cible"] = out["corr_weight_ic"]
    rv = (os.getenv("BRAIN_RIDGE_ALIGN") or "").strip().lower()
    if rv in ("1", "true", "on", "yes"):
        try:
            import swarm_brain as sb2
            mults = {k: v for k, v in (sb2._ridge_mults() or {}).items() if k in weights}
            if len(mults) >= 3:
                out["cible"] = "ridge"
                out["corr_weight_cible"] = rank_corr(weights, mults)
        except Exception:
            pass
    # §96 : GARDE NON-CIRCULAIRE. Le corr poids↔cible ci-dessus est CIRCULAIRE quand
    # RIDGE_ALIGN=1 (les poids DÉRIVENT de la cible ridge -> corr +0.74 « SAIN » garanti,
    # même si le banc sur-pondère un agent perdant). Contrôle indépendant : aucun agent
    # SUR-pondéré (poids > 1, au-dessus de la moyenne ~1) ne doit être significativement
    # NÉGATIF dans la métrique qui pilote le SIZING — le PEARSON IC (≈ PnL), PAS le Rank IC
    # (qui diffère de signe pour ~5 agents, §96 : l'utiliser ici crierait à tort sur
    # technicals dont le pearson est +0.03). t ≤ −2 = significatif sur l'échantillon courant.
    suspects = overweight_negatifs(weights, pic)
    out["overweight_negatifs"] = suspects

    cw = out["corr_weight_cible"]
    aligne = (cw is not None and cw >= CORR_MIN)
    out["healthy"] = bool(aligne and not suspects)       # les DEUX gardes doivent passer
    if suspects:                                         # priorité : la fuite d'edge réelle
        noms = ", ".join(f"{s['agent']} (poids {s['poids']}, pearsonIC {s['pearson_ic']:+.3f} "
                         f"t {s['pearson_t']:+.1f})" for s in suspects)
        out["note"] = ("ALERTE : agent(s) SUR-pondéré(s) NÉGATIF(s) en pearsonIC (métrique de "
                       f"sizing, §96) — {noms}. La corr poids↔cible {out['cible'].upper()} "
                       f"({cw:+.2f}) ne le voit pas (circulaire).")
    elif cw is None:
        out["note"] = "corrélation non calculable (données insuffisantes)"
    elif aligne:
        out["note"] = (f"poids alignés sur la cible {out['cible'].upper()} (corr {cw:+.2f}) ; "
                       "garde pearson OK (aucun sur-poids négatif)")
    else:
        out["note"] = (f"ALERTE : poids DÉSALIGNÉS de la cible {out['cible'].upper()} "
                       f"(corr {cw:+.2f} < {CORR_MIN}) — le correctif ne compense pas"
                       + ("" if out["ic_align"] else " (BRAIN_IC_ALIGN est OFF !)"))
    return out


def _signature(s):
    """PUR. Signature stable de l'état de santé : santé globale + agents signalés
    par la garde §96 (les valeurs chiffrées fluctuent, la LISTE fait l'état)."""
    return {"healthy": bool(s.get("healthy")),
            "agents": sorted(x["agent"] for x in (s.get("overweight_negatifs") or []))}


def _decision_alerte(sig, precedent, now):
    """PUR. (envoyer, motif) — la garde §96 peut rester tendue des JOURS sur un
    désaccord légitime (marginal vs multivarié) : marteler le même message toutes
    les 6 h fabrique de la fatigue d'alarme. On alerte au CHANGEMENT d'état
    (nouvel état malsain, liste d'agents modifiée, rétablissement — une fois),
    avec un rappel au plus quotidien tant que l'alerte persiste inchangée."""
    if precedent is None:
        return ((not sig["healthy"]), "nouvel état")
    if sig != precedent.get("sig"):
        return (True, "rétabli" if sig["healthy"] else "changement")
    if not sig["healthy"] and now - float(precedent.get("ts", 0)) >= RAPPEL_S:
        return (True, "rappel quotidien")
    return (False, "")


def check_and_alert():
    """Calcule la santé et ALERTE Telegram sur CHANGEMENT d'état (voir
    _decision_alerte). Retourne le snapshot. Fail-safe : ne lève jamais ;
    l'état de déduplication n'est écrit qu'après un envoi réussi (un envoi
    raté sera retenté au prochain passage)."""
    import time
    s = snapshot()
    sig = _signature(s)
    precedent = None
    try:
        precedent = json.loads(ETAT_ALERTE.read_text(encoding="utf-8"))
    except Exception:
        pass
    envoyer, motif = _decision_alerte(sig, precedent, time.time())
    if envoyer:
        try:
            import telegram_notifier as tn
            if sig["healthy"]:
                tn.send_message(
                    "✅ SANTÉ APPRENTISSAGE rétablie — garde §96 OK, "
                    f"corr poids↔cible {s.get('corr_weight_cible')} ({s.get('cible')})")
            else:
                sus = s.get("overweight_negatifs") or []
                ligne_sus = ("\n· ⚠ sur-poids négatifs (pearson) : "
                             + ", ".join(f"{x['agent']} {x['poids']}/{x['pearson_ic']:+.3f}" for x in sus)
                             if sus else "")
                tn.send_message(
                    f"⚠️ SANTÉ APPRENTISSAGE ({motif}) — " + s["note"]
                    + f"\n· corr poids↔cible {s.get('corr_weight_cible')} ({s.get('cible')})"
                    + f"\n· corr hit-rate↔IC {s['corr_hitrate_ic']} (cause racine)"
                    + f"\n· IC-align {'ARMÉ' if s['ic_align'] else 'OFF'}"
                    + ligne_sus)
            ETAT_ALERTE.write_text(json.dumps({"sig": sig, "ts": time.time()}),
                                   encoding="utf-8")
        except Exception:
            pass
    return s


def _check_xs_promotion(alert=False):
    """§82 : alerte UNE fois quand le labo long-short neutre franchit sa barre de
    promotion (la promotion effective reste une décision propriétaire)."""
    from pathlib import Path as _P
    flag = _P(__file__).resolve().parent / ".xs_promotion_alerted"
    try:
        import xs_paper
        st = xs_paper.promotion_status()
    except Exception:
        return None
    if st.get("qualifie") and alert and not flag.exists():
        try:
            import telegram_notifier as tn
            tn.send_telegram(f"🎓 Labo xs long-short QUALIFIÉ pour le réel borné : "
                             f"{st['jours']} j · {st['rebalances']} rebal · PnL fictif "
                             f"{st['pnl_usdt']} $. La promotion reste une décision "
                             "propriétaire (rien ne s'arme tout seul).")
            flag.touch()
        except Exception:
            pass
    return st


def main():
    import sys
    _xs = _check_xs_promotion(alert=("--alert" in sys.argv[1:]))
    if _xs is not None:
        q = "QUALIFIÉ" if _xs.get("qualifie") else "en cours"
        print(f"labo xs : {q} — {_xs.get('jours')} j · {_xs.get('rebalances')} rebal · "
              f"PnL {_xs.get('pnl_usdt')} $ (barre {_xs.get('barre')})")
    import sys
    s = check_and_alert() if "--alert" in sys.argv else snapshot()
    print("=== SANTÉ DE L'APPRENTISSAGE (§68, lecture seule) ===")
    print(f"corr POIDS ↔ cible {str(s.get('cible','ic')).upper():5s}: {s.get('corr_weight_cible')}  (doit être ≥ {CORR_MIN})")
    print(f"  dont corr poids ↔ IC : {s['corr_weight_ic']}  ·  corr hit-rate ↔ IC {s['corr_hitrate_ic']}  (~0 = EARCP de base cassé)")
    print(f"IC-align (correctif)   : {'ARMÉ' if s['ic_align'] else 'OFF'}  ·  agents {s['n_agents']}")
    sus = s.get("overweight_negatifs") or []
    print("garde pearson (§96)    : " + ("OK — aucun sur-poids négatif dans la métrique de sizing"
          if not sus else "⚠ ALERTE — " + ", ".join(
              f"{x['agent']} (poids {x['poids']}, pearsonIC {x['pearson_ic']:+.3f} t {x['pearson_t']:+.1f})"
              for x in sus)))
    print(f"Verdict : {'SAIN' if s['healthy'] else 'ALERTE'} — {s['note']}")
    print("Lecture seule. Aucun ordre. VERDICT: SAFE")


if __name__ == "__main__":
    main()
