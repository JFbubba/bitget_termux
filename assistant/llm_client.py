"""
assistant/llm_client.py — client LLM minimal, multi-fournisseur (LECTURE SEULE).

Classement : SAFE. Aucune clé en dur : elle est lue depuis l'environnement
(.env). Aucun ordre, aucune écriture de trading.

- Par défaut : API Anthropic (Messages), avec boucle d'outils (tool use).
  Modèle par défaut : Claude Haiku (pas cher, excellent en tool-use).
- Extension réservée : endpoint OpenAI-compatible (Kimi/Moonshot, Ollama local)
  via LLM_BASE_URL, pour du texte simple. La boucle agentique passe par Anthropic.

Dépendance : requests (déjà dans requirements).
"""

import os
from pathlib import Path

import requests

try:  # charge le .env de la racine du repo (présent sur le VPS) avant tout getenv
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

DEFAULT_MODEL = os.getenv("LLM_MODEL") or "claude-haiku-4-5"
PROVIDER = (os.getenv("LLM_PROVIDER") or "anthropic").lower()


class LLMError(Exception):
    pass


def _anthropic_key():
    key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY manquant dans .env")
    return key


def anthropic_chat(system, messages, tools=None, model=None, max_tokens=2048, timeout=60):
    """Un appel à l'API Anthropic Messages. Retourne le JSON brut (dict)."""
    headers = {
        "x-api-key": _anthropic_key(),
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
    resp = requests.post(ANTHROPIC_URL, headers=headers, json=body, timeout=timeout)
    if resp.status_code >= 400:
        raise LLMError(f"Anthropic {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def openai_compatible_text(system, user, model=None, max_tokens=2048, timeout=60):
    """Point d'extension OpenAI-compatible (Kimi/Moonshot, Ollama) — texte simple.

    Les outils ne sont pas gérés ici pour l'instant : le chemin agentique (avec
    outils) passe par Anthropic. Réservé pour garder l'option ouverte sans
    verrouillage fournisseur.
    """
    base = (os.getenv("LLM_BASE_URL") or "").rstrip("/")
    if not base:
        raise LLMError("LLM_BASE_URL manquant pour le provider OpenAI-compatible")
    key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or "none"
    headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    body = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    resp = requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=timeout)
    if resp.status_code >= 400:
        raise LLMError(f"LLM {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"]
