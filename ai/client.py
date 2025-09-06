from __future__ import annotations
import os, json
from typing import Dict, Any
from openai import OpenAI

# Pick the highest-accuracy model you have access to.
PRIMARY_MODEL   = os.getenv("AI_MODEL_PRIMARY", "gpt-5")     # top reasoning quality
FALLBACK_MODEL  = os.getenv("AI_MODEL_FALLBACK", "gpt-4.1")   # strong general model

SYSTEM_MSG = (
    "You are a cautious market commentator. Use ONLY the provided JSON facts. "
    "Return ONLY valid JSON matching the schema. No markdown, no extra text. "
    "Rating: 1=strongly bearish, 2=bearish, 3=neutral, 4=bullish, 5=strongly bullish. "
    "Prefer 3 unless multiple aligned signals. Keep arrays concise; round values. "
    "If data is insufficient, choose 3 and note uncertainty."
)

# The fixed schema we expect back (kept here for clarity)
SCHEMA_HINT = {
  "symbol": "TICKER",
  "rating": 3,
  "confidence": 0.62,
  "summary": "One-liner",
  "trend": {"dir":"up|down|side","rsi":61.2,"sma20_above50":True,"price_vs_sma200":"above"},
  "levels": {"support":[236.5], "resistance":[242.0]},
  "signals_bull": ["..."],
  "signals_bear": ["..."],
  "derivs": {"funding":0.0001,"oi_chg_24h":0.03,"iv_rank":0.62},
  "events": {"next_earn":"YYYY-MM-DD","div_ex":"YYYY-MM-DD"},
  "news": ["headline1","headline2"],
  "risk_notes": ["..."]
}

def _user_message(facts: Dict[str, Any], horizon: str, risk: str) -> str:
    # ultra-compact to help the model focus
    return (
        f"HORIZON={horizon}\nRISK={risk}\n"
        f"SCHEMA={json.dumps(SCHEMA_HINT, separators=(',',':'))}\n"
        f"FACTS={json.dumps(facts, separators=(',',':'))}"
    )

def analyze(facts: Dict[str, Any], *, horizon="swing", risk="medium") -> Dict[str, Any]:
    client = OpenAI()

    def _call(model_name: str) -> Dict[str, Any]:
        resp = client.chat.completions.create(
            model=model_name,
            temperature=0.2,          # stable
            max_tokens=700,           # give room for accuracy
            response_format={"type":"json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user",   "content": _user_message(facts, horizon, risk)},
            ],
        )
        txt = resp.choices[0].message.content
        return json.loads(txt)

    try:
        return _call(PRIMARY_MODEL)
    except Exception:
        # fallback if org lacks access to o3-pro
        return _call(FALLBACK_MODEL)