from pathlib import Path


AGENTS = [
    {
        "id": "preorder_guard_agent",
        "name": "Preorder Guard Agent",
        "role": "Bloque les nouveaux pré-ordres lorsque le portefeuille paper est en observation.",
        "file": "preorder_guard.py",
        "permissions": ["read_open_outcomes", "read_pending_orders", "write_pending_orders", "write_guard_journal"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "paper_report_agent",
        "name": "Paper Report Agent",
        "role": "Produit un résumé lecture seule des positions paper et du journal paper.",
        "file": "paper_report.py",
        "permissions": ["read_paper_positions", "read_paper_position_journal"],
        "risk_level": "LOW",
        "can_trade": False,
    },
    {
        "id": "paper_position_agent",
        "name": "Paper Position Agent",
        "role": "Maintient les positions paper ouvertes après dry-run, sans ordre réel.",
        "file": "paper_positions.py",
        "permissions": ["read_paper_positions", "write_paper_positions"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "paper_position_reconciler_agent",
        "name": "Paper Position Reconciler Agent",
        "role": "Surveille les positions paper et les ferme en paper si TP ou SL est touché.",
        "file": "paper_position_reconciler.py",
        "permissions": ["read_paper_positions", "read_market_data", "write_paper_position_journal"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "execution_gateway_agent",
        "name": "Execution Gateway Agent",
        "role": "Simule l’exécution des pré-ordres approuvés en mode dry-run uniquement, sans ordre réel.",
        "file": "execution_gateway.py",
        "permissions": ["read_pending_orders", "write_execution_journal", "dry_run_execution"],
        "risk_level": "HIGH",
        "can_trade": False,
    },
    {
        "id": "preorder_approval_agent",
        "name": "Preorder Approval Agent",
        "role": "Valide ou refuse les pré-ordres en simulation uniquement et journalise les décisions.",
        "file": "preorder_approval.py",
        "permissions": ["read_pending_orders", "write_approval_journal", "simulate_approval"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "preorder_agent",
        "name": "Preorder Agent",
        "role": "Transforme les signaux exploitables en pré-ordres verrouillés, sans exécution réelle.",
        "file": "preorder_engine.py",
        "permissions": ["read_signal_journal", "read_open_state", "write_pending_orders"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "order_signal_agent",
        "name": "Order Signal Agent",
        "role": "Transforme les analyses marché en signaux d’ordres proposés, sans exécution réelle.",
        "file": "order_signal_engine.py",
        "permissions": ["read_signal_journal", "generate_order_signals"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "getagent_audit_agent",
        "name": "GetAgent Audit Agent",
        "role": "Audite le skill GetAgent installé et signale les fonctions sensibles de trading réel.",
        "file": "getagent_audit.py",
        "permissions": ["scan_getagent_skill", "detect_sensitive_trading_functions"],
        "risk_level": "LOW",
        "can_trade": False,
    },
    {
        "id": "config_guard_agent",
        "name": "Config Guard Agent",
        "role": "Définit les paramètres modifiables et les limites de sécurité avant toute modification de configuration.",
        "file": "config_guard_agent.py",
        "permissions": ["read_config", "validate_config_change"],
        "risk_level": "LOW",
        "can_trade": False,
    },
    {
        "id": "security_agent",
        "name": "Security Agent",
        "role": "Vérifie que le système reste en lecture seule, sans droit de trading ni action dangereuse.",
        "file": "security_agent.py",
        "permissions": ["read_agent_manifest", "scan_local_files", "verify_safety_rules"],
        "risk_level": "LOW",
        "can_trade": False,
    },
    {
        "id": "market_agent",
        "name": "Market Agent",
        "role": "Analyse les marchés, calcule les indicateurs et propose des signaux.",
        "file": "journal_scanner.py",
        "permissions": ["read_market_data", "write_signal_journal"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "outcome_agent",
        "name": "Outcome Agent",
        "role": "Suit les signaux ouverts, détecte TP/SL et met à jour les résultats.",
        "file": "outcome_state.py",
        "permissions": ["read_signal_journal", "write_open_state", "write_final_outcomes"],
        "risk_level": "LOW",
        "can_trade": False,
    },
    {
        "id": "risk_agent",
        "name": "Risk Agent",
        "role": "Contrôle le risque, le levier implicite, l’exposition et l’état du portefeuille.",
        "file": "compact_report.py",
        "permissions": ["read_open_state", "read_final_outcomes"],
        "risk_level": "LOW",
        "can_trade": False,
    },
    {
        "id": "report_agent",
        "name": "Report Agent",
        "role": "Génère les rapports détaillés et compacts.",
        "file": "state_report.py",
        "permissions": ["read_open_state", "read_final_outcomes"],
        "risk_level": "LOW",
        "can_trade": False,
    },
    {
        "id": "telegram_agent",
        "name": "Telegram Agent",
        "role": "Envoie les notifications et reçoit les commandes autorisées.",
        "file": "telegram_command_bot.py",
        "permissions": ["send_telegram", "read_telegram_commands"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "hub_agent",
        "name": "Hub Agent",
        "role": "Supervise les modules, l’état global, les journaux et les commandes utiles.",
        "file": "agent_hub.py",
        "permissions": ["read_agent_status", "read_config", "read_journals"],
        "risk_level": "LOW",
        "can_trade": False,
    },
    {
        "id": "control_agent",
        "name": "Control Agent",
        "role": "Exécute le cycle complet des agents dans le bon ordre.",
        "file": "agent_control.py",
        "permissions": ["run_local_cycle"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "loop_agent",
        "name": "Loop Agent",
        "role": "Lance automatiquement le cycle à intervalle régulier.",
        "file": "agent_loop.py",
        "permissions": ["run_scheduled_cycle"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
    {
        "id": "balance_agent",
        "name": "Balance Agent",
        "role": "Lit le solde futures Bitget en lecture seule.",
        "file": "bitget_balance_reader.py",
        "permissions": ["read_bitget_balance"],
        "risk_level": "MEDIUM",
        "can_trade": False,
    },
]


def get_agent_by_id(agent_id):
    for agent in AGENTS:
        if agent["id"] == agent_id:
            return agent
    return None


def agent_file_exists(agent):
    return Path(agent["file"]).exists()


def installed_agents():
    return [agent for agent in AGENTS if agent_file_exists(agent)]


def missing_agents():
    return [agent for agent in AGENTS if not agent_file_exists(agent)]


def print_manifest():
    print("=== AGENTS MANIFEST ===")
    print()

    for agent in AGENTS:
        exists = agent_file_exists(agent)
        icon = "✅" if exists else "❌"

        print(f"{icon} {agent['name']} ({agent['id']})")
        print(f"   Fichier: {agent['file']}")
        print(f"   Rôle: {agent['role']}")
        print(f"   Permissions: {', '.join(agent['permissions'])}")
        print(f"   Risque: {agent['risk_level']}")
        print(f"   Trading réel autorisé: {agent['can_trade']}")
        print()

    print("Résumé:")
    print(f"- Agents déclarés: {len(AGENTS)}")
    print(f"- Agents installés: {len(installed_agents())}")
    print(f"- Agents manquants: {len(missing_agents())}")


if __name__ == "__main__":
    print_manifest()
