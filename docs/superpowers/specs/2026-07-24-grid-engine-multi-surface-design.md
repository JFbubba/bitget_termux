# Spec — `grid_engine` : grille exhaustive multi-surface (spot · marge · futures)

- **Date** : 2026-07-24
- **Statut** : design validé (proprio), prêt pour plan d'implémentation
- **Contexte** : demande proprio « crée ta propre stratégie/algorithme de grille en spot, marge et futures ».
  Critères de succès retenus (les trois) : (1) un **edge MESURÉ**, (2) un **bot déployable** borné §67,
  (3) une **infra réutilisable**. Angle choisi : **C exhaustif** — moteur général, tous les modes balayés,
  la porte DSR tranche.
- **Antériorité mesurée (ne pas re-tester ce qui est mort)** : `docs/GRID_STRATEGIES.md` §4 (spot long-only
  0/16 REJETÉ) + §5 (futures long-only 0/24 REJETÉ). Instruments : `grid_lab.py`, `grid_futures_measure.py`.
  **Ce spec ne re-mesure PAS le long-only** ; il ouvre les dimensions que ces mesures ont EXPLICITEMENT
  exclues (obs. « long-only to isolate fee effect ; shorts and funding = Phase 3 ») : **short** (marge/futures)
  et **funding** (perp). La variante « grille neutre » (§1 var. 11) fut écartée par RAISONNEMENT — jamais
  mesurée — et ce raisonnement comptait le funding comme coût des deux côtés, en oubliant qu'un cash-and-carry
  peut l'ENCAISSER. Ce spec comble ce trou par la mesure.

---

## 1. But & non-buts

**But** : un moteur de grille PUR et généralisé, un labo qui balaie exhaustivement
`mode × surface × funding × configs × symboles × échelle TF (M1..W1)` et rend un verdict
déflaté honnête, et un adaptateur d'exécution borné §67 **défaut OFF / DRY** qui ne déploiera
qu'une config ayant PASSÉ la porte (ou un override proprio journalisé).

**Non-buts** :
- Aucun **code d'ordre neuf** : l'adaptateur DÉLÈGUE aux exécuteurs audités (`spot_trader`,
  `margin_trader`, `futures_executor`) — jamais d'appel `bitget_execute` direct (modèle `market_maker.py` §94).
- Aucun **retrait** (clé Trade-only, aucun code de retrait n'existe).
- Pas de feed live de taux d'emprunt marge (borrow = **paramètre de sensibilité** tant qu'aucune cellule ne survit).
- Ne pas desserrer un mur, jamais (murs en dur absolus, cf. §6).

## 2. Faits chiffrés vérifiés (autoritatifs, `docs/BITGET_REFERENCE.md`)

| Surface | Maker (net BGB) | Short ? | Funding | Levier | Cap mur |
|---|---|---|---|---|---|
| **spot** | 0,08 % (8 bps) | NON (inventaire long) | non | ×1 | 200/500 |
| **marge croisée** | 0,08 % (8 bps) | OUI (borrow+sell) | non | (marge) | 200/500 |
| **futures** | 0,02 % (2 bps) | OUI (side long/short) | **oui, 8 h** | ≤×5 | 50/250 |

> **Conséquence de design honnête** : la marge n'apporte PAS de frais plus bas (8 bps comme le spot) — son
> SEUL levier neuf est le **short**. Le **futures** est la seule surface à 2 bps ET funding ET levier.
> Le funding (`funding_history`, profondeur ~3 ans paginée) est le terme économique NEUF décisif.

## 3. Architecture — 3 couches isolées

```
candles_history + funding_history
        │
        ▼
① grid_engine.py       moteur PUR (aucun I/O, aucun ordre) — réutilisable
        │                sim généralisée : mode × surface × funding + comptabilité TOTAL
        ▼
② grid_engine_lab.py   labo de MESURE — balaie tout, juge DSR/PBO/OOS/stress, verdict JSON
        │
        ▼  (SEULEMENT si une cellule SURVIT, sur décision proprio)
③ grid_trader.py       adaptateur §67 — défaut OFF, DRY, murs, DÉLÈGUE aux exécuteurs audités
```

`grid_lab.py` (verdict spot committé) reste **intact** comme référence long-only. Le moteur réutilise ses
briques PURES : `grid_lines`, `regle_dor`, `_prepare` (indicateurs ATR/ADX/BB/vol), et le juge
`evaluate_symbol_tf` / `deflated_sharpe` / `pbo`.

## 4. ① `grid_engine.py` — moteur pur (classé SAFE)

Fonctions pures, zéro réseau, zéro ordre. Sorties = valeurs de retour uniquement.

### 4.1 Descripteur de surface
```
SURFACE = {
  "spot":    {maker_bps: 8, slip_bps: 2, short: False, funding: False, lev_max: 1, cap: (200, 500)},
  "margin":  {maker_bps: 8, slip_bps: 2, short: True,  funding: False, lev_max: 1, cap: (200, 500),
              borrow_bps_per_day: <param, défaut 0 pour isoler ; sweep de sensibilité>},
  "futures": {maker_bps: 2, slip_bps: 4, short: True,  funding: True,  lev_max: 5, cap: (50, 250)},
}
```
Le `slip_bps` futures = 4 modélise le repli taker ~6 bps du post-only sur seed/coupe (cohérent
`grid_futures_measure.py`).

### 4.2 Mode de grille
- **`long_only`** : barreaux d'achat sous le mid, vente pour prendre le profit (= comportement `grid_lab`).
  Sur `spot` uniquement (pas de short). Sert de **baseline de contrôle** (doit reproduire le verdict mort).
- **`bidirectional`** : barreaux LONG sous le mid + barreaux SHORT au-dessus. Exige `short: True`.
  Fill short = le prix TRAVERSE un barreau de vente à la HAUSSE (ouverture short), rachat quand il
  retraverse en BAISSE. Symétrique → profite des deux sens du range.
- **`neutral`** : bidirectionnel + une **couverture de base statique** dimensionnée pour que le delta
  net moyen ≈ 0 (short de couverture = inventaire long attendu au centre du range). Objectif : SUPPRIMER
  structurellement le tueur #2 (perte directionnelle de l'inventaire en cassure). Sur `futures`, la
  couverture perp collecte/paye le funding. Réglage `funding_lean` (config, défaut 0 = neutre strict) :
  incline la taille du hedge selon le SIGNE/percentile du funding pour l'ENCAISSER — c'est un knob du
  mode neutral, PAS un mode séparé.

### 4.3 Comptabilité (identité TESTÉE)
```
TOTAL = grid_réalisé + latent_MTM + funding − frais − borrow
```
- `funding` : appliqué à la position perp NETTE à chaque intervalle 8 h (série `funding_history.load`).
  Signe : funding positif × position LONGUE = coût ; funding positif × position SHORT = **revenu**.
- `borrow` : `borrow_bps_per_day × |inventaire short marge| × jours` (0 par défaut, balayé en sensibilité).
- Cap d'exposition ANTI-MARTINGALE conservé : barreaux de taille FIXE, `exposition ≤ max_levels·rung`,
  aucun ajout de niveau après lancement, aucun doublement.

### 4.4 Honnêtetés héritées (BORNE SUPÉRIEURE)
Fill sans file d'attente, 1 transition/cellule/barre, seed+coupe en taker, régime-gating d'activation
(ADX<seuil ET BB stable ET volume non-expansif), coupe disciplinée sur cassure. Le réel fera MOINS bien.

## 5. ② `grid_engine_lab.py` — labo de mesure (classé SAFE)

Balaie `mode × surface × config × symbole × TF`. Réutilise le juge de `grid_lab`
(`evaluate_symbol_tf` : split OOS 60/40, DSR déflatée, PBO 8 blocs, walk-forward k=5, stress ×{1.5,2},
bat-B&H apparié). Sortie : `.grid_engine_result.json` (gitignoré) + rapport console. Fail-safe par cellule.

### 5.1 Combinaisons valides (une surface ne fait que ce qu'elle permet)
| Surface | Modes testés |
|---|---|
| spot | long_only (baseline de contrôle) |
| margin | bidirectional, neutral |
| futures | bidirectional, neutral (dont le knob `funding_lean`) |

### 5.2 Gardes d'honnêteté de mesure (LE piège de l'exhaustif C)
1. **Déflation sur TOUT le balayage** : `n_trials` = nombre TOTAL de configs testées sur la cellule
   (modes × configs), pas par mode. La DSR déflate pour l'ampleur du balayage — sinon on « trouve » un
   survivant par pur surapprentissage. **Invariant testé** : n_trials effectif ≥ nb de configs balayées.
2. **B&H apparié au MODE** : le benchmark du mode `neutral` est un **portefeuille couvert** (delta ≈ 0),
   pas le long naïf — sinon on compare une grille neutre à un B&H directionnel (faux vainqueur en range).
3. **Funding faible-puissance signalé** : profondeur funding par symbole rapportée ; une cellule dont le
   verdict DÉPEND du funding sur **< 90 intervalles (~1 mois, 8 h × 90)** est **marquée `low_power_funding`**
   (jamais un faux vert).
4. **Baseline de contrôle** : le mode `long_only`/spot DOIT reproduire ~le verdict mort (0 survivant) —
   s'il « survit », c'est un BUG du moteur, pas un edge (test de non-régression du verdict connu).

### 5.3 Périmètre symboles
Défaut = cœur liquide **BTC/ETH/SOL** (tractable pour un balayage lourd). Option `--univers` branche
`universe.py` (source de vérité dynamique, ERR-001-symboles). Balayage lourd → `run_in_background`,
historique borné d'emblée (VPS 2 cœurs, ERR labos-lourds).

## 6. ③ `grid_trader.py` — adaptateur d'exécution §67 (défaut OFF, DRY)

**Ne place AUCUN ordre lui-même.** Coordonne et DÉLÈGUE :
- spot → `spot_trader` (quote/order), marge → `margin_trader.order(...)`, futures → `futures_executor` (open/reduce).
- Modèle `market_maker.py` §94 : le module tient son inventaire logique, les ordres passent par les
  surfaces audités qui appliquent LEURS propres gardes.

**Gardes propres (SOUS les murs, jamais au-dessus)** :
- `GRID_TRADE_LIVE=0` défaut OFF → **DRY** (journalise l'intention, ne délègue rien).
- Caps effectifs par-op / jour / **exposition** (≤ caps murs de la surface, cf. §2).
- **Kill-switch fail-closed** : `KILL_SWITCH` présent → aucun ordre (spot ET futures ET marge).
- Post-only (maker) sur les fills de grille ; seed/coupe = repli taker gardé.
- Ne déploie qu'une config **`survives=True`** du labo, OU un override proprio explicite avec
  **espérance mesurée journalisée + notifiée Telegram** (§92).
- Une action/cycle bornée, journalisée, réversible. **Retrait impossible.**

## 7. Flux de données
`candles_history + funding_history` → `grid_engine` (sim pure) → `grid_engine_lab` (mesure/DSR) →
verdict JSON → **[si survit & proprio arme]** → `grid_trader` (DRY/live, délègue §67, sous les murs).

## 8. Murs & fail-safe (constitution — non négociables)
Murs en dur intacts (futures 50/250 ×5, marge 200/500, spot 200/500), stop −5 %→kill-switch,
kill-switch fail-closed, DRY par défaut, chaque cellule fail-safe (cassée → sautée, jamais de crash),
aucun code d'ordre neuf hors exécuteurs audités. Les 3 (4) portes doivent passer avant push.
**Hygiène d'armement** : un éventuel `GRID_TRADE_LIVE`/hausse de cap voyage en commit ISOLÉ, motivé, réversible.

## 9. Tests (pytest `tests/`, ERR-001 échelle complète)
- Génération barreaux short + fill short (prix traverse à la hausse → short ; rachat en baisse).
- **Signe du funding** (long paie / short encaisse sur funding positif).
- **Invariant delta ≈ 0** en mode neutral (sur un range synthétique).
- **Identité comptable** `TOTAL = grid + latent + funding − frais − borrow` (jeu déterministe).
- Monotonie du stress de coûts (frais ↑ → TOTAL ↓).
- Caps d'exposition JAMAIS dépassés.
- **Non-régression du verdict** : `long_only`/spot ne survit pas (reproduit le mort connu).
- `grid_trader` en DRY ne délègue AUCUN ordre ; kill-switch présent → aucune délégation.

## 10. Livrables & classification sécurité
| Fichier | Rôle | Classe |
|---|---|---|
| `grid_engine.py` | moteur pur | SAFE (aucun ordre) |
| `grid_engine_lab.py` | labo de mesure | SAFE (lecture seule + JSON) |
| `grid_trader.py` | adaptateur §67 | SAFE si délégation stricte (audité à part par `security_agent`/`safe_push_check` comme surface §67) |
| `tests/test_grid_engine_*.py` | banc unitaire | test |
| `.grid_engine_result.json` | sortie labo | gitignoré |

## 11. Risques & honnêteté a priori
Le prior reste **négatif** : frais (marge = 8 bps comme spot), double frais du hedge, funding qui peut
s'inverser, risque de base spot↔perp. Le mode `neutral` est **la seule hypothèse non réfutée** par mes
mesures ; il n'est pas garanti gagnant. **Succès = verdict HONNÊTE**, pas un survivant à tout prix. Si tout
mesure mort, la grille est close DÉFINITIVEMENT sur les 3 surfaces (et on l'écrit dans `GRID_STRATEGIES.md` §6).
