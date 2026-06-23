# Commandes Termux — Bitget Local Agent

Mode **paper / dry-run only**. Aucun ordre réel. Aucun secret dans Git.
Toutes les commandes se lancent depuis le dossier du moteur (ex. `~/bitget-agent`).

---

## 1. Installation / mise à jour

```bash
# Dépendances Termux + Python (requests, python-dotenv) depuis requirements.txt
bash bootstrap_termux.sh
```

> Ne jamais lancer `pip install --upgrade pip` sous Termux.
> `python-pip` n'est PAS un paquet séparé : pip est livré avec `python`.

Créer le `.env` localement (jamais versionné) :

```bash
nano .env
# TELEGRAM_BOT_TOKEN=...
# TELEGRAM_CHAT_ID=...
# BITGET_API_KEY=...        (optionnel, lecture seule)
# BITGET_API_SECRET=...
# BITGET_API_PASSPHRASE=...
```

---

## 2. Lancer le moteur

```bash
python agent_control.py        # un seul cycle (scan + journaux + rapport)
python agent_loop.py           # boucle continue au premier plan (CTRL+C pour stopper)
bash restart_agent.sh          # (re)lance la boucle en arrière-plan (nohup) proprement
```

Le PID de la boucle est écrit dans `agent_loop.pid`.

```bash
cat agent_loop.pid                 # voir le PID courant
kill "$(cat agent_loop.pid)"       # arrêt PROPRE (SIGTERM -> finally)
```

---

## 3. Bot Telegram (commandes à distance, lecture seule)

```bash
python telegram_command_bot.py                                  # au premier plan
nohup python telegram_command_bot.py >> telegram_bot.log 2>&1 & # en arrière-plan
```

Commandes Telegram utiles : `/status` `/git_version` `/system_health`
`/watchdog` `/orderflow` `/macro` `/confluence` `/stats` `/security`
`/signals` `/preorders` `/pause` `/resume` `/help`.

---

## 4. Surveillance / observabilité

```bash
python watchdog.py             # la boucle agent_loop tourne-t-elle ? (PID + /proc + fraîcheur)
python watchdog.py --alert     # idem + alerte Telegram si DOWN/STALE
python system_health.py        # bilan : fichiers, fraîcheur, tailles journaux, pré-ordres, can_trade=False
python git_version.py          # commit, branche, dernier tag, état du dépôt
python stats_report.py         # stats TP/SL par symbole et sens (résultats finalisés)
```

---

## 5. Maintenance

```bash
bash restart_agent.sh                     # arrêt propre + relance de la boucle
bash rotate_logs.sh                       # rotation des journaux (gzip + rétention)
MAX_KB=1024 KEEP=14 bash rotate_logs.sh   # seuil et rétention configurables
```

La rotation ne touche QUE les journaux append-only ; jamais les fichiers
d'état (`signals_journal.csv`, `open_outcomes_state.csv`, `final_outcomes_journal.csv`).

---

## 6. Tests & sécurité (avant chaque push)

```bash
python tests_audit.py          # tests unitaires (sans réseau, sans ordre)
python security_agent.py       # doit afficher VERDICT: SAFE
bash safe_push_check.sh        # contrôle complet avant git push
```

---

## 7. Workflow Git sûr

```bash
bash safe_push_check.sh && \
  git add -A && \
  git commit -m "message clair" && \
  git push -u origin main
```

`safe_push_check.sh` bloque le push si : fichier interdit suivi (.env, logs,
journaux), vraie valeur de secret en dur, fonction de trading réel, ou test
en échec. Les simples `os.getenv("...")` et la documentation sont autorisés.

---

## 8. Planification (optionnel)

Watchdog + rotation périodiques avec `termux-job-scheduler`
(paquet `termux-api`) ou une boucle simple :

```bash
# Exemple : vérifier le watchdog et tourner les logs toutes les 15 min
while true; do
  python watchdog.py --alert
  bash rotate_logs.sh
  sleep 900
done
```

---

## Rappels de sécurité

- Mode **paper / dry-run uniquement**. `can_trade=False` pour tous les agents.
- Aucune fonction de trading réel (`place_order`, `open_long`, `open_short`,
  `close_position`, `cancel_order`, `change_leverage`, `transfer`, `withdraw`).
- Ne jamais versionner `.env`, clés Bitget, token Telegram, chat_id, journaux runtime.
- `system_health` vérifie en continu que `ordres réels envoyés = 0`.
