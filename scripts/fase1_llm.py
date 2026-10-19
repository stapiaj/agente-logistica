"""Phase 1: talk to Gemini from Python.

Step 1: send a test message and print the reply.
"""

import os
import sys

from dotenv import load_dotenv
from google import genai


def load_config() -> tuple[str, str]:
    """Read the API key and model name from .env. Stop if any is missing."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")
    if not api_key or not model:
        sys.exit("Missing GEMINI_API_KEY or GEMINI_MODEL in .env")
    return api_key, model


def main() -> None:
    api_key, model = load_config()
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents="Responde en una frase: ¿estás funcionando?",
    )
    print(f"Model: {model}")
    print(f"Reply: {response.text}")


if __name__ == "__main__":
    main()
