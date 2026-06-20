from pathlib import Path


GETAGENT_PATHS = [
    Path.home() / ".codex" / "skills" / "getagent",
    Path.home() / ".claude" / "skills" / "getagent",
    Path.home() / ".cursor" / "skills" / "getagent",
]

DANGEROUS_PATTERNS = [
    "transfer",
    "withdraw",
    "change_leverage",
    "place_order",
    "cancel_order",
    "modify_limit_order",
    "close_position",
    "modify_take_profit",
    "modify_stop_loss",
    "open_long_market",
    "open_short_market",
    "open_long_limit",
    "open_short_limit",
]

SECRET_PATTERNS = [
    "BITGET_API",
    "BITGET_SECRET",
    "BITGET_PASSPHRASE",
    "GETAGENT",
    "TOKEN",
    "SECRET",
    "KEY",
]


def scan_text_files(base_path, patterns):
    findings = []

    if not base_path.exists():
        return findings

    for path in base_path.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in [".md", ".py", ".js", ".json", ".sh", ".txt", ".yml", ".yaml"]:
            continue

        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue

        lowered = text.lower()

        for pattern in patterns:
            if pattern.lower() in lowered:
                findings.append((str(path), pattern))

    return findings


def main():
    print("=== GETAGENT SKILL AUDIT ===")
    print()

    installed = [path for path in GETAGENT_PATHS if path.exists()]

    print("Installations détectées:")
    for path in GETAGENT_PATHS:
        print(f"- {path}: {'présent' if path.exists() else 'absent'}")

    print()

    dangerous_findings = []
    secret_findings = []

    for path in installed:
        dangerous_findings.extend(scan_text_files(path, DANGEROUS_PATTERNS))
        secret_findings.extend(scan_text_files(path, SECRET_PATTERNS))

    print("Fonctions sensibles détectées:")
    if dangerous_findings:
        for filename, pattern in dangerous_findings[:80]:
            print(f"- {pattern}: {filename}")

        if len(dangerous_findings) > 80:
            print(f"- ... {len(dangerous_findings) - 80} autres occurrences")
    else:
        print("- aucune")

    print()

    print("Indices de secrets / clés détectés:")
    if secret_findings:
        for filename, pattern in secret_findings[:80]:
            print(f"- {pattern}: {filename}")

        if len(secret_findings) > 80:
            print(f"- ... {len(secret_findings) - 80} autres occurrences")
    else:
        print("- aucun")

    print()

    print("Verdict:")
    if dangerous_findings:
        print("WARNING")
        print("- GetAgent contient des références à des fonctions de trading réel.")
        print("- Ne pas fournir de clé API live à ce skill.")
        print("- Usage recommandé: documentation, playbook, backtest, génération de stratégie uniquement.")
    else:
        print("SAFE")

    print()
    print("Règle opérationnelle:")
    print("- Toute clé API donnée à GetAgent doit être lecture seule ou sandbox/demo.")
    print("- Aucune permission retrait.")
    print("- Aucune permission trade réel tant que le système n’a pas de validateur d’ordres séparé.")


if __name__ == "__main__":
    main()
