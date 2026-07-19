# TAPE_STORE — persistance bornée de la tape brute signée (socle microstructure)

**Module** : `tape_store.py` · **Hook** : `book_collector.tick()` · **Classement** : SAFE
(market-data, fichiers locaux, aucun ordre, aucune clé, aucun réseau) · **Défaut** : ON.

## Pourquoi
`book_collector.py` reçoit la tape signée par trade (`parse_ws_trades`) mais la **vidait à
chaque tick** (`tick()` : `pop(s, [])`) après agrégation — la magnitude buy/sell par trade
était **perdue**. Seuls des snapshots agrégés ~60 s survivaient (`microstructure_history.jsonl`).
Il n'existait donc **aucune tape tick-level historique** : c'est ce manque qui a forcé le
labo VPIN (`vpin_lab.py`) à faire du **BVC-barre** au lieu d'un vrai **VPIN signé tick-level**
(cf. `docs/VPIN_LAB.md` / `docs/VERDICTS.md`). `tape_store` comble ce trou en append-only.

## Ce que fait (et ne fait pas) le module
- **Fait** : APPEND la tape brute AVANT qu'elle soit jetée, 1 ligne JSONL par trade, avec
  rotation par taille et garde d'espace disque. Expose `load_tape()` en lecture pour les labos.
- **Ne fait PAS** : aucune agrégation, aucun signal, aucune décision, aucun réseau, aucun
  ordre. Le hook dans `tick()` est une **addition pure** : il ne change rien à l'agrégation,
  au snapshot ni au book.

## Format
- Répertoire dédié **`.tape/`** (gitignoré), un fichier par symbole : `.tape/<SYMBOL>.jsonl`.
- Une ligne = un trade : `{"ts", "symbol", "side", "size", "price"}`.
  `ts` = horodatage **tick-level** (ms epoch Bitget si le WS le fournit — `parse_ws_trades`
  le préserve désormais ; sinon repli sur le ts du tick). `side` = "buy"/"sell" (agresseur).

## Bornage disque (DUR)
- Rotation par **taille** : quand `.tape/<SYMBOL>.jsonl` atteint `TAPE_MAX_MB` (défaut 50 Mo),
  il est renommé `.1`, les anciens décalés (`.1`->`.2`, …), et on garde au plus `TAPE_KEEP`
  rotations (défaut 4). Le plus ancien au-delà est supprimé.
- **Plafond dur par symbole** : `(TAPE_KEEP + 1) × TAPE_MAX_MB` = **5 × 50 = 250 Mo/symbole**.
  Collecteur par défaut = 1 symbole (BTCUSDT) -> **~250 Mo** ; 3 symboles -> **~750 Mo max**.
- **Garde d'espace libre** : sous `TAPE_MIN_FREE_MB` (défaut 500 Mo), on **s'abstient**
  (skip + log throttlé), la collecte continue.

## Fail-safe absolu
Toute erreur (mkdir / rotation / disque / écriture) est attrapée : on **skip**, on **log**
(throttlé, 1/5 min par symbole), on **continue**. La persistance ne peut JAMAIS faire
planter ni ralentir le collecteur — book/microstructure priment.

## Gating (`.env` / `config.py`)
| Knob | Défaut | Rôle |
|---|---|---|
| `TAPE_PERSIST` | `1` (ON) | 1 = persiste, 0 = coupe instantanément |
| `TAPE_MAX_MB` | `50` | taille max d'un fichier avant rotation |
| `TAPE_KEEP` | `4` | nb de rotations conservées par symbole |
| `TAPE_MIN_FREE_MB` | `500` | plancher d'espace libre (sinon abstention) |

**Défaut ON justifié** : c'est un collecteur market-data SAFE dont le BUT est d'accumuler la
vérité tick-level ; un défaut OFF en ferait un persisteur **dormant** (ERR-013). Le bornage
dur + le fail-safe rendent le ON sûr ; `TAPE_PERSIST=0` coupe. (Les « défaut OFF » de la
constitution visent les leviers d'argent/voix, pas une persistance de données.)

## Comment un labo la lit (anti-ERR-013 : consommé dès que ça tourne)
```python
import tape_store
rows = tape_store.load_tape("BTCUSDT", since_ts=None, limit=None)   # ordre chronologique
# rows = [{"ts","symbol","side","size","price"}, ...] à travers rotations + fichier vif
```
Diagnostic (lecture seule) : `python tape_store.py BTCUSDT` (présence/tailles + échantillon).

## Débloque
Le **VPIN tick-level** (buckets de volume égal, classification signée par trade — le domaine
NATIF du VPIN, cf. `docs/VPIN_LAB.md`) devient possible une fois **~quelques jours** de tape
accumulés : `load_tape` remplace le repli BVC-barre par la vraie séquence signée. Idem pour
les recherches orderflow/exécution sub-barre (`orderflow_watch.py`, `orderflow_tape.py`).
