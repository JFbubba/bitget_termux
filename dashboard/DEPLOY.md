# Déploiement du dashboard sur le VPS

Dashboard web **lecture seule** (stdlib Python, aucune dépendance lourde).
Sécurisé par défaut : il écoute sur **127.0.0.1** (pas exposé à Internet).
Tu le regardes via un **tunnel SSH** (zéro port ouvert) ou derrière nginx.

## 1. Sécuriser le VPS d'abord

```bash
# clés SSH (depuis ton PC) puis sur le VPS : désactiver le login root par mot de passe
# /etc/ssh/sshd_config : PermitRootLogin prohibit-password ; PasswordAuthentication no
sudo ufw default deny incoming
sudo ufw allow OpenSSH
sudo ufw enable          # n'ouvre QUE le SSH ; le dashboard reste en localhost
```

## 2. Récupérer le code

```bash
cd ~
git clone https://github.com/JFbubba/bitget_termux ~/bitget_termux_repo   # si pas déjà fait
cd ~/bitget_termux_repo
git checkout claude/beautiful-heisenberg-c5aoqu
git pull
pip install -r requirements.txt   # requests + python-dotenv + numpy (agents quantitatifs)
```

> **numpy est requis** par les agents quantitatifs (simons, savant, futuretester,
> evolution). Sans lui, ces agents retombent gracieusement en neutre mais ne
> contribuent pas.

### Mise à jour ultérieure (one-liner)

Pour mettre à jour le VPS après de nouveaux commits (pull + deps + tests + gate
sécurité + redémarrage des services systemd) :

```bash
cd ~/bitget_termux_repo && bash update_vps.sh
```

Le script **ne redémarre les services que si `security_agent` renvoie `VERDICT: SAFE`**.

## 3. Lancer le dashboard

```bash
python dashboard/server.py        # écoute http://127.0.0.1:8787
```

## 4. Le regarder (tunnel SSH, recommandé — rien d'exposé)

Depuis **ton PC** :

```bash
ssh -L 8787:localhost:8787 racine@187.77.67.45
```

Puis ouvre dans ton navigateur : **http://localhost:8787**

## 5. (Optionnel) Service systemd — tourne en continu

`/etc/systemd/system/bitget-dashboard.service` :

```ini
[Unit]
Description=Bitget read-only dashboard
After=network-online.target

[Service]
WorkingDirectory=/root/bitget_termux_repo
ExecStart=/usr/bin/python3 dashboard/server.py
Environment=DASH_HOST=127.0.0.1
Environment=DASH_PORT=8787
Environment=DASH_SYMBOL=BTCUSDT
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bitget-dashboard
sudo systemctl status bitget-dashboard
```

## 6. (Optionnel) Accès permanent via nginx + mot de passe

Si tu veux y accéder sans tunnel, mets nginx devant **avec auth basique + HTTPS**
(Let's Encrypt) et ouvre seulement 443 dans ufw. Ne JAMAIS exposer le port
8787 brut sur Internet sans authentification.

---

Rappels : le dashboard est **lecture seule**, n'envoie aucun ordre, n'affiche
aucun secret. Il agrège stats, order-flow Bitget (API publique), contexte macro
et santé du système.
