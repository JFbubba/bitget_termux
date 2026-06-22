"""
check_env.py — verifie quelles cles sont presentes dans le .env.

Classement : SAFE. N'AFFICHE JAMAIS la valeur d'une cle : seulement
OK + le nombre de caracteres, ou MANQUANT. Aucun secret n'est revele,
aucun ordre, aucune ecriture.

CLI : python check_env.py
"""

import os

try:  # python-dotenv est present sur le VPS (requirements) ; optionnel ailleurs
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # sans dotenv on lit directement os.environ

# Cles indispensables pour faire tourner le moteur + les notifs.
REQUIRED = [
    "BITGET_API_KEY",
    "BITGET_API_SECRET",
    "BITGET_API_PASSPHRASE",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]

# Cles optionnelles par usage (le systeme tourne sans, en mode degrade).
OPTIONAL = {
    "X / Twitter (lecture sentiment)": [
        "X_BEARER_TOKEN", "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET",
    ],
    "Assistant conversationnel (LLM)": ["ANTHROPIC_API_KEY"],
    "Data (cles gratuites)": [
        "COINGECKO_API_KEY", "CRYPTOPANIC_API_TOKEN", "FMP_API_KEY", "FINNHUB_API_KEY",
        "FRED_API_KEY", "BIRDEYE_API_KEY", "HELIUS_API_KEY", "NEYNAR_API_KEY",
        "LUNARCRUSH_API_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "KALSHI_API_KEY",
    ],
}


def status_line(name, value, optional=False):
    """Ligne d'etat masquee : ne contient JAMAIS la valeur (longueur seule)."""
    if value:
        return f"  {name}: OK ({len(value)} caracteres)"
    return f"  {name}: {'(optionnel) non defini' if optional else 'MANQUANT'}"


def build_report():
    lines = ["=== CHECK ENV (aucune valeur affichee, longueurs seulement) ===", "", "Obligatoires :"]
    missing = 0
    for name in REQUIRED:
        value = os.getenv(name)
        if not value:
            missing += 1
        lines.append(status_line(name, value))
    for group, names in OPTIONAL.items():
        lines.append("")
        lines.append(f"{group} :")
        for name in names:
            lines.append(status_line(name, os.getenv(name), optional=True))
    lines.append("")
    if missing == 0:
        lines.append("Resultat: cles obligatoires presentes. .env OK.")
    else:
        lines.append(f"Resultat: {missing} cle(s) obligatoire(s) manquante(s).")
    return "\n".join(lines)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
