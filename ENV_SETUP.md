# Mettre ses clés API dans le `.env` (procédure simple)

Le `.env` est un **fichier privé** posé **à côté du code, sur le VPS** (là où le
bot tourne). Il contient des lignes `NOM=valeur`. Le programme le lit au
démarrage. Il n'est **jamais** envoyé sur GitHub (il est gitignoré) et **jamais**
collé dans un chat.

> ⚠️ Personne (ni Claude côté cloud, ni le dépôt) ne doit voir tes clés.
> Toi seul les colles dans le `.env` sur ton VPS.

## 1. Créer / éditer le `.env` sur le VPS

```bash
ssh racine@187.77.67.45
cd ~/bitget_termux_repo        # le dossier du dépôt sur le VPS
cp .env.example .env           # une seule fois (si le .env n'existe pas)
nano .env                      # éditer
```

## 2. Coller chaque clé APRÈS le `=`

Exemple pour X / Twitter (les noms du portail développeur X → variables) :

| Sur le portail X (developer.x.com) | Variable dans `.env` |
|---|---|
| API Key (Consumer Key)             | `X_API_KEY`        |
| API Key Secret (Consumer Secret)   | `X_API_SECRET`     |
| Bearer Token                       | `X_BEARER_TOKEN`   |
| Access Token                       | `X_ACCESS_TOKEN`   |
| Access Token Secret                | `X_ACCESS_SECRET`  |

Dans `nano`, ça donne :

```
X_BEARER_TOKEN=colle_ici_la_valeur
X_API_KEY=colle_ici_la_valeur
X_API_SECRET=colle_ici_la_valeur
X_ACCESS_TOKEN=colle_ici_la_valeur
X_ACCESS_SECRET=colle_ici_la_valeur
```

Sauver : **Ctrl+O** puis **Entrée**. Quitter : **Ctrl+X**.

## 3. Vérifier (sans révéler les valeurs)

```bash
python check_env.py
```

Affiche pour chaque clé `OK (n caractères)` ou `MANQUANT` — **jamais la valeur**.
Depuis Telegram : `/envcheck` (même résultat masqué).

## Notes

- Les clés **X / data sont optionnelles** : le système tourne sans (mode dégradé).
  Seules Bitget + Telegram sont indispensables.
- Si tu as collé tes clés dans un fichier `.md` sur ton PC : c'est du texte en
  clair. Mets-les dans le `.env` puis **supprime ce `.md`**, et ne le commit jamais.
- Le token API **Hostinger (VPS)** ne va PAS dans ce `.env` → credentials **n8n**.
