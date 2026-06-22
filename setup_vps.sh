#!/usr/bin/env bash
# setup_vps.sh — installe les dépendances et prépare l'environnement sur le VPS.
#
# Périmètre SÛR : lecture seule / paper. N'exécute aucun ordre, n'expose aucun
# secret. À lancer depuis le dossier du dépôt sur le VPS :
#   bash setup_vps.sh
#
# Idempotent : ne réécrit pas un .env existant.

set -uo pipefail

echo "=== Setup VPS — bitget_termux ==="
echo "Branche courante : $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
echo

# 1. Dépendances système (Ubuntu/Debian)
if command -v apt-get >/dev/null 2>&1; then
  echo "[1/4] Dépendances système (apt)..."
  apt-get update -y
  apt-get install -y python-is-python3 python3-pip python3-dotenv python3-requests python3-matplotlib
else
  echo "[1/4] apt-get absent — installe Python 3 + 'requests' + 'python-dotenv' manuellement."
fi
echo

# 2. .env (créé depuis le modèle s'il n'existe pas ; jamais écrasé)
echo "[2/4] Fichier .env..."
if [ -f .env ]; then
  echo "  .env déjà présent — conservé."
elif [ -f .env.example ]; then
  cp .env.example .env
  echo "  .env créé depuis .env.example — édite-le : nano .env"
else
  echo "  .env.example introuvable — es-tu sur la branche de dev ?"
fi
echo

# 3. Vérification des clés (valeurs masquées, jamais affichées)
echo "[3/4] check_env..."
python check_env.py || true
echo

# 4. Contrôles d'intégrité (tests + sécurité)
echo "[4/4] Contrôles..."
python tests_audit.py 2>/dev/null | tail -1 || echo "  (tests indisponibles)"
python security_agent.py 2>/dev/null | grep -E 'VERDICT' || echo "  (security_agent indisponible)"
echo

echo "=== Terminé. Prochaines étapes ==="
echo "- Compléter le .env (Bitget + Telegram) : nano .env ; python check_env.py"
echo "- Lancer le dashboard (lecture seule)   : DASH_HOST=127.0.0.1 python dashboard/server.py"
echo "- Le voir depuis ton PC (tunnel SSH)    : ssh -L 8787:localhost:8787 root@<IP_VPS>"
echo "                                          puis http://localhost:8787"
echo "- Service permanent + firewall          : voir dashboard/DEPLOY.md"
