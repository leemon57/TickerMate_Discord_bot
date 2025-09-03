import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
key = os.getenv("OPENAI_API_KEY")
if not key:
    raise SystemExit("OPENAI_API_KEY missing—check your .env")

client = OpenAI(api_key=key)

try:
    resp = client.responses.create(
        model="gpt-4o-mini",
        input="Reply with exactly: OK"
    )
    print("API reply:", resp.output_text)
except Exception as e:
    print("OpenAI error:", e)
    