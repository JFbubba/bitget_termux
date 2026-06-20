import os
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv(dotenv_path=Path(".env"))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN manquant dans .env")


def main():
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

    response = requests.get(url, timeout=10)
    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        print("Erreur Telegram:")
        print(data)
        return

    results = data.get("result", [])

    if not results:
        print("Aucun message reçu.")
        print("Ouvre ton bot Telegram et envoie-lui /start, puis relance ce script.")
        return

    print("=== TELEGRAM CHAT IDS ===")

    for update in results:
        message = update.get("message") or update.get("edited_message")

        if not message:
            continue

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        chat_type = chat.get("type")
        username = chat.get("username")
        first_name = chat.get("first_name")
        text = message.get("text", "")

        print()
        print(f"chat_id: {chat_id}")
        print(f"type: {chat_type}")
        print(f"username: {username}")
        print(f"first_name: {first_name}")
        print(f"dernier message: {text}")


if __name__ == "__main__":
    main()
