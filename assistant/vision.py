"""
assistant/vision.py — analyse d'images de charts via modèle multimodal (LECTURE SEULE).

Classement : SAFE. Lecture seule, aucun ordre. Utilise un endpoint
OpenAI-compatible multimodal (par défaut Gemini gratuit). Séparé du LLM texte
(qui peut rester sur Groq) : ne sert qu'aux images.

Config (.env) :
  VISION_API_KEY   (clé Gemini : aistudio.google.com/apikey)
  VISION_MODEL     (défaut gemini-2.0-flash)
  VISION_BASE_URL  (défaut endpoint OpenAI-compatible Gemini)

CLI : python assistant/vision.py IMAGE [question]
"""

import os
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_MODEL = "gemini-2.0-flash"

VISION_SYSTEM = (
    "Tu es un analyste technique crypto en LECTURE SEULE. On te montre une image "
    "de graphique. Décris HONNÊTEMENT ce que tu vois : tendance, structure, niveaux "
    "de support/résistance, figures (patterns), volumes si visibles. Sois prudent et "
    "explicite sur l'incertitude (lire une image est indicatif, pas un signal). "
    "Tu n'exécutes aucun ordre et tu ne donnes pas de conseil financier."
)


class VisionError(Exception):
    pass


def build_messages(question, image_b64, media_type="image/png"):
    return [
        {"role": "system", "content": VISION_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": question or "Analyse ce graphique de trading."},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
        ]},
    ]


def analyze_image(question, image_b64, media_type="image/png", timeout=90):
    base = (os.getenv("VISION_BASE_URL") or DEFAULT_BASE).rstrip("/")
    key = os.getenv("VISION_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
    if not key:
        raise VisionError("VISION_API_KEY manquant (clé Gemini gratuite : aistudio.google.com/apikey)")
    model = os.getenv("VISION_MODEL") or DEFAULT_MODEL
    headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    body = {"model": model, "max_tokens": 1024, "messages": build_messages(question, image_b64, media_type)}
    r = requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=timeout)
    if r.status_code >= 400:
        raise VisionError(f"Vision {r.status_code} (modèle={model}): {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"]


def analyze_file(path, question=None):
    import base64
    import mimetypes
    data = Path(path).read_bytes()
    media = mimetypes.guess_type(path)[0] or "image/png"
    return analyze_image(question, base64.b64encode(data).decode(), media)


def main():
    if len(sys.argv) < 2:
        print("Usage: python assistant/vision.py IMAGE [question]")
        raise SystemExit(2)
    path = sys.argv[1]
    question = " ".join(sys.argv[2:]) or None
    try:
        print(analyze_file(path, question))
    except VisionError as exc:
        print(f"❌ {exc}")


if __name__ == "__main__":
    main()
