"""List the Gemini models available to this API key (only Flash ones)."""

import os

from dotenv import load_dotenv
from google import genai

load_dotenv()  # reads .env and loads its values as environment variables

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

for model in client.models.list():
    if "flash" in model.name.lower():
        print(model.name)
