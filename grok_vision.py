#!/usr/bin/env python3
"""grok_vision.py — LECTURE de chart par Grok vision -> voix d'OMBRE MESURÉE (opt-in).

Classement : SAFE. Lecture seule côté marché + LLM cloud (xAI) + journal d'OMBRE.
AUCUN ordre, NE TOUCHE PAS le consensus ni le banc gelé §62, ne desserre AUCUN mur
(50/250, ×5, stop −5 %, kill-switch, porte d'edge). Il peut au plus SUGGÉRER une
direction, journalisée en ombre `grok_shadow` et mesurée par live_ic_audit — exactement
comme news_shadow / nn_shadow / qml_shadow. Il ne gagnera une VRAIE voix (via la porte
d'edge 'deflated') que si son IC live se PROUVE.

Pipeline (à la demande, `python grok_vision.py --analyze SYMBOL TF`) :
  1. bougies : candles_history.load(SYMBOL, TF) (lecture seule, endpoint public) ;
  2. rendu : chart CHANDELIERS PNG propre (mplfinance si dispo, sinon matplotlib pur) ;
  3. Grok vision : endpoint OpenAI-compatible https://api.x.ai/v1, clé XAI_API_KEY ->
     lecture Wyckoff + patterns chartistes en JSON strict ;
  4. croisement : wyckoff_lab.detect_events (événements OBJECTIFS look-ahead-free) ->
     rapport d'ACCORD/désaccord Grok <-> détecteur ;
  5. ombre : {ts, symbol, tf, bias, confidence} journalisé pour mesure d'IC.

Prior HONNÊTE : Grok est un LLM NON DÉTERMINISTE qui HALLUCINE sur la lecture de chart.
Sa lecture est du BRUIT jusqu'à preuve d'IC. Ce module ne fait qu'ACCUMULER une preuve
mesurable, jamais armer une décision.

FAIL-SAFE ABSOLU : gated GROK_VISION_ENABLED (défaut OFF) + XAI_API_KEY requis. Sans
clé / flag / réseau KO / timeout / réponse incohérente -> None, LOG, JAMAIS de crash ni
de blocage.
"""
from __future__ import annotations

import base64
import io
import json
import os
import time as _time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OVERLAY = ROOT / ".overlay_votes.jsonl"              # même journal que news/nn/qml (live_ic_audit)
JOURNAL = ROOT / ".grok_vision_journal.jsonl"        # analyse structurée COMPLÈTE (revue humaine)

# Valeurs de bias -> vote directionnel signé (comme EVENTS de wyckoff_lab).
_BIAS_SIGN = {"long": +1.0, "short": -1.0, "neutral": 0.0}
# Événements Wyckoff HAUSSIERS / BAISSIERS (pour le croisement avec le détecteur objectif).
_BULL_EVENTS = {"SC", "SPRING", "SOS", "LPS", "ST", "BU", "BUEC"}
_BEAR_EVENTS = {"BC", "UTAD", "UT", "SOW", "LPSY", "AR"}
# Événements objectifs de wyckoff_lab.detect_events -> signe.
_OBJ_SIGN = {"sc_long": +1, "spring_long": +1, "bc_short": -1, "upthrust_short": -1}


def _knob(name, default):
    """Bouton opérationnel : .env / os.environ PRIORITAIRE (armable sans éditer config.py
    suivi par git), sinon config, sinon défaut. Comme llm_agent._knob."""
    v = os.getenv(name)
    if v is not None and v.strip() != "":
        return v.strip()
    try:
        from config_utils import cfg as _cfg
        return _cfg(name, default)
    except Exception:
        return default


def _load_env():
    """Charge .env dans os.environ (best-effort, N'ÉCRASE PAS l'existant) — un lancement nu
    ou un cron n'a pas XAI_API_KEY sinon. Idempotent. Réutilise le chargeur canonique."""
    try:
        from config_utils import load_env
        load_env()
    except Exception:
        pass


def enabled():
    """Interrupteur maître (défaut OFF) : .env PRIORITAIRE (charge .env d'abord), sinon
    config. Comme llm_agent.enabled() / news_agent.enabled()."""
    _load_env()
    v = os.getenv("GROK_VISION_ENABLED", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    try:
        from config_utils import cfg as _cfg
        return bool(_cfg("GROK_VISION_ENABLED", False))
    except Exception:
        return False


def has_key():
    """True si XAI_API_KEY est présent (charge .env d'abord). Sans clé, le module est inerte."""
    _load_env()
    return bool(os.getenv("XAI_API_KEY", "").strip())


# ===================== 1. BOUGIES =====================
def _candles(symbol, tf, n=180, allow_download=True):
    """Charge les bougies via candles_history (lecture seule). Retourne
    {o,h,l,c,v,ts} (listes, au plus n dernières) OU None. Fail-safe. Si le cache local
    est vide, tente un téléchargement BORNÉ (best-effort) — seulement pour l'outil à la
    demande ; les tests injectent leurs bougies et ne touchent jamais le réseau."""
    try:
        import candles_history as ch
        rows = ch.load(symbol, tf)
        if not rows and allow_download:
            try:
                ch.download(symbol, tf, jours=30, max_pages=20)
                rows = ch.load(symbol, tf)
            except Exception:
                rows = []
        if not rows:
            return None
        rows = rows[-int(n):]
        return {
            "ts": [int(r[0]) for r in rows],
            "o": [float(r[1]) for r in rows],
            "h": [float(r[2]) for r in rows],
            "l": [float(r[3]) for r in rows],
            "c": [float(r[4]) for r in rows],
            "v": [float(r[5]) for r in rows],
        }
    except Exception:
        return None


# ===================== 2. RENDU CHANDELIERS =====================
def render_chart(candles, symbol="", tf="", max_bytes=20 * 1024 * 1024):
    """PNG chandeliers PROPRE (OHLC + volume) depuis {o,h,l,c,v,ts}. Retourne des bytes PNG
    OU None (skip propre) si le rendu est indisponible. AUCUN réseau. FAIL-SAFE.

    Essaie mplfinance si importable (le plus soigné), sinon un rendu matplotlib PUR
    (matplotlib est présent dans le Python du bot -> pas de venv nécessaire). Si aucun
    backend graphique n'est disponible -> None (le module continue sans chart, no-op)."""
    try:
        o = candles.get("o") or []
        h = candles.get("h") or []
        low = candles.get("l") or []
        c = candles.get("c") or []
        v = candles.get("v") or []
    except Exception:
        return None
    n = len(c)
    if n < 5 or not (len(o) == len(h) == len(low) == len(c) == n):
        return None

    png = _render_mplfinance(candles, symbol, tf)
    if png is None:
        png = _render_matplotlib(o, h, low, c, v, symbol, tf)
    if png is None:
        return None
    if len(png) > int(max_bytes):                    # borne dure (l'API vision plafonne à 20 MiB)
        return None
    return png


def _render_mplfinance(candles, symbol, tf):
    """Rendu via mplfinance SI importable (dépendance tierce optionnelle). None sinon."""
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import mplfinance as mpf
        import pandas as pd
        idx = pd.to_datetime(candles.get("ts"), unit="ms")
        df = pd.DataFrame({"Open": candles["o"], "High": candles["h"], "Low": candles["l"],
                           "Close": candles["c"], "Volume": candles["v"]}, index=idx)
        buf = io.BytesIO()
        mpf.plot(df, type="candle", volume=True, style="charles",
                 title=f"{symbol} {tf}", savefig=dict(fname=buf, dpi=110, format="png"))
        buf.seek(0)
        data = buf.getvalue()
        return data or None
    except Exception:
        return None


def _render_matplotlib(o, h, low, c, v, symbol, tf):
    """Rendu chandeliers en matplotlib PUR (fallback sans mplfinance). None si échec."""
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception:
        return None
    try:
        n = len(c)
        x = list(range(n))
        up = [c[i] >= o[i] for i in range(n)]
        col = ["#26a69a" if u else "#ef5350" for u in up]        # vert haussier / rouge baissier
        fig, (axp, axv) = plt.subplots(
            2, 1, sharex=True, figsize=(12, 6.5),
            gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05})
        # mèches (high-low) puis corps (open-close)
        for i in x:
            axp.plot([i, i], [low[i], h[i]], color=col[i], linewidth=0.7, zorder=1)
        bottoms = [min(o[i], c[i]) for i in x]
        heights = [max(abs(c[i] - o[i]), (h[i] - low[i]) * 1e-3, 1e-9) for i in x]
        axp.bar(x, heights, bottom=bottoms, width=0.7, color=col, linewidth=0, zorder=2)
        axp.set_title(f"{symbol} {tf} — chandeliers (n={n})", fontsize=11)
        axp.set_ylabel("prix")
        axp.grid(True, alpha=0.2)
        axv.bar(x, v, width=0.7, color=col, linewidth=0)
        axv.set_ylabel("volume")
        axv.grid(True, alpha=0.2)
        # axe X clairsemé (indices de barre — repères lisibles sans dépendre du fuseau)
        ticks = list(range(0, n, max(1, n // 8)))
        axv.set_xticks(ticks)
        axv.set_xticklabels([str(t) for t in ticks], fontsize=8)
        axv.set_xlim(-1, n)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        data = buf.getvalue()
        return data or None
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def to_data_uri(png_bytes):
    """PNG bytes -> data-URI base64 (format attendu par l'API vision). '' si vide."""
    if not png_bytes:
        return ""
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


# ===================== 3. PROMPT + APPEL GROK =====================
def build_prompt(symbol="", tf=""):
    """PUR. Prompt structuré : demande une lecture Wyckoff + patterns chartistes en JSON
    STRICT borné. Aucun secret, aucun solde, aucune position — seulement le chart."""
    return (
        f"Tu es un analyste technique SCEPTIQUE spécialiste de la méthode Wyckoff. "
        f"Voici un graphique en chandeliers ({symbol} {tf}, OHLC + volume). "
        "Lis-le et réponds UNIQUEMENT par un JSON compact, rien d'autre :\n"
        '{"phase": "accumulation|distribution|markup|markdown|range|unclear", '
        '"events": ["SC","BC","Spring","UTAD","SOS","LPSY","AR","ST"], '
        '"structure": "BOS|CHoCH|none", '
        '"patterns": ["double top","H&S","triangle","..."], '
        '"bias": "long|short|neutral", '
        '"confidence": 0.0, '
        '"raison": "<= 120 caracteres"}\n'
        "phase = phase Wyckoff dominante. events = evenements Wyckoff VISIBLES (liste vide "
        "si aucun net). structure = cassure de structure. patterns = figures chartistes "
        "classiques visibles. bias = biais directionnel NET pour les prochaines barres. "
        "confidence in [0,1]. Sois PRUDENT : si le chart est ambigu, phase=unclear, "
        "bias=neutral, confidence basse. Ne fabrique pas d'evenement absent."
    )


def _call_grok(prompt, data_uri, model=None, timeout=None):
    """Appel Grok vision (endpoint OpenAI-compatible xAI). LÈVE en cas d'échec (clé absente,
    réseau, timeout, réponse vide) -> capté par analyze() qui retourne None. Réutilise le
    paquet `openai` si présent, sinon urllib POST brut (comme llm_agent._call_cloud)."""
    key = os.getenv("XAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("XAI_API_KEY absent")
    if not data_uri:
        raise RuntimeError("image vide")
    model = model or str(_knob("GROK_VISION_MODEL", "grok-4.1-fast"))
    timeout = float(timeout if timeout is not None else _knob("GROK_VISION_TIMEOUT_S", 30.0))
    base_url = str(_knob("GROK_VISION_BASE_URL", "https://api.x.ai/v1"))
    max_tokens = int(float(_knob("GROK_VISION_MAX_TOKENS", 700)))
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_uri}},
    ]
    # Chemin préféré : paquet openai (client OpenAI-compatible pointé sur xAI).
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=base_url, timeout=timeout)
        resp = client.chat.completions.create(
            model=model, max_tokens=max_tokens, temperature=0.2,
            messages=[{"role": "user", "content": content}])
        return resp.choices[0].message.content or ""
    except ImportError:
        pass                                          # openai non installé -> urllib brut
    import urllib.request
    body = json.dumps({"model": model, "max_tokens": max_tokens, "temperature": 0.2,
                       "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    ch = data.get("choices")
    if not ch:                                        # erreur/quota -> pas de choices
        raise RuntimeError((data.get("error") or {}).get("message", "réponse sans choices"))
    return ch[0]["message"].get("content") or ""


# ===================== 4. PARSING ROBUSTE =====================
def _parse(text):
    """Extrait un dict STRUCTURÉ borné d'une réponse Grok (JSON tolérant, défauts sûrs si
    champ manquant). Retourne None seulement si aucun objet JSON n'est trouvable."""
    try:
        text = (text or "").strip()
        i, j = text.find("{"), text.rfind("}")
        if i < 0 or j <= i:
            return None
        obj = json.loads(text[i:j + 1])
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None

    def _slist(key):
        val = obj.get(key)
        if isinstance(val, str):
            val = [val]
        if not isinstance(val, list):
            return []
        return [str(x)[:40] for x in val if str(x).strip()][:12]

    phase = str(obj.get("phase", "unclear")).strip().lower() or "unclear"
    if phase not in ("accumulation", "distribution", "markup", "markdown", "range", "unclear"):
        phase = "unclear"
    structure = str(obj.get("structure", "none")).strip().upper() or "NONE"
    if structure not in ("BOS", "CHOCH", "NONE"):
        structure = "NONE"
    bias = str(obj.get("bias", "neutral")).strip().lower() or "neutral"
    if bias not in ("long", "short", "neutral"):
        bias = "neutral"
    try:
        conf = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(conf, 1.0))
    return {
        "phase": phase,
        "events": [e.upper() for e in _slist("events")],
        "structure": structure,
        "patterns": _slist("patterns"),
        "bias": bias,
        "confidence": round(conf, 3),
        "raison": str(obj.get("raison", ""))[:120],
    }


# ===================== 5. CROISEMENT AVEC wyckoff_lab =====================
def cross_wyckoff(candles, window=None):
    """Détecteur OBJECTIF look-ahead-free (wyckoff_lab.detect_events) sur les MÊMES bougies.
    Retourne {objective_events, objective_bias, n} : événements objectifs situés dans la
    fenêtre récente (au plus `window` dernières barres), et leur biais net signé. Fail-safe
    -> {} si wyckoff_lab / numpy indisponible."""
    try:
        import numpy as np
        import wyckoff_lab as wl
        o = candles["o"]; h = candles["h"]; low = candles["l"]
        c = candles["c"]; v = candles["v"]
        n = len(c)
        ev = wl.detect_events(o, h, low, c, v)
        win = int(window) if window else max(10, n // 6)
        cutoff = n - win
        recent = {}
        net = 0
        for name, idx in ev.items():
            arr = [int(t) for t in np.asarray(idx, int).tolist() if t >= cutoff]
            if arr:
                recent[name] = arr
                net += _OBJ_SIGN.get(name, 0) * len(arr)
        objective_bias = "long" if net > 0 else "short" if net < 0 else "neutral"
        return {"objective_events": recent, "objective_bias": objective_bias,
                "n_events": sum(len(a) for a in recent.values()), "window": win}
    except Exception:
        return {}


def agreement(grok, objective):
    """PUR. Accord Grok <-> détecteur objectif. Retourne {bias_agree, event_overlap,
    note}. Un désaccord n'est PAS une erreur — c'est une donnée à mesurer."""
    if not grok or not objective:
        return {"bias_agree": None, "event_overlap": False, "note": "croisement indisponible"}
    gb = grok.get("bias", "neutral")
    ob = objective.get("objective_bias", "neutral")
    bias_agree = (gb == ob)
    # Grok voit-il un climax/spring/upthrust là où le détecteur objectif en trouve un ?
    obj_dir = set()
    for name in (objective.get("objective_events") or {}):
        s = _OBJ_SIGN.get(name, 0)
        if s > 0:
            obj_dir |= _BULL_EVENTS
        elif s < 0:
            obj_dir |= _BEAR_EVENTS
    g_events = set(grok.get("events") or [])
    overlap = bool(g_events & obj_dir)
    if not (objective.get("objective_events") or {}):
        note = "aucun événement objectif dans la fenêtre"
    elif bias_agree and overlap:
        note = "accord biais + événement"
    elif bias_agree:
        note = "accord biais seul"
    elif overlap:
        note = "accord événement, biais divergent"
    else:
        note = "désaccord"
    return {"bias_agree": bias_agree, "event_overlap": overlap, "note": note}


def _bias_to_vote(bias, confidence):
    """PUR. Vote directionnel signé ∈ [-1,1] pour l'ombre : sign(bias)·confidence, borné
    par GROK_VISION_CONF_CAP (défaut 0.5) — une voix opt-in ne doit pas dominer le banc."""
    try:
        cap = float(_knob("GROK_VISION_CONF_CAP", 0.5))
    except Exception:
        cap = 0.5
    mag = max(0.0, min(float(confidence or 0.0), cap))
    return round(_BIAS_SIGN.get(str(bias).lower(), 0.0) * mag, 3)


# ===================== ORCHESTRATION =====================
def analyze(symbol, tf, candles=None, call_fn=None, render_fn=None, now=None):
    """I/O : bougies -> chart -> Grok -> parse -> croisement wyckoff_lab -> dict structuré
    OU None. Tout injectable (tests hermétiques) :
      - candles : {o,h,l,c,v,ts} (sinon candles_history.load) ;
      - render_fn(candles,symbol,tf)->png bytes (sinon render_chart) ;
      - call_fn(prompt,data_uri)->texte Grok (sinon _call_grok).
    FAIL-SAFE : toute étape KO (bougies vides / rendu None / Grok indispo / parse KO) -> None,
    JAMAIS d'exception."""
    try:
        if call_fn is None:
            _load_env()                               # XAI_API_KEY depuis .env (lancement nu)
        candles = _candles(symbol, tf) if candles is None else candles
        if not candles or len(candles.get("c") or []) < 5:
            return None
        png = (render_fn or render_chart)(candles, symbol, tf)
        if not png:
            return None
        data_uri = to_data_uri(png)
        text = (call_fn or _call_grok)(build_prompt(symbol, tf), data_uri)
        grok = _parse(text)
        if not grok:
            return None
        objective = cross_wyckoff(candles)
        acc = agreement(grok, objective)
        px = None
        try:
            px = float(candles["c"][-1])
        except Exception:
            px = None
        vote = _bias_to_vote(grok["bias"], grok["confidence"])
        return {
            "ts": int(_time.time() if now is None else now),
            "symbol": str(symbol).upper(),
            "tf": str(tf),
            "price": px,
            "phase": grok["phase"],
            "events": grok["events"],
            "structure": grok["structure"],
            "patterns": grok["patterns"],
            "bias": grok["bias"],
            "confidence": grok["confidence"],
            "raison": grok["raison"],
            "vote": vote,
            "objective": objective,
            "agreement": acc,
            "png_bytes": len(png),
        }
    except Exception:
        return None


# ===================== OMBRE (mesure) =====================
def shadow_record(vote, symbol, price, tf="", now=None):
    """PUR. Enregistrement d'OMBRE pour live_ic_audit : {ts, symbol, price, tf,
    votes:{grok_shadow}}. Même forme que news_agent.shadow_record."""
    return {"ts": int(_time.time() if now is None else now), "symbol": str(symbol).upper(),
            "price": float(price), "tf": str(tf), "votes": {"grok_shadow": round(float(vote), 3)}}


def record(result, overlay_path=None, journal_path=None):
    """Journalise le résultat : vote d'OMBRE dans .overlay_votes.jsonl (mesuré par
    live_ic_audit.overlay_snapshot) + analyse COMPLÈTE dans .grok_vision_journal.jsonl
    (revue humaine). Best-effort : ne lève jamais. Retourne True si l'ombre a été écrite."""
    if not result or result.get("price") is None:
        return False
    ok = False
    try:
        import journal_append as ja
        rec = shadow_record(result["vote"], result["symbol"], result["price"],
                            tf=result.get("tf", ""), now=result.get("ts"))
        ok = bool(ja.append_jsonl(Path(overlay_path) if overlay_path else OVERLAY, rec))
        full = {k: v for k, v in result.items() if k != "png_bytes"}
        ja.append_jsonl(Path(journal_path) if journal_path else JOURNAL, full)
    except Exception:
        pass
    return ok


# ===================== CLI =====================
def _fmt(result):
    a = result.get("agreement") or {}
    obj = result.get("objective") or {}
    ev = ", ".join(result.get("events") or []) or "—"
    pat = ", ".join(result.get("patterns") or []) or "—"
    oe = obj.get("objective_events") or {}
    oe_txt = ", ".join(f"{k}×{len(vv)}" for k, vv in oe.items()) or "aucun"
    return (
        f"=== GROK VISION — {result['symbol']} {result['tf']} ===\n"
        f"  phase       : {result['phase']}\n"
        f"  events       : {ev}\n"
        f"  structure    : {result['structure']}\n"
        f"  patterns     : {pat}\n"
        f"  bias         : {result['bias']} (confidence {result['confidence']}) -> vote d'ombre {result['vote']:+.3f}\n"
        f"  raison       : {result['raison'] or '—'}\n"
        f"  objectif WY  : biais {obj.get('objective_bias', '—')} · événements [{oe_txt}] "
        f"(fenêtre {obj.get('window', '—')} barres)\n"
        f"  accord       : {a.get('note', '—')}\n"
        f"  (OMBRE MESURÉE — aucune décision, aucun ordre ; edge À PROUVER par IC live)\n"
        f"Lecture seule. VERDICT: SAFE"
    )


def analyze_cli(symbol, tf):
    """Outil à la demande : rend le chart + l'analyse Grok, journalise l'ombre, imprime.
    No-op propre si OFF ou sans clé."""
    if not enabled():
        print("grok_vision : GROK_VISION_ENABLED off — rien fait (opt-in, défaut OFF).")
        return 0
    if not has_key():
        print("grok_vision : XAI_API_KEY absent — module inerte (aucun appel Grok).")
        return 0
    result = analyze(symbol, tf)
    if not result:
        print(f"grok_vision : pas d'analyse ({symbol} {tf}) — bougies/rendu/Grok indispo (fail-safe).")
        return 0
    record(result)
    print(_fmt(result))
    return 0


def status():
    """Consultation (lecture seule). No-op si pas de clé — n'appelle JAMAIS Grok."""
    en = enabled()
    key = has_key()
    model = str(_knob("GROK_VISION_MODEL", "grok-4.1-fast"))
    n_shadow = 0
    try:
        import journal_append as ja
        for e in ja.read_jsonl(OVERLAY):
            if isinstance(e, dict) and "grok_shadow" in (e.get("votes") or {}):
                n_shadow += 1
    except Exception:
        pass
    print("=== GROK VISION — statut ===")
    print(f"  GROK_VISION_ENABLED : {'ON' if en else 'OFF (défaut)'}")
    print(f"  XAI_API_KEY         : {'présente' if key else 'ABSENTE -> inerte'}")
    print(f"  modèle              : {model}")
    print(f"  votes d'ombre grok_shadow journalisés : {n_shadow}")
    print("  Voix d'OMBRE opt-in MESURÉE : aucun ordre, ne touche pas le consensus, "
          "ne desserre aucun mur. Edge À PROUVER (prior : lecture LLM = bruit).")
    print("Lecture seule. VERDICT: SAFE")
    return 0


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--analyze":
        sym = argv[1] if len(argv) > 1 else "BTCUSDT"
        tf = argv[2] if len(argv) > 2 else "1H"
        return analyze_cli(sym, tf)
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
