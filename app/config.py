"""Load settings from .env (moved here from scripts/fase1_llm.py)."""

import os
import sys

from dotenv import load_dotenv


def load_config() -> tuple[str, str]:
    """Read the API key and model name from .env. Stop if any is missing."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")
    if not api_key or not model:
        sys.exit("Missing GEMINI_API_KEY or GEMINI_MODEL in .env")
    return api_key, model


def load_fallback_model() -> str | None:
    """Optional backup model, used only if the main one fails with a 5xx."""
    load_dotenv()
    return os.getenv("GEMINI_FALLBACK_MODEL") or None
