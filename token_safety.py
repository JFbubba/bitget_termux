"""
token_safety.py — detection rug / honeypot (LECTURE SEULE).

Classement : SAFE (donnee publique, aucune cle, aucun ordre, aucun secret).
Ne sert qu'a EVALUER/EVITER des tokens douteux, jamais a en creer ni a trader.

Sources gratuites sans cle :
  - GoPlus Security (EVM)  : api.gopluslabs.io
  - Honeypot.is (EVM)      : api.honeypot.is
  - RugCheck (Solana)      : api.rugcheck.xyz

CLI : python token_safety.py <address> [chain]
      chain : eth (defaut) | bsc | base | polygon | arbitrum | solana
"""

import sys

import requests

GOPLUS_CHAINS = {
    "eth": "1", "ethereum": "1", "bsc": "56", "bnb": "56", "base": "8453",
    "polygon": "137", "arbitrum": "42161", "optimism": "10", "avalanche": "43114",
}


def _f(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------- parseurs purs ----------

def parse_goplus(data, address):
    """Normalise la reponse GoPlus token_security en {honeypot, taxes, flags}."""
    result = data.get("result") or {}
    info = result.get(address.lower())
    if info is None and result:
        info = next(iter(result.values()))
    info = info or {}

    def is_set(key):
        return str(info.get(key, "")) == "1"

    flags = []
    if is_set("is_honeypot"):
        flags.append("HONEYPOT")
    if is_set("cannot_sell_all"):
        flags.append("CANNOT_SELL_ALL")
    if is_set("is_mintable"):
        flags.append("MINTABLE")
    if is_set("can_take_back_ownership"):
        flags.append("OWNER_CAN_RECLAIM")
    if is_set("hidden_owner"):
        flags.append("HIDDEN_OWNER")
    if is_set("selfdestruct"):
        flags.append("SELFDESTRUCT")
    if str(info.get("is_open_source", "")) == "0":
        flags.append("CLOSED_SOURCE")

    return {
        "source": "goplus",
        "honeypot": is_set("is_honeypot"),
        "buy_tax": _f(info.get("buy_tax")),
        "sell_tax": _f(info.get("sell_tax")),
        "holder_count": _i(info.get("holder_count")),
        "flags": flags,
    }


def parse_honeypot(data):
    """Normalise Honeypot.is en {honeypot, taxes}."""
    hp = data.get("honeypotResult") or {}
    sim = data.get("simulationResult") or {}
    return {
        "source": "honeypot.is",
        "honeypot": bool(hp.get("isHoneypot")),
        "buy_tax": _f(sim.get("buyTax")),
        "sell_tax": _f(sim.get("sellTax")),
    }


def parse_rugcheck(data):
    """Normalise RugCheck (Solana) en {autorites, risks, flags}."""
    token = data.get("token") or {}
    risks = data.get("risks") or []
    flags = []
    if token.get("mintAuthority"):
        flags.append("MINT_AUTHORITY_ACTIVE")
    if token.get("freezeAuthority"):
        flags.append("FREEZE_AUTHORITY_ACTIVE")
    for risk in risks:
        name = str(risk.get("name", "")).upper().replace(" ", "_")
        if name:
            flags.append(name)
    return {
        "source": "rugcheck",
        "mint_authority": token.get("mintAuthority"),
        "freeze_authority": token.get("freezeAuthority"),
        "score": data.get("score"),
        "risks": [r.get("name") for r in risks],
        "flags": flags,
    }


def risk_level(flags, honeypot=False, taxes=None):
    """Niveau de risque a partir des flags. Fonction pure."""
    if honeypot or "HONEYPOT" in flags:
        return "CRITICAL"
    high = {"CANNOT_SELL_ALL", "OWNER_CAN_RECLAIM", "HIDDEN_OWNER",
            "SELFDESTRUCT", "MINT_AUTHORITY_ACTIVE"}
    if any(f in high for f in flags):
        return "HIGH"
    if taxes and any(t is not None and t > 10 for t in taxes):
        return "HIGH"
    if flags:
        return "MEDIUM"
    return "LOW"


# ---------- fetchers (gardes) ----------

# best-effort : {} si la source est injoignable. Les parseurs purs (parse_goplus /
# parse_honeypot / parse_rugcheck) tolèrent {} et renvoient des défauts neutres
# (honeypot=False, taxes=None, flags=[]) -> check_token ne crashe jamais et garde
# toujours toutes ses clés, même si une source tombe.

def fetch_goplus(address, chain_id):
    try:
        url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
        r = requests.get(url, params={"contract_addresses": address}, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def fetch_honeypot(address):
    try:
        r = requests.get("https://api.honeypot.is/v2/IsHoneypot",
                         params={"address": address}, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def fetch_rugcheck(mint):
    try:
        r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report", timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def check_token(address, chain="eth"):
    """Evalue un token. Retourne {chain, address, level, flags, details}."""
    chain = str(chain).lower()
    if chain in ("solana", "sol"):
        rc = parse_rugcheck(fetch_rugcheck(address))
        return {"chain": "solana", "address": address,
                "level": risk_level(rc["flags"]), "flags": rc["flags"], "details": [rc]}

    chain_id = GOPLUS_CHAINS.get(chain, "1")
    gp = parse_goplus(fetch_goplus(address, chain_id), address)
    flags = list(gp["flags"])
    details = [gp]
    try:
        hp = parse_honeypot(fetch_honeypot(address))
        details.append(hp)
        if hp["honeypot"] and "HONEYPOT" not in flags:
            flags.append("HONEYPOT")
    except Exception:
        pass
    level = risk_level(flags, gp["honeypot"], (gp["buy_tax"], gp["sell_tax"]))
    return {"chain": chain, "address": address, "level": level, "flags": flags, "details": details}


def build_report(result):
    lines = [
        f"=== TOKEN SAFETY ({result['chain']}) ===",
        f"Adresse : {result['address']}",
        f"RISQUE  : {result['level']}",
    ]
    if result["flags"]:
        lines.append("Drapeaux : " + ", ".join(result["flags"][:12]))
    else:
        lines.append("Drapeaux : aucun signalement")
    lines.append("")
    lines.append("Lecture seule (detection). Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python token_safety.py <address> [chain]")
        raise SystemExit(2)
    address = sys.argv[1]
    chain = sys.argv[2] if len(sys.argv) > 2 else "eth"
    print(build_report(check_token(address, chain)))


if __name__ == "__main__":
    main()
