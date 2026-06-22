"""
assistant/agent.py — assistant conversationnel crypto (LECTURE SEULE).

Classement : SAFE. Boucle agentique : le LLM (Claude Haiku par défaut) répond en
langage naturel et appelle des OUTILS read-only pour récupérer des données
réelles. Il n'exécute aucun ordre.

CLI :  python assistant/agent.py "ta question"
       (nécessite ANTHROPIC_API_KEY dans .env)
"""

import sys
from pathlib import Path

# Racine du repo importable (modules data + package assistant), quel que soit
# le mode de lancement.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from assistant import llm_client, tools  # noqa: E402

SYSTEM = (
    "Tu es l'assistant de trading crypto de l'utilisateur, en FRANÇAIS.\n"
    "RÈGLE ABSOLUE : tu es en LECTURE SEULE / paper. Tu n'exécutes JAMAIS d'ordre "
    "réel ; tu ne crées ni ne promeus de token. Tu aides à ANALYSER et à DÉTECTER.\n"
    "Avant de répondre, utilise les OUTILS pour récupérer des données réelles "
    "(order-flow, macro, confluence, détection rug/honeypot, DeFi, DEX, sentiment, "
    "stats). Sois concret, chiffré et concis. Si on te demande de passer un ordre, "
    "rappelle que tu es en lecture seule et propose plutôt une analyse."
)

MAX_ITERS = 6


def run(user_message, history=None, max_iters=MAX_ITERS):
    """Boucle agentique Anthropic. Retourne (texte, messages)."""
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
                        "content": out,
                    })
            messages.append({"role": "user", "content": results})
            continue
        text = "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
        return text.strip() or "(réponse vide)", messages
    return "(limite d'itérations atteinte — reformule ta question)", messages


def main():
    if len(sys.argv) < 2:
        print('Usage: python assistant/agent.py "ta question"')
        raise SystemExit(2)
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
