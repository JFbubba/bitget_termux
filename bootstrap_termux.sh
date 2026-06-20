#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

echo "=== BOOTSTRAP BITGET TERMUX AGENT ==="

pkg update -y
pkg install -y git python nano

python -m pip install --upgrade pip
python -m pip install requests python-dotenv

echo "Vérification fichiers requis"
test -f config.py
test -f agents_manifest.py
test -f security_agent.py
test -f tests_audit.py

echo "Compilation Python"
python -m py_compile *.py

echo "Audit"
python tests_audit.py
python security_agent.py

echo "Bootstrap OK"
echo "Créer .env localement si nécessaire. Ne jamais le versionner."
