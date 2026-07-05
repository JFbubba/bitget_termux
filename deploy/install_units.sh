#!/usr/bin/env bash
# install_units.sh — installe/active TOUTES les units systemd du bot (idempotent).
#
# Perimetre SUR : copie de fichiers .service/.timer + systemctl. AUCUN ordre, aucun
# secret. A lancer sur le VPS (root ou sudo) :
#   cd ~/bitget_termux_repo && sudo bash deploy/install_units.sh
#
# Points cles de l'incident (stop -5% + supervision) couverts ici :
#   - bitget-stop-guardian : ENFORCEUR du stop, daemon Restart=always + WatchdogSec ;
#   - bitget-failsafe@      : template OnFailure (alerte immediate) ;
#   - timers brain/scan ENABLE (un timer non-enable = mort silencieuse au reboot).

set -uo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DST="/etc/systemd/system"

echo "=== INSTALL UNITS bitget (depuis $SRC) ==="

# 1. Copier toutes les units presentes dans deploy/
cp -v "$SRC"/bitget-*.service "$SRC"/bitget-*.timer "$DST"/ 2>/dev/null || true
systemctl daemon-reload
echo

# 2. Activer (enable) les TIMERS -> survivent au reboot. Un timer non-enable est la
#    cause meme de l'incident : le service ne tourne plus, en silence.
echo "[timers] enable + start"
for t in bitget-brain bitget-scan bitget-watchdog bitget-notify bitget-validation \
         bitget-spend-watch bitget-mtiming bitget-micro-watch bitget-backup \
         bitget-logrotate bitget-security-audit bitget-revue; do
  if [ -f "$DST/${t}.timer" ]; then
    systemctl enable --now "${t}.timer" 2>/dev/null \
      && echo "  enable+start: ${t}.timer" \
      || echo "  (deja/erreur: ${t}.timer)"
  fi
done
echo

# 3. Activer le DAEMON enforceur du stop (Couche 2). Restart=always : toujours vivant.
echo "[daemon] enforceur stop -5%"
if [ -f "$DST/bitget-stop-guardian.service" ]; then
  systemctl enable --now bitget-stop-guardian.service 2>/dev/null \
    && echo "  enable+start: bitget-stop-guardian" \
    || echo "  (deja/erreur: bitget-stop-guardian)"
fi
echo

# 4. Le template failsafe n'a pas besoin d'enable (instancie par OnFailure a la demande).
[ -f "$DST/bitget-failsafe@.service" ] && echo "[template] bitget-failsafe@ installe (declenche par OnFailure)."
echo

echo "=== Verification rapide ==="
systemctl is-active bitget-stop-guardian.service 2>/dev/null | sed 's/^/  guardian: /'
for t in bitget-brain bitget-scan bitget-watchdog; do
  printf '  %s.timer: ' "$t"; systemctl is-active "${t}.timer" 2>/dev/null || true
done
echo
echo "Etat detaille : systemctl status bitget-stop-guardian ; python stop_guardian.py --status"
