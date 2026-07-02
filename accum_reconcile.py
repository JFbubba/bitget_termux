"""
accum_reconcile.py — RÉCONCILIATION de l'accumulation RÉELLE (LECTURE SEULE).

Classement : SAFE. Aucun ordre, aucune écriture dans le registre de l'exécuteur
(accumulation_real_ledger.json reste la propriété exclusive de spot_executor).
Lectures : fills spot via l'Agent Hub (--read-only forcé par bitget_hub_bridge),
solde BTC via bitget_balance_reader, prix courant via le ticker spot.

Pourquoi : le chemin réel était AVEUGLE après l'achat — le registre note le
montant USDT et le clientOid, mais ni le prix de remplissage, ni la quantité de
BTC, ni les frais. Impossible de répondre à « quel est mon prix de revient
RÉEL ? » ni de détecter un écart registre ↔ compte. Ce module répond aux deux :

  • PRIX DE REVIENT RÉEL : VWAP des fills appariés au registre (Σ USDT / Σ BTC),
    frais inclus dans le rapport ; PnL latent vs prix courant.
  • RÉCONCILIATION 3 SOURCES : registre (intentions journalisées) ↔ fills
    (exécutions vues par Bitget) ↔ solde BTC du compte. Un fill sans achat
    journalisé, un achat sans fill, ou un solde BTC INFÉRIEUR au cumul acheté
    (le compte ne vend jamais -> ne devrait qu'augmenter) = ANOMALIE affichée.

Appariement par (proximité temporelle, similarité de montant) : les fills spot
Bitget n'exposent PAS le clientOid, on ne peut pas joindre par identifiant.
Limite honnête : l'historique de fills renvoyé par l'API est borné (~100) ; la
réconciliation couvre la fenêtre visible et l'AFFICHE (jamais un faux « tout va
bien » sur une fenêtre tronquée).

CLI : python accum_reconcile.py
"""

import json
import time

from config_utils import cfg as _cfg
from numeric_utils import safe_float

SYMBOL = "BTCUSDT"
APPARIEMENT_TOL_S = 300          # |ts registre − ts fill| max (l'achat part à la seconde)
APPARIEMENT_TOL_RATIO = 0.35     # écart de montant toléré (frais/arrondis/fills partiels)


# ---------- cœurs purs (testables) ----------

def _fee_btc(fee_detail):
    """PUR. Frais en BTC (valeur ABSOLUE) d'un feeDetail Bitget ({'feeCoin','totalFee'}),
    JSON string toléré. 0.0 si illisible ou frais dans une autre devise (BGB...)."""
    d = fee_detail
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except (ValueError, TypeError):
            return 0.0
    if not isinstance(d, dict) or str(d.get("feeCoin", "")).upper() != "BTC":
        return 0.0
    return abs(safe_float(d.get("totalFee")) or 0.0)


def group_fills(rows):
    """PUR. Agrège les fills spot BUY par orderId (un ordre peut remplir en plusieurs
    fois) : [{order_id, ts, price_avg (VWAP), size_btc, amount_usdt, fee_btc}], trié
    par ts croissant. Entrées illisibles / non-buy ignorées."""
    par_ordre = {}
    for r in rows or []:
        if not isinstance(r, dict) or str(r.get("side", "")).lower() != "buy":
            continue
        oid = str(r.get("orderId") or "")
        ts = safe_float(r.get("cTime"))
        size = safe_float(r.get("size"))
        amt = safe_float(r.get("amount"))
        if not oid or ts is None or size is None or amt is None or size <= 0 or amt <= 0:
            continue
        g = par_ordre.setdefault(oid, {"order_id": oid, "ts": ts / 1000.0,
                                       "size_btc": 0.0, "amount_usdt": 0.0, "fee_btc": 0.0})
        g["ts"] = min(g["ts"], ts / 1000.0)
        g["size_btc"] += size
        g["amount_usdt"] += amt
        g["fee_btc"] += _fee_btc(r.get("feeDetail"))
    out = []
    for g in par_ordre.values():
        g["price_avg"] = round(g["amount_usdt"] / g["size_btc"], 2) if g["size_btc"] > 0 else None
        g["size_btc"] = round(g["size_btc"], 8)
        g["amount_usdt"] = round(g["amount_usdt"], 6)
        g["fee_btc"] = round(g["fee_btc"], 10)
        out.append(g)
    out.sort(key=lambda g: g["ts"])
    return out


def match_buys(buys, groups, tol_s=APPARIEMENT_TOL_S, tol_ratio=APPARIEMENT_TOL_RATIO):
    """PUR. Apparie chaque achat du registre au groupe de fills le plus PROCHE dans le
    temps (|Δt| ≤ tol_s, montant à ±tol_ratio près), chaque groupe servant au plus une
    fois. Retourne (paires [{buy, fill}], achats_orphelins, fills_orphelins) — les
    fills orphelins sont limités à la fenêtre couverte par le registre (après le 1er
    achat − tol_s) : un fill ANTÉRIEUR au 1er achat journalisé n'est pas un écart."""
    buys = sorted((b for b in buys or [] if safe_float(b.get("ts")) is not None),
                  key=lambda b: float(b["ts"]))
    libres = list(groups or [])
    paires, orphelins = [], []
    for b in buys:
        ts_b = float(b["ts"])
        amt_b = safe_float(b.get("amount_usdt")) or 0.0
        meilleur, meilleur_dt = None, None
        for g in libres:
            dt = abs(g["ts"] - ts_b)
            if dt > tol_s:
                continue
            if amt_b > 0 and abs(g["amount_usdt"] - amt_b) / amt_b > tol_ratio:
                continue
            if meilleur is None or dt < meilleur_dt:
                meilleur, meilleur_dt = g, dt
        if meilleur is None:
            orphelins.append(b)
        else:
            libres.remove(meilleur)
            paires.append({"buy": b, "fill": meilleur})
    debut = (float(buys[0]["ts"]) - tol_s) if buys else float("inf")
    fills_orphelins = [g for g in libres if g["ts"] >= debut]
    return paires, orphelins, fills_orphelins


def bilan(paires, achats_orphelins, fills_orphelins, btc_compte=None, prix=None,
          tolerance_btc=1e-8):
    """PUR. Bilan de réconciliation : prix de revient RÉEL (VWAP des fills appariés),
    frais, PnL latent vs prix courant, écart solde BTC vs cumul acheté. Le compte
    n'ACHETANT que du BTC (jamais de vente), un solde < cumul acheté − frais est une
    ANOMALIE (vente/retrait hors périmètre) ; un solde supérieur est normal (dépôts,
    achats antérieurs au registre)."""
    usdt = sum(p["fill"]["amount_usdt"] for p in paires)
    btc = sum(p["fill"]["size_btc"] for p in paires)
    fees = sum(p["fill"]["fee_btc"] for p in paires)
    btc_net = btc - fees                                   # frais BTC prélevés sur la base
    cb = (usdt / btc) if btc > 0 else None
    pnl_pct = None
    prix = safe_float(prix)
    if cb and prix and prix > 0:
        pnl_pct = (prix / cb - 1.0) * 100.0
    anomalies = []
    if achats_orphelins:
        anomalies.append(f"{len(achats_orphelins)} achat(s) du registre SANS fill apparié")
    if fills_orphelins:
        anomalies.append(f"{len(fills_orphelins)} fill(s) buy SANS achat journalisé")
    btc_compte = safe_float(btc_compte)
    ecart_btc = None
    if btc_compte is not None:
        ecart_btc = btc_compte - btc_net
        if ecart_btc < -max(tolerance_btc, 0.0):
            anomalies.append(f"solde BTC ({btc_compte:.8f}) < cumul acheté net "
                             f"({btc_net:.8f}) — vente/retrait hors périmètre ?")
    return {"n_apparies": len(paires), "n_achats_orphelins": len(achats_orphelins),
            "n_fills_orphelins": len(fills_orphelins),
            "usdt_depense": round(usdt, 4), "btc_achete": round(btc, 8),
            "btc_net_frais": round(btc_net, 8), "frais_btc": round(fees, 10),
            "cost_basis": round(cb, 2) if cb is not None else None,
            "prix_courant": prix,
            "pnl_latent_pct": round(pnl_pct, 3) if pnl_pct is not None else None,
            "btc_compte": btc_compte,
            "ecart_btc": round(ecart_btc, 8) if ecart_btc is not None else None,
            "anomalies": anomalies, "ok": not anomalies}


# ---------- lectures réseau (best-effort, cachées) ----------

def fetch_fills(limit=100):
    """Fills spot BTCUSDT via l'Agent Hub (LECTURE SEULE forcée). [] si indisponible."""
    def _fetch():
        import bitget_hub_bridge as hub
        d = hub._read(["spot", "spot_get_fills", "--symbol", SYMBOL,
                       "--limit", str(int(limit))])
        rows = (d or {}).get("data") if isinstance(d, dict) else None
        return rows if isinstance(rows, list) else []
    try:
        import runtime_cache as rc
        return rc.get("accum_fills", _cfg("ACCUM_RECONCILE_TTL_S", 900), _fetch, fallback=[])
    except Exception:
        return []


def fetch_btc_compte():
    """BTC total (disponible + gelé) du wallet spot. None si indisponible."""
    def _fetch():
        import bitget_balance_reader as br
        for row in (br.get_spot_assets("BTC") or {}).get("data") or []:
            if str(row.get("coin", "")).upper() == "BTC":
                dispo = safe_float(row.get("available")) or 0.0
                gele = safe_float(row.get("frozen")) or 0.0
                return dispo + gele
        return None
    try:
        import runtime_cache as rc
        return rc.get("accum_btc_compte", _cfg("ACCUM_RECONCILE_TTL_S", 900),
                      _fetch, fallback=None)
    except Exception:
        return None


def _prix_courant():
    """Prix spot courant (mid du carnet via l'Agent Hub, lecture seule). None sinon."""
    try:
        import spot_executor as se
        q = se._best_quote()
        return q.get("mid") if q else None
    except Exception:
        return None


def snapshot():
    """Réconciliation complète (best-effort). Ne lève jamais, n'écrit RIEN."""
    try:
        import spot_executor as se
        buys = se._load_real().get("buys", [])
    except Exception:
        buys = []
    groupes = group_fills(fetch_fills())
    paires, orphelins, fills_orphelins = match_buys(buys, groupes)
    out = bilan(paires, orphelins, fills_orphelins, fetch_btc_compte(), _prix_courant())
    out["n_registre"] = len(buys)
    out["fenetre_fills"] = len(groupes)
    return out


# ---------- rapport ----------

def _n(v, motif="{:.2f}"):
    return motif.format(v) if isinstance(v, (int, float)) else "—"


def build_report(s=None):
    """Rapport texte lisible ; s=None -> collecte via snapshot()."""
    s = snapshot() if s is None else s
    lignes = [
        "=== RÉCONCILIATION ACCUMULATION RÉELLE (registre ↔ fills ↔ compte) ===",
        f"Registre : {s.get('n_registre', 0)} achats · appariés {s.get('n_apparies', 0)} "
        f"(fenêtre fills visible : {s.get('fenetre_fills', 0)} ordres)",
        f"Dépensé  : {_n(s.get('usdt_depense'))} USDT -> {_n(s.get('btc_achete'), '{:.8f}')} BTC "
        f"(net frais {_n(s.get('btc_net_frais'), '{:.8f}')})",
        f"Prix de revient RÉEL : {_n(s.get('cost_basis'))} $ · prix courant {_n(s.get('prix_courant'))} $ "
        f"· PnL latent {_n(s.get('pnl_latent_pct'), '{:+.2f}')} %",
        f"Compte   : {_n(s.get('btc_compte'), '{:.8f}')} BTC · écart vs acheté net "
        f"{_n(s.get('ecart_btc'), '{:+.8f}')} (≥0 attendu : on ne vend jamais)",
    ]
    if s.get("anomalies"):
        lignes.append("⚠️ ANOMALIES : " + " ; ".join(s["anomalies"]))
    else:
        lignes.append("Aucune anomalie : chaque achat journalisé a son fill, le solde couvre le cumul.")
    lignes.append("Lecture seule (aucune écriture, aucun ordre). VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
