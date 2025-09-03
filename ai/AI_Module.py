import os
from config import settings
from openai import OpenAI

key = settings.OPENAI_API_KEY
if not key:
    raise SystemExit("OPENAI_API_KEY missing—check your .env")

client = OpenAI(api_key=key)

try:
    resp = client.responses.create(
        model="gpt-5",
        input="Reply with exactly: OK"
    )
    print("API reply:", resp.output_text)
except Exception as e:
    print("OpenAI error:", e)

