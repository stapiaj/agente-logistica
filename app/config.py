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


def load_fallback_models() -> list[str]:
    """Optional backup models, in order (comma separated in .env).

    Used only if the main model fails with a 5xx (overloaded) or a 429 (quota).
    """
    load_dotenv()
    raw = os.getenv("GEMINI_FALLBACK_MODEL", "")
    return [name.strip() for name in raw.split(",") if name.strip()]
