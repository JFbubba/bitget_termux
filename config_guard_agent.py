import config


# tf-ladder-ok : dict de LIMITES de config (les TF y sont des valeurs autorisées opérationnelles, pas un test)
SAFE_LIMITS = {
    "RISK_PER_TRADE_PERCENT": {
        "min": 0.1,
        "max": 2.0,
        "current": config.RISK_PER_TRADE_PERCENT,
        "unit": "%",
        "editable": True,
    },
    "MAX_IMPLIED_LEVERAGE": {
        "min": 1.0,
        "max": 3.0,
        "current": config.MAX_IMPLIED_LEVERAGE,
        "unit": "x",
        "editable": True,
    },
    "TIMEFRAME": {
        "allowed": ["5m", "15m", "30m", "1H", "4H"],
        "current": config.TIMEFRAME,
        "editable": True,
    },
    "SYMBOLS": {
        "current": config.SYMBOLS,
        "editable": True,
        "rule": "Symboles USDT futures uniquement. Exemple: BTCUSDT.",
    },
    "LOOP_INTERVAL_SECONDS": {
        "min": 300,
        "max": 3600,
        "current": config.LOOP_INTERVAL_SECONDS,
        "unit": "seconds",
        "editable": True,
    },
    "PRODUCT_TYPE": {
        "current": config.PRODUCT_TYPE,
        "editable": False,
        "reason": "Ne pas modifier sans revoir toute l’API Bitget.",
    },
    "HEDGE_MODE": {
        "current": config.HEDGE_MODE,
        "editable": False,
        "reason": "Dépend de la logique des positions ouvertes.",
    },
}


def validate_numeric(name, value):
    rules = SAFE_LIMITS[name]

    if not rules.get("editable"):
        return False, f"{name} n’est pas modifiable."

    try:
        numeric_value = float(value)
    except ValueError:
        return False, f"{name} doit être un nombre."

    if numeric_value < rules["min"]:
        return False, f"{name} trop bas. Minimum: {rules['min']}."

    if numeric_value > rules["max"]:
        return False, f"{name} trop haut. Maximum: {rules['max']}."

    return True, f"{name} accepté: {numeric_value}{rules.get('unit', '')}."


def validate_timeframe(value):
    rules = SAFE_LIMITS["TIMEFRAME"]

    if value not in rules["allowed"]:
        return False, f"TIMEFRAME refusé. Valeurs autorisées: {', '.join(rules['allowed'])}."

    return True, f"TIMEFRAME accepté: {value}."


def validate_symbol(symbol):
    symbol = symbol.strip().upper()

    if not symbol.endswith("USDT"):
        return False, "Symbole refusé: doit finir par USDT."

    if not symbol.isalnum():
        return False, "Symbole refusé: caractères invalides."

    if len(symbol) < 6 or len(symbol) > 15:
        return False, "Symbole refusé: longueur suspecte."

    return True, f"Symbole accepté: {symbol}."


def print_guard_report():
    print("=== CONFIG GUARD AGENT ===")
    print()

    print("Paramètres modifiables:")
    for name, rules in SAFE_LIMITS.items():
        if rules.get("editable"):
            print(f"- {name}: actuel={rules['current']}")

            if "min" in rules and "max" in rules:
                print(f"  Limites: {rules['min']} → {rules['max']} {rules.get('unit', '')}")

            if "allowed" in rules:
                print(f"  Autorisés: {', '.join(rules['allowed'])}")

            if "rule" in rules:
                print(f"  Règle: {rules['rule']}")

    print()

    print("Paramètres verrouillés:")
    for name, rules in SAFE_LIMITS.items():
        if not rules.get("editable"):
            print(f"- {name}: actuel={rules['current']}")
            print(f"  Raison: {rules.get('reason', 'verrouillé par sécurité')}")

    print()

    print("Verdict:")
    print("- Configuration modifiable uniquement dans les limites définies.")
    print("- Aucun changement automatique n’est appliqué par ce fichier.")
    print("- Ce module prépare les futures commandes Telegram sécurisées.")


if __name__ == "__main__":
    print_guard_report()
