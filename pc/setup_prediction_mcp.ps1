#!/usr/bin/env pwsh
# setup_prediction_mcp.ps1 — installe le MCP prediction-mcp (Polymarket + Kalshi)
# dans Claude Code, sur Windows / PowerShell.
#
# Polymarket = lecture publique SANS clé. Aucun secret, aucun ordre.
# Usage : pwsh ./pc/setup_prediction_mcp.ps1

param([string]$Name = "prediction")

$ErrorActionPreference = "Stop"

foreach ($c in @("node", "npx", "claude")) {
  if (-not (Get-Command $c -ErrorAction SilentlyContinue)) {
    Write-Error "$c manquant."
    exit 1
  }
}

# Windows : npx doit passer par "cmd /c". '--' passé littéralement via splat.
$claudeArgs = @('mcp', 'add', '-s', 'user', $Name, '--', 'cmd', '/c', 'npx', '-y', 'prediction-mcp')
& claude @claudeArgs

Write-Host "OK. Verifie: claude mcp list ; puis /mcp dans Claude Code."
