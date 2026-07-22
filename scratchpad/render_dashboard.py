#!/usr/bin/env python3
"""render_dashboard.py — instantané STATIQUE du dashboard MIROFISH pour un Artifact claude.ai.

Lit /api/state (lecture seule) et reconstruit un HTML autonome, CSP-safe (aucun fetch
dynamique, aucune ressource externe), thème clair + sombre, format FR, tabular-nums.

Fail-safe : si le fetch échoue, sort en code != 0 SANS écraser le HTML de sortie.

Usage :  python3 render_dashboard.py [sortie.html]
         (défaut : dashboard.html à côté du script)
"""
import html
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

URL = "http://127.0.0.1:8787/api/state?symbol=BTCUSDT&tf=5m"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")


# ----------------------------------------------------------------------------- utils
def fetch_state():
    req = urllib.request.Request(URL, headers={"User-Agent": "render_dashboard"})
    with urllib.request.urlopen(req, timeout=25) as r:
        payload = json.load(r)
    st = payload.get("state")
    if not isinstance(st, dict):
        raise ValueError("clé 'state' absente ou invalide")
    return st


def g(d, *path, default=None):
    """Accès imbriqué tolérant : g(d, 'a', 'b', default=0)."""
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def fr(x, dec=2):
    """Nombre au format FR : espace fine insécable pour les milliers, virgule décimale."""
    if x is None or x == "":
        return "—"
    try:
        s = f"{float(x):,.{dec}f}"
    except (TypeError, ValueError):
        return html.escape(str(x))
    return s.replace(",", " ").replace(".", ",")


def esc(x):
    return html.escape(str(x))


def when(iso):
    try:
        dt = datetime.fromisoformat(str(iso))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%d/%m/%Y · %H:%M UTC")
    except Exception:
        return esc(iso)


def hm(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%d/%m %H:%M")
    except Exception:
        return "—"


def pill(text, kind="neutral"):
    return f'<span class="pill {kind}">{esc(text)}</span>'


def kv(label, value, cls=""):
    return f'<div class="kv"><span class="k">{esc(label)}</span><span class="v {cls}">{value}</span></div>'


def panel(title, badge_html, body_html, span=""):
    return (
        f'<section class="panel {span}">'
        f'<header class="phead"><h2>{esc(title)}</h2>{badge_html}</header>'
        f'<div class="pbody">{body_html}</div>'
        f"</section>"
    )


def bar(frac, kind="accent"):
    frac = max(0.0, min(1.0, float(frac)))
    return f'<div class="bar"><span class="fill {kind}" style="width:{frac*100:.1f}%"></span></div>'


def sign_cls(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return ""
    return "pos" if x > 0 else ("neg" if x < 0 else "")


def _agents_dry_rows():
    """Mesures des agents DRY/ombre (best-effort, HORS /api/state — journaux locaux).
    Léger volontairement : l'IC complet des ombres reste dans live_ic_audit (99k entrées,
    trop lourd pour un render). AUCUN ordre, lecture seule."""
    import sys
    REPO = "/root/bitget_termux_repo"
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    # Le backbone de config.py charge .env dans os.environ dès l'import de `config` (via
    # nn_agent ci-dessous), donc la porte d'edge reflète le runtime ('deflated'), pas le
    # défaut config.py. Plus besoin de charger .env à la main ici (fix env↔config systémique).
    rows = []
    try:
        import nn_agent
        rows.append(kv("Porte d'edge", pill(nn_agent._gate_mode(), "accent")))
    except Exception:
        pass
    try:
        import json as _j
        import neural_net as _nn
        for fn, lab in (("neural_net_meta.json", "Voix NN (16ᵉ)"), ("qml_voice_weights.json", "Voix QML (18ᵉ)")):
            try:
                m = _j.load(open(REPO + "/" + fn))
                m = m.get("meta", m)
                d = _nn.edge_deflated(m, n_trials=30)
                parle = d is not None and d > 0
                rows.append(kv(lab, (pill("PARLE", "good") if parle else pill("muette", "neutral"))
                             + f' <small>edge {fr(d,3)}</small>'))
            except Exception:
                pass
    except Exception:
        pass
    try:
        import listing_hype as _lh
        rep = _lh.dry_report()
        nopen = len(_lh._load_positions())
        wr = rep.get("win_rate")
        rows.append(kv("Listing-hype DRY",
                       f'{rep.get("round_trips",0)} trips · win {fr(wr*100,0)+" %" if wr is not None else "—"} · '
                       f'net {fr(rep.get("pnl_net_usd",0),3)} $ · {nopen} ouv.',
                       sign_cls(rep.get("pnl_net_usd", 0))))
    except Exception:
        pass
    try:
        txt = open(REPO + "/.overlay_votes.jsonl", encoding="utf-8").read()
        c = {k: txt.count('"' + k + '"') for k in ("news_shadow", "qml_shadow", "nn_shadow")}
        rows.append(kv("Ombres (obs)", f'news {c["news_shadow"]} · qml {c["qml_shadow"]} · nn {c["nn_shadow"]}'))
        rows.append(kv("IC des ombres", pill("via live_ic_audit (dès 50 obs)", "neutral")))
    except Exception:
        pass
    return rows


# ----------------------------------------------------------------------------- build
def build(st):
    ts = when(g(st, "timestamp"))
    mode = esc(g(st, "mode", default="—"))

    kill = bool(g(st, "verrous", "kill_switch", default=False))
    kill_badge = pill("KILL-SWITCH ACTIF", "crit") if kill else pill("kill-switch OFF", "neutral")

    total = g(st, "portfolio", "total_usdt", default=0)

    # ---- KPI ----
    win = g(st, "stats", "win_rate", default=0)
    tp = g(st, "stats", "tp", default=0)
    sl = g(st, "stats", "sl", default=0)
    equity = g(st, "futures_live", "equity", default=0)
    stop_pct = g(st, "futures_live", "stop_pct", default=0)
    net_bot = g(st, "futures_live", "fills_bot", "net_usdt", default=0)
    n_fills = g(st, "futures_live", "fills_bot", "n_fills", default=0)
    consensus = g(st, "brain", "consensus", default=0)
    bias = g(st, "brain", "bias", default="—")
    accum_spent = g(st, "accumulation", "real_spent_usd", default=0)
    accum_n = g(st, "accumulation", "real_n_buys", default=0)
    spot_free = g(st, "accumulation", "spot_free_usdt", default=0)

    kpis = "".join([
        kpi("Patrimoine total", fr(total) + " <small>USDT</small>", "accent"),
        kpi("Equity futures", fr(equity) + " <small>USDT</small>", "", f"stop −{fr(stop_pct,0)}%"),
        kpi("Win rate", fr(win, 1) + " <small>%</small>", ("neg" if float(win or 0) < 50 else "pos"), f"{tp} TP / {sl} SL"),
        kpi("Consensus BTC", fr(consensus, 3), "", esc(bias)),
        kpi("PnL bot net", fr(net_bot) + " <small>USDT</small>", sign_cls(net_bot), f"{n_fills} fills"),
        kpi("Accumulation", fr(accum_spent) + " <small>$</small>", "accent", f"{accum_n} achats · {fr(spot_free,0)}$ libre"),
    ])

    panels = []

    # ---- Cerveau ----
    vol = g(st, "brain", "volatility", default={})
    cog = g(st, "brain", "cognition", default={})
    agents = sorted(g(st, "brain", "agents", default=[]) or [], key=lambda a: abs(a.get("vote", 0) * a.get("weight", 0)), reverse=True)
    inval = set(g(st, "brain", "invalidated", default=[]) or [])
    rows = [
        kv("Consensus", fr(consensus, 3)),
        kv("Biais", pill(bias, "accent" if bias not in ("NEUTRE", "—") else "neutral")),
        kv("Conviction ajustée", fr(g(st, "brain", "adjusted_conviction", default=0), 3)),
        kv("Régime vol.", pill(g(vol, "regime", default="—"), "warn" if g(vol, "regime") == "stressed" else "neutral") + f' <small>×{fr(g(vol,"ratio",default=1),2)}</small>'),
        kv("Entropie poids", fr(g(cog, "weight_entropy", default=0), 3)),
        kv("Accord / prudence", f'{fr(g(cog,"agreement",default=0),2)} / {fr(g(cog,"prudence",default=0),2)}'),
    ]
    ag_rows = ['<div class="agtbl">', '<div class="agh"><span>agent</span><span>vote</span><span>conf</span><span>poids</span></div>']
    for a in agents[:8]:
        nm = a.get("agent", "?")
        flag = ' <span class="inval">invalidé</span>' if nm in inval else ""
        ag_rows.append(
            f'<div class="agr"><span class="an">{esc(nm)}{flag}</span>'
            f'<span class="{sign_cls(a.get("vote"))}">{fr(a.get("vote"),2)}</span>'
            f'<span>{fr(a.get("conf"),2)}</span>'
            f'<span class="w">{fr(a.get("weight"),2)}</span></div>'
        )
    ag_rows.append("</div>")
    panels.append(panel("Cerveau · 14 agents", pill(g(st, "brain", "symbol", default="BTC"), "neutral"),
                        '<div class="kvs">' + "".join(rows) + "</div>" + "".join(ag_rows)))

    # ---- Orderflow (§orderflow, MESURE — non branché au banc) ----
    ofs = g(st, "orderflow_signals", default={})
    cvdf = g(ofs, "cvd_futures", default={}) or {}
    cvds = g(ofs, "cvd_spot", default={}) or {}
    div = g(ofs, "cvd_divergence", default={}) or {}
    fp = g(ofs, "footprint_poc", default={}) or {}
    lt = g(ofs, "large_trades", default={}) or {}
    ofliq = g(ofs, "liquidations", default={}) or {}
    posn = g(ofs, "positioning", default={}) or {}
    div_badge = pill("DIVERGENCE", "warn") if g(div, "diverge") else pill("alignés", "neutral")
    of_rows = [
        kv("CVD futures", fr(g(cvdf, "delta", default=0), 3), sign_cls(g(cvdf, "delta"))),
        kv("CVD spot", fr(g(cvds, "delta", default=0), 3), sign_cls(g(cvds, "delta"))),
        kv("Divergence spot/fut", div_badge + f' <small>{esc(g(div, "note", default="—"))}</small>'),
        kv("Footprint (bin dominant)",
           f'{fr(g(fp, "price_lo"), 0)}–{fr(g(fp, "price_hi"), 0)} · Δ {fr(g(fp, "delta"), 2)}', sign_cls(g(fp, "delta"))),
        kv("Gros trades ≥50k$", f'{g(lt, "n", default=0)} · buy {fr(g(lt, "buy_usd"), 0)}$ / sell {fr(g(lt, "sell_usd"), 0)}$'),
        kv("Liquidations (net)",
           pill(g(ofliq, "bias", default="—"), "neutral") + f' <small>{fr(g(ofliq, "net_notional"), 0)}$ · {g(ofliq, "n", default=0)} evts</small>'),
        kv("Positioning (positions)",
           pill(g(posn, "bias", default="—"), "neutral") + f' <small>L {fr(g(posn, "long"), 3)} / S {fr(g(posn, "short"), 3)}</small>'),
    ]
    panels.append(panel("Orderflow · mesure", pill("non branché au banc", "neutral"),
                        '<div class="kvs">' + "".join(of_rows) + "</div>"))

    # ---- Futures §45 ----
    fl = g(st, "futures_live", default={})
    caps = g(fl, "caps", default={})
    ev = g(fl, "events", default={})
    stop = g(fl, "stop", default={})
    oe = g(stop, "open_equity", default=0) or 1
    frac = (equity or 0) / oe if oe else 0
    dec = g(fl, "decision", default={})
    carry = g(fl, "carry", default={})
    fut_badge = pill("ARMÉ", "good") if g(fl, "armed") else pill("désarmé", "neutral")
    fut_rows = [
        kv("Décision", pill(g(dec, "action", default="—"), "neutral") + f'<div class="raison">{esc(g(dec,"raison",default=""))}</div>'),
        kv("Equity / ouverture", f'{fr(equity)} / {fr(oe)} <small>USDT</small>', sign_cls((equity or 0) - oe)),
        f'<div class="kv col"><span class="k">Distance au stop −{fr(stop_pct,0)}%</span>{bar(frac,"good" if frac>=1 else "warn")}</div>',
        kv("Caps effectifs", f'{fr(g(caps,"per_trade"),0)}$/trade · {fr(g(caps,"gross"),0)}$ cumul'),
        kv("Murs absolus", f'{fr(g(caps,"mur_per_trade"),0)} / {fr(g(caps,"mur_gross"),0)} <small>USDT</small>', "dim"),
        kv("Funding reçu", fr(g(fl, "funding", "total_usdt", default=0), 4) + " <small>USDT</small>", "pos"),
        kv("Fills bot", f'{g(fl,"fills_bot","n_fills",default=0)} · net {fr(net_bot)}$ · frais {fr(g(fl,"fills_bot","frais_usdt",default=0))}$'),
        kv("Carry", pill(g(carry, "attrait", default="—"), "neutral") + f' <small>APR {fr(g(carry,"apr",default=0),2)}% · couv. {fr(g(carry,"couverture",default=0),0)}$</small>'),
    ]
    ev_chips = "".join(f'<span class="chip">{esc(k)} <b>{v}</b></span>' for k, v in ev.items())
    panels.append(panel("Futures borné · §45", fut_badge,
                        '<div class="kvs">' + "".join(fut_rows) + "</div>" + f'<div class="chips">{ev_chips}</div>'))

    # ---- Portefeuille ----
    acc = g(st, "portfolio", "accounts", default={})
    labels = {"spot": "Spot", "futures": "Futures", "funding": "Funding", "earn": "Earn", "bots": "Bots", "margin": "Marge"}
    prows = "".join(kv(labels.get(k, k), fr(v) + " <small>USDT</small>") for k, v in acc.items())
    prows += kv("Total", fr(total) + " <small>USDT</small>", "accent")
    panels.append(panel("Portefeuille réel", pill("lecture seule", "neutral"), '<div class="kvs">' + prows + "</div>"))

    # ---- Verrous effectifs ----
    v = g(st, "verrous", default={})
    surf = g(v, "surfaces", default={})
    def lock(state):
        return pill("ARMÉ", "good") if state else pill("OFF", "neutral")
    vrows = [
        kv("Résumé", f'<div class="raison">{esc(g(v,"resume",default=""))}</div>'),
        kv("Mandat LIVE", lock(g(v, "mandate_live"))),
        kv("Futures autonome", lock(g(v, "futures", "effectif"))),
        kv("Accumulation auto", lock(g(v, "accum", "effectif"))),
        kv("Porte d'edge outrepassée", pill("OUI", "warn") if g(v, "edge_gate_override") else pill("non", "neutral")),
        kv("Kill-switch", pill("ACTIF", "crit") if kill else pill("OFF", "neutral")),
        kv("Notional futures", fr(g(v, "notional_futures"), 0) + " <small>USDT</small>"),
        kv("Surfaces §67", f'{g(v,"surfaces_armees",default=0)}/4 armées'),
    ]
    surf_chips = "".join(f'<span class="chip {"on" if val else ""}">{esc(k.replace("_TRADE_LIVE","").replace("_LIVE",""))}</span>' for k, val in surf.items())
    panels.append(panel("Verrous effectifs", pill(".env ⊕ config", "neutral"),
                        '<div class="kvs">' + "".join(vrows) + "</div>" + f'<div class="chips">{surf_chips}</div>'))

    # ---- Edge ladder ----
    el = g(st, "edge_ladder", default={})
    tiers = g(el, "tiers", default={})
    top = g(el, "top", default=[])
    tier_cls = {"LIVE": "good", "PROBATION": "warn", "PAPER": "neutral"}
    trows = "".join(kv(k, pill(val, tier_cls.get(val, "neutral"))) for k, val in tiers.items())
    top_tbl = ['<div class="agtbl">', '<div class="agh"><span>agent</span><span>DSR</span><span>n</span></div>']
    for t in top:
        top_tbl.append(f'<div class="agr"><span class="an">{esc(t.get("agent"))}</span><span class="{sign_cls(t.get("dsr"))}">{fr(t.get("dsr"),3)}</span><span>{t.get("n","—")}</span></div>')
    top_tbl.append("</div>")
    panels.append(panel("Échelle d'edge", pill(f'mode {g(el,"mode",default="—")} · {g(el,"n_symbols",default=0)} sym.', "neutral"),
                        '<div class="kvs">' + trows + "</div>" + "".join(top_tbl)))

    # ---- Stats trades ----
    stt = g(st, "stats", default={})
    bs = g(stt, "by_side", default={})
    srows = [
        kv("Trades finalisés", fr(g(stt, "total"), 0)),
        kv("TP / SL", f'{g(stt,"tp",default=0)} / {g(stt,"sl",default=0)}'),
        kv("Win rate", fr(win, 1) + " %", "neg" if float(win or 0) < 50 else "pos"),
        kv("Ratio TP/SL", fr(g(stt, "tp_sl_ratio", default=0), 2)),
        kv("Positions ouvertes", fr(g(st, "health", "open_positions"), 0)),
        kv("Signaux traités", fr(g(st, "health", "signals"), 0)),
    ]
    for side in ("LONG", "SHORT"):
        d = bs.get(side, {})
        srows.append(kv(side.capitalize(), f'{d.get("tp",0)} TP / {d.get("sl",0)} SL'))
    panels.append(panel("Statistiques trades", pill("cumul", "neutral"), '<div class="kvs">' + "".join(srows) + "</div>"))

    # ---- Macro ----
    mc = g(st, "macro", default={})
    regime = g(mc, "regime", default="—")
    kal = g(mc, "kalshi", "prochain", default={})
    mrows = [
        kv("Régime", pill(regime, "good" if regime == "RISK_ON" else ("crit" if regime == "RISK_OFF" else "warn")) + f' <small>score {g(mc,"score",default=0)}</small>'),
        kv("VIX", fr(g(mc, "vix"), 2)),
        kv("Courbe 2s10s", fr(g(mc, "yield_2s10s"), 2)),
        kv("DXY", fr(g(mc, "dxy_change_pct"), 2) + " %", sign_cls(g(mc, "dxy_change_pct"))),
        kv("Pétrole WTI", fr(g(mc, "oil_wti"), 1) + " <small>$</small>"),
    ]
    if kal:
        mrows.append(kv("Kalshi", f'<div class="raison">{esc(g(kal,"titre",default=""))} · dans {fr(g(kal,"jours",default=0),1)} j</div>'))
    notes = g(mc, "notes", default=[])
    notes_html = "".join(f'<li>{esc(n)}</li>' for n in notes)
    panels.append(panel("Macro", pill("vivant", "neutral"), '<div class="kvs">' + "".join(mrows) + "</div>" + (f'<ul class="notes">{notes_html}</ul>' if notes else "")))

    # ---- Accumulation ----
    ac = g(st, "accumulation", default={})
    rec = g(ac, "reconcile", default={})
    arows = [
        kv("Auto armée", pill("OUI", "good") if g(ac, "autonomous_armed") else pill("non", "neutral")),
        kv("Dépensé réel", f'{fr(g(ac,"real_spent_usd"))} $ · {g(ac,"real_n_buys",default=0)} achats'),
        kv("Opportunité", fr(g(ac, "opportunity", default=0), 3)),
        kv("DCA reco / réel", f'{fr(g(ac,"dca_reco"))} / {fr(g(ac,"dca_real"))} $'),
        kv("RSI · Fear&Greed", f'{fr(g(ac,"rsi"),1)} · {fr(g(ac,"fear_greed"),0)}'),
        kv("Premium vs fair", fr(g(ac, "premium_pct", default=0), 4) + " %"),
        kv("Fair price", fr(g(ac, "fair")) + " <small>$</small>"),
        kv("Prix de revient", fr(g(rec, "cost_basis")) + " <small>$</small>"),
        kv("USDT spot libre", fr(g(ac, "spot_free_usdt")) + " <small>USDT</small>"),
    ]
    panels.append(panel("Accumulation BTC", pill("RÉELLE", "good"), '<div class="kvs">' + "".join(arows) + "</div>"))

    # ---- Positions réelles ----
    rp = g(st, "real_positions", default={})
    cnt = g(rp, "counts", default={})
    tot = g(rp, "totals", default={})
    rrows = [
        kv("Spot", f'{cnt.get("spot",0)} pos · {fr(g(tot,"spot_usdt"))} $'),
        kv("Marge isolée", f'{cnt.get("margin_iso",0)} pos'),
        kv("Marge croisée", f'{cnt.get("margin_cross",0)} pos'),
        kv("Futures", f'{cnt.get("futures",0)} pos · notionnel {fr(g(tot,"futures_notional_usdt"))} $'),
        kv("uPnL futures", fr(g(tot, "futures_upnl_usdt")) + " <small>USDT</small>", sign_cls(g(tot, "futures_upnl_usdt"))),
    ]
    panels.append(panel("Positions réelles", pill("lecture seule", "neutral"), '<div class="kvs">' + "".join(rrows) + "</div>"))

    # ---- Agents DRY / mesures (HORS /api/state : journaux locaux, best-effort) ----
    dry_rows = _agents_dry_rows()
    if dry_rows:
        panels.append(panel("Agents DRY · mesures", pill("mesure · aucun ordre", "neutral"),
                            '<div class="kvs">' + "".join(dry_rows) + "</div>"))

    # ---- Validation & Parité (chaîne LIVE + instruments du 21/07, clé validation_gates) ----
    vg = g(st, "validation_gates", default={}) or {}
    if vg:
        vrows = []
        paires = (vg.get("parite") or {}).get("paires") or []
        if paires:
            nb_ok = sum(1 for p in paires if p.get("parite"))
            vrows.append(kv("Parité live→recherche", f"{nb_ok}/{len(paires)} paires",
                            "pos" if nb_ok == len(paires) else "neg"))
        hold = vg.get("holdout") or []
        if hold:
            cont = [str(h.get("version")) for h in hold if h.get("contamine")]
            vrows.append(kv("Holdout profond",
                            ("CONTAMINÉ : " + ", ".join(cont)) if cont
                            else f"{len(hold)} version(s), aucune contaminée",
                            "neg" if cont else "pos"))
        ann = vg.get("annuel") or {}
        cpc = vg.get("cpcv") or {}
        cpa = cpc.get("agents") or {}
        for a in sorted(set(ann) | set(cpa)):
            ic = ann.get(a)
            c = cpa.get(a) or {}
            p10, fneg = c.get("ic_p10"), c.get("frac_neg")
            fragile = (p10 is not None and p10 <= 0) or (fneg is not None and fneg > 0.10)
            txt = (f"annuel {fr(ic, 3) if ic is not None else '—'} · "
                   f"cpcv p10 {fr(p10, 3) if p10 is not None else '—'}"
                   f" / neg {fr((fneg or 0) * 100, 0)}%")
            vrows.append(kv(esc(a), txt, "neg" if (fragile or (ic is not None and ic < 0)) else ""))
        geo = vg.get("geometric_sizing") or {}
        if geo:
            vrows.append(kv("Geometric sizing",
                            (f"armé · scale {fr(geo.get('scale'), 2)} · z {fr(geo.get('systemic_z'), 2)}"
                             if geo.get("arme") else "désarmé"),
                            "neg" if (geo.get("arme") and (geo.get("scale") or 1) < 1) else ""))
        badge = pill("CPCV armée" if cpc.get("gate_armee") else "CPCV désarmée",
                     "good" if cpc.get("gate_armee") else "neutral")
        panels.append(panel("Validation & Parité", badge,
                            '<div class="kvs">' + "".join(vrows) + "</div>"))

    panels_html = "".join(panels)

    return TEMPLATE.format(ts=ts, mode=mode, kill_badge=kill_badge, total=fr(total),
                           kpis=kpis, panels=panels_html)


def kpi(label, value, cls="", sub=""):
    sub_html = f'<span class="ksub">{esc(sub)}</span>' if sub else ""
    return f'<div class="kpi"><span class="klab">{esc(label)}</span><span class="kval {cls}">{value}</span>{sub_html}</div>'


# ----------------------------------------------------------------------------- template
TEMPLATE = """<title>MIROFISH · Salle de pilotage</title>
<style>
:root{{
  --bg:#eef2f5; --surface:#ffffff; --surface-2:#f4f8fa; --border:#d7e0e6;
  --text:#0f1b24; --dim:#5a6b76; --accent:#0c8399; --accent-soft:#e0f2f6;
  --good:#0f9d6b; --warn:#b06d0f; --crit:#cf3a3a;
  --mono:ui-monospace,"SF Mono",Menlo,"Cascadia Code",Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}}
@media (prefers-color-scheme:dark){{
  :root{{
    --bg:#080e15; --surface:#101a23; --surface-2:#0c141c; --border:#1d2b36;
    --text:#e6eef4; --dim:#7d94a3; --accent:#22d3ee; --accent-soft:#0e2730;
    --good:#34d399; --warn:#fbbf24; --crit:#f87171;
  }}
}}
:root[data-theme="light"]{{
  --bg:#eef2f5; --surface:#ffffff; --surface-2:#f4f8fa; --border:#d7e0e6;
  --text:#0f1b24; --dim:#5a6b76; --accent:#0c8399; --accent-soft:#e0f2f6;
  --good:#0f9d6b; --warn:#b06d0f; --crit:#cf3a3a;
}}
:root[data-theme="dark"]{{
  --bg:#080e15; --surface:#101a23; --surface-2:#0c141c; --border:#1d2b36;
  --text:#e6eef4; --dim:#7d94a3; --accent:#22d3ee; --accent-soft:#0e2730;
  --good:#34d399; --warn:#fbbf24; --crit:#f87171;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1440px;margin:0 auto;padding:0 20px 48px}}
.num,.kval,.v,.chip b,.agr span,.bar{{font-variant-numeric:tabular-nums}}

/* topbar */
.top{{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--border);margin-bottom:24px}}
.topin{{max-width:1440px;margin:0 auto;padding:14px 20px;display:flex;align-items:center;
  gap:16px;flex-wrap:wrap}}
.brand{{display:flex;flex-direction:column;gap:2px;margin-right:auto}}
.brand h1{{margin:0;font-size:17px;font-weight:650;letter-spacing:.04em}}
.brand .dot{{color:var(--accent)}}
.brand small{{color:var(--dim);font-size:12px;font-family:var(--mono)}}
.mode{{font-size:12px;color:var(--dim);font-family:var(--mono);
  border:1px solid var(--border);border-radius:6px;padding:4px 10px;background:var(--surface)}}
.tot{{text-align:right}}
.tot .l{{display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}}
.tot .n{{font-family:var(--mono);font-size:20px;font-weight:650;color:var(--accent)}}

/* KPI */
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:22px}}
.kpi{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:14px 16px;display:flex;flex-direction:column;gap:4px}}
.klab{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}}
.kval{{font-family:var(--mono);font-size:22px;font-weight:600;line-height:1.15}}
.kval small{{font-size:12px;color:var(--dim);font-weight:400}}
.ksub{{font-size:11px;color:var(--dim);font-family:var(--mono)}}

/* panels grid */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;align-items:start}}
.panel{{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden}}
.phead{{display:flex;align-items:center;justify-content:space-between;gap:8px;
  padding:12px 16px;border-bottom:1px solid var(--border);background:var(--surface-2)}}
.phead h2{{margin:0;font-size:13px;font-weight:640;letter-spacing:.02em}}
.pbody{{padding:12px 16px 16px}}

/* key/value */
.kvs{{display:flex;flex-direction:column}}
.kv{{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
  padding:6px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 55%,transparent)}}
.kv:last-child{{border-bottom:none}}
.kv.col{{flex-direction:column;align-items:stretch;gap:6px}}
.kv .k{{color:var(--dim);font-size:12.5px;flex-shrink:0}}
.kv .v{{font-family:var(--mono);text-align:right;font-size:13px}}
.kv .v small{{color:var(--dim)}}
.v.pos,.pos{{color:var(--good)}}
.v.neg,.neg{{color:var(--crit)}}
.v.accent{{color:var(--accent);font-weight:600}}
.v.dim,.dim{{color:var(--dim)}}
.raison{{color:var(--dim);font-size:11.5px;font-family:var(--sans);text-align:right;margin-top:2px}}

/* pills & chips */
.pill{{display:inline-block;font-size:10.5px;font-weight:600;letter-spacing:.04em;
  padding:2px 8px;border-radius:20px;font-family:var(--sans);white-space:nowrap;
  border:1px solid transparent}}
.pill.good{{background:color-mix(in srgb,var(--good) 15%,transparent);color:var(--good);border-color:color-mix(in srgb,var(--good) 35%,transparent)}}
.pill.warn{{background:color-mix(in srgb,var(--warn) 15%,transparent);color:var(--warn);border-color:color-mix(in srgb,var(--warn) 35%,transparent)}}
.pill.crit{{background:color-mix(in srgb,var(--crit) 15%,transparent);color:var(--crit);border-color:color-mix(in srgb,var(--crit) 40%,transparent)}}
.pill.accent{{background:var(--accent-soft);color:var(--accent);border-color:color-mix(in srgb,var(--accent) 35%,transparent)}}
.pill.neutral{{background:var(--surface-2);color:var(--dim);border-color:var(--border)}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}}
.chip{{font-size:10.5px;font-family:var(--mono);color:var(--dim);background:var(--surface-2);
  border:1px solid var(--border);border-radius:6px;padding:3px 7px}}
.chip b{{color:var(--text);font-weight:600}}
.chip.on{{color:var(--good);border-color:color-mix(in srgb,var(--good) 40%,transparent)}}

/* agent table */
.agtbl{{margin-top:12px;font-family:var(--mono);font-size:12px}}
.agh,.agr{{display:grid;grid-template-columns:1fr auto auto auto;gap:10px;padding:4px 0}}
.agh{{color:var(--dim);font-size:10px;letter-spacing:.08em;text-transform:uppercase;
  border-bottom:1px solid var(--border)}}
.agr{{border-bottom:1px solid color-mix(in srgb,var(--border) 45%,transparent)}}
.agr:last-child{{border-bottom:none}}
.agr .an{{color:var(--text)}}
.agr .w{{color:var(--accent)}}
.agr span:not(.an){{text-align:right;min-width:44px}}
.inval{{color:var(--crit);font-size:9px;font-family:var(--sans);border:1px solid color-mix(in srgb,var(--crit) 40%,transparent);border-radius:4px;padding:0 4px;margin-left:4px}}

/* bar */
.bar{{height:8px;background:var(--surface-2);border-radius:6px;overflow:hidden;border:1px solid var(--border)}}
.fill{{display:block;height:100%;border-radius:6px}}
.fill.accent{{background:var(--accent)}}
.fill.good{{background:var(--good)}}
.fill.warn{{background:var(--warn)}}
.fill.crit{{background:var(--crit)}}

.notes{{margin:10px 0 0;padding-left:16px;color:var(--dim);font-size:11.5px;display:flex;flex-direction:column;gap:2px}}
.foot{{margin-top:28px;text-align:center;color:var(--dim);font-size:11px;font-family:var(--mono)}}
@media (max-width:480px){{.kval{{font-size:19px}}.grid{{grid-template-columns:1fr}}}}
</style>

<div class="top"><div class="topin">
  <div class="brand"><h1>MIROFISH <span class="dot">·</span> Salle de pilotage</h1>
    <small>instantané {ts}</small></div>
  <span class="mode">{mode}</span>
  {kill_badge}
  <div class="tot"><span class="l">Patrimoine</span><span class="n">{total} USDT</span></div>
</div></div>

<div class="wrap">
  <div class="kpis">{kpis}</div>
  <div class="grid">{panels}</div>
  <div class="foot">Instantané lecture seule · aucun ordre passé · données /api/state du bot</div>
</div>
"""


def main():
    try:
        st = fetch_state()
    except Exception as e:
        sys.stderr.write(f"[render_dashboard] fetch KO, HTML non écrasé : {e}\n")
        return 1
    out_html = build(st)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(out_html)
    os.replace(tmp, OUT)
    sys.stderr.write(f"[render_dashboard] OK -> {OUT} ({len(out_html)} octets)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
