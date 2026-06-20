# Bitget Agent Hub dans Claude Code (côté PC)

Installation du **Bitget Agent Hub** (serveur MCP officiel) dans **Claude Code
sur le PC**, pour donner à Claude un accès aux données et aux opérations Bitget.

> ⚠️ **Argent réel.** Avec des clés de trading, ce pont peut passer de **vrais
> ordres**. Procède par paliers (public → lecture seule → trading) et garde une
> confirmation humaine avant toute écriture.

---

## Architecture (2 machines)

- **Termux (Android)** — le dépôt `bitget_termux` : moteur de monitoring
  **paper / dry-run**, collecte/analyse, envoi de signaux. Reste
  `can_trade=False`, **aucun ordre réel**.
- **PC (Claude Code + Bitget Agent Hub)** — ce composant : pont MCP vers
  l'exchange Bitget, **capable de trading réel**. C'est ici que vivent les
  permissions sensibles.

Les deux ne partagent **pas** les mêmes clés ni le même niveau de risque.

---

## Où et comment lancer l'installation

`claude mcp add` est une commande de la **CLI Claude Code** : on la tape dans un
**terminal**, **pas** dans le chat Claude. Une fois le serveur enregistré, c'est
l'agent Claude qui utilise les outils (tu vérifies avec `/mcp`).

| Shell | Script fourni | Quand |
|---|---|---|
| **PowerShell** (Windows) | `pc/setup_bitget_mcp.ps1` | natif Windows |
| **Git Bash / WSL** (Windows) | `pc/setup_bitget_mcp.sh` | si Git for Windows / WSL |
| **Terminal** (macOS / Linux) | `pc/setup_bitget_mcp.sh` | natif |

PowerShell — palier public (sans clés) :

```powershell
pwsh ./pc/setup_bitget_mcp.ps1 -Public
# ou la commande directe (cmd /c requis sur Windows) :
claude mcp add -s user bitget-public -- cmd /c npx -y bitget-mcp-server --modules spot,futures
```

> **Windows (important).** Claude Code natif Windows ne peut pas lancer `npx`
> directement : il faut le préfixer par **`cmd /c`** (sinon avertissement
> « Windows requires 'cmd /c' wrapper to execute npx »). Les scripts
> `setup_bitget_mcp.*` le gèrent automatiquement. En **Git Bash**, ajoute
> `MSYS_NO_PATHCONV=1` devant la commande pour que `/c` ne soit pas converti
> en chemin :
>
> ```bash
> MSYS_NO_PATHCONV=1 claude mcp add -s user bitget-public -- cmd /c npx -y bitget-mcp-server --modules spot,futures
> ```

PowerShell — lecture seule (clés via `$env:`) :

```powershell
$env:BITGET_API_KEY="<ta_cle_api>"
$env:BITGET_SECRET_KEY="<ta_cle_secrete>"
$env:BITGET_PASSPHRASE="<ta_passphrase>"
pwsh ./pc/setup_bitget_mcp.ps1
```

> Si PowerShell interprète mal le séparateur `--`, utilise le script `.ps1`
> (il passe `--` littéralement) ou bascule sur **Git Bash / WSL**.

---

## Prérequis (sur le PC)

- **Node.js ≥ 18** + `npx` (`node --version`)
- **Claude Code** installé et authentifié (`claude --version`, `claude doctor`)
- Un **compte Bitget** et une **clé API dédiée** à Claude (voir ci-dessous)

### Créer une clé API Bitget (recommandations)

- Une clé **dédiée** à Claude Code (pas ta clé principale).
- Permissions **minimales** : lecture seule au début ; trade seulement quand
  tu passes au palier trading.
- **JAMAIS** la permission de **retrait** (withdraw).
- **Whitelist IP** de ton PC si possible.
- Trois secrets : `BITGET_API_KEY`, `BITGET_SECRET_KEY`, `BITGET_PASSPHRASE`.
  Tu les exportes dans ton shell, **jamais** dans Git.

---

## Palier 1 — Smoke test public (sans clés)

Valide Node / npx / Claude / MCP sans aucun secret :

```bash
claude mcp add -s user bitget-public -- npx -y bitget-mcp-server --modules spot,futures
```

Vérifie puis teste dans Claude Code :

```bash
claude mcp list
```
```text
/mcp
Show the latest BTCUSDT spot market data from Bitget.
Check the BTCUSDT futures funding rate on Bitget.
```

---

## Palier 2 — Compte en lecture seule (clés + `--read-only`)

Exporte tes clés dans le shell (valeurs réelles côté PC, jamais commit) :

```bash
export BITGET_API_KEY=<ta_cle_api>
export BITGET_SECRET_KEY=<ta_cle_secrete>
export BITGET_PASSPHRASE=<ta_passphrase>
```

Enregistre le serveur authentifié, **verrouillé en lecture seule** :

```bash
claude mcp add -s user bitget \
  --env "BITGET_API_KEY=$BITGET_API_KEY" \
  --env "BITGET_SECRET_KEY=$BITGET_SECRET_KEY" \
  --env "BITGET_PASSPHRASE=$BITGET_PASSPHRASE" \
  -- npx -y bitget-mcp-server --modules spot,futures,account --read-only
```

> Le **nom `bitget` vient AVANT** les `--env` (sinon certaines versions du CLI
> renvoient « Invalid environment variable format: bitget »). Sous Windows,
> remplace `npx` par `cmd /c npx`.

Vérifie et teste (toujours aucun ordre possible) :

```bash
claude mcp list
claude mcp get bitget
```
```text
/mcp
Show my available balance on Bitget.
Summarize my open futures positions on Bitget.
What is my unrealized PnL on Bitget?
```

> Modules disponibles : `spot,futures,account,margin,copytrading,convert,earn,p2p,broker`
> (défaut `spot,futures,account` = 36 outils).

---

## Palier 3 — Trading réel (opt-in explicite)

Quand tu veux autoriser les ordres réels, le changement doit être **délibéré** :

1. Génère/active une **clé API avec permission de trade** (toujours **sans retrait**).
2. Remplace le serveur en retirant `--read-only` :

```bash
claude mcp remove bitget
claude mcp add -s user bitget \
  --env "BITGET_API_KEY=$BITGET_API_KEY" \
  --env "BITGET_SECRET_KEY=$BITGET_SECRET_KEY" \
  --env "BITGET_PASSPHRASE=$BITGET_PASSPHRASE" \
  -- npx -y bitget-mcp-server --modules spot,futures,account
```

3. Garde **toujours** une confirmation humaine avant chaque ordre dans Claude.

---

## Script d'installation (raccourci)

Les scripts automatisent ces paliers (lisent les clés depuis l'environnement,
ne stockent aucun secret). Bash (macOS / Linux / Git Bash / WSL) :

```bash
bash pc/setup_bitget_mcp.sh --public        # palier 1
bash pc/setup_bitget_mcp.sh                 # palier 2 (lecture seule)
bash pc/setup_bitget_mcp.sh --trading       # palier 3 (confirmation requise)
```

PowerShell (Windows) :

```powershell
pwsh ./pc/setup_bitget_mcp.ps1 -Public      # palier 1
pwsh ./pc/setup_bitget_mcp.ps1              # palier 2 (lecture seule)
pwsh ./pc/setup_bitget_mcp.ps1 -Trading     # palier 3 (confirmation requise)
```

---

## Voie alternative : Skill + CLI `bgc`

Au lieu (ou en plus) du MCP :

```bash
npm install -g bitget-client
bgc --version
bgc spot spot_get_ticker --symbol BTCUSDT       # public, sans clés
bgc account account_get_balance                 # privé (clés via env)
```

Déploiement complet des skills Bitget pour Claude Code :

```bash
npx bitget-hub upgrade-all --target claude
```

`bgc` supporte aussi un mode `--read-only` qui restreint aux outils de lecture.

---

## Vérification & dépannage

- État des serveurs : `claude mcp list`, `claude mcp get bitget`, et `/mcp`
  (affiche le **nombre d'outils** réellement chargés).
- `AUTH_MISSING` / credentials absents : les 3 variables ne sont pas dans
  l'environnement du process MCP — réenregistre avec les `--env`.
- Erreurs de **signature / timestamp** : vérifie l'horloge du PC. Référence de
  temps serveur Bitget :

```bash
curl https://api.bitget.com/api/v2/public/time
```

- Outils manquants : mauvais périmètre `--modules` (ex. demander `account`
  alors que seul `spot,futures` est chargé).

---

## Checklist sécurité

- [ ] Clé API **dédiée** à Claude Code (séparée de la clé principale).
- [ ] **Aucune** permission de retrait (withdraw).
- [ ] **Whitelist IP** du PC activée.
- [ ] `--read-only` par défaut ; trading seulement en palier 3, confirmé.
- [ ] Clés **jamais** dans Git ; `~/.claude.json` protégé (contient les clés).
- [ ] Clé compromise → la **supprimer immédiatement** côté Bitget.

---

## Désinstaller

```bash
claude mcp remove bitget
claude mcp remove bitget-public
```
