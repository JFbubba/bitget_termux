"""etat_effectif.py — ÉTAT du bot en UN COUP D'ŒIL (source de vérité de LECTURE).

SAFE : lecture seule, LOCAL (aucun réseau). Agrège en un seul endroit ce qui était
éclaté entre .env / config.py / journaux : verrous d'exécution EFFECTIFS (via
verrous_effectifs, logique `.env OR config`), voix opt-in, caps durs, garde-fous.
Répond en 5 s à « le bot trade-t-il en réel ? combien ? qu'est-ce qui est actif ? »
sans avoir à croiser 3 fichiers (la cause du piège des verrous du 08/07).

Pour le LIVE (positions/PnL/equity, qui exige le réseau) : `python futures_report.py`.

    python3 etat_effectif.py
"""
from __future__ import annotations
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
except Exception:
    pass
from config_utils import cfg  # noqa: E402
import verrous_effectifs as ve  # noqa: E402

# Caps futures EFFECTIFS lus à la SOURCE de vérité (futures_executor), pour que
# l'affichage suive EXACTEMENT ce que guards() applique — jamais un paramètre d'une
# autre couche (ex. MAX_TOTAL_NOTIONAL_USDT = cap portefeuille risk_limits, ≠ mur
# cumulé futures). Import sûr : futures_executor n'importe que json/time/pathlib/cfg
# au top-level (aucun réseau, aucun ordre au chargement). Fail-safe si indispo.
try:
    import futures_executor as _fx  # noqa: E402
    _FUT_PER_TRADE_EFF = _fx._capped("FUTURES_REAL_MAX_PER_TRADE_USDT", 10.0, _fx.FUT_ABS_MAX_PER_TRADE_USDT)
    _FUT_GROSS_EFF = _fx._capped("FUTURES_REAL_MAX_GROSS_USDT", 20.0, _fx.FUT_ABS_MAX_GROSS_USDT)
    _FUT_PER_TRADE_MUR = float(_fx.FUT_ABS_MAX_PER_TRADE_USDT)
    _FUT_GROSS_MUR = float(_fx.FUT_ABS_MAX_GROSS_USDT)
except Exception:
    _FUT_PER_TRADE_EFF = _FUT_PER_TRADE_MUR = None
    _FUT_GROSS_EFF = _FUT_GROSS_MUR = None

# voix opt-in : (gate, label, note)
VOIX = [
    ("LLM_AGENT_ENABLED", "LLM (15ᵉ)", "libre"),
    ("NN_AGENT_ENABLED", "NN fusion (16ᵉ)", "soumise à la porte d'edge (muette si l'edge ne passe pas)"),
    ("CLASSICS_AGENT_ENABLED", "classics (17ᵉ)", "mesurée coupée (t≈−11)"),
    ("QML_AGENT_ENABLED", "QML (18ᵉ)", "soumise à la porte d'edge (muette si l'edge ne passe pas)"),
]


def _on(name):
    return (os.getenv(name) or "").strip().lower() in ve.TRUEISH or bool(cfg(name, False))


def summary():
    v = ve.summary()
    voix = {}
    for gate, label, note in VOIX:
        voix[gate] = {"label": label, "on": _on(gate), "note": note}
    return {
        "armement": v,
        "voix": voix,
        "caps": {
            # caps futures EFFECTIFS (= ce que guards() applique) + murs absolus
            "futures_per_trade_eff_usd": _FUT_PER_TRADE_EFF if _FUT_PER_TRADE_EFF is not None
                                         else cfg("MAX_POSITION_USD", 50.0),
            "futures_per_trade_mur_usd": _FUT_PER_TRADE_MUR,
            "futures_gross_eff_usd": _FUT_GROSS_EFF,
            "futures_gross_mur_usd": _FUT_GROSS_MUR,
            # cap portefeuille agrégé — AUTRE couche (risk_limits), pas le mur futures
            "portefeuille_notional_usd": cfg("MAX_TOTAL_NOTIONAL_USDT", 300.0),
            "levier_mur": cfg("MANDATE_MAX_LEVERAGE", 5.0),
            "mdd_halte_pct": cfg("MANDATE_MAX_DRAWDOWN_PCT", 20.0),
            "accum_par_achat_usd": cfg("ACCUM_REAL_MAX_PER_BUY_USDT", 5.0),
            "accum_par_jour_usd": cfg("ACCUM_REAL_MAX_DAILY_USDT", 5.0),
            "notional_boucle_usd": v.get("notional_futures"),
        },
        "gardes": {"kill_switch": v["kill_switch"],
                   "halte": (HERE / "TRADING_HALT").exists(),
                   "pause": (HERE / "PAUSE").exists()},
    }


def render(s):
    v, c, g = s["armement"], s["caps"], s["gardes"]
    L = ["=== ÉTAT DU BOT (effectif · lecture seule locale) ==="]
    L.append(f"ARMEMENT : {v['resume']}")
    L.append(f"  verrou maître (mandat) : {'ARMÉ' if v['mandate_live'] else 'coupé'}")
    for k in ("futures", "accum"):
        d = v[k]
        warn = "  ⚠ config.py=False (armé via .env)" if d["ecart"] else ""
        L.append(f"  {k:<13}: {'ARMÉ' if d['actif'] else 'paper'} (src {d['source']}){warn}")
    L.append(f"  porte edge   : {'outrepassée' if v['edge_gate_override'] else 'fermée'}"
             f" (override={v['edge_gate_override']})")
    L.append(f"  surfaces §67 : {v['surfaces_armees']}/4 armées "
             f"({', '.join(k.replace('_LIVE','').lower() for k,on in v['surfaces'].items() if on) or '—'})")
    L.append(f"  kill-switch  : {'ACTIF ⛔' if g['kill_switch'] else 'non'}"
             f"{' · HALTE' if g['halte'] else ''}{' · PAUSE' if g['pause'] else ''}")
    L.append("VOIX (banc 14 déterministe = socle ; surcouches opt-in) :")
    for gate, d in s["voix"].items():
        L.append(f"  {d['label']:<16}: {'ARMÉE' if d['on'] else 'off'} — {d['note']}")
    L.append("CAPS DURS (caps effectifs · murs absolus) :")
    pm = f" (mur {c['futures_per_trade_mur_usd']:.0f})" if c['futures_per_trade_mur_usd'] else ""
    if c['futures_gross_eff_usd'] is not None:
        gross_txt = f"{c['futures_gross_eff_usd']:.0f}$ cumulé (mur {c['futures_gross_mur_usd']:.0f})"
    else:
        gross_txt = "cumulé n/d (source futures_executor indispo)"
    L.append(f"  futures      : {c['futures_per_trade_eff_usd']:.0f}$/trade{pm} · {gross_txt}"
             f" · levier ×{c['levier_mur']} · MDD halte {c['mdd_halte_pct']}%")
    L.append(f"  portefeuille : {c['portefeuille_notional_usd']:.0f}$ notionnel agrégé (couche risk_limits)")
    L.append(f"  accum        : {c['accum_par_achat_usd']}$/achat · {c['accum_par_jour_usd']}$/jour"
             f"   ·   notional boucle : {c['notional_boucle_usd']}$")
    if v["ecarts"]:
        L.append(f"⚠ ÉCARTS .env↔config : {', '.join(v['ecarts'])} (armés via .env, config=False)")
    L.append("--- LIVE (positions/PnL/equity) : python futures_report.py (réseau) ---")
    return "\n".join(L)


if __name__ == "__main__":
    print(render(summary()))
