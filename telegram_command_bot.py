import os
import time
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv

import config
from telegram_notifier import send_telegram_message


load_dotenv(dotenv_path=Path(".env"))

TOKEN = os.getenv("COMMAND_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN manquant dans .env")

if not ALLOWED_CHAT_ID:
    raise RuntimeError("TELEGRAM_CHAT_ID manquant dans .env")


OFFSET_FILE = Path("telegram_offset.txt")
PAUSE_FILE = Path("agent_paused.flag")


def get_offset():
    if not OFFSET_FILE.exists():
        return None

    value = OFFSET_FILE.read_text().strip()

    if not value:
        return None

    return int(value)


def save_offset(offset):
    OFFSET_FILE.write_text(str(offset))


def telegram_get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

    params = {
        "timeout": 20,
    }

    if offset is not None:
        params["offset"] = offset

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(f"Erreur Telegram getUpdates: {data}")

    return data.get("result", [])


def get_compact_report_text():
    result = subprocess.run(
        ["python", "compact_report.py"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return (
            "❌ Erreur compact_report.py\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    return result.stdout


def build_config_text():
    return (
        "⚙️ CONFIG ACTUELLE\n\n"
        f"Symboles: {', '.join(config.SYMBOLS)}\n"
        f"Product type: {config.PRODUCT_TYPE}\n"
        f"Timeframe: {config.TIMEFRAME}\n"
        f"Limite bougies: {config.CANDLE_LIMIT}\n"
        f"Risque par trade: {config.RISK_PER_TRADE_PERCENT}%\n"
        f"Levier implicite max: {config.MAX_IMPLIED_LEVERAGE}x\n"
        f"Hedge mode: {config.HEDGE_MODE}\n"
        f"Intervalle boucle: {config.LOOP_INTERVAL_SECONDS // 60} min\n"
    )


def handle_command(text):
    text = text.strip()

    if text == "/start":
        return (
            "✅ Bitget Local Agent connecté.\n\n"
            "Commandes disponibles:\n"
            "/status - rapport compact\n"
            "/config - configuration actuelle\n"
            "/config_guard - limites de configuration\n"
            "/hub - tableau de bord local\n"
            "/agents - liste des agents\n"
            "/security - audit sécurité\n"
            "/getagent_audit - audit du skill GetAgent\n"
            "/git_version - version Git du dépôt (lecture seule)\n"
            "/system_health - bilan de santé du système (lecture seule)\n"
            "/watchdog - état de la boucle agent_loop (lecture seule)\n"
            "/stats - statistiques TP/SL par symbole et sens (lecture seule)\n"
            "/orderflow [SYMBOL] - microstructure: carnet, CVD, OI, funding (lecture seule)\n"
            "/macro - contexte macro risk-on/off: VIX, courbe 2s10s, DXY (lecture seule)\n"
            "/confluence SYMBOL SIDE - signal vs carnet/CVD/macro (lecture seule)\n"
            "/ask QUESTION - assistant IA (langage naturel, lecture seule)\n"
            "/forget - efface la mémoire de conversation de l'assistant\n"
            "/price SYMBOLES - prix & market cap (ex. /price BTC ETH)\n"
            "/news [DEVISES] - dernières news crypto (ex. /news BTC,ETH)\n"
            "/feargreed - indice Fear & Greed crypto\n"
            "/defi - TVL DeFi + top chaines (DefiLlama)\n"
            "/rugcheck ADRESSE [chain] - détection rug/honeypot d’un token\n"
            "/dexsearch REQUETE - recherche de paires DEX (DexScreener)\n"
            "/envcheck - quelles clés API sont configurées (sans révéler les valeurs)\n"
            "/signals - propositions d’ordres sans exécution\n"
            "/preorders - pré-ordres verrouillés sans exécution\n"
            "/approve_preorder ID - approuve un pré-ordre en simulation uniquement\n"
            "/approval_journal - dernières validations simulées\n"
            "/dry_run_order ID - simule l’exécution sans ordre réel\n"
            "/execution_journal - dernières simulations d’exécution\n"
            "/paper_positions - positions paper ouvertes\n"
            "/paper_journal - dernières fermetures paper TP/SL\n"
            "/guard_journal - derniers blocages pré-ordres OBSERVATION\n"
            "/run_once - lancer un cycle maintenant\n"
            "/pause - mettre l’agent en pause\n"
            "/resume - relancer l’agent\n"
            "/pause_status - voir l’état pause\n"
            "/help - aide"
        )

    if text == "/help":
        return (
            "Commandes disponibles:\n"
            "/status - envoie le rapport compact\n"
            "/config - affiche les paramètres actuels\n"
            "/config_guard - affiche les limites de configuration\n"
            "/hub - affiche le tableau de bord local\n"
            "/agents - affiche le manifest des agents\n"
            "/security - lance le Security Agent\n"
            "/getagent_audit - audite le skill GetAgent\n"
            "/git_version - affiche la version Git (commit, branche, tag, état)\n"
            "/system_health - affiche le bilan de santé (lecture seule)\n"
            "/watchdog - vérifie si agent_loop tourne (lecture seule)\n"
            "/stats - statistiques des résultats finalisés (TP/SL)\n"
            "/orderflow [SYMBOL] - carnet, CVD, open interest, funding (lecture seule)\n"
            "/macro - VIX / courbe des taux / DXY -> régime risk-on/off (lecture seule)\n"
            "/confluence SYMBOL SIDE - confluence signal + microstructure + macro\n"
            "/ask QUESTION - assistant IA conversationnel (lecture seule)\n"
            "/price SYMBOLES · /news [DEVISES] - prix & news\n"
            "/feargreed - Fear & Greed · /defi - TVL DefiLlama\n"
            "/rugcheck ADRESSE [chain] - détection rug/honeypot\n"
            "/dexsearch REQUETE - paires DEX (DexScreener)\n"
            "/envcheck - clés API configurées (longueurs seulement)\n"
            "/signals - génère les propositions d’ordres\n"
            "/preorders - affiche les pré-ordres verrouillés\n"
            "/approve_preorder ID - validation simulée, aucun ordre réel\n"
            "/approval_journal - affiche les dernières validations simulées\n"
            "/dry_run_order ID - exécution dry-run uniquement\n"
            "/execution_journal - affiche les derniers dry-run\n"
            "/paper_positions - affiche les positions paper ouvertes\n"
            "/paper_journal - affiche les dernières fermetures paper\n"
            "/guard_journal - affiche les derniers blocages OBSERVATION\n"
            "/run_once - lance un cycle complet maintenant\n"
            "/pause - met l’agent en pause\n"
            "/resume - relance l’agent\n"
            "/pause_status - affiche l’état pause\n"
            "/help - aide\n\n"
            "Mode actuel: monitoring / paper / lecture seule.\n"
            "Aucun ordre réel n’est envoyé."
        )

    if text == "/status":
        return (
            "📊 BITGET LOCAL AGENT\n"
            "Mode: monitoring / paper / lecture seule\n\n"
            f"{get_compact_report_text()}"
        )

    if text == "/config":
        return build_config_text()

    if text == "/config_guard":
        result = subprocess.run(
            ["python", "config_guard_agent.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur config_guard_agent.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/hub":
        result = subprocess.run(
            ["python", "agent_hub.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur agent_hub.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/agents":
        result = subprocess.run(
            ["python", "agents_manifest.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur agents_manifest.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/security":
        result = subprocess.run(
            ["python", "security_agent.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur security_agent.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/git_version":
        result = subprocess.run(
            ["python", "git_version.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur git_version.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/system_health":
        result = subprocess.run(
            ["python", "system_health.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur system_health.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text.startswith("/orderflow"):
        parts = text.split(maxsplit=1)
        symbol = parts[1].strip().upper() if len(parts) > 1 else "BTCUSDT"

        result = subprocess.run(
            ["python", "bitget_market_data.py", symbol],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur bitget_market_data.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text.startswith("/confluence"):
        parts = text.split()
        if len(parts) < 3:
            return "Usage: /confluence SYMBOL SIDE\nex. /confluence BTCUSDT LONG"
        symbol, side = parts[1].upper(), parts[2].upper()
        result = subprocess.run(
            ["python", "confluence_score.py", symbol, side],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return (
                "❌ Erreur confluence_score.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )
        return result.stdout

    if text == "/forget":
        result = subprocess.run(["python", "assistant/agent.py", "--reset"], capture_output=True, text=True, timeout=30)
        return result.stdout if result.returncode == 0 else f"❌ {result.stderr[-1500:]}"

    if text.startswith("/ask"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: /ask ta question\nex. /ask analyse l'order flow de BTC et le sentiment"
        result = subprocess.run(
            ["python", "assistant/agent.py", parts[1]],
            capture_output=True, text=True, timeout=180,
        )
        return result.stdout if result.returncode == 0 else f"❌ assistant\n{result.stderr[-1500:]}"

    if text.startswith("/news"):
        parts = text.split()
        args = ["python", "news_feed.py"] + ([parts[1]] if len(parts) > 1 else [])
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return result.stdout if result.returncode == 0 else f"❌ news_feed.py\n{result.stderr[-1500:]}"

    if text.startswith("/price"):
        parts = text.split()
        if len(parts) < 2:
            return "Usage: /price BTC ETH SOL"
        result = subprocess.run(["python", "coingecko_data.py"] + parts[1:], capture_output=True, text=True, timeout=30)
        return result.stdout if result.returncode == 0 else f"❌ coingecko_data.py\n{result.stderr[-1500:]}"

    if text == "/feargreed":
        result = subprocess.run(["python", "sentiment_index.py"], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else f"❌ sentiment_index.py\n{result.stderr[-1500:]}"

    if text == "/defi":
        result = subprocess.run(["python", "defi_data.py"], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else f"❌ defi_data.py\n{result.stderr[-1500:]}"

    if text.startswith("/rugcheck"):
        parts = text.split()
        if len(parts) < 2:
            return "Usage: /rugcheck ADRESSE [chain]\nex. /rugcheck 0x... eth\n/rugcheck <mint> solana"
        address = parts[1]
        chain = parts[2] if len(parts) > 2 else "eth"
        result = subprocess.run(["python", "token_safety.py", address, chain], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else f"❌ token_safety.py\n{result.stderr[-1500:]}"

    if text.startswith("/dexsearch"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: /dexsearch REQUETE\nex. /dexsearch SOL"
        result = subprocess.run(["python", "dex_scanner.py", parts[1]], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else f"❌ dex_scanner.py\n{result.stderr[-1500:]}"

    if text == "/envcheck":
        result = subprocess.run(["python", "check_env.py"], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else f"❌ check_env.py\n{result.stderr[-1500:]}"

    if text == "/macro":
        result = subprocess.run(
            ["python", "macro_context.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur macro_context.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/stats":
        result = subprocess.run(
            ["python", "stats_report.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur stats_report.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/watchdog":
        result = subprocess.run(
            ["python", "watchdog.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur watchdog.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/getagent_audit":
        result = subprocess.run(
            ["python", "getagent_audit.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur getagent_audit.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/signals":
        result = subprocess.run(
            ["python", "order_signal_engine.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur order_signal_engine.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/preorders":
        result = subprocess.run(
            ["python", "preorder_engine.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur preorder_engine.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text.startswith("/approve_preorder"):
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            return (
                "Usage:\n"
                "/approve_preorder ORDER_ID\n\n"
                "Simulation uniquement. Aucun ordre réel envoyé."
            )

        order_id = parts[1].strip()

        result = subprocess.run(
            ["python", "preorder_approval.py", "approve", order_id],
            capture_output=True,
            text=True,
        )

        output = result.stdout.strip()

        if result.stderr:
            output += "\n\nSTDERR:\n" + result.stderr[-1500:]

        if not output:
            output = "Aucune réponse de preorder_approval.py"

        return output

    if text == "/approval_journal":
        path = Path("preorder_approvals_journal.jsonl")

        if not path.exists():
            return "Aucun journal de validation trouvé."

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        recent = lines[-8:]

        if not recent:
            return "Journal de validation vide."

        return "=== APPROVAL JOURNAL ===\n" + "\n".join(recent)

    if text.startswith("/dry_run_order"):
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            return (
                "Usage:\n"
                "/dry_run_order ORDER_ID\n\n"
                "DRY_RUN_ONLY. Aucun ordre réel envoyé."
            )

        order_id = parts[1].strip()

        result = subprocess.run(
            ["python", "execution_gateway.py", "dry_run", order_id],
            capture_output=True,
            text=True,
        )

        output = result.stdout.strip()

        if result.stderr:
            output += "\n\nSTDERR:\n" + result.stderr[-1500:]

        if not output:
            output = "Aucune réponse de execution_gateway.py"

        return output

    if text == "/execution_journal":
        path = Path("execution_dry_run_journal.jsonl")

        if not path.exists():
            return "Aucun journal d’exécution dry-run trouvé."

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        recent = lines[-8:]

        if not recent:
            return "Journal d’exécution dry-run vide."

        return "=== EXECUTION DRY-RUN JOURNAL ===\n" + "\n".join(recent)

    if text == "/paper_positions":
        result = subprocess.run(
            ["python", "paper_positions.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur paper_positions.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return result.stdout

    if text == "/paper_journal":
        path = Path("paper_positions_journal.jsonl")

        if not path.exists():
            return "Aucun journal paper trouvé. Aucune position paper fermée pour l’instant."

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        recent = lines[-8:]

        if not recent:
            return "Journal paper vide."

        return "=== PAPER POSITION JOURNAL ===\n" + "\n".join(recent)

    if text == "/guard_journal":
        import json
        from pathlib import Path

        path = Path("preorder_guard_journal.jsonl")

        if not path.exists():
            return "Aucun journal guard trouvé. Aucun blocage OBSERVATION journalisé pour l’instant."

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        recent = lines[-8:]

        if not recent:
            return "Journal guard vide."

        output = ["=== PREORDER GUARD JOURNAL ==="]

        for line in recent:
            try:
                event = json.loads(line)
                output.append(
                    f"{event.get('timestamp')} | "
                    f"{event.get('action')} | "
                    f"mode={event.get('mode')} | "
                    f"neg={event.get('negative_count')} | "
                    f"bloqués={event.get('blocked_count')}"
                )

                ids = event.get("blocked_order_ids") or []
                if ids:
                    output.append("  IDs: " + ", ".join(ids[:5]))

            except Exception:
                output.append(line[:500])

        return "\n".join(output)

    if text == "/run_once":
        send_telegram_message("▶️ Cycle manuel lancé. Attends le rapport de fin.")
        result = subprocess.run(
            ["python", "agent_control.py"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return (
                "❌ Erreur pendant agent_control.py\n\n"
                f"STDOUT:\n{result.stdout[-2500:]}\n\n"
                f"STDERR:\n{result.stderr[-2500:]}"
            )

        return (
            "✅ Cycle manuel terminé.\n"
            "Le rapport compact a été envoyé séparément par agent_control.py."
        )

    if text == "/pause":
        PAUSE_FILE.write_text("paused\n")
        return "⏸ Agent mis en pause. Le scan sera bloqué au prochain cycle."

    if text == "/resume":
        if PAUSE_FILE.exists():
            PAUSE_FILE.unlink()
        return "▶️ Agent relancé. Le scan sera autorisé au prochain cycle."

    if text == "/pause_status":
        if PAUSE_FILE.exists():
            return "⏸ État: agent en pause."
        return "▶️ État: agent actif."

    return (
        "Commande inconnue.\n"
        "Utilise /help pour voir les commandes disponibles."
    )


def main():
    print("=== TELEGRAM COMMAND BOT ===")
    print("Commandes actives: /status /config /config_guard /hub /agents /security /getagent_audit /git_version /system_health /watchdog /stats /orderflow /macro /confluence /ask /forget /price /news /feargreed /defi /rugcheck /dexsearch /envcheck /signals /preorders /approve_preorder /approval_journal /dry_run_order /execution_journal /paper_positions /paper_journal /guard_journal /run_once /pause /resume /pause_status /help")
    print("Sécurité: seul le chat_id configuré est autorisé.")
    print("Arrêt manuel: CTRL + C")
    print()

    offset = get_offset()

    while True:
        updates = telegram_get_updates(offset=offset)

        for update in updates:
            update_id = update["update_id"]
            offset = update_id + 1
            save_offset(offset)

            message = update.get("message")

            if not message:
                continue

            chat = message.get("chat", {})
            chat_id = str(chat.get("id"))
            text = message.get("text", "")

            if chat_id != str(ALLOWED_CHAT_ID):
                print(f"Message refusé depuis chat_id non autorisé: {chat_id}")
                continue

            print(f"Commande reçue: {text}")

            reply = handle_command(text)
            send_telegram_message(reply)

        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("Arrêt manuel détecté.")
        print("Bot Telegram arrêté proprement.")
