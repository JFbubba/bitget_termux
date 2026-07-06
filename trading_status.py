"""
trading_status.py — état LECTURE SEULE des surfaces de trading bornées §67.

Classement : SAFE, read-only. N'exécute RIEN : il lit les verrous LIVE (armé/OFF), les
caps effectifs et le dépensé du jour de chaque surface (spot / marge / virements / earn)
pour le dashboard. Aucun ordre, aucun mouvement de fonds. Séparé du serveur pour que
`dashboard/server.py` n'ait à référencer aucun module d'exécution.
"""
import bitget_execute as ex
import spot_trader as st
import margin_trader as mt
import account_transfers as at
import earn_manager as em

# (surface, libellé, flag LIVE, clé cap/op, défaut, absolu, clé cap/jour, défaut, absolu)
_DEFS = [
    ("spot", "Spot libre", st.LIVE_FLAG, "SPOT_TRADE_MAX_PER_OP_USDT", 10.0, st.ABS_PER_OP_USDT,
     "SPOT_TRADE_MAX_DAILY_USDT", 50.0, st.ABS_DAILY_USDT),
    ("margin", "Marge iso/cross", mt.LIVE_FLAG, "MARGIN_MAX_PER_OP_USDT", 10.0, mt.ABS_PER_OP_USDT,
     "MARGIN_MAX_DAILY_USDT", 50.0, mt.ABS_DAILY_USDT),
    ("transfer", "Virements internes", at.LIVE_FLAG, "TRANSFER_MAX_PER_OP_USDT", 25.0, at.ABS_PER_OP_USDT,
     "TRANSFER_MAX_DAILY_USDT", 100.0, at.ABS_DAILY_USDT),
    ("earn", "Earn", em.LIVE_FLAG, "EARN_MAX_PER_OP_USDT", 25.0, em.ABS_PER_OP_USDT,
     "EARN_MAX_DAILY_USDT", 100.0, em.ABS_DAILY_USDT),
]


def snapshot():
    """Liste de l'état de chaque surface : armé/OFF + caps effectifs + dépensé du jour."""
    out = []
    for surface, label, flag, pk, pf, pabs, dk, df, dabs in _DEFS:
        out.append({
            "surface": surface, "label": label, "flag": flag,
            "armed": bool(ex.gate(flag)),
            "per_op": ex.capped(pk, pf, pabs), "per_op_abs": pabs,
            "daily": ex.capped(dk, df, dabs), "daily_abs": dabs,
            "spent_today": ex.today_spent(surface),
        })
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(snapshot(), indent=2, ensure_ascii=False))
