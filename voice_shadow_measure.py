#!/usr/bin/env python3
"""voice_shadow_measure.py — SUIVI des voix opt-in MUETTES (qml_shadow, nn_shadow).

Classement : SAFE. Lecture seule (audit IC + métas d'entraînement ; aucun ordre, aucun
secret). Ne touche JAMAIS le consensus ni les murs.

Une voix gatée se TAIT tant que son `wf_edge` (edge walk-forward hors-échantillon, borne
du gate) ≤ 0. Mais elle journalise son OMBRE (§89) -> un IC live jugé par le même audit
que les 14. La porte se fie au `wf_edge` (out-of-sample, conservateur) ; l'IC live est la
2ᵉ preuve. Ce suivi expose la DIVERGENCE backtest↔live et alerte quand l'IC live devient
fortement positif (pearsonIC = métrique PnL §78 — PAS le rankIC seul : signes parfois
opposés, §96) ALORS QUE le gate reste fermé -> déclencheur de REVUE. JAMAIS une promotion
auto : le gate a raison de se fier au walk-forward ; seule une décision proprio outrepasse.

Le franchissement du `wf_edge` lui-même (la voix qui parle) est déjà alerté par les
scripts de train (neural_net `_notify_gate_transition`, qml_prototype/train_voice). Ici
on surveille la preuve que le gate IGNORE : l'IC live de l'ombre.

Usage : python voice_shadow_measure.py [--alert]
  --alert : Telegram SEULEMENT au CHANGEMENT de verdict (dédup via .voice_shadow_state.json)
            -> pas de répétition hebdomadaire (anti-fatigue, leçon ERR-012).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".voice_shadow_state.json"
MIN_N = 500             # échantillon minimal d'ombre pour juger
PIC_MIN = 0.02          # pearsonIC (PnL) : seuil de « fortement positif »
PIC_T_MIN = 3.0         # significativité (t-stat)
VOICES = {"qml_shadow": "qml_voice_weights.json", "nn_shadow": "neural_net_meta.json",
          "firm_shadow": "firm_voice_meta.json"}   # §firme : firm n'a pas de wf_edge (LLM non
# entraîné) -> wf_edge=None ; le suivi mesure alors l'IC live d'ombre et FLAGGE une revue si
# fortement positif (l'armement de la voix reste un acte délibéré, jamais auto).


def wf_edge_of(voice, root=None):
    """wf_edge du dernier entraînement de la voix. qml niche sous 'meta', nn est plat."""
    root = Path(root) if root else ROOT
    try:
        d = json.loads((root / VOICES[voice]).read_text(encoding="utf-8"))
        meta = d.get("meta", d) if isinstance(d, dict) else {}
        v = meta.get("wf_edge")
        return None if v is None else float(v)
    except Exception:
        return None


def verdict(voice, m, wf_edge):
    """PURE. (clef, message). m = {ic, ic_t, pic, pic_t, n} ou None.
    clefs : building (n<MIN_N) · watch (live PnL+ fort mais gate fermé -> revue) ·
    aligned-pos (live+ ET gate+) · aligned (live non concluant -> mutisme justifié)."""
    n = (m or {}).get("n") or 0
    if not m or n < MIN_N:
        return "building", f"{voice} : ombre insuffisante (n={n} < {MIN_N})."
    pic, pic_t, ic = m.get("pic"), m.get("pic_t"), m.get("ic")
    we = "?" if wf_edge is None else f"{wf_edge:+.3f}"
    base = (f"{voice} : IC live pearson {0.0 if pic is None else pic:+.3f} "
            f"(t {0.0 if pic_t is None else pic_t:+.1f}) · rank {0.0 if ic is None else ic:+.3f} "
            f"· wf_edge backtest {we} (n {n})")
    fort_positif = (pic is not None and pic_t is not None and pic >= PIC_MIN and pic_t >= PIC_T_MIN)
    if fort_positif:
        if wf_edge is not None and wf_edge <= 0:
            return "watch", ("🔮 " + base + " → edge LIVE positif ALORS QUE le gate (wf_edge) "
                             "reste fermé : DIVERGENCE backtest↔live. REVUE proprio — le gate se fie "
                             "au walk-forward (plus conservateur) ; ne pas promouvoir sur le live seul.")
        return "aligned-pos", "🔮 " + base + " → live ET gate positifs (la voix parle si armée)."
    return "aligned", base + " → IC live non concluant ; le mutisme (gate) reste justifié."


def collect():
    """I/O : IC d'ombre (overlay_snapshot) + wf_edge par voix -> [(voice, m, wf_edge, key, msg)]."""
    import live_ic_audit as la
    snap = la.overlay_snapshot()
    par_voix = {a["agent"]: a for a in snap.get("agents", [])}
    out = []
    for v in VOICES:
        m = par_voix.get(v)
        we = wf_edge_of(v)
        key, msg = verdict(v, m, we)
        out.append((v, m, we, key, msg))
    return out


def _load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(st):
    try:
        STATE.write_text(json.dumps(st), encoding="utf-8")
    except Exception:
        pass


def _telegram(msg):
    try:
        import telegram_notifier as tn
        return bool(tn.send_telegram_message(msg))
    except Exception:
        return False


def main():
    alert = "--alert" in sys.argv[1:]
    rows = collect()
    print("=== SUIVI VOIX SHADOW (opt-in muettes) — lecture seule ===")
    st = _load_state()
    changed = False
    for voice, m, we, key, msg in rows:
        print(f"VERDICT[{key}] {msg}")
        if alert and key in ("watch", "aligned-pos") and st.get(voice) != key:
            print("  [telegram]", _telegram(msg))
            st[voice] = key
            changed = True
        elif alert and st.get(voice) != key:
            st[voice] = key                  # mémorise sans notifier (retour au calme)
            changed = True
    if alert and changed:
        _save_state(st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
