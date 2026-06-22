#!/usr/bin/env bash
set -euo pipefail

# setup_prediction_mcp.sh — installe le MCP prediction-mcp (Polymarket + Kalshi)
# dans Claude Code. A LANCER SUR LE PC (macOS / Linux / WSL / Git Bash).
#
# Polymarket = lecture publique SANS clé : odds/sentiment BTC, ETH, Fed, ETF.
# Aucun secret, aucun ordre.
#
# Usage : bash pc/setup_prediction_mcp.sh   (nom par défaut: prediction)

NAME="${1:-prediction}"

command -v node   >/dev/null 2>&1 || { echo "Node.js manquant (>=18)."; exit 1; }
command -v npx    >/dev/null 2>&1 || { echo "npx manquant."; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "Claude Code CLI manquant."; exit 1; }

# Sous Git Bash/MSYS, npx doit passer par "cmd /c" ; sinon npx direct.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) NPX_LAUNCH=(cmd //c npx) ;;
  *)                    NPX_LAUNCH=(npx) ;;
esac

echo "Installation MCP prediction-mcp (Polymarket public, lecture seule): $NAME"
claude mcp add -s user "$NAME" -- "${NPX_LAUNCH[@]}" -y prediction-mcp

echo "OK. Verifie: claude mcp list ; puis /mcp dans Claude Code."
echo "Astuce: epingle une version (projet en debut de dev) si besoin."
