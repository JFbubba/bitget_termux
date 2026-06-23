"""
assistant/agent.py — assistant conversationnel crypto (LECTURE SEULE).

Classement : SAFE. Boucle agentique : le LLM répond en langage naturel et appelle
des OUTILS read-only pour récupérer des données réelles. Il n'exécute aucun ordre.

Provider :
- Anthropic (Claude Haiku) par défaut.
- OpenAI-compatible (Groq/Gemini/Ollama…) si LLM_BASE_URL est défini dans .env.

CLI :  python assistant/agent.py "ta question"
"""

import json
import sys
from pathlib import Path

# Racine du repo importable (modules data + package assistant), quel que soit
# le mode de lancement.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from assistant import llm_client, memory, tools  # noqa: E402
import prompt_guard  # noqa: E402  (anti prompt-injection, racine du repo)

SYSTEM = (
    "Tu es l'assistant de trading crypto de l'utilisateur, en FRANÇAIS.\n"
    "RÈGLE ABSOLUE : tu es en LECTURE SEULE / paper. Tu n'exécutes JAMAIS d'ordre "
    "réel ; tu ne crées ni ne promeus de token. Tu aides à ANALYSER et à DÉTECTER.\n"
    "Avant de répondre, utilise les OUTILS pour récupérer des données réelles "
    "(order-flow, macro, confluence, détection rug/honeypot, DeFi, DEX, sentiment, "
    "stats). Sois concret, chiffré et concis. Si on te demande de passer un ordre, "
    "rappelle que tu es en lecture seule et propose plutôt une analyse."
) + prompt_guard.SYSTEM_HARDENING


def _safe_tool_out(name, out):
    """Encapsule les sorties d'outils TEXTUELLES comme données externes non fiables ;
    assainit les champs texte des sorties STRUCTURÉES (dict/list) — anti prompt-injection."""
    if isinstance(out, str):
        return prompt_guard.wrap_untrusted(out, source=name)
    return prompt_guard.sanitize_obj(out)

MAX_ITERS = 6


def _run_anthropic(user_message, history, max_iters):
    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})
    for _ in range(max_iters):
        resp = llm_client.anthropic_chat(SYSTEM, messages, tools=tools.TOOLS)
        content = resp.get("content", []) or []
        messages.append({"role": "assistant", "content": content})
        if resp.get("stop_reason") == "tool_use":
            results = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    out = tools.dispatch(block.get("name"), block.get("input") or {})
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.get("id"),
                        "content": _safe_tool_out(block.get("name"), out),
                    })
            messages.append({"role": "user", "content": results})
            continue
        text = "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
        return text.strip() or "(réponse vide)", messages
    return "(limite d'itérations atteinte — reformule ta question)", messages


def _run_openai(user_message, history, max_iters):
    messages = list(history or [])
    if not any(isinstance(m, dict) and m.get("role") == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": SYSTEM})
    messages.append({"role": "user", "content": user_message})
    for _ in range(max_iters):
        resp = llm_client.openai_chat(messages, tools=tools.TOOLS)
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls")
        assistant_msg = {"role": "assistant", "content": msg.get("content") or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)
        if tool_calls:
            for call in tool_calls:
                fn = call.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                out = tools.dispatch(fn.get("name"), args)
                messages.append({"role": "tool", "tool_call_id": call.get("id"),
                                 "content": _safe_tool_out(fn.get("name"), out)})
            continue
        return (msg.get("content") or "").strip() or "(réponse vide)", messages
    return "(limite d'itérations atteinte — reformule ta question)", messages


def run(user_message, history=None, max_iters=MAX_ITERS, use_memory=True):
    """Boucle agentique. Choisit le provider selon LLM_BASE_URL. Retourne (texte, messages).

    use_memory=True charge l'historique de conversation et y enregistre le tour.
    """
    user_message = prompt_guard.sanitize(user_message)  # neutralise contrôle/zero-width/marqueurs
    if history is None and use_memory:
        history = memory.load_messages()
    if llm_client.use_openai():
        text, msgs = _run_openai(user_message, history, max_iters)
    else:
        text, msgs = _run_anthropic(user_message, history, max_iters)
    text = prompt_guard.redact_secrets(text)  # anti-exfiltration : masque toute clé en sortie
    if use_memory:
        memory.save_turn(user_message, text)
    return text, msgs


def main():
    if len(sys.argv) < 2:
        print('Usage: python assistant/agent.py "ta question"  (ou --reset)')
        raise SystemExit(2)
    if sys.argv[1] in ("--reset", "reset"):
        memory.reset()
        print("🧠 Mémoire de conversation effacée.")
        return
    question = " ".join(sys.argv[1:])
    try:
        answer, _ = run(question)
        print(answer)
    except llm_client.LLMError as exc:
        print(f"❌ Assistant indisponible : {exc}")
    except Exception as exc:  # pragma: no cover - garde-fou CLI
        print(f"❌ Erreur : {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
