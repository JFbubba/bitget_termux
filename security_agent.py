from pathlib import Path

from agents_manifest import AGENTS


ENV_FILE = Path(".env")
PAUSE_FILE = Path("agent_paused.flag")

GETAGENT_PATHS = [
    Path.home() / ".codex" / "skills" / "getagent",
    Path.home() / ".claude" / "skills" / "getagent",
    Path.home() / ".cursor" / "skills" / "getagent",
]

SENSITIVE_FILENAMES = [
    ".env",
]

DANGEROUS_KEYWORDS = [
    "place_order", "open_long", "open_short", "close_position",
    "cancel_order", "change_leverage", "transfer", "withdraw",
    "send_order", "create_order", "submit_order", "set_leverage",
    "market_order", "limit_order", "post_order",
    "placeorder", "createorder", "submitorder", "cancelorder",
    "closeposition", "setleverage", "createmarketorder", "createlimitorder",
    "order/place", "/api/v2/mix/order", "/api/mix/v1/order",
    "batch-place-order", "place-order", "close-positions",
]

# Module d'exécution AUTORISÉ (achat spot BTC seul). Il a le DROIT de contenir un
# ordre, mais on l'audite différemment : il ne doit JAMAIS contenir de vente/levier/
# futures/retrait, et doit GARDER ses verrous (MANDATE_LIVE + kill_switch).
AUTHORIZED_EXEC_FILES = ["spot_executor.py"]
EXEC_FORBIDDEN = [
    "withdraw", "transfer", "close_position", "close-positions", "closeposition",
    "set_leverage", "change_leverage", "setleverage", "_sell", "sell_",
    "futures_place_order", "futures_set_leverage", "open_long", "open_short",
    "cancel_order", "cancelorder", "margin_",
]
EXEC_REQUIRED_GUARDS = ["mandate_live_enabled", "kill_switch", "confirm"]

# 2e module d'exécution BORNÉ (futures, RESEARCH_NOTES §34). À l'étape 1 il reste DRY-RUN
# (chemin réel non câblé). Audité à part : on TOLÈRE le vocabulaire d'ordre futures borné
# mais on reste STRICT sur ce qui est interdit même au module autorisé (retrait/transfert/
# changement de levier hors mur/vente), et on EXIGE ses verrous (double verrou + edge +
# kill_switch + confirm). Liste séparée -> AUTHORIZED_EXEC_FILES (spot) reste inchangé.
FUTURES_EXEC_FILES = ["futures_executor.py"]
# §45 (02/07/2026, décision propriétaire) : le chemin réel futures est câblé — le
# réglage du levier (BORNÉ au mur ×5 par les gardes) et le side 'sell' (shorts du
# carry/directionnel) font désormais partie du périmètre du module.
# §exec-frais (09/07/2026) : le MODE MAKER (post-only + repli taker) exige d'ANNULER un
# ordre futures NON rempli -> l'annulation FUTURES (futures_cancel_orders) devient
# LÉGITIME. Elle est SÛRE par nature : retirer un ordre du carnet ne peut ni sortir des
# fonds, ni dépasser un cap, ni changer le levier — c'est RÉDUCTEUR de risque. L'ancien
# motif d'interdit "aucun besoin d'annuler (ordres market/IOC)" ne tient plus. Restent
# INTERDITS DURS : retrait, virement, annulation SPOT/MARGE (le module ne touche QUE le
# futures), les noms de vente spot (_sell/sell_), et le MARGIN TRADING — motif précisé
# le 02/07 (option 1) : l'ancien "margin_" large matchait des paramètres API légitimes
# (marginCoin/marginMode via MARGIN_COIN) ; on interdit la liste EXACTE des outils margin.
FUTURES_EXEC_FORBIDDEN = [
    "withdraw", "transfer", "_sell", "sell_",
    # AUCUN tool SPOT ni MARGE : le module ne touche QUE le futures. On cible les NOMS de tools
    # bgc (string literals "spot_..."/"margin_..." via le guillemet ouvrant) -> pas de faux
    # positif sur les paramètres camelCase marginCoin/marginMode. ALLOW-LIST DE FAIT (durci
    # §code-review 09/07) : seuls les tools "futures_..." passent (place/cancel/get_orders/
    # get_fills/get_positions/get_ticker/set_leverage/update_config). Toute surface
    # d'annulation/placement/modification spot ou marge (spot_modify_order, spot_cancel_order,
    # plan_cancel, margin_borrow…) est ainsi bloquée sans avoir à l'énumérer.
    '"spot_', '"margin_', "'spot_", "'margin_",
    "account_transfer", "earn_",
]
FUTURES_EXEC_REQUIRED_GUARDS = [
    "mandate_live_enabled", "futures_autonomous_live", "futures_live_allowed",
    "kill_switch", "confirm",
]

# ---------------------------------------------------------------------------
# Exécuteurs de surface BORNÉS §67 (spot libre, marge iso/cross, virements
# internes, earn). Ils s'appuient sur le NOYAU audité bitget_execute.py (gating
# LIVE défaut OFF + kill-switch fail-closed + caps durs + DRY par défaut). Audit :
#   • RETRAIT (withdraw) interdit PARTOUT (clé Trade-only) — invariant dur ;
#   • le VIREMENT (transfer) n'est autorisé QUE dans account_transfers.py ;
#   • le réglage de levier futures n'a rien à y faire ;
#   • chaque exécuteur DOIT déléguer au noyau (import bitget_execute), avoir un
#     verrou LIVE (_LIVE) et le mode confirm (DRY par défaut).
KERNEL_EXEC_FILE = "bitget_execute.py"
KERNEL_FORBIDDEN = ["withdraw", "transfer", "place_order", "set_leverage", "margin_place_order"]
KERNEL_REQUIRED_GUARDS = ["kill_active", "gate", "capped", "confirm"]

TRADING_EXEC_FILES = ["spot_trader.py", "margin_trader.py", "account_transfers.py", "earn_manager.py"]
TRANSFER_ALLOWED_FILE = "account_transfers.py"   # SEUL fichier autorisé à contenir 'transfer'
TRADING_EXEC_FORBIDDEN = [
    "withdraw", "account withdraw", "withdraw(", "/spot/wallet/withdrawal",
    "set_leverage", "change_leverage", "setleverage",
    "copy_place_order", "broker_", "sub_account", "subaccount",
]
TRADING_EXEC_REQUIRED_GUARDS = ["bitget_execute", "confirm", "_live"]

# Module de DÉCISION liquidité §76 : il DÉCIDE (une action par cycle) et DÉLÈGUE
# toute exécution aux surfaces §67 (account_transfers/earn_manager — qui portent
# verrous LIVE, kill-switch, caps). Il a le droit de NOMMER 'transfer' (délégation)
# mais AUCUN vocabulaire d'écriture directe (ordre, levier, retrait, hub en écriture).
LIQUIDITY_DECISION_FILE = "liquidity_manager.py"
LIQUIDITY_FORBIDDEN = [
    "withdraw", "place_order", "set_leverage", "change_leverage", "setleverage",
    "margin_borrow", "margin_repay", "sub_account", "subaccount", "broker_",
    "hub._write", "hub._exec", "_run_bgc", "order/place",
]
LIQUIDITY_REQUIRED = ["liquidity_auto", "account_transfers", "earn_manager",
                      "confirm", "kill-switch", "fail-closed"]

# Module de DÉCISION carry §82-83 : même classe que la liquidité — il NOMME ses
# délégués (spot_trader/margin_trader/futures_executor/account_transfers, d'où le
# mot 'transfer') mais ne doit contenir AUCUN vocabulaire d'écriture directe.
CARRY_DECISION_FILE = "alt_carry.py"
CARRY_FORBIDDEN = [
    "withdraw", "place_order", "set_leverage", "change_leverage", "setleverage",
    "margin_borrow", "margin_repay", "sub_account", "subaccount", "broker_",
    "hub._write", "hub._exec", "_run_bgc", "order/place",
]
CARRY_REQUIRED = ["alt_carry_live", "spot_trader", "margin_trader", "futures_executor",
                  "account_transfers", "confirm", "compensation", "fail-closed"]

# Module de DÉCISION market making §94 : même classe que liquidité/carry — il
# calcule un plan de cotation et DÉLÈGUE toute écriture à spot_trader (quote/cancel,
# verrous LIVE + caps mm + kill-switch). Aucun vocabulaire d'écriture directe.
MM_DECISION_FILE = "market_maker.py"
MM_FORBIDDEN = [
    "withdraw", "transfer", "place_order", "set_leverage", "change_leverage",
    "setleverage", "margin_borrow", "margin_repay", "sub_account", "subaccount",
    "broker_", "hub._write", "hub._exec", "_run_bgc", "order/place",
]
MM_REQUIRED = ["mm_auto", "spot_trader", "confirm", "kill", "fail-closed"]

# Fichier de STATUT lecture seule §67 : agrège l'état des surfaces pour le dashboard.
# Il référence les noms des exécuteurs (d'où 'transfer') mais ne doit contenir AUCUN
# vocabulaire d'ÉCRITURE — on prouve ainsi qu'il ne peut QUE lire.
STATUS_READONLY_FILES = ["trading_status.py"]
STATUS_FORBIDDEN = [
    "withdraw", "spot_place_order", "margin_place_order", "earn_subscribe_redeem",
    "margin_borrow", "margin_repay", "_run_bgc", "account transfer",
    ".execute(", ".order(", ".borrow(", ".repay(", "confirm=true",
]

FILES_TO_SCAN = [
    "config.py",
    "journal_scanner.py",
    "outcome_state.py",
    "state_report.py",
    "compact_report.py",
    "agent_control.py",
    "agent_loop.py",
    "telegram_notifier.py",
    "telegram_command_bot.py",
    "preorder_approval.py",
    "execution_gateway.py",
    "paper_positions.py",
    "paper_position_reconciler.py",
    "paper_report.py",
    "preorder_engine.py",
    "preorder_guard.py",
    "agent_hub.py",
    "agents_manifest.py",
    "bitget_balance_reader.py",
    "bitget_hub_bridge.py",
    "mandate.py",
    "macro_regime.py",
    "edge_ladder.py",
    "fair_price.py",
    "volatility.py",
    "universe.py",
    "accumulation_engine.py",
    "spot_executor.py",
    "futures_executor.py",
    "bitget_execute.py",
    "spot_trader.py",
    "margin_trader.py",
    "account_transfers.py",
    "earn_manager.py",
    "liquidity_manager.py",
    "alt_carry.py",
    "market_maker.py",
    "mm_lab.py",
    "trade_forensics.py",
    "promotion_board.py",
    "daily_digest.py",
    "backup_restore_drill.py",
    "trading_status.py",
    "account_equity.py",
    "real_positions.py",
    "bitget_explorer.py",
    "dash_chat.py",
    "git_version.py",
    "system_health.py",
    "watchdog.py",
    "stop_guardian.py",
    "failsafe_escalate.py",
    "stats_report.py",
    "pro_indicators.py",
    "order_flow.py",
    "bitget_market_data.py",
    "macro_context.py",
    "macro_data.py",
    "confluence_score.py",
    "regime_gate.py",
    "dashboard/server.py",
    "sentiment_index.py",
    "defi_data.py",
    "token_safety.py",
    "dex_scanner.py",
    "technicals.py",
    "backtest_brain.py",
    "chart.py",
    "aggregated_derivs.py",
    "ccxt_markets.py",
    "polymarket_data.py",
    "risk_manager.py",
    "swarm_brain.py",
    "liquidations.py",
    "econ_calendar.py",
    "arbitrage.py",
    "coingecko_data.py",
    "news_feed.py",
    "check_env.py",
    "derivs_positioning.py",
    "onchain_btc.py",
    "stablecoin_flow.py",
    "deribit_vol.py",
    "flows_agent.py",
    "carry_agent.py",
    "carry_monitor.py",
    "assistant/llm_client.py",
    "assistant/tools.py",
    "assistant/agent.py",
    "assistant/memory.py",
    "assistant/vision.py",
]


def scan_file_for_keywords(filename):
    path = Path(filename)

    if not path.exists():
        return []

    text = path.read_text(errors="ignore").lower()
    findings = []

    for keyword in DANGEROUS_KEYWORDS:
        if keyword.lower() in text:
            findings.append(keyword)

    return findings


def scan_authorized_exec(filename):
    """Audit du module d'exécution AUTORISÉ : il PEUT acheter (spot BTC), mais ne doit
    contenir AUCUN mot interdit (vente/levier/futures/retrait) et DOIT garder ses
    verrous (MANDATE_LIVE_ENABLED, kill_switch, confirm). Retourne la liste des soucis."""
    path = Path(filename)
    if not path.exists():
        return []
    text = path.read_text(errors="ignore").lower()
    issues = []
    for kw in EXEC_FORBIDDEN:
        if kw.lower() in text:
            issues.append(f"interdit:{kw}")
    for guard in EXEC_REQUIRED_GUARDS:
        if guard.lower() not in text:
            issues.append(f"garde manquante:{guard}")
    return issues



def scan_futures_exec(filename):
    """Audit du 2e module d'exécution BORNÉ (futures, §34). Tolère le vocabulaire d'ordre
    futures borné — Y COMPRIS l'annulation FUTURES (mode maker §exec-frais : sûre, retire un
    ordre du carnet) — mais reste STRICT sur l'interdit dur (retrait/transfert/vente/margin,
    et annulation SPOT/MARGE) et EXIGE les verrous (double verrou + edge + kill_switch +
    confirm). Retourne la liste des soucis."""
    path = Path(filename)
    if not path.exists():
        return []
    text = path.read_text(errors="ignore").lower()
    issues = []
    for kw in FUTURES_EXEC_FORBIDDEN:
        if kw.lower() in text:
            issues.append(f"interdit:{kw}")
    for guard in FUTURES_EXEC_REQUIRED_GUARDS:
        if guard.lower() not in text:
            issues.append(f"garde manquante:{guard}")
    return issues


def scan_kernel_exec(filename):
    """Audit du NOYAU d'exécution partagé (bitget_execute.py) : générique et NEUTRE — il
    ne doit contenir AUCUN mot-clé d'ordre/virement/retrait/levier, et DOIT porter la
    logique de sûreté (kill fail-closed, gating, caps, confirm)."""
    path = Path(filename)
    if not path.exists():
        return []
    text = path.read_text(errors="ignore").lower()
    issues = []
    for kw in KERNEL_FORBIDDEN:
        if kw.lower() in text:
            issues.append(f"interdit:{kw}")
    for guard in KERNEL_REQUIRED_GUARDS:
        if guard.lower() not in text:
            issues.append(f"garde manquante:{guard}")
    return issues


def scan_trading_exec(filename):
    """Audit d'un exécuteur de surface borné §67. RETRAIT interdit PARTOUT ; VIREMENT
    autorisé UNIQUEMENT dans account_transfers.py ; délégation au noyau + verrou LIVE +
    confirm EXIGÉS. Retourne la liste des soucis."""
    path = Path(filename)
    if not path.exists():
        return []
    text = path.read_text(errors="ignore").lower()
    issues = []
    forbidden = list(TRADING_EXEC_FORBIDDEN)
    if filename != TRANSFER_ALLOWED_FILE:
        forbidden.append("transfer")            # seul account_transfers peut virer
    for kw in forbidden:
        if kw.lower() in text:
            issues.append(f"interdit:{kw}")
    for guard in TRADING_EXEC_REQUIRED_GUARDS:
        if guard.lower() not in text:
            issues.append(f"garde manquante:{guard}")
    return issues


def scan_liquidity_decision(filename):
    """Audit du module de DÉCISION liquidité (§76) : aucun vocabulaire d'écriture
    directe (le module ne fait que déléguer aux surfaces §67 auditées) ; le gate
    LIQUIDITY_AUTO, la délégation aux deux surfaces, confirm et la mention des
    invariants (kill-switch, fail-closed) DOIVENT être présents."""
    path = Path(filename)
    if not path.exists():
        return []
    text = path.read_text(errors="ignore").lower()
    issues = [f"interdit:{kw}" for kw in LIQUIDITY_FORBIDDEN if kw.lower() in text]
    issues += [f"garde manquante:{req}" for req in LIQUIDITY_REQUIRED
               if req.lower() not in text]
    return issues


def scan_carry_decision(filename):
    """Audit du module de DÉCISION alt-carry (§83) : délégation obligatoire, aucun
    vocabulaire d'écriture directe, compensations et gates présents."""
    path = Path(filename)
    if not path.exists():
        return []
    text = path.read_text(errors="ignore").lower()
    issues = [f"interdit:{kw}" for kw in CARRY_FORBIDDEN if kw.lower() in text]
    issues += [f"garde manquante:{req}" for req in CARRY_REQUIRED
               if req.lower() not in text]
    return issues


def scan_mm_decision(filename):
    """Audit du module de DÉCISION market making (§94) : délégation obligatoire à
    spot_trader, aucun vocabulaire d'écriture directe, gate MM_AUTO + kill-switch +
    fail-closed présents."""
    path = Path(filename)
    if not path.exists():
        return []
    text = path.read_text(errors="ignore").lower()
    issues = [f"interdit:{kw}" for kw in MM_FORBIDDEN if kw.lower() in text]
    issues += [f"garde manquante:{req}" for req in MM_REQUIRED
               if req.lower() not in text]
    return issues


def scan_status_readonly(filename):
    """Audit d'un fichier de STATUT lecture seule §67 : il peut référencer les noms
    d'exécuteurs, mais ne doit contenir AUCUN vocabulaire d'écriture (il ne fait que lire
    l'état armé/caps/dépensé). Retourne la liste des soucis."""
    path = Path(filename)
    if not path.exists():
        return []
    text = path.read_text(errors="ignore").lower()
    return [f"interdit:{kw}" for kw in STATUS_FORBIDDEN if kw.lower() in text]


def telegram_auth_is_present(text):
    import re

    has_const = "ALLOWED_CHAT_ID" in text
    pattern = re.compile(
        r"(chat_id\s*[!=]=\s*str\(\s*ALLOWED_CHAT_ID\s*\)"
        r"|str\(\s*chat_id\s*\)\s*[!=]=\s*ALLOWED_CHAT_ID"
        r"|[!=]=\s*ALLOWED_CHAT_ID"
        r"|is_authorized\s*\()",
        re.IGNORECASE,
    )
    return has_const, bool(pattern.search(text))

def main():
    warnings = []

    print("=== SECURITY AGENT ===")
    print()

    print("Vérification manifest:")
    for agent in AGENTS:
        can_trade = agent.get("can_trade", None)

        if can_trade is not False:
            warnings.append(f"{agent['id']} a can_trade={can_trade}")

        print(f"- {agent['name']}: can_trade={can_trade}")

    print()

    print("Vérification fichiers sensibles:")
    print(f"- .env présent: {ENV_FILE.exists()}")
    print("- contenu .env: non affiché volontairement")
    print()

    print("Vérification pause:")
    print(f"- agent_paused.flag présent: {PAUSE_FILE.exists()}")
    print("- mécanisme pause disponible: True")
    print()

    print("Scan mots-clés dangereux:")
    dangerous_hits = {}

    for filename in FILES_TO_SCAN:
        if filename in FUTURES_EXEC_FILES:
            hits = scan_futures_exec(filename)
            label = "exec futures non conforme"
        elif filename in AUTHORIZED_EXEC_FILES:
            hits = scan_authorized_exec(filename)
            label = "exec autorisé non conforme"
        elif filename == KERNEL_EXEC_FILE:
            hits = scan_kernel_exec(filename)
            label = "noyau exec non conforme"
        elif filename in TRADING_EXEC_FILES:
            hits = scan_trading_exec(filename)
            label = "exec surface non conforme"
        elif filename == LIQUIDITY_DECISION_FILE:
            hits = scan_liquidity_decision(filename)
            label = "décision liquidité non conforme"
        elif filename == CARRY_DECISION_FILE:
            hits = scan_carry_decision(filename)
            label = "décision carry non conforme"
        elif filename == MM_DECISION_FILE:
            hits = scan_mm_decision(filename)
            label = "décision market making non conforme"
        elif filename in STATUS_READONLY_FILES:
            hits = scan_status_readonly(filename)
            label = "statut read-only non conforme"
        else:
            hits = scan_file_for_keywords(filename)
            label = "mots-clés suspects"

        if hits:
            dangerous_hits[filename] = hits
            warnings.append(f"{filename}: {label} {hits}")

        print(f"- {filename}: {'WARNING ' + str(hits) if hits else 'OK'}")

    print()

    print("Vérification GetAgent:")
    getagent_installed = [path for path in GETAGENT_PATHS if path.exists()]
    print(f"- installations détectées: {len(getagent_installed)}")

    for path in GETAGENT_PATHS:
        print(f"- {path}: {'présent' if path.exists() else 'absent'}")

    if getagent_installed:
        print("- statut: WARNING contrôlé")
        print("- raison: GetAgent contient des références à des fonctions de trading réel.")
        print("- règle: aucune clé API live ne doit être fournie à GetAgent.")
    else:
        print("- statut: absent")

    print()

    print("Vérification Telegram:")
    telegram_file = Path("telegram_command_bot.py")
    telegram_text = telegram_file.read_text(errors="ignore") if telegram_file.exists() else ""

    has_allowed_chat = "ALLOWED_CHAT_ID" in telegram_text
    has_chat_check = "chat_id != str(ALLOWED_CHAT_ID)" in telegram_text

    print(f"- ALLOWED_CHAT_ID présent: {has_allowed_chat}")
    print(f"- contrôle chat_id présent: {has_chat_check}")

    if not has_allowed_chat:
        warnings.append("ALLOWED_CHAT_ID absent de telegram_command_bot.py")

    if not has_chat_check:
        warnings.append("contrôle chat_id absent ou modifié dans telegram_command_bot.py")

    print()

    if warnings:
        print("VERDICT: WARNING")
        print()
        print("Points à vérifier:")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("VERDICT: SAFE")
        print()
        print("Aucun droit de trading détecté.")
        print("Aucun mot-clé critique détecté.")
        print("Contrôle Telegram actif.")
        print("Pause disponible.")


if __name__ == "__main__":
    main()
