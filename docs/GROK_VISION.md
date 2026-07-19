# grok_vision.py — lecture de chart par Grok vision (voix d'OMBRE mesurée)

## Ce que c'est

Un outil à la demande qui :

1. rend un **chart CHANDELIERS** propre (OHLC + volume, ~180 dernières bougies) depuis
   `candles_history.load(SYMBOL, TF)` (lecture seule, endpoint public) ;
2. l'envoie à **Grok vision** (xAI, endpoint OpenAI-compatible `https://api.x.ai/v1`) ;
3. récupère une lecture **Wyckoff + patterns chartistes** en JSON strict
   (`phase`, `events`, `structure`, `patterns`, `bias`, `confidence`, `raison`) ;
4. la **croise** avec `wyckoff_lab.detect_events` — un détecteur d'événements OBJECTIF,
   look-ahead-free — et rapporte l'ACCORD/désaccord (Grok voit-il un climax là où le
   détecteur en trouve un ?) ;
5. journalise un **vote d'ombre `grok_shadow`** dans `.overlay_votes.jsonl` — le même
   journal que `news_shadow`/`nn_shadow`/`qml_shadow` — pour mesure d'IC par
   `live_ic_audit`.

## Ce que ce n'est PAS (les bornes)

- **AUCUN ordre.** Le module n'importe aucun exécuteur (`spot_executor`/`futures_executor`/
  `bitget_execute`/`spot_trader`/…). Il est classé SAFE, dans `security_agent.FILES_TO_SCAN`.
- **Ne touche PAS le consensus** ni le banc déterministe gelé à 14 (§62).
- **Ne desserre AUCUN mur** (caps 50/250, levier ×5, stop −5 %, kill-switch, porte d'edge).
  Il peut au plus SUGGÉRER une direction, journalisée en ombre et MESURÉE avant tout poids.
- **Défaut OFF**, et inerte sans clé xAI.

## Honnêteté sur l'edge (prior)

Grok est un LLM **NON DÉTERMINISTE qui HALLUCINE** sur la lecture de chart. Sa lecture est
du **BRUIT jusqu'à preuve d'IC**. Ce module ne fait qu'ACCUMULER une preuve mesurable ; il
ne gagnera une vraie voix (via la porte d'edge `deflated`, anti sur-testing) que si son IC
live se PROUVE. Rappel : les voix `llm` (15ᵉ) et `classics` (17ᵉ) ont déjà été COUPÉES
(t ≈ −4,5 / −11) — la mesure décide, pas l'intuition.

## Activation (décision propriétaire — défaut OFF)

Dans `.env` (gitignored, jamais committé) :

```
GROK_VISION_ENABLED=1
XAI_API_KEY=<votre clé xAI>          # https://console.x.ai — clé API, JAMAIS committée
# facultatif :
GROK_VISION_MODEL=grok-4             # modèle vision xAI. ⚠️ vérifié 19/07 : `grok-4.1-fast` et
                                     # `grok-2-vision-1212` renvoient « Model not found » ; `grok-4`
                                     # est reconnu. Confirmer l'ID exact via GET /v1/models une fois
                                     # une clé VALIDE en place (les IDs xAI changent).
GROK_VISION_TIMEOUT_S=30             # défaut
GROK_VISION_CONF_CAP=0.5             # borne du vote d'ombre (une voix opt-in ne domine pas)
GROK_VISION_BASE_URL=https://api.x.ai/v1
```

Sans `GROK_VISION_ENABLED=1` **ou** sans `XAI_API_KEY`, le module est un **no-op propre**
(aucun appel réseau, aucune exception).

## Usage

```bash
python grok_vision.py --status                 # consultation (no-op si pas de clé)
python grok_vision.py --analyze BTCUSDT 1H      # rend le chart + analyse Grok + journalise l'ombre
```

L'échelle de TF suit `candles_history` : `1m 5m 15m 30m 1H 4H 1D 1W`.

## Coût

Grok vision `grok-4` : **~<0,03 $/chart** (un petit prompt + une image PNG). L'outil
est **à la demande** (pas de cron) — le coût est négligeable et sous le contrôle du
propriétaire. Aucune boucle automatique n'est posée ; le module ne s'exécute que quand on
l'invoque.

## Dépendances

- **Rendu** : `matplotlib` (déjà présent dans le Python du bot) → rendu chandeliers PUR.
  `mplfinance` est utilisé S'IL est importable (rendu plus soigné), sinon fallback
  matplotlib, sinon skip propre (`None`, jamais de crash). Aucune dépendance système
  imposée. Pour un rendu mplfinance dédié on peut l'installer en venv isolé
  `/root/grokviz_venv` (ERR-004) — inutile ici puisque matplotlib suffit et reste
  importable dans le process.
- **Appel Grok** : le paquet `openai` est utilisé s'il est présent (client
  OpenAI-compatible pointé sur xAI), sinon `urllib` POST brut (comme `llm_agent`).

## Fail-safe

Toute étape KO — pas de clé, réseau indisponible, timeout (30 s), réponse illisible/
incohérente, bougies vides, rendu impossible — retourne `None`, journalise, et **ne lève
JAMAIS**. Le module est indépendant : sa panne n'a aucun effet sur le cerveau, les boucles
ou les murs.

## Mesure

Le vote d'ombre `grok_shadow` (∈ [−1, 1], borné par `GROK_VISION_CONF_CAP`) apparaît dans
`live_ic_audit` (`python live_ic_audit.py` → bloc « voix opt-in ») une fois ≥ 50 votes
accumulés. L'analyse structurée complète (phase/events/patterns/accord objectif) est aussi
journalisée dans `.grok_vision_journal.jsonl` pour revue humaine. Statuts et sort du module :
`docs/VERDICTS.md`.
