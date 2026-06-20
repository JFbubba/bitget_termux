import os
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv(dotenv_path=Path(".env"))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN manquant dans .env")

if not CHAT_ID:
    raise RuntimeError("TELEGRAM_CHAT_ID manquant dans .env")


def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(f"Erreur Telegram: {data}")

    return data


if __name__ == "__main__":
    send_message(
        "✅ Bitget Local Agent connecté à Telegram.\n"
        "Mode actuel: monitoring uniquement.\n"
        "Aucun ordre envoyé."
    )

    print("Message Telegram envoyé.")
