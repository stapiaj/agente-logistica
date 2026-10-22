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


def load_sheets_config() -> tuple[str, str]:
    """Read the Google Sheet ID and the service account key file from .env.

    The key file is the robot's credential (a secret, never in Git); the ID
    only says which spreadsheet to open (useless without permission).
    """
    load_dotenv()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not sheet_id or not key_file:
        sys.exit("Missing GOOGLE_SHEET_ID or GOOGLE_SERVICE_ACCOUNT_FILE in .env")
    return sheet_id, key_file


VALID_DATA_SOURCES = ("memory", "sheets")


def load_data_source() -> str:
    """Where shipments, customers and the log live: "memory" or "sheets".

    Empty -> "memory" (quick tests, no API quota). Anything else stops the
    program: a typo like "shets" must not silently fall back to memory.
    """
    load_dotenv()
    source = os.getenv("DATA_SOURCE", "").strip().lower() or "memory"
    if source not in VALID_DATA_SOURCES:
        sys.exit(f"Invalid DATA_SOURCE={source!r} in .env, use one of {VALID_DATA_SOURCES}")
    return source
