"""
portefeuille.py — inventaire VALORISÉ du portefeuille spot (LECTURE SEULE).

Classement : SAFE. Lectures compte + tickers, aucun ordre, aucune écriture.

Pourquoi (demande propriétaire 03/07 « utilise les tokens de mon portefeuille ») :
le bot ne voyait que USDT et BTC — or l'essentiel du portefeuille est ailleurs
(BGBTC ~175 $, wrapper BTC de Bitget). Ce module rend le portefeuille visible
(dashboard, /portefeuille, revue hebdo) et calcule l'EXPOSITION BTC TOTALE
(BTC natif + wrappers) qui sert de couverture à la jambe carry (carry_auto).

Constat honnête sur les autres tokens : ~20 lignes de POUSSIÈRE (< 0.5 $ chacune,
~1.3 $ au total) — invendables par API dans le périmètre (spot_executor n'achète
que du BTC, on ne vend jamais), sous les minimums du module convert. Elles sont
listées, pas « utilisées » : il n'y a rien d'honnête à en tirer.
"""

import time

from numeric_utils import safe_float

# wrappers/dérivés comptant comme exposition BTC (mêmes clés que carry_auto)
_EXPO_BTC = ("BTC", "BGBTC")
_SEUIL_POUSSIERE_USDT = 0.5


def _prix(coin):
    """Prix USDT spot d'un coin (None si pas de paire/illisible). Best-effort."""
    if coin == "USDT":
        return 1.0
    try:
        import bitget_hub_bridge as hub
        d = hub._read(["spot", "spot_get_ticker", "--symbol", f"{coin}USDT"])
        row = ((d or {}).get("data") or [{}])[0]
        return safe_float(row.get("lastPr"))
    except Exception:
        return None


def inventaire():
    """[{coin, quantite, valeur_usdt}] trié par valeur décroissante + agrégats :
    {actifs, poussiere_usdt, n_poussiere, total_usdt, expo_btc_usdt}. Caché 15 min
    (les tickers par coin coûtent un appel chacun). {} si compte illisible."""
    def _fetch():
        import bitget_balance_reader as br
        rows = (br.get_spot_assets() or {}).get("data")
        if rows is None:
            return {}
        actifs, poussiere, n_poussiere, total, expo_btc = [], 0.0, 0, 0.0, 0.0
        for r in rows:
            coin = str(r.get("coin", "")).upper()
            q = (safe_float(r.get("available")) or 0.0) + (safe_float(r.get("frozen")) or 0.0)
            if q <= 0:
                continue
            px = _prix(coin)
            val = q * px if px is not None else None
            if val is not None:
                total += val
                if coin in _EXPO_BTC:
                    expo_btc += val
            if val is None or val < _SEUIL_POUSSIERE_USDT:
                poussiere += val or 0.0
                n_poussiere += 1
                continue
            actifs.append({"coin": coin, "quantite": round(q, 8), "valeur_usdt": round(val, 2)})
        actifs.sort(key=lambda a: -a["valeur_usdt"])
        return {"actifs": actifs, "poussiere_usdt": round(poussiere, 2),
                "n_poussiere": n_poussiere, "total_usdt": round(total, 2),
                "expo_btc_usdt": round(expo_btc, 2), "ts": int(time.time())}
    try:
        import runtime_cache as rc
        return rc.get("portefeuille_spot", 900, _fetch, fallback={})
    except Exception:
        try:
            return _fetch()
        except Exception:
            return {}


def _n(v, motif="{:.2f}"):
    return motif.format(v) if isinstance(v, (int, float)) else "—"


def build_report(inv=None):
    inv = inventaire() if inv is None else inv
    if not inv:
        return ("=== PORTEFEUILLE SPOT ===\nCompte illisible (réessayer). "
                "Lecture seule. VERDICT: SAFE")
    lignes = ["=== PORTEFEUILLE SPOT (valorisé) ==="]
    for a in inv.get("actifs", []):
        expo = "  ← exposition BTC" if a["coin"] in _EXPO_BTC else ""
        lignes.append(f"  {a['coin']:<8} {a['quantite']:>14.8f}  ≈ {a['valeur_usdt']:>8.2f} ${expo}")
    lignes.append(f"  poussière : {inv.get('n_poussiere', 0)} tokens ≈ {_n(inv.get('poussiere_usdt'))} $ "
                  "(sous les minimums d'échange — listée, pas utilisable)")
    lignes.append(f"TOTAL ≈ {_n(inv.get('total_usdt'))} $ · exposition BTC totale "
                  f"{_n(inv.get('expo_btc_usdt'))} $ (couverture de la jambe carry, "
                  "wrapper décoté 10 % côté exécution)")
    lignes.append("Lecture seule, aucun ordre. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
