#!/usr/bin/env bash
# install_learning_timers.sh — installe/active les timers d'AUTO-AMÉLIORATION manquants (§68).
#
# À LANCER PAR LE PROPRIÉTAIRE (crée des jobs planifiés persistants) :
#     sudo bash deploy/install_learning_timers.sh
#
# Ajoute 3 boucles qui étaient à l'arrêt (audit §68) :
#   • bitget-neural-train    — ré-entraîne le réseau neuronal (quotidien 04:20) ;
#   • bitget-strategy-lab    — optimiseur autonome sep-CMA-ES / backtest (hebdo, dim 05:00) ;
#   • bitget-learning-health — moniteur : alerte Telegram si les poids appris décrochent de
#                              l'IC (toutes les 6 h).
# Tout est LECTURE SEULE / entraînement offline — aucun ordre. Réversible :
#     sudo systemctl disable --now bitget-neural-train.timer bitget-strategy-lab.timer bitget-learning-health.timer
set -euo pipefail
REPO=/root/bitget_termux_repo
D=/etc/systemd/system

write_unit () { cat > "$D/$1"; echo "  écrit $1"; }

write_unit bitget-neural-train.service <<'EOF'
[Unit]
Description=Bitget re-entrainement du reseau neuronal de fusion (nn) sur brain_log_history (§65/§68)
[Service]
Type=oneshot
WorkingDirectory=/root/bitget_termux_repo
ExecStart=/usr/bin/python3 neural_net.py --train
TimeoutStartSec=1200
User=root
Nice=15
EOF

write_unit bitget-neural-train.timer <<'EOF'
[Unit]
Description=Bitget re-entrainement NN (quotidien 04:20)
[Timer]
OnCalendar=*-*-* 04:20:00
AccuracySec=10min
Persistent=true
[Install]
WantedBy=timers.target
EOF

write_unit bitget-strategy-lab.service <<'EOF'
[Unit]
Description=Bitget laboratoire de strategies (sep-CMA-ES / backtest walk-forward, lecture seule) (§68)
[Service]
Type=oneshot
WorkingDirectory=/root/bitget_termux_repo
ExecStart=/usr/bin/python3 strategy_lab.py BTCUSDT 1H
TimeoutStartSec=3000
User=root
Nice=18
EOF

write_unit bitget-strategy-lab.timer <<'EOF'
[Unit]
Description=Bitget strategy-lab / optimiseur CMA-ES (hebdomadaire, dimanche 05:00)
[Timer]
OnCalendar=Sun *-*-* 05:00:00
AccuracySec=30min
Persistent=true
[Install]
WantedBy=timers.target
EOF

write_unit bitget-learning-health.service <<'EOF'
[Unit]
Description=Bitget moniteur de sante de l'apprentissage : alerte si poids appris decrochent de l'IC (§68)
[Service]
Type=oneshot
WorkingDirectory=/root/bitget_termux_repo
ExecStart=/usr/bin/python3 learning_health.py --alert
TimeoutStartSec=300
User=root
Nice=15
EOF

write_unit bitget-learning-health.timer <<'EOF'
[Unit]
Description=Bitget sante apprentissage (toutes les 6h)
[Timer]
OnBootSec=25min
OnUnitActiveSec=6h
AccuracySec=15min
Persistent=true
[Install]
WantedBy=timers.target
EOF

echo "Rechargement systemd + activation des timers…"
systemctl daemon-reload
systemctl enable --now bitget-neural-train.timer bitget-strategy-lab.timer bitget-learning-health.timer
echo "OK. Timers actifs :"
systemctl list-timers 'bitget-neural-train*' 'bitget-strategy-lab*' 'bitget-learning-health*' --all
