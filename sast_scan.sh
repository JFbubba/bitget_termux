#!/usr/bin/env bash
# sast_scan.sh — scan SAST MANUEL et 100 % LOCAL du bot, via semgrep (venv isolé).
#
# POURQUOI CE WRAPPER. Le plugin semgrep « officiel » (hook global opaque) a été
# DÉSACTIVÉ en fail-safe (settings.json global). On lui préfère un appel EXPLICITE,
# transparent et À LA DEMANDE — jamais un hook. Garanties :
#   • le CODE NE QUITTE JAMAIS LA MACHINE : télémétrie coupée (--metrics=off, env
#     SEMGREP_SEND_METRICS=off), pas d'appel réseau « version » (--disable-version-check),
#     moteur OSS pur sans login (--oss-only) ;
#   • seules des RÈGLES PUBLIQUES entrent (packs registry, mises en cache ~/.semgrep) ;
#   • semgrep vit dans un venv ISOLÉ HORS dépôt (/root/semgrep_venv, ERR-004) — le
#     Python du bot n'est jamais touché.
#
# PÉRIMÈTRE SÛR : lecture seule. N'exécute AUCUN code du bot, ne passe AUCUN ordre.
# Outil INFORMATIF : le code de sortie distingue « erreur outil » de « findings »,
# il ne bloque JAMAIS une porte de push (les 3 portes restent tests/security/safe_push).
#
# USAGE :
#   bash sast_scan.sh                         # scan du dépôt (exclusions via .semgrepignore)
#   bash sast_scan.sh chemin/ fichier.py      # cibles explicites (ex. un labo scratchpad/)
#   SAST_CONFIG="p/python p/secrets" bash sast_scan.sh   # jeu de règles personnalisé
#
# Rapports (dossier gitignored sast_out/) : semgrep_report.json + semgrep_summary.txt
#
# set -e VOLONTAIREMENT ABSENT (comme gates.sh/update_vps.sh) : on gère les codes de
# sortie nous-mêmes ; semgrep renvoie 1 quand il TROUVE (normal), ce n'est pas une erreur.
set -uo pipefail

SEMGREP_BIN="${SEMGREP_BIN:-/root/semgrep_venv/bin/semgrep}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$REPO/sast_out"
JSON_OUT="$OUT_DIR/semgrep_report.json"
TXT_OUT="$OUT_DIR/semgrep_summary.txt"
CONFIG="${SAST_CONFIG:-p/python p/secrets p/command-injection}"

[ -x "$SEMGREP_BIN" ] || { echo "❌ semgrep introuvable : $SEMGREP_BIN (venv isolé absent ?)"; exit 2; }

mkdir -p "$OUT_DIR"

TARGETS=("$@")
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=("$REPO")

CONFIG_ARGS=()
for c in $CONFIG; do CONFIG_ARGS+=(--config "$c"); done

echo "— SAST semgrep (100 % local, télémétrie OFF, moteur OSS) —"
echo "  binaire : $SEMGREP_BIN"
echo "  règles  : $CONFIG"
echo "  cibles  : ${TARGETS[*]}"
echo

export SEMGREP_SEND_METRICS=off
"$SEMGREP_BIN" scan \
  --metrics=off --disable-version-check --oss-only \
  "${CONFIG_ARGS[@]}" \
  --json --output "$JSON_OUT" \
  "${TARGETS[@]}"
rc=$?

if [ ! -s "$JSON_OUT" ]; then
  echo "❌ semgrep n'a produit aucun rapport (rc=$rc)"; exit "${rc:-2}"
fi

echo
echo "— Résumé (aussi écrit dans $TXT_OUT) —"
/root/semgrep_venv/bin/python - "$JSON_OUT" <<'PY' | tee "$TXT_OUT"
import json,sys,collections
d=json.load(open(sys.argv[1]))
res=d.get("results",[]); errs=d.get("errors",[])
sev=collections.Counter(r["extra"].get("severity","?") for r in res)
print(f"Findings: {len(res)}  |  sévérités: {dict(sev)}  |  erreurs moteur (timeouts/parse): {len(errs)}")
for r in sorted(res,key=lambda r:(r['extra'].get('severity',''),r['path'],r['start']['line'])):
    ex=r["extra"]; msg=(ex.get('message','') or '').strip().replace('\n',' ')
    print(f"  [{ex.get('severity','?')}] {r['path']}:{r['start']['line']}  {r['check_id']}")
    print(f"        {msg[:160]}")
PY

# Code de sortie INFORMATIF : 0 = scan propre (avec ou sans findings), >=2 = vraie erreur outil
if [ "$rc" -ge 2 ]; then exit "$rc"; fi
exit 0
