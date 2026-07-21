# Dashboard : SWR + rafraîchisseur de fond, rendez-vous §110, structure par terme

Date : 2026-07-21 · Statut : approuvé par le propriétaire (deux volets)

## Problème mesuré

- `/api/state` : 41,5 s à froid, **9,9 s à chaud** (promesse §69 : ~0,04 s à chaud).
  Cause : à l'expiration d'un TTL court (cerveau 45 s, positions 15 s, book 8 s…),
  le producteur réseau est recalculé DANS le chemin de requête ; `health` n'est
  jamais caché ; `projection` est recalculée à chaque requête.
- Contenu : le panneau rendez-vous affiche « fenêtre DCA (16-20h) » approximatif
  (la vraie cadence §110 = tirs horaires 16:05–19:05, 1 achat/j) ; la structure
  par terme Deribit (descripteur de régime, cron 07:40) n'est affichée nulle part.

## Volet 1 — latence : stale-while-revalidate + rafraîchisseur

1. `_cached(key, ttl, producer)` passe en **SWR** : frais → servi ; périmé mais
   < borne dure (min(max(5×ttl, 120 s), 3600 s)) → l'ANCIEN est servi
   immédiatement et un thread daemon single-flight par clé rafraîchit en fond
   (plafond global de rafraîchissements simultanés : 6 — au-delà on sert l'ancien
   sans lancer de thread, le prochain appel réessaie) ; absent ou au-delà de la
   borne dure → calcul synchrone (comportement actuel).
2. **Rafraîchisseur de fond** (thread daemon dans `main()`) : toutes les ~20 s,
   si une requête a été vue il y a < 10 min (ou depuis le boot), reconstruit
   `build_state(dernier symbol, dernier tf)` — les caches restent chauds, le
   chemin de requête ne paie plus jamais un producteur réseau déjà vu.
3. Boucher les trous : `health` caché 20 s ; `projection` cachée 20 s
   (clé `proj:{symbol}:{tf}`).

Résultat attendu : `/api/state` stable ≤ ~0,3 s à chaud (mesuré avant/après).
Aucun changement de comportement fonctionnel : mêmes producteurs, lecture seule.

## Volet 2 — contenu

1. Rendez-vous : fonction PURE `prochain_tir_dca(now, dernier_achat_ts)`
   (testable sans réseau) → prochain tir :05 dans la fenêtre 16:05–19:05 UTC,
   reporté au lendemain 16:05 si achat déjà fait aujourd'hui ou fenêtre passée.
   Libellé : « tir DCA (fenêtre 16:05–19:05) ».
2. Nouveau bloc d'état `term_structure` (TTL 1800 s, comme `vol_iv`) :
   `term_structure.snapshot()` (GET Deribit keyless) avec REPLI sur la dernière
   ligne de `term_structure_history.jsonl` (relevé du cron 07:40) si le réseau
   est muet. Panneau compact : régime + stress, basis médian, pente, points.

## Tests (tests_audit.py)

- `test_dashboard_cache_swr` : frais → servi sans recalcul ; périmé → ancien
  servi immédiatement puis valeur rafraîchie en fond ; absent → calcul synchrone.
- `test_dashboard_prochain_tir_dca` : avant/pendant/après la fenêtre, achat déjà
  fait aujourd'hui, bord de fenêtre.

## Hors périmètre

`futures_live` expose déjà les événements §109 ; murs/verrous déjà sourcés ;
aucun nouvel appel signé ; aucun chemin d'exécution touché.
