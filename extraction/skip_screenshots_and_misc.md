---
source: package/Screenshot_*.jpg (7 fichiers Instagram), package/*.exe, `desktop.ini`,
       `auto_trading.log`, `auto_trading.pid`, `gemini-code-*.txt`,
       `package_dedup_plan.txt`, `package_inventory.py`, `source.txt`
category: skip-noise
action: skipped
target: —
---

## Détail

- **Screenshots Instagram** (7 .jpg, juin 2026) : captures de posts pédagogiques
  trading. Faible signal réutilisable (image bruyante, pas de texte structuré).
- **`mt5tester.setup (1).exe` (11 Mo)** : installateur MT5 ; aucun intérêt pour
  un repo Bitget/Python. **Ne pas** committer (binaire, viral risk).
- **`desktop.ini`** : présents dans chaque sous-dossier (créés par Windows). Bruit.
- **`auto_trading.log` / `.pid`** : logs/PID d'une exécution passée, périmés.
- **`gemini-code-1781361361215.txt`** : 1370 octets — probablement un token de
  device auth Gemini périmé. À supprimer.
- **`package_dedup_plan.txt`**, **`package_inventory.py`** : outils internes d'un
  triage antérieur — on a maintenant `drive_triage.json` + `extraction/` qui les
  remplacent.
- **`source.txt`** : 502 ko de texte non identifié ; à ouvrir une fois pour
  décider, sinon `skipped`.

## Cible d'intégration
Aucune. Ces items polluent l'arborescence sans rien apporter.
