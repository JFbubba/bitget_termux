"""
assistant/llm_client.py — client LLM minimal, multi-fournisseur (LECTURE SEULE).

Classement : SAFE. Clé lue depuis l'environnement (.env). Aucun ordre.

Deux chemins, tous deux avec OUTILS (tool/function calling) :
- Anthropic Messages (Claude Haiku par défaut) — si LLM_BASE_URL n'est PAS défini.
- OpenAI-compatible (Groq, Gemini, Ollama, Moonshot/Kimi) — si LLM_BASE_URL EST
  défini (provider gratuit possible). Format chat/completions standard.

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


class LLMError(Exception):
    pass


def use_openai():
    """True si un endpoint OpenAI-compatible est configuré (Groq/Gemini/Ollama…)."""
    return bool(os.getenv("LLM_BASE_URL"))


# ---------- Anthropic ----------

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


# ---------- OpenAI-compatible (Groq / Gemini / Ollama / Moonshot) ----------

def to_openai_tools(tools):
    """Convertit les outils (format Anthropic) au format function-calling OpenAI."""
    out = []
    for t in tools or []:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        })
    return out


def openai_chat(messages, tools=None, model=None, max_tokens=2048, timeout=90):
    """Un appel chat/completions OpenAI-compatible. Retourne le JSON brut (dict)."""
    base = (os.getenv("LLM_BASE_URL") or "").rstrip("/")
    if not base:
        raise LLMError("LLM_BASE_URL manquant pour le provider OpenAI-compatible")
    key = os.getenv("LLM_API_KEY")
    if not key:
        raise LLMError("LLM_API_KEY manquant dans .env (clé du fournisseur Groq/Gemini, pas la clé Anthropic)")
    headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    body = {"model": model or DEFAULT_MODEL, "max_tokens": max_tokens, "messages": messages}
    if tools:
        body["tools"] = to_openai_tools(tools)
        body["tool_choice"] = "auto"
    resp = requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=timeout)
    if resp.status_code >= 400:
        raise LLMError(f"LLM {resp.status_code}: {resp.text[:300]}")
    return resp.json()
