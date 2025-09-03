import os
from dotenv import load_dotenv
load_dotenv()

class Setting:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not DISCORD_TOKEN:
        print("No DISCORD_TOKEN found. Check .env")
        raise SystemExit(1)
    if not POLYGON_API_KEY:
        print("No POLYGON_API_KEY found. Check .env")
        raise SystemExit(1)
    if not OPENAI_API_KEY:
        print("No OPENAI_API_KEY found. Check .env")
        raise SystemExit(1)

settings = Setting()
