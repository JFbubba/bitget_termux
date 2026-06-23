#!/usr/bin/env pwsh
# setup_bitget_mcp.ps1 — installe le Bitget Agent Hub (MCP) dans Claude Code.
#
# A LANCER SUR LE PC Windows, dans PowerShell. Ne stocke AUCUN secret :
# les cles sont lues depuis $env: et passees a `claude mcp add` (qui les
# ecrit dans ton ~/.claude.json local).
#
# Paliers :
#   -Public            serveur SANS cles, marche public uniquement (smoke test)
#   (defaut)           serveur authentifie en LECTURE SEULE (--read-only)
#   -Trading           RETIRE --read-only : ordres reels possibles (confirmation)
#   -Modules "spot,futures,account"
#   -Name "bitget"
#
# Exemples :
#   pwsh ./pc/setup_bitget_mcp.ps1 -Public
#   $env:BITGET_API_KEY="..."; $env:BITGET_SECRET_KEY="..."; $env:BITGET_PASSPHRASE="..."
#   pwsh ./pc/setup_bitget_mcp.ps1
#   pwsh ./pc/setup_bitget_mcp.ps1 -Trading

param(
  [switch]$Public,
  [switch]$Trading,
  [string]$Modules = "spot,futures,account",
  [string]$Name = ""
)

$ErrorActionPreference = "Stop"

function Need($cmd) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Error "$cmd manquant."
    exit 1
  }
}
Need node
Need npx
Need claude

$nodeMajor = [int](node -p "process.versions.node.split('.')[0]")
if ($nodeMajor -lt 18) {
  Write-Error "Node.js >= 18 requis (detecte: $(node --version))."
  exit 1
}

# --- Palier public (aucune cle) ---
if ($Public) {
  if (-not $Name) { $Name = "bitget-public" }
  Write-Host "MCP PUBLIC (sans cles, marche public): $Name [$Modules]"
  # Windows : npx doit passer par "cmd /c".
  $publicArgs = @('mcp','add','-s','user', $Name, '--', 'cmd','/c','npx','-y','bitget-mcp-server','--modules', $Modules)
  & claude @publicArgs
  Write-Host "OK. Verifie: claude mcp list ; puis /mcp dans Claude Code."
  exit 0
}

# --- Paliers authentifies : exiger les 3 variables d'environnement ---
foreach ($v in @("BITGET_API_KEY","BITGET_SECRET_KEY","BITGET_PASSPHRASE")) {
  if (-not (Test-Path "env:$v")) {
    Write-Error "Definis `$env:$v avant de lancer (jamais dans Git)."
    exit 1
  }
}
if (-not $Name) { $Name = "bitget" }

$readOnly = $true
if ($Trading) {
  Write-Host "================================================================"
  Write-Host " MODE TRADING REEL : les ordres reels deviennent POSSIBLES."
  Write-Host " Recommande : cle API DEDIEE, SANS droit de retrait,"
  Write-Host "              IP whitelistee, confirmation humaine avant chaque ordre."
  Write-Host "================================================================"
  $confirm = Read-Host "Taper exactement 'OUI JE VEUX TRADER' pour continuer"
  if ($confirm -ne "OUI JE VEUX TRADER") {
    Write-Host "Annule. Aucun changement."
    exit 1
  }
  $readOnly = $false
}

# Arguments construits en tableau puis splattes : '--' est passe LITTERALEMENT
# (evite que PowerShell n'interprete le separateur).
$claudeArgs = @(
  'mcp','add','-s','user', $Name,
  '--env', "BITGET_API_KEY=$env:BITGET_API_KEY",
  '--env', "BITGET_SECRET_KEY=$env:BITGET_SECRET_KEY",
  '--env', "BITGET_PASSPHRASE=$env:BITGET_PASSPHRASE",
  '--',
  'cmd','/c','npx','-y','bitget-mcp-server','--modules', $Modules
)
if ($readOnly) { $claudeArgs += '--read-only' }

Write-Host ("MCP authentifie: {0} [{1}] {2}" -f $Name, $Modules, ($(if ($readOnly) {'--read-only'} else {'(ecriture activee)'})))
& claude @claudeArgs

Write-Host "OK. Verifie: claude mcp list ; claude mcp get $Name ; puis /mcp dans Claude Code."
Write-Host "Rappel securite: protege ~/.claude.json (il contient desormais tes cles)."
