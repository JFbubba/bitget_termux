#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

echo "=== BOOTSTRAP BITGET TERMUX AGENT ==="

# 1. Paquets systeme Termux.
#    pip est livre AVEC le paquet "python" sous Termux : il n'existe PAS de
#    paquet "python-pip" separe (l'installer fait echouer pkg install).
pkg update -y
pkg install -y git python nano

# 2. Dependances Python.
#    On installe depuis requirements.txt (source unique de verite).
#    IMPORTANT : ne JAMAIS lancer "pip install --upgrade pip" sous Termux,
#    cela casse regulierement l'environnement Python de Termux.
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
else
  echo "AVERTISSEMENT: requirements.txt absent, installation minimale."
  pip install requests python-dotenv
fi

echo "Verification fichiers requis"
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
echo "Creer .env localement si necessaire. Ne jamais le versionner."
