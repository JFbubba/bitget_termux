"""
bitget_hub_bridge.py — PONT entre les outils Bitget Agent Hub et le bot.

Classement : SAFE. LECTURE SEULE + garde de mandat ADVISORY. Ce module n'exécute
JAMAIS d'écriture : il LIT l'état du compte via les outils de l'Agent Hub (CLI
`bgc`, best-effort, dégrade proprement s'il est absent) et il SOUMET toute décision
du bot à `mandate.py` avant de la déclarer autorisée ou non.

Architecture (rappel) : ce dépôt = le CERVEAU (paper, `can_trade=False`). L'Agent
Hub = les MAINS (capable de trader, sur la machine de trading). Le pont relie les
deux SANS franchir la frontière : il produit un VERDICT (autorisé/bloqué + raisons +
paramètres bornés). L'exécution réelle reste à l'Agent Hub, derrière SA confirmation.

Aucune chaîne d'exécution d'écriture n'est encodée ici (gate sécurité OK).
"""

import json
import shutil
import subprocess

HUB_CLI = "bgc"          # bitget-client (Agent Hub) ; lecture seule utilisée ici


def _cfg(name, fallback):
    try:
        import config
        return getattr(config, name, fallback)
    except Exception:
        return fallback


# ---------- accès LECTURE SEULE aux outils de l'Agent Hub ----------

def available(which=shutil.which):
    """L'Agent Hub (CLI `bgc`) est-il installé sur cette machine ?"""
    try:
        return which(HUB_CLI) is not None
    except Exception:
        return False


def _hub_env(base=None, dotenv_vals=None):
    """Env pour `bgc` : mappe les noms de clés du .env du bot (BITGET_API_SECRET /
    BITGET_API_PASSPHRASE) vers ceux attendus par l'Agent Hub (BITGET_SECRET_KEY /
    BITGET_PASSPHRASE). PUR si on injecte base/dotenv_vals. Aucune clé n'est journalisée."""
    import os
    env = dict(os.environ if base is None else base)
    if dotenv_vals is None:
        try:
            from dotenv import dotenv_values
            dotenv_vals = dotenv_values()
        except Exception:
            dotenv_vals = {}
    aliases = {"BITGET_API_KEY": ["BITGET_API_KEY"],
               "BITGET_SECRET_KEY": ["BITGET_SECRET_KEY", "BITGET_API_SECRET"],
               "BITGET_PASSPHRASE": ["BITGET_PASSPHRASE", "BITGET_API_PASSPHRASE"]}
    for target, sources in aliases.items():
        if not env.get(target):
            for s in sources:
                v = env.get(s) or (dotenv_vals or {}).get(s)
                if v:
                    env[target] = v
                    break
    return env


def _read(args, runner=None):
    """Exécute une commande de LECTURE de l'Agent Hub et renvoie le JSON. Best-effort
    (None si absent/erreur). Force --read-only. `runner` injectable pour les tests."""
    if runner is None:
        if not available():
            return None
        def runner(a):
            return subprocess.run([HUB_CLI, "--read-only", *a], capture_output=True,
                                  text=True, timeout=20, env=_hub_env()).stdout
    try:
        out = runner(args)
        return json.loads(out) if out else None
    except Exception:
        return None


# vrais outils de LECTURE de l'Agent Hub (vérifiés dans bitget-client 1.1.1)
_ASSET_TOOLS = [["account", "get_account_assets"], ["spot", "get_account_assets"]]


def _parse_assets(data):
    """Parse tolérant des outils d'assets de l'Agent Hub. Accepte :
      • all-account-balance : liste de {accountType, usdtBalance} -> ventilation + total ;
      • liste de soldes par coin {coin, available} -> avoirs ;
      • dict type compte {usdtEquity/available}. PUR. None sur erreur API ou vide."""
    if not data:
        return None
    if isinstance(data, dict) and data.get("ok") is False:
        return None
    d = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(d, dict):
        eq = _num(d.get("usdtEquity") or d.get("accountEquity") or d.get("usdtBalance"))
        if eq is not None:
            return {"equity_usdt": eq, "available_usdt": _num(d.get("available")),
                    "accounts": {}, "holdings": {}, "source": "agent_hub"}
        d = [d]
    if isinstance(d, list):
        # ventilation par TYPE de compte (spot/futures/earn/bots/margin/funding)
        if d and isinstance(d[0], dict) and "accountType" in d[0]:
            accounts = {}
            for row in d:
                at = str(row.get("accountType", "")).lower()
                bal = _num(row.get("usdtBalance"))
                if at and bal is not None:
                    accounts[at] = round(bal, 2)
            if accounts:
                return {"equity_usdt": round(sum(accounts.values()), 2),
                        "available_usdt": accounts.get("spot"),
                        "accounts": accounts, "holdings": {}, "source": "agent_hub"}
        # soldes par coin
        holdings, usdt = {}, None
        for row in d:
            if not isinstance(row, dict):
                continue
            coin = str(row.get("coin") or row.get("coinName") or row.get("marginCoin") or "").upper()
            avail = _num(row.get("available") or row.get("availableBalance") or row.get("usdtEquity"))
            if avail and avail > 0:
                holdings[coin] = avail
            if coin == "USDT":
                usdt = avail
        if holdings or usdt is not None:
            return {"equity_usdt": usdt, "available_usdt": usdt,
                    "accounts": {}, "holdings": holdings, "source": "agent_hub"}
    return None


def account_snapshot(runner=None):
    """État du compte via l'Agent Hub (lecture). Essaie les vrais outils d'assets,
    dégrade vers bitget_balance_reader, puis None. Retourne un dict ou None."""
    for args in _ASSET_TOOLS:
        parsed = _parse_assets(_read(args, runner=runner))
        if parsed:
            return parsed
    # repli : lecteur de solde signé déjà présent dans le dépôt (lecture seule)
    try:
        import bitget_balance_reader as br
        res = br.get_futures_accounts()
        accts = res.get("data", []) if isinstance(res, dict) else []
        if accts:
            a0 = accts[0]
            return {"equity_usdt": _num(a0.get("usdtEquity")),
                    "available_usdt": _num(a0.get("available")),
                    "holdings": {}, "source": "balance_reader"}
    except Exception:
        pass
    return None


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---------- GARDE DE MANDAT (advisory, pur) ----------

def gate_decision(decision, report=None):
    """Soumet une décision du bot au MANDAT et renvoie un VERDICT. PUR (advisory).

    decision = {market: 'spot'|'futures', symbol, side, agent, conviction, volatility,
                notional_usd, equity_usd, equity_curve, hour_utc, now_ts, macro_events,
                usd_change_pct}. Aucune écriture : on dit seulement ce qui EST autorisé.
    """
    import mandate as m
    d = decision or {}
    reasons, blocks = [], []

    live = m.live_enabled()
    if not live:
        blocks.append("verrou réel coupé (MANDATE_LIVE_ENABLED=False) -> paper")

    # 1. halte drawdown (la limite qui borne « MAX »)
    halt, dd = m.drawdown_halt(d.get("equity_curve", []) or [])
    if halt:
        blocks.append(f"halte drawdown {dd:.1f}% ≥ MDD")

    # 2. black-out macro (CPI/FOMC)
    if m.macro_blackout(d.get("now_ts", 0) or 0, d.get("macro_events", []) or []):
        blocks.append("black-out macro (annonce à fort impact)")

    # 3. porte d'edge pour le FUTURES (un agent doit battre le seuil déflaté)
    if d.get("market") == "futures":
        if not m.futures_live_allowed(d.get("agent"), report):
            blocks.append(f"agent '{d.get('agent')}' ne passe pas la porte d'edge (DSR/échantillon)")

    # 4. levier borné par le mur
    capped_lev = m.target_leverage(d.get("conviction", 0.0) or 0.0,
                                   d.get("volatility", 0.02) or 0.02)
    if d.get("market") == "spot":
        capped_lev = 1.0
        reasons.append("spot : aucun levier")

    # 5. taille ≤ capital déployable (réserve cash gardée)
    eq = _num(d.get("equity_usd")) or 0.0
    cap_notional = m.deployable_usd(eq) if eq > 0 else None
    notional = _num(d.get("notional_usd")) or 0.0
    if cap_notional is not None and notional > cap_notional:
        blocks.append(f"taille {notional:.0f}$ > déployable {cap_notional:.0f}$ (réserve cash)")

    # 6. fenêtre de session (avertissement, ne bloque pas)
    if d.get("hour_utc") is not None and not m.in_active_session(d.get("hour_utc")):
        reasons.append("hors session active (slippage probable)")

    allow = live and not blocks
    return {"allow": allow, "live": live, "blocks": blocks, "notes": reasons,
            "capped_leverage": capped_lev,
            "max_notional_usd": cap_notional,
            "verdict": "AUTORISÉ" if allow else "BLOQUÉ"}


def format_instruction(decision, verdict):
    """Rend des PARAMÈTRES BORNÉS prêts à exécuter — PAR L'AGENT HUB, avec SA
    confirmation. N'encode AUCUNE commande d'écriture (frontière respectée)."""
    d = decision or {}
    if not verdict.get("allow"):
        return (f"[BLOQUÉ] {d.get('market')} {d.get('symbol')} {d.get('side')} — "
                + " ; ".join(verdict.get("blocks", [])) + ". Aucune exécution.")
    return (f"[AUTORISÉ] {d.get('market')} {d.get('symbol')} {d.get('side')} · "
            f"levier ≤×{verdict.get('capped_leverage')} · taille ≤ "
            f"{verdict.get('max_notional_usd')}$ -> exécuter via l'Agent Hub (confirmation requise).")


# ---------- rapport ----------

def build_report():
    hub = available()
    snap = account_snapshot() if hub else None
    lines = ["=== PONT BITGET AGENT HUB <-> BOT (lecture seule + mandat) ==="]
    lines.append(f"Agent Hub (`bgc`) détecté : {'oui' if hub else 'non (paper / advisory seulement)'}")
    if snap:
        acc = snap.get("accounts") or {}
        if acc:
            lines.append(f"Portefeuille total : {snap.get('equity_usdt')} USDT ({snap.get('source')})")
            lines.append("  " + " · ".join(f"{k} {v}" for k, v in acc.items()))
        else:
            lines.append(f"Compte (lecture) : USDT dispo {snap.get('available_usdt')} "
                         f"({snap.get('source')})")
        hold = snap.get("holdings") or {}
        if hold:
            top = ", ".join(f"{c} {v}" for c, v in list(hold.items())[:8])
            lines.append(f"Avoirs : {top}")
    else:
        lines.append("Compte : non lu (Agent Hub absent ou clés non fournies) — normal en paper.")
    try:
        import mandate as m
        lines.append(f"Mandat : verrou réel {'ARMÉ' if m.live_enabled() else 'VERROUILLÉ'} "
                     f"· levier ≤×{m.max_leverage()} · agents futures réels : "
                     f"{m.live_agents() or 'aucun'}")
    except Exception:
        pass
    lines.append("Aucune écriture passée ici. Exécution = Agent Hub (confirmation). VERDICT: SAFE")
    return "\n".join(lines)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
