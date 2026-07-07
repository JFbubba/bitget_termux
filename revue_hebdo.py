"""
revue_hebdo.py — REVUE HEBDOMADAIRE automatique du bot (lecture seule + envoi Telegram).

Classement : SAFE. Aucun ordre, aucune écriture d'état de trading. Compile les
journaux posés à l'audit (§46) en UN rapport de décision hebdomadaire : c'est le
matériau de la revue J+14 — l'humain décide (caps, débrayages), le bot mesure.

Sections :
  • ACCUMULATION : achats 7 j, prix de revient réel, PnL latent, et l'AVANTAGE
    COST-BASIS RÉEL vs un DCA plat sur les mêmes jours (la métrique honnête de
    §38/§44 — mesurée sur les fills réels, plus sur un backtest) ;
  • FUTURES : equity + delta 7 j, PnL réalisé NET du bot, activité des boucles
    (décisions, ouvertures/fermetures) et DISTRIBUTION du consensus (les seuils
    0.35/0.15 se jugent sur cette distribution, §45) ;
  • CARRY : répartition ATTRACTIF/NEUTRE/NEGATIF sur la semaine, APR médian ;
  • CERVEAU : bornes des poids (alerte saturation), fraîcheur de la validation ;
  • RUNWAY : USDT spot libre + autonomie estimée du DCA.

CLI : python revue_hebdo.py [--send]   (--send = pousse aussi sur Telegram ;
      le timer systemd hebdomadaire l'utilise ; /revue affiche sans --send)
"""

import json
import statistics
import time
from pathlib import Path

from config_utils import cfg as _cfg
from numeric_utils import safe_float

ROOT = Path(__file__).resolve().parent
SEMAINE_S = 7 * 86400


# ---------- cœurs purs (testables) ----------

def stats_consensus(entries, seuil_entree=0.35, depuis_ts=None):
    """PUR. Distribution du |consensus| des cycles journalisés (boucle auto_dir) :
    n, médiane, p90, max, % de cycles au-dessus du seuil d'entrée. Les seuils se
    jugent sur CETTE distribution, pas sur une intuition."""
    vals = []
    for e in entries or []:
        if not isinstance(e, dict) or e.get("boucle") not in (None, "auto_dir"):
            continue
        if depuis_ts is not None and (safe_float(e.get("ts")) or 0) < depuis_ts:
            continue
        c = safe_float(e.get("consensus"))
        if c is not None:
            vals.append(abs(c))
    if not vals:
        return {"n": 0}
    vals.sort()
    return {"n": len(vals),
            "p50": round(statistics.median(vals), 3),
            "p90": round(vals[max(0, int(len(vals) * 0.9) - 1)], 3),
            "max": round(vals[-1], 3),
            "pct_seuil": round(100.0 * sum(1 for v in vals if v >= seuil_entree) / len(vals), 1)}


def stats_actions(entries, depuis_ts=None):
    """PUR. Compte les décisions par (boucle, action) sur la fenêtre."""
    out = {}
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        if depuis_ts is not None and (safe_float(e.get("ts")) or 0) < depuis_ts:
            continue
        k = f"{e.get('boucle', 'auto_dir')}:{e.get('action', '?')}"
        out[k] = out.get(k, 0) + 1
    return out


def stats_carry(journal, depuis_ts=None, symbol="BTCUSDT"):
    """PUR. Répartition des attraits carry du symbole sur la fenêtre + APR médian."""
    comptes, aprs = {}, []
    for entry in journal or []:
        if not isinstance(entry, dict):
            continue
        if depuis_ts is not None and (safe_float(entry.get("ts")) or 0) < depuis_ts:
            continue
        for r in entry.get("resultats") or []:
            if isinstance(r, dict) and str(r.get("symbol", "")).upper() == symbol:
                a = str(r.get("attrait", "?"))
                comptes[a] = comptes.get(a, 0) + 1
                v = safe_float(r.get("apr_net_pct"))
                if v is not None:
                    aprs.append(v)
    return {"comptes": comptes,
            "apr_median": round(statistics.median(aprs), 2) if aprs else None}


def runway_jours(libre, montants_recents, defaut_jour=3.0):
    """PUR. Autonomie estimée du DCA : USDT libre / dépense quotidienne moyenne
    (moyenne des derniers achats réels, repli sur defaut_jour)."""
    libre = safe_float(libre)
    if libre is None or libre <= 0:
        return None
    ms = [safe_float(m) for m in (montants_recents or [])]
    ms = [m for m in ms if m and m > 0]
    par_jour = (sum(ms) / len(ms)) if ms else float(defaut_jour)
    return round(libre / par_jour, 1) if par_jour > 0 else None


def avantage_reel_vs_plat(paires):
    """PUR. Avantage cost-basis RÉEL vs DCA plat sur les MÊMES jours/prix, calculé
    sur les fills appariés (accum_reconcile). C'est la matérialisation — ou non —
    de l'edge de sizing §38/§44 en production. None si < 3 achats (pas de sens)."""
    if not paires or len(paires) < 3:
        return None
    try:
        import accum_backtest as ab
        montants = [p["fill"]["amount_usdt"] for p in paires]
        prix = [p["fill"]["price_avg"] for p in paires]
        adv = ab.avantage_pct(montants, prix)
        return round(adv, 4) if adv is not None else None
    except Exception:
        return None


def concentration_futures(trips):
    """PUR (re-mesure §97). L'edge directionnel tient-il sur UN SEUL trade ? Mesure la
    part du plus gros gagnant dans le PnL total, le PnL SANS lui, et les symboles
    NET-perdants (le cœur qui saigne les frais). trips : [{symbol, pnl_usdt, ...}].
    {} si aucun trip. part_top = None si le PnL total est ≤ 0 (part non définie)."""
    pnls = [(str(t.get("symbol") or "?"), safe_float(t.get("pnl_usdt")) or 0.0)
            for t in (trips or [])]
    if not pnls:
        return {}
    total = round(sum(p for _, p in pnls), 4)
    top_sym, top_pnl = max(pnls, key=lambda x: x[1])
    par_sym = {}
    for s, p in pnls:
        par_sym[s] = round(par_sym.get(s, 0.0) + p, 4)
    negatifs = {s: v for s, v in par_sym.items() if v < 0}
    part_top = round(top_pnl / total, 3) if total > 1e-9 and top_pnl > 0 else None
    return {"n": len(pnls), "pnl_total": total,
            "top": {"symbol": top_sym, "pnl": round(top_pnl, 4)},
            "part_top": part_top, "pnl_sans_top": round(total - top_pnl, 4),
            "symboles_negatifs": negatifs}


# ---------- collecte (lecture seule, best-effort) ----------

def collecter(now=None):
    now = time.time() if now is None else now
    depuis = now - SEMAINE_S
    out = {"ts": int(now)}

    # accumulation : reconcile + achats 7 j + avantage réel vs plat
    try:
        import accum_reconcile as ar
        import spot_executor as se
        rec = ar.snapshot()
        out["accum"] = {k: rec.get(k) for k in ("cost_basis", "pnl_latent_pct",
                                                "btc_achete", "usdt_depense",
                                                "n_apparies", "ok", "anomalies")}
        buys = se._load_real().get("buys", [])
        recents = [b for b in buys if (safe_float(b.get("ts")) or 0) >= depuis]
        out["accum"]["n_achats_7j"] = len(recents)
        out["accum"]["usdt_7j"] = round(sum(safe_float(b.get("amount_usdt")) or 0
                                            for b in recents), 2)
        groupes = ar.group_fills(ar.fetch_fills())
        paires, _, _ = ar.match_buys(buys, groupes)
        out["accum"]["avantage_vs_plat_pct"] = avantage_reel_vs_plat(paires)
        out["accum"]["montants_recents"] = [safe_float(b.get("amount_usdt"))
                                            for b in buys[-7:]]
    except Exception:
        out["accum"] = {}

    # futures : equity/PnL + activité des boucles + distribution du consensus
    try:
        import futures_report as fr
        s = fr.snapshot()
        out["futures"] = {"equity": s.get("equity_usdt"),
                          "delta7_pct": s.get("equity_7j_delta_pct"),
                          "fills_bot": s.get("fills_bot"),
                          "funding": s.get("funding"),
                          "events": s.get("events")}
    except Exception:
        out["futures"] = {}
    try:
        import journal_append as ja
        dec = ja.read_jsonl(ROOT / "futures_auto_journal.jsonl")
        out["decisions"] = stats_actions(dec, depuis_ts=depuis)
        out["consensus"] = stats_consensus(dec, seuil_entree=float(
            _cfg("FUTURES_AUTO_SEUIL_ENTREE", 0.35)), depuis_ts=depuis)
    except Exception:
        out["decisions"], out["consensus"] = {}, {}

    # forensique futures : concentration du PnL (re-mesure §97 — l'edge tient-il sur 1 trade ?)
    try:
        import trade_forensics as tf
        out["forensics"] = concentration_futures((tf.snapshot(168) or {}).get("trips") or [])
    except Exception:
        out["forensics"] = {}

    # mémoire de situations : LA LIRE en la mesurant (§97 — le « read » qui manquait)
    try:
        import situation_memory as sm
        out["situations"] = sm.evaluate()
    except Exception:
        out["situations"] = {}

    # carry : répartition sur la semaine
    try:
        import carry_monitor as cm
        journal = json.loads(cm.JOURNAL_FILE.read_text(encoding="utf-8"))
        out["carry"] = stats_carry(journal, depuis_ts=depuis)
    except Exception:
        out["carry"] = {}

    # cerveau : bornes des poids + fraîcheur validation
    try:
        import swarm_brain as sb
        w = sb.load_weights()
        hi = max(w, key=w.get)
        lo = min(w, key=w.get)
        out["cerveau"] = {"poids_max": (hi, w[hi]), "poids_min": (lo, w[lo]),
                          "saturation": w[hi] >= 2.7}
        import edge_ladder as el
        rep = el._load()
        out["cerveau"]["validation_age_h"] = round(
            (now - (safe_float(rep.get("generated_at")) or now)) / 3600.0, 1)
        out["cerveau"]["ranking_mode"] = rep.get("ranking_mode")
    except Exception:
        out["cerveau"] = {}

    # runway spot
    try:
        import spot_executor as se
        libre = se._spot_free_usdt()
        out["runway"] = {"libre": round(libre, 2) if libre is not None else None,
                         "jours": runway_jours(libre,
                                               (out.get("accum") or {}).get("montants_recents"))}
    except Exception:
        out["runway"] = {}
    # portefeuille : total + exposition BTC (couverture carry)
    try:
        import portefeuille as pf
        inv = pf.inventaire()
        out["portefeuille"] = {"total": inv.get("total_usdt"),
                               "expo_btc": inv.get("expo_btc_usdt"),
                               "n_actifs": len(inv.get("actifs", [])),
                               "poussiere": inv.get("poussiere_usdt")}
    except Exception:
        out["portefeuille"] = {}
    return out


def recommandations(d):
    """PUR (§60, gouvernance). Recommandations CHIFFRÉES à partir des données de
    la revue — le matériau de décision, l'humain tranche. Déclencheurs :
      • espérance directionnelle réelle négative avec n >= 30 -> proposer de
        refermer la porte d'edge (FUTURES_EDGE_GATE_OVERRIDE=0) ou durcir le
        seuil d'entrée ;
      • agent au palier LIVE en attente -> le signaler ;
      • exécution propre 30 j (aucun échec d'ordre) -> rappeler que la montée
        des caps par paliers est prévue par §45 (décision propriétaire)."""
    recs = []
    fb = (d.get("futures") or {}).get("fills_bot") or {}
    n, net = fb.get("n_fills", 0) or 0, fb.get("net_usdt")
    if n >= 30 and net is not None and net < 0:
        recs.append(f"⚠️ Espérance directionnelle RÉELLE négative ({net:+.4f} $ sur "
                    f"{n} fills) : envisager FUTURES_EDGE_GATE_OVERRIDE=0 ou seuil "
                    "d'entrée plus dur (0.45).")
    elif n < 30:
        recs.append(f"Directionnel réel : {n}/30 fills — pas de verdict avant 30 "
                    "(discipline anti-conclusion-hâtive).")
    fo = d.get("forensics") or {}
    if fo.get("part_top") is not None and fo["part_top"] >= 0.5 and fo.get("n", 0) >= 5:
        recs.append(f"⚠️ Edge futures CONCENTRÉ : {fo['part_top'] * 100:.0f} % du PnL vient d'UN "
                    f"trade ({fo['top']['symbol']}) — sans lui {fo['pnl_sans_top']:+.4f} $ sur "
                    f"{fo['n']} trips. L'edge n'est pas prouvé (§97) : envisager "
                    "FUTURES_EDGE_GATE_OVERRIDE=0 tant qu'il tient sur 1-2 coups.")
    el = d.get("exit_lab") or {}
    pl = el.get("paper") or {}
    if pl.get("ratio_tp_sl") is not None and pl["ratio_tp_sl"] < 0.6:
        recs.append(f"Exit lab : ratio TP/SL paper {pl['ratio_tp_sl']} — le RR 2 "
                    "conventionnel mérite l'examen quand l'échantillon réel suffira.")
    si = d.get("situations") or {}
    if si.get("n") and (si.get("ic", 0) or 0) > 0 and (si.get("ic_t", 0) or 0) >= 2.0:
        recs.append(f"Mémoire situations : IC {si['ic']:+.4f} (t {si['ic_t']:+.1f}) sur {si['n']} obs "
                    "— devient prédictive ; CONFIRMER sur plusieurs semaines avant un overlay "
                    "ADVISORY gated OFF (mesure d'abord — jamais un branchement direct).")
    audit = (d.get("audit_live") or {}).get("agents") or []
    for r in audit[:3]:
        if (r.get("ic_t") or 0) >= 3.0:
            recs.append(f"Agent '{r['agent']}' : IC live {r['ic']:+.3f} (t {r['ic_t']:+.1f}) "
                        "— si le xs et le profond confirment, promotion à surveiller.")
    for r in audit:
        if (r.get("ic_t") or 0) <= -3.0:
            recs.append(f"⚠️ Agent '{r['agent']}' : IC live {r['ic']:+.3f} "
                        f"(t {r['ic_t']:+.1f}) — formulation à auditer (méthode §48-49).")
    return recs


def _n(v, motif="{:.2f}"):
    return motif.format(v) if isinstance(v, (int, float)) else "—"


def build_report(d=None):
    d = collecter() if d is None else d
    try:
        import exit_lab
        d.setdefault("exit_lab", exit_lab.snapshot())
    except Exception:
        pass
    try:
        import live_ic_audit
        d.setdefault("audit_live", live_ic_audit.snapshot())
    except Exception:
        pass
    a = d.get("accum") or {}
    f = d.get("futures") or {}
    fb = f.get("fills_bot") or {}
    c = d.get("consensus") or {}
    ca = d.get("carry") or {}
    br = d.get("cerveau") or {}
    rw = d.get("runway") or {}
    lignes = [
        "📊 REVUE HEBDO (auto) — matériau de décision, l'humain tranche",
        "",
        "— ACCUMULATION —",
        f"7 j : {a.get('n_achats_7j', 0)} achats · {_n(a.get('usdt_7j'))} $ · "
        f"cumul {_n(a.get('btc_achete'), '{:.8f}')} BTC",
        f"Prix de revient réel : {_n(a.get('cost_basis'))} $ · PnL latent "
        f"{_n(a.get('pnl_latent_pct'), '{:+.2f}')} %",
        f"Avantage sizing vs DCA plat (réel) : "
        f"{_n(a.get('avantage_vs_plat_pct'), '{:+.4f}')} %"
        + ("" if a.get("avantage_vs_plat_pct") is not None else " (< 3 achats appariés)"),
        "",
        "— FUTURES —",
        f"Equity : {_n(f.get('equity'))} $ · 7 j : {_n(f.get('delta7_pct'), '{:+.2f}')} %",
        f"PnL réalisé NET bot : {_n(fb.get('net_usdt'), '{:+.4f}')} $ "
        f"({fb.get('n_fills', 0)} fills, frais {_n(fb.get('frais_usdt'), '{:.4f}')} $)",
        (lambda fu: f"Funding net : {_n(fu.get('total_usdt'), '{:+.6f}')} $ "
                    f"({fu.get('n', 0)} règlements) — le revenu du carry"
         )(f.get("funding") or {}),
        f"Consensus 7 j : n={c.get('n', 0)} · |médiane| {_n(c.get('p50'))} · "
        f"p90 {_n(c.get('p90'))} · max {_n(c.get('max'))} · "
        f"≥ seuil : {_n(c.get('pct_seuil'), '{:.1f}')} % des cycles",
        f"Décisions 7 j : {d.get('decisions') or 'journal trop jeune'}",
        (lambda fo: ("\n— FORENSIQUE FUTURES (re-mesure §97 : l'edge tient-il ?) —\n"
                     f"{fo.get('n', 0)} round-trips · PnL {_n(fo.get('pnl_total'), '{:+.4f}')} $"
                     + (f" · dont {_n((fo.get('part_top') or 0) * 100, '{:.0f}')} % sur 1 trade "
                        f"({fo['top']['symbol']} {_n(fo['top']['pnl'], '{:+.3f}')} $)"
                        if fo.get("part_top") is not None else "")
                     + f"\nPnL SANS le meilleur : {_n(fo.get('pnl_sans_top'), '{:+.4f}')} $"
                     + (" · cœur négatif : " + ", ".join(
                         f"{s} {v:+.3f}$" for s, v in fo["symboles_negatifs"].items())
                        if fo.get("symboles_negatifs") else ""))
         if fo else "")(d.get("forensics") or {}),
        "",
        "— CARRY —",
        f"Répartition 7 j : {ca.get('comptes') or 'journal trop jeune'} · "
        f"APR médian {_n(ca.get('apr_median'))} %",
        "",
        "— CERVEAU / RUNWAY —",
        f"Poids : max {br.get('poids_max')} · min {br.get('poids_min')}"
        + (" ⚠ SATURATION (≥2.7 : le clamp masque l'apprentissage)" if br.get("saturation") else ""),
        f"Validation : {_n(br.get('validation_age_h'), '{:.1f}')} h "
        f"(mode {br.get('ranking_mode')})",
        f"Runway spot : {_n(rw.get('libre'))} $ libres ≈ {_n(rw.get('jours'), '{:.0f}')} jours de DCA",
        (lambda p: f"Portefeuille : {_n(p.get('total'))} $ ({p.get('n_actifs', 0)} actifs + "
                   f"{_n(p.get('poussiere'))} $ de poussière) · exposition BTC "
                   f"{_n(p.get('expo_btc'))} $ = couverture carry")(d.get("portefeuille") or {}),
        "",
        "Lecture seule. Décisions (caps, débrayages) = propriétaire. VERDICT: SAFE",
    ]
    el = d.get("exit_lab") or {}
    if el:
        pl, rl = el.get("paper") or {}, el.get("reels") or {}
        lignes += ["", "— EXIT LAB (sorties, advisory §60) —",
                   f"paper : n {pl.get('n', 0)} · WR {_n(pl.get('wr_pct'))}% · "
                   f"ratio TP/SL {_n(pl.get('ratio_tp_sl'), '{:.3f}')}",
                   f"réel : {rl.get('note', 'n/a')}"]
    audit = (d.get("audit_live") or {}).get("agents") or []
    if audit:
        try:
            from live_ic_audit import _signe_divergent as _sd
        except Exception:
            _sd = lambda r: False
        lignes += ["", "— AUDIT IC LIVE (1 h, votes émis §60 ; rank + pearson §96) —"]
        for r in audit[:5]:
            pic = r.get("pic")
            pbloc = f" · pearson {pic:+.4f}" if pic is not None else ""
            flag = "  ⚠ signes opposés (poids suit pearson)" if _sd(r) else ""
            lignes.append(f"{r['agent']:<12} rank {r['ic']:+.4f} (t {r['ic_t']:+.2f}){pbloc}{flag}")
    si = d.get("situations") or {}
    if si.get("n"):
        ic, ict = si.get("ic", 0) or 0, si.get("ic_t", 0) or 0
        verdict = (" — IC positif SIGNIFICATIF : à confirmer sur plusieurs semaines (jamais armer sur 1)"
                   if ic > 0 and ict >= 2.0 else " — aucun edge -> NON branchée dans la décision (correct)")
        lignes += ["", "— MÉMOIRE SITUATIONS (advisory, mesurée §97 ; verdict = IC régime-neutre) —",
                   f"n {si['n']} · IC hint→résultat {_n(ic, '{:+.4f}')} (t {_n(ict, '{:+.2f}')}) · "
                   f"hit {_n(si.get('hit_rate'), '{:.3f}')} vs base {_n(si.get('base_rate'), '{:.3f}')}"
                   + verdict]
    recs = recommandations(d)
    if recs:
        lignes += ["", "— RECOMMANDATIONS (données -> décision propriétaire) —"]
        lignes += [f"• {r}" for r in recs]
    return "\n".join(lignes)


def main():
    import sys
    rapport = build_report()
    print(rapport)
    if "--send" in sys.argv[1:]:
        try:
            import telegram_notifier as tn
            tn.send_telegram(rapport)
            print("(envoyé sur Telegram)")
        except Exception as exc:
            print(f"(envoi Telegram impossible : {type(exc).__name__})")


if __name__ == "__main__":
    main()
