"""Agent LLM — 15ᵉ agent OPT-IN du cerveau mixture-of-experts.

Classement : SAFE (lecture seule, AUCUN ordre). Émet un vote directionnel de même
interface que les 14 agents déterministes ({vote∈[-1,1], confidence∈[0,1], note}),
mais via un LLM (Ollama LOCAL par défaut ; OpenRouter en option).

Politique (décision propriétaire 06/07/2026, contrainte « aucun réseau de neurones »
LEVÉE) :
  • DÉTERMINISTE D'ABORD : gated LLM_AGENT_ENABLED (défaut OFF). Le banc 14 reste le
    socle ; ce module est une SURCOUCHE additive à poids fixe borné (jamais persisté,
    donc l'apprentissage EARCP du banc gelé à 14 reste intact, §62).
  • FAIL-SAFE TOTAL : OFF, indispo, timeout, réponse incohérente/illisible ->
    {vote:0, confidence:0} -> ignoré par aggregate. JAMAIS de crash, jamais de blocage.
  • AUCUN pouvoir sur les murs argent : guards() (caps 50/250, levier ×5, stop
    journalier, kill-switch, porte d'edge) reste ABSOLU et déterministe.

Données : LLM_AGENT_BACKEND='local' garde TOUT sur le VPS (qwen). ='gemini' envoie le
snapshot à Google AI Studio EN DIRECT (GEMINI_API_KEY) ; ='cloud' l'envoie à OpenRouter
(OPENROUTER_API_KEY) — les deux autorisés par le propriétaire. On n'envoie JAMAIS de
secret ni de solde/position : uniquement des features de PRIX agrégées et le symbole.
"""
from __future__ import annotations

import json
import os

from config_utils import cfg as _cfg

NEUTRE = {"vote": 0, "confidence": 0, "note": "n/a"}


def _knob(name, default):
    """Bouton opérationnel : .env PRIORITAIRE (armable sans éditer config.py suivi par
    git, comme les verrous FUTURES_AUTONOMOUS_LIVE/ACCUM_*), sinon config, sinon défaut."""
    v = os.getenv(name)
    return v if v is not None else _cfg(name, default)


def enabled():
    """Interrupteur maître (défaut OFF). Tant qu'il est False, agent() est un no-op
    neutre de confiance nulle -> le cerveau se comporte EXACTEMENT comme aujourd'hui.
    Armable via .env (LLM_AGENT_ENABLED=1) OU config."""
    v = os.getenv("LLM_AGENT_ENABLED", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(_cfg("LLM_AGENT_ENABLED", False))


def _budget_guard():
    """Lève si le budget LLM cloud journalier est atteint (idée NERVA cost_control).
    Ne bloque PAS si le module de coût est indisponible (défaut d'infra != dépassement)."""
    try:
        import llm_cost
        over = not llm_cost.budget_ok()
    except Exception:
        return
    if over:
        raise RuntimeError("budget LLM cloud journalier atteint")


def _record_cost(backend, model, data):
    """Journalise le coût d'un appel cloud (best-effort) depuis la réponse brute."""
    try:
        import llm_cost
        if backend == "gemini":
            um = data.get("usageMetadata") or {}
            llm_cost.record("gemini", model, tokens=um.get("totalTokenCount", 0), cost_usd=0.0)
        else:
            u = data.get("usage") or {}
            llm_cost.record("cloud", model, tokens=u.get("total_tokens", 0), cost_usd=u.get("cost", 0.0))
    except Exception:
        pass


def _symbol_allowed(symbol):
    """Liste blanche de symboles (LLM_AGENT_SYMBOLS='BTCUSDT,ETHUSDT'). Vide = tous.
    Sert à BORNER le coût : un backend local lent (~18 s/appel sur ce VPS CPU) ne peut
    pas voter sur TOUT l'univers à chaque cycle 1 min sans faire exploser la cadence —
    on le limite à 1-2 symboles clés. Le cloud (rapide) peut lever cette limite."""
    wl = str(_knob("LLM_AGENT_SYMBOLS", "")).strip()
    if not wl:
        return True
    return symbol.upper() in {s.strip().upper() for s in wl.split(",") if s.strip()}


def _snapshot(symbol):
    """Features de prix compactes (aucun secret, aucun solde, aucune position)."""
    import statistics

    import market_sources as ms
    closes = ms.closes(symbol, limit=60) or []
    closes = [float(c) for c in closes if c]
    if len(closes) < 20:
        return None
    last = closes[-1]
    ref = closes[-min(len(closes), 24)]
    chg = (last / ref - 1.0) * 100 if ref else 0.0
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1]]
    vol = statistics.pstdev(rets[-20:]) * 100 if len(rets) >= 2 else 0.0
    window = closes[-24:]
    hi, lo = max(window), min(window)
    pos = (last - lo) / (hi - lo) if hi > lo else 0.5
    return {"symbol": symbol, "last": round(last, 4), "chg_pct": round(chg, 2),
            "vol_pct": round(vol, 3), "range_pos": round(pos, 2)}


def _prompt(snap):
    return (
        "Tu es un trader crypto quantitatif. Voici un instantané de prix (aucune "
        "position, aucun solde). Donne un vote directionnel pour les prochaines heures.\n"
        f"{json.dumps(snap)}\n"
        "Réponds STRICTEMENT en JSON compact, rien d'autre : "
        '{"vote": <nombre -1..1>, "confidence": <nombre 0..1>, "why": "<8 mots max>"}'
    )


def _keepalive():
    """Durée de résidence du modèle local en RAM. .env PRIORITAIRE (comme les autres
    leviers) : un modèle lourd doit pouvoir être relâché SANS toucher config.py — mesuré
    le 20/07, un 7b campait 4,6 Go pendant 30 min sur ce VPS de 7,9 Go qui trade."""
    return str(_knob("LLM_AGENT_KEEPALIVE", "30m"))


def _call_local(prompt, model, timeout):
    import urllib.request
    # keep_alive : garde le modèle EN MÉMOIRE entre les cycles (sinon rechargement
    # ~40 s via swap à chaque appel sur ce VPS). À chaud, une génération ≈ 18 s.
    keep = _keepalive()
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "format": "json", "keep_alive": keep,
                       "options": {"temperature": 0.2}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()).get("response", "")


def _call_gemini(prompt, model, timeout):
    """Google AI Studio (Gemini) EN DIRECT — hors OpenRouter (le seul fournisseur cloud
    crédité au 06/07). Clé GEMINI_API_KEY (.env gitignored). JSON forcé via responseMimeType."""
    import urllib.request
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY absent")
    _budget_guard()                                  # #3 : budget cloud journalier
    max_tokens = int(float(_cfg("LLM_AGENT_MAX_TOKENS", 800)))
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
           f":generateContent?key={key}")
    # thinkingBudget=0 : coupe le raisonnement (gemini-2.5-flash est un modèle « thinking »
    # qui, sinon, épuise maxOutputTokens en réflexion et renvoie un contenu VIDE). Un vote
    # directionnel rapide n'en a pas besoin -> réponse immédiate, tient dans le budget.
    think = int(float(_cfg("LLM_AGENT_GEMINI_THINKING", 0)))
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens,
                             "responseMimeType": "application/json",
                             "thinkingConfig": {"thinkingBudget": think}},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    _record_cost("gemini", model, data)              # #3 : journalise tokens/coût
    cands = data.get("candidates")
    if not cands:                                # quota/erreur -> pas de candidates
        raise RuntimeError((data.get("error") or {}).get("message", "réponse sans candidates"))
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


def _call_cloud(prompt, model, timeout):
    import urllib.request
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY absent")
    _budget_guard()                                  # #3 : budget cloud journalier
    # Budget de sortie généreux : les modèles « thinking » (gpt-5*, o3, deepseek-r1)
    # dépensent des tokens de RAISONNEMENT avant le contenu — trop bas -> content vide
    # (finish_reason=length). 800 par défaut suffit pour un petit JSON après réflexion.
    max_tokens = int(float(_cfg("LLM_AGENT_MAX_TOKENS", 800)))
    body = json.dumps({"model": model, "max_tokens": max_tokens, "temperature": 0.2,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    _record_cost("cloud", model, data)               # #3 : journalise tokens/coût
    ch = data.get("choices")
    if not ch:                                   # 402/erreur OpenRouter -> pas de choices
        raise RuntimeError((data.get("error") or {}).get("message", "réponse sans choices"))
    return ch[0]["message"].get("content") or ""


def _parse(text):
    """Extrait (vote, confidence, why) d'une réponse LLM. None si illisible/hors bornes."""
    try:
        text = (text or "").strip()
        i, j = text.find("{"), text.rfind("}")
        if i < 0 or j <= i:
            return None
        obj = json.loads(text[i:j + 1])
        vote = float(obj.get("vote"))
        conf = float(obj.get("confidence"))
        if not (-1.0 <= vote <= 1.0) or not (0.0 <= conf <= 1.0):
            return None
        return vote, conf, str(obj.get("why", ""))[:40]
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _produce_vote(symbol):
    """Un appel LLM -> vote FRAIS. LÈVE en cas d'échec (snapshot/backend/parse) pour que
    runtime_cache dégrade en stale (dernier bon vote) ou fallback neutre, SANS mettre
    l'échec en cache."""
    snap = _snapshot(symbol)
    if not snap:
        raise RuntimeError("snapshot n/a")
    backend = str(_knob("LLM_AGENT_BACKEND", "local")).lower()
    timeout = float(_knob("LLM_AGENT_TIMEOUT_S", 8.0))
    if backend == "cloud":                       # OpenRouter (multi-fournisseurs)
        model = str(_knob("LLM_AGENT_MODEL_CLOUD", "openai/gpt-5-mini"))
        text = _call_cloud(_prompt(snap), model, timeout)
    elif backend == "gemini":                    # Google AI Studio EN DIRECT
        model = str(_knob("LLM_AGENT_MODEL_GEMINI", "gemini-2.5-flash"))
        text = _call_gemini(_prompt(snap), model, timeout)
    else:                                        # Ollama LOCAL (rien ne sort du VPS)
        model = str(_knob("LLM_AGENT_MODEL_LOCAL", "qwen2.5:1.5b"))
        text = _call_local(_prompt(snap), model, timeout)
    parsed = _parse(text)
    if not parsed:
        raise RuntimeError(f"{backend}:parse KO")
    vote, conf, why = parsed
    # confiance BORNÉE : un agent opt-in ne doit pas dominer le banc déterministe.
    conf = max(0.0, min(conf, float(_cfg("LLM_AGENT_CONF_CAP", 0.5))))
    return {"vote": round(vote, 3), "confidence": round(conf, 3),
            "note": f"{backend}:{why}" if why else backend}


def agent(symbol):
    """{vote, confidence, note}. FAIL-SAFE : neutre de confiance nulle si OFF / hors
    liste / erreur (donc ignoré par l'agrégation).

    Le vote frais est CACHÉ par symbole (runtime_cache, TTL LLM_AGENT_TTL_S, défaut
    15 min, persisté sur disque donc partagé entre les process cerveau relancés chaque
    minute). But : couvrir TOUT l'univers sans rappeler le LLM à chaque cycle 1 min ->
    respecte le quota du fournisseur. En cas d'échec, runtime_cache réutilise le dernier
    bon vote (stale-while-error)."""
    if not enabled():
        return {**NEUTRE, "note": "off"}
    if not _symbol_allowed(symbol):
        return {**NEUTRE, "note": "off:hors liste"}
    ttl = float(_cfg("LLM_AGENT_TTL_S", 900))
    try:
        import runtime_cache as rc
        return rc.get(f"llm_vote_{symbol.upper()}", ttl,
                      lambda: _produce_vote(symbol),
                      fallback={**NEUTRE, "note": "n/a"})
    except Exception:                            # runtime_cache indispo -> direct, fail-safe
        try:
            return _produce_vote(symbol)
        except Exception as exc:                 # noqa: BLE001 — fail-safe volontaire
            return {**NEUTRE, "note": f"err {type(exc).__name__}"}
