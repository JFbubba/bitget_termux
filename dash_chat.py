"""dash_chat.py — chat LECTURE SEULE du dashboard : répond aux questions du
propriétaire sur l'état du bot via un LLM (Ollama local ou OpenRouter cloud).

Classement : SAFE.
  - AUCUN ordre, AUCUNE écriture d'état de trading, AUCUN accès aux clés Bitget :
    le module reçoit un contexte déjà construit (dict, sans secret) et rend du texte.
  - fail-safe : toute erreur -> {"ok": False, "erreur": ...} lisible, jamais d'exception
    qui remonte au serveur (le dashboard reste debout).
  - budget cloud : réutilise le garde-fou + le ledger de llm_agent (idée #3) — le
    backend local (Ollama) est gratuit et ne consomme aucun budget.

Leviers .env (jamais committés) :
  DASH_CHAT_MODEL_LOCAL   modèle Ollama local (défaut qwen2.5:7b, déjà sur ce VPS)
  DASH_CHAT_MODEL_CLOUD   modèle OpenRouter   (défaut anthropic/claude-haiku-4.5)
  DASH_CHAT_MAX_TOKENS    plafond de réponse  (défaut 700)
  DASH_CHAT_TIMEOUT_S     timeout d'appel     (défaut 120 local / 60 cloud)
"""
import json
import os
import time

from config_utils import cfg as _cfg


def _knob(name, default):
    """Bouton opérationnel : .env prioritaire, sinon config, sinon défaut."""
    v = os.getenv(name)
    return v if v is not None else _cfg(name, default)


SYSTEME = (
    "Tu es l'assistant du bot de trading MIROFISH (compte Bitget réel, borné par des "
    "murs durs : futures 50/250 $, levier ≤×5, stop journalier −5 %, retraits "
    "impossibles — clé Trade-only). Tu réponds en FRANÇAIS, de façon brève et précise, "
    "à partir du CONTEXTE JSON fourni : c'est l'état LIVE du bot, en lecture seule. "
    "Tu ne peux exécuter AUCUNE action : aucun ordre, aucun virement, aucun réglage — "
    "si on te le demande, explique que seuls le propriétaire et les boucles autonomes "
    "auditées agissent. Si une donnée manque du contexte, dis-le au lieu d'inventer. "
    "Les montants sont en USDT sauf mention contraire."
)


def _messages(question, contexte, history=None, max_hist=8):
    """Construit la liste de messages du chat (PUR, testable) : system + contexte,
    historique BORNÉ venu du navigateur (rôles user/assistant uniquement — un rôle
    system injecté côté client est IGNORÉ), puis la question."""
    msgs = [{"role": "system",
             "content": SYSTEME + "\n\nCONTEXTE:\n"
             + json.dumps(contexte or {}, ensure_ascii=False, default=str)}]
    for m in list(history or [])[-int(max_hist):]:
        role = str((m or {}).get("role") or "")
        content = str((m or {}).get("content") or "").strip()
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content[:4000]})
    msgs.append({"role": "user", "content": str(question or "")[:2000]})
    return msgs


def _local(msgs, timeout):
    """Ollama local (http://localhost:11434/api/chat). keep_alive garde le modèle en
    mémoire entre deux questions (sinon rechargement ~40 s via swap sur ce VPS)."""
    import urllib.request
    model = str(_knob("DASH_CHAT_MODEL_LOCAL", "qwen2.5:7b"))
    body = json.dumps({
        "model": model, "messages": msgs, "stream": False, "keep_alive": "30m",
        "options": {"temperature": 0.3,
                    "num_predict": int(float(_knob("DASH_CHAT_MAX_TOKENS", 700)))},
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return model, str((data.get("message") or {}).get("content") or "").strip()


def _cloud(msgs, timeout):
    """OpenRouter (clé OPENROUTER_API_KEY, .env gitignored). Passe par le même
    garde-fou de budget journalier et le même ledger de coût que la 15ᵉ voix."""
    import urllib.request
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY absent — utiliser le backend local")
    import llm_agent
    llm_agent._budget_guard()                    # budget cloud journalier partagé
    model = str(_knob("DASH_CHAT_MODEL_CLOUD", "anthropic/claude-haiku-4.5"))
    body = json.dumps({"model": model, "temperature": 0.3,
                       "max_tokens": int(float(_knob("DASH_CHAT_MAX_TOKENS", 700))),
                       "messages": msgs}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                 data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    llm_agent._record_cost("cloud", model, data)  # journalise tokens/coût (best-effort)
    ch = data.get("choices")
    if not ch:
        raise RuntimeError((data.get("error") or {}).get("message", "réponse sans choices"))
    return model, str(ch[0]["message"].get("content") or "").strip()


def repondre(question, contexte, backend="local", history=None):
    """Répond à une question sur l'état du bot. Renvoie TOUJOURS un dict :
    {"ok": True, "reponse", "backend", "model", "ms"} ou {"ok": False, "erreur", ...}."""
    t0 = time.time()
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "erreur": "question vide"}
    backend = "cloud" if str(backend or "").lower() == "cloud" else "local"
    msgs = _messages(q, contexte, history)
    try:
        if backend == "cloud":
            model, texte = _cloud(msgs, float(_knob("DASH_CHAT_TIMEOUT_S", 60)))
        else:
            model, texte = _local(msgs, float(_knob("DASH_CHAT_TIMEOUT_S", 120)))
        if not texte:
            return {"ok": False, "erreur": "réponse vide du modèle",
                    "backend": backend, "model": model,
                    "ms": int((time.time() - t0) * 1000)}
        return {"ok": True, "reponse": texte, "backend": backend, "model": model,
                "ms": int((time.time() - t0) * 1000)}
    except Exception as exc:                     # noqa: BLE001 — fail-safe par contrat
        return {"ok": False, "erreur": f"{type(exc).__name__}: {exc}",
                "backend": backend, "ms": int((time.time() - t0) * 1000)}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Quel est l'état du bot ?"
    print(json.dumps(repondre(q, {"note": "contexte de test CLI (vide)"}),
                     indent=2, ensure_ascii=False))
