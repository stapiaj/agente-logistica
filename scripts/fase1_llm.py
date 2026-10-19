"""Phase 1: talk to Gemini from Python.

Step 2: give the model a role (system prompt) and a delayed-shipment case.
"""

import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types

SYSTEM_PROMPT = """You are a customer service agent for a mid-sized logistics operator.
Your job is to handle delayed shipments.

Rules:
1. Always write an email to the customer: apologise, explain the reason for the delay
   and the expected delay, in a professional tone and in the customer's language.
2. Escalate to a human supervisor if ANY of these is true:
   - delay_hours > 24
   - customer priority is "alta"
   - data is missing or inconsistent
3. Never invent data (dates, compensations, discounts) that is not in the shipment data.
"""

TEST_CASE = """Delayed shipment data:
- shipment_id: ENV-1002
- customer: Distribuciones Norte SL (priority: normal, language: es)
- route: Madrid -> Bilbao
- carrier: TransIberia
- expected_date: 2026-10-20
- delay_hours: 30
- delay_reason: Retención en el centro de distribución de Zaragoza
"""


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
        contents=TEST_CASE,  # the case of the day -> user message
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,  # the job manual -> system prompt
        ),
    )
    print(f"Model: {model}")
    print(f"Reply:\n{response.text}")


if __name__ == "__main__":
    main()
