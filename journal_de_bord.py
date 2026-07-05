"""
journal_de_bord.py — journal de bord du bot (lecture seule, SAFE).

§63 : les derniers ÉVÉNEMENTS notables fusionnés — ordres RÉELS futures, achats
DCA réels, fermetures SL/TP côté exchange, échecs et black-outs de la boucle
directionnelle. Source de vérité PARTAGÉE : le dashboard (panneau « journal de
bord ») ET la commande Telegram /bord lisent CE module — une seule logique, pas
de dérive entre les deux surfaces.

Fonctions PURES côté parsing. AUCUN ordre, AUCUN réseau. Best-effort : ne lève
jamais, retourne [] / rapport dégradé si une source manque.
CLI : python journal_de_bord.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
JOURNAL = REPO_ROOT / "futures_auto_journal.jsonl"

_ICONES = {"ordre": "🎯", "dca": "🟠", "sl_tp": "🔒", "echec": "⚠️", "blackout": "🌑"}


def evenements(limit=12):
    """Derniers événements notables fusionnés, plus récents d'abord.
    [{ts, type, txt}] avec ts en SECONDES epoch. Lecture seule, [] best-effort."""
    evs = []
    try:
        lignes = JOURNAL.read_text(encoding="utf-8", errors="ignore").splitlines()[-2000:]
        for ligne in lignes:
            try:
                e = json.loads(ligne)
            except Exception:
                continue
            ts = e.get("ts")
            if not ts:
                continue
            if e.get("action") == "fermee_exchange":
                evs.append({"ts": ts, "type": "sl_tp",
                            "txt": f"SL/TP exchange : {e.get('side')} {e.get('symbol', '')}"})
                continue
            d = e.get("decision") or {}
            res = e.get("resultat") or {}
            if res and not res.get("executed"):
                evs.append({"ts": ts, "type": "echec",
                            "txt": f"échec {d.get('action')} {e.get('symbol') or ''}"})
            elif "black-out" in str(d.get("raison", "")):
                evs.append({"ts": ts, "type": "blackout",
                            "txt": "ouverture gelée (black-out macro)"})
    except Exception:
        pass
    try:                                       # ordres RÉELS : source de vérité = ledger exécuteur
        import futures_auto as fa
        for e in (fa._executor_events() or [])[-60:]:
            if not isinstance(e, dict) or e.get("action") != "FUTURES_REAL":
                continue
            o = e.get("order") or {}
            evs.append({"ts": e.get("ts"), "type": "ordre",
                        "txt": f"{'RÉDUIT' if o.get('reduce') else 'OUVRE'} "
                               f"{o.get('side') or ''} {o.get('symbol') or 'BTCUSDT'} "
                               f"~{o.get('notional_usdt') or '?'} $ ({o.get('agent')})"})
    except Exception:
        pass
    try:
        import spot_executor as se
        for b in (se._load_real().get("buys") or [])[-10:]:
            if b.get("ts"):
                m = b.get("amount_usdt")
                evs.append({"ts": b["ts"], "type": "dca",
                            "txt": f"DCA réel {m if m is not None else '?'} $ BTC"})
    except Exception:
        pass
    evs = [e for e in evs if e.get("ts")]
    evs.sort(key=lambda x: -x["ts"])
    return evs[:limit]


def _horodatage(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%d/%m %H:%M")
    except Exception:
        return "?"


def build_report(limit=12):
    """Rapport texte du journal de bord — pour /bord et le CLI. VERDICT: SAFE."""
    evs = evenements(limit)
    lignes = ["=== JOURNAL DE BORD — derniers événements (UTC) ==="]
    if not evs:
        lignes.append("  (aucun événement notable récent)")
    for e in evs:
        icone = _ICONES.get(e.get("type"), "•")
        lignes.append(f"  {icone} {_horodatage(e.get('ts'))} — {e.get('txt')}")
    lignes.append("Lecture seule — le passé du bot, sans retouche. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
