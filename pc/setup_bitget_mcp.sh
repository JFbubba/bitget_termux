#!/usr/bin/env bash
set -euo pipefail

# setup_bitget_mcp.sh — installe le Bitget Agent Hub (MCP) dans Claude Code.
#
# A LANCER SUR LE PC ou tourne Claude Code (macOS / Linux / WSL / Git Bash).
# Ne stocke AUCUN secret dans le depot : les cles sont lues depuis tes
# variables d'environnement et passees a `claude mcp add` (qui les ecrit
# dans ton ~/.claude.json local, sur TA machine).
#
# Paliers (du plus sur au plus permissif) :
#   --public          serveur SANS cles, marche public uniquement (smoke test)
#   (defaut)          serveur authentifie en LECTURE SEULE (--read-only)
#   --trading         RETIRE --read-only : ordres reels possibles (opt-in)
#   --modules "..."   surcharge la liste de modules
#   --name NOM        nom du serveur MCP
#
# Exemples :
#   bash setup_bitget_mcp.sh --public
#   export BITGET_API_KEY=...; export BITGET_SECRET_KEY=...; export BITGET_PASSPHRASE=...
#   bash setup_bitget_mcp.sh                      # lecture seule
#   bash setup_bitget_mcp.sh --trading            # trading reel (confirmation requise)

MODE="readonly"
MODULES="spot,futures,account"
NAME=""

while [ $# -gt 0 ]; do
  case "$1" in
    --public)  MODE="public"; shift ;;
    --trading) MODE="trading"; shift ;;
    --modules) MODULES="${2:?--modules requiert une valeur}"; shift 2 ;;
    --name)    NAME="${2:?--name requiert une valeur}"; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Option inconnue: $1"; exit 2 ;;
  esac
done

# --- Prerequis ---
command -v node   >/dev/null 2>&1 || { echo "Node.js manquant (>=18 requis)."; exit 1; }
command -v npx    >/dev/null 2>&1 || { echo "npx manquant."; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "Claude Code CLI manquant."; exit 1; }

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo "Node.js >= 18 requis (detecte: $(node --version))."; exit 1
fi

# Sous Git Bash / MSYS / Cygwin, `claude` est l'exe Windows : npx doit etre
# lance via "cmd /c". Sous WSL / Linux / macOS, npx direct.
# ("//c" empeche MSYS de convertir "/c" en chemin "C:\".)
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) NPX_LAUNCH=(cmd //c npx) ;;
  *)                    NPX_LAUNCH=(npx) ;;
esac

# --- Palier public (aucune cle) ---
if [ "$MODE" = "public" ]; then
  NAME="${NAME:-bitget-public}"
  echo "MCP PUBLIC (sans cles, marche public): $NAME [$MODULES]"
  claude mcp add -s user "$NAME" -- "${NPX_LAUNCH[@]}" -y bitget-mcp-server --modules "$MODULES"
  echo "OK. Verifie: claude mcp list ; puis /mcp dans Claude Code."
  exit 0
fi

# --- Paliers authentifies : exiger les 3 variables d'environnement ---
: "${BITGET_API_KEY:?Definis BITGET_API_KEY dans ton environnement (jamais dans Git)}"
: "${BITGET_SECRET_KEY:?Definis BITGET_SECRET_KEY dans ton environnement}"
: "${BITGET_PASSPHRASE:?Definis BITGET_PASSPHRASE dans ton environnement}"

NAME="${NAME:-bitget}"

if [ "$MODE" = "trading" ]; then
  echo "================================================================"
  echo " MODE TRADING REEL : les ordres reels deviennent POSSIBLES."
  echo " Recommande : cle API DEDIEE, SANS droit de retrait,"
  echo "              IP whitelistee, confirmation humaine avant chaque ordre."
  echo "================================================================"
  printf "Taper exactement 'OUI JE VEUX TRADER' pour continuer: "
  read -r CONFIRM
  if [ "$CONFIRM" != "OUI JE VEUX TRADER" ]; then
    echo "Annule. Aucun changement."; exit 1
  fi
  READONLY_FLAG=""
else
  READONLY_FLAG="--read-only"
fi

echo "MCP authentifie ($MODE): $NAME [$MODULES] ${READONLY_FLAG:-(ecriture activee)}"

# Le couple cle=valeur est mis ENTIEREMENT entre guillemets pour ne jamais
# exposer une valeur litterale dans le source du script.
claude mcp add -s user \
  --env "BITGET_API_KEY=$BITGET_API_KEY" \
  --env "BITGET_SECRET_KEY=$BITGET_SECRET_KEY" \
  --env "BITGET_PASSPHRASE=$BITGET_PASSPHRASE" \
  "$NAME" \
  -- "${NPX_LAUNCH[@]}" -y bitget-mcp-server --modules "$MODULES" ${READONLY_FLAG}

echo "OK. Verifie: claude mcp list ; claude mcp get $NAME ; puis /mcp dans Claude Code."
echo "Rappel securite: protege ~/.claude.json (il contient desormais tes cles)."
