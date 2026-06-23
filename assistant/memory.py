"""
assistant/memory.py — mémoire de conversation persistante (LECTURE SEULE).

Classement : SAFE. Stocke un historique SIMPLIFIÉ (question / réponse en texte,
sans blocs d'outils) sur disque, partagé entre les appels (chaque /ask est un
process neuf). Plafonné pour rester léger et agnostique au fournisseur.

Le fichier d'état est gitignoré (contenu de conversation, pas un secret mais
runtime). Effaçable via reset().
"""

import json
import os
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent / "conversation_state.json"
MAX_TURNS = int(os.getenv("ASSISTANT_MEMORY_TURNS") or "8")  # paires Q/R gardées


def _read():
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {"turns": []}


def load_messages():
    """Historique en messages {role, content} (texte seul) pour le LLM."""
    msgs = []
    for turn in (_read().get("turns") or [])[-MAX_TURNS:]:
        if turn.get("user"):
            msgs.append({"role": "user", "content": turn["user"]})
        if turn.get("assistant"):
            msgs.append({"role": "assistant", "content": turn["assistant"]})
    return msgs


def save_turn(user, assistant):
    data = _read()
    turns = (data.get("turns") or []) + [{"user": user, "assistant": assistant}]
    data["turns"] = turns[-MAX_TURNS:]
    try:
        STORE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # la mémoire ne doit jamais casser l'assistant


def reset():
    try:
        STORE.unlink()
    except FileNotFoundError:
        pass
