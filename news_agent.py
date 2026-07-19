#!/usr/bin/env python3
"""news_agent.py — SIGNAL COMPLÉMENTAIRE depuis le corpus de news (décision proprio 17/07).

Classement : SAFE. Lecture + LLM + journal d'OMBRE ; AUCUN ordre, NE TOUCHE PAS le consensus.
Lit le corpus du collecteur (data_collector/sorted_items.jsonl), demande à un LLM (réutilise
llm_agent : local Ollama / cloud OpenRouter) un READ directionnel NET des news récentes, et
journalise un vote en OMBRE (`news_shadow`) mesuré par live_ic_audit — exactement comme
nn_shadow / qml_shadow. Il ne gagnera une VRAIE voix (via la porte d'edge, désormais
'deflated') que si son IC live se PROUVE.

Prior HONNÊTE (recherche 17/07) : les news sont souvent EN RETARD / price-in / bruit ->
filtre sévère, mesure d'abord, jamais d'armement sur l'intuition. Ce module ne fait
qu'ACCUMULER une preuve mesurable.
"""
import json
import time as _time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ITEMS_PATH = ROOT / "data_collector" / "sorted_items.jsonl"
OVERLAY = ROOT / ".overlay_votes.jsonl"


def _ts_of(it):
    for k in ("ts", "collected_ts", "published_ts", "date_ts"):
        try:
            v = float(it.get(k))
            if v > 0:
                return v
        except (TypeError, ValueError):
            continue
    return 0.0


def recent_items(items, now=None, hours=36, cap=40):
    """PUR. Items des `hours` dernières heures (défaut 36 : le collecteur tourne 1×/jour,
    les items frais ont jusqu'à ~24h), les plus récents d'abord (au plus `cap`)."""
    now = _time.time() if now is None else now
    cutoff = now - float(hours) * 3600.0
    # borne HAUTE `<= now` : en live c'est un no-op, mais en REPLAY-IC (now = point de coupe passé)
    # ça empêche d'injecter des news POSTÉRIEURES au point de coupe (fuite du futur, IC gonflée).
    out = [it for it in (items or []) if cutoff <= _ts_of(it) <= now]
    out.sort(key=_ts_of, reverse=True)
    return out[:cap]


def build_prompt(items):
    """PUR. Prompt LLM : titres récents -> read directionnel crypto en JSON strict borné."""
    titres = "\n".join(f"- {str(it.get('title') or it.get('titre') or '')[:160]}"
                       for it in (items or [])[:40] if (it.get('title') or it.get('titre')))
    return (
        "Tu es un analyste crypto SCEPTIQUE. Titres d'actualité récents :\n"
        f"{titres}\n\n"
        "Réponds UNIQUEMENT par un JSON : {\"vote\": x, \"confidence\": y, \"why\": \"...\"}. "
        "vote in [-1,1] = read directionnel NET du marché crypto à court terme (+1 très haussier, "
        "-1 très baissier, 0 neutre ou DÉJÀ price-in). confidence in [0,1]. why <= 40 caractères. "
        "Une news déjà largement connue est price-in -> vote proche de 0."
    )


def _load_items(path=None):
    p = Path(path) if path else ITEMS_PATH
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return out


def _call_llm(prompt):
    """Réutilise le dispatch LLM de llm_agent. Backend DÉDIÉ news (NEWS_AGENT_BACKEND) :
    défaut 'cloud' — le 7b local est non viable sur ce VPS (>150 s/inférence, 2 cœurs).
    Cadence JOURNALIÈRE -> coût cloud négligeable (~1 appel/jour)."""
    import llm_agent as la
    backend = str(la._knob("NEWS_AGENT_BACKEND", "cloud")).lower()
    timeout = float(la._knob("NEWS_AGENT_TIMEOUT_S", 40.0))
    if backend == "local":
        return la._call_local(prompt, str(la._knob("LLM_AGENT_MODEL_LOCAL", "qwen2.5:1.5b")), timeout)
    if backend == "gemini":
        return la._call_gemini(prompt, str(la._knob("LLM_AGENT_MODEL_GEMINI", "gemini-2.5-flash")), timeout)
    return la._call_cloud(prompt, str(la._knob("NEWS_AGENT_MODEL_CLOUD", "openai/gpt-4o-mini")), timeout)


def _load_env():
    """Charge .env dans os.environ (best-effort, N'ÉCRASE PAS l'existant) — un cron nu n'a
    pas les clés sinon (OPENROUTER_API_KEY pour le LLM cloud). Idempotent."""
    import os
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k and k not in os.environ:
                os.environ[k] = v.strip()
    except Exception:
        pass


def analyze(items=None, call_fn=None, now=None):
    """I/O : corpus -> prompt -> LLM -> parse (réutilise llm_agent._parse) ->
    {vote, confidence, note, n_items} OU None. call_fn(prompt)->texte injectable (test)."""
    if call_fn is None:
        _load_env()                                  # clés .env pour le LLM cloud (cron nu)
    items = _load_items() if items is None else items
    hours = 36.0
    try:
        from config_utils import cfg as _cfg
        hours = float(_cfg("NEWS_AGENT_HOURS", 36))
    except Exception:
        pass
    items = recent_items(items, now=now, hours=hours)
    if not items:
        return None
    try:
        text = (call_fn or _call_llm)(build_prompt(items))
    except Exception:
        return None
    import llm_agent as la
    parsed = la._parse(text)
    if not parsed:
        return None
    vote, conf, why = parsed
    cap = 0.5
    try:
        from config_utils import cfg as _cfg
        cap = float(_cfg("NEWS_AGENT_CONF_CAP", 0.5))
    except Exception:
        pass
    return {"vote": round(float(vote), 3), "confidence": round(max(0.0, min(float(conf), cap)), 3),
            "note": f"news:{why}" if why else "news", "n_items": len(items)}


def shadow_record(vote, symbol, price, now=None):
    """PUR. Enregistrement d'OMBRE pour live_ic_audit : {ts, symbol, price, votes:{news_shadow}}."""
    return {"ts": int(_time.time() if now is None else now), "symbol": str(symbol).upper(),
            "price": float(price), "votes": {"news_shadow": round(float(vote), 3)}}


def _px(symbol):
    try:
        from candle_reader import get_bitget_candles
        c = get_bitget_candles(symbol, limit=1)
        return float(c[-1]["close"]) if c else None
    except Exception:
        return None


def cycle(items=None, call_fn=None, overlay_path=None, price_fn=None, symbols=None, now=None):
    """Produit le signal news et le JOURNALISE en OMBRE pour chaque symbole de l'univers
    (mesuré par live_ic_audit). AUCUN ordre, NE TOUCHE PAS le consensus. Tout injectable."""
    sig = analyze(items=items, call_fn=call_fn, now=now)
    if not sig:
        return {"signal": None, "journalises": 0}
    if symbols is None:
        try:
            import universe
            symbols = universe.build_universe() if universe.enabled() else None
        except Exception:
            symbols = None
        symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    price_fn = _px if price_fn is None else price_fn
    op = Path(overlay_path) if overlay_path else OVERLAY
    n = 0
    for sym in symbols:
        px = price_fn(sym)
        if not px:
            continue
        try:
            import journal_append as ja
            ja.append_jsonl(op, shadow_record(sig["vote"], sym, px, now=now))
            n += 1
        except Exception:
            pass
    return {"signal": sig, "journalises": n}


def enabled():
    """Interrupteur (défaut OFF) : .env PRIORITAIRE (charge .env d'abord — cron nu), sinon
    config. Comme llm_agent.enabled()."""
    import os
    _load_env()
    v = os.getenv("NEWS_AGENT_ENABLED", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    try:
        from config_utils import cfg as _cfg
        return bool(_cfg("NEWS_AGENT_ENABLED", False))
    except Exception:
        return False


def main():
    if not enabled():
        print("news_agent : NEWS_AGENT_ENABLED off — rien fait (opt-in).")
        return 0
    r = cycle()
    s = r["signal"]
    if s:
        print(f"news_shadow : vote {s['vote']:+.3f} · conf {s['confidence']} · {s['n_items']} items "
              f"· {s['note']} -> journalisé sur {r['journalises']} symboles (OMBRE, mesuré).")
    else:
        print("news_agent : pas de signal (corpus vide ou LLM indispo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
