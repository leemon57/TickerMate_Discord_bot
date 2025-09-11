from __future__ import annotations
import os
import json
from typing import Dict, Any
from openai import OpenAI

# ──────────────────────────────────────────────────────────────────────────────
# Model selection
# ──────────────────────────────────────────────────────────────────────────────
PRIMARY_MODEL  = os.getenv("AI_MODEL_PRIMARY",  "gpt-5")
FALLBACK_MODEL = os.getenv("AI_MODEL_FALLBACK", "gpt-4.1")

AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.1"))
AI_MAX_TOKENS  = int(os.getenv("AI_MAX_TOKENS", "900"))
AI_DEBUG       = os.getenv("AI_DEBUG", "0") == "1"

# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_MSG = (
    "You are a cautious market commentator. Use ONLY the provided JSON facts. "
    "Return structured fields for the analysis. "
    "Do NOT default to 3; pick the most likely direction based on evidence. "
    "If evidence is balanced, use 3 with LOW confidence and include a brief uncertainty note in risk_notes. "
    "You MUST include: an action among {buy,hold,sell}, levels (support/resistance), and both entry_plan and exit_plan. "
    "Entry guidance should be concrete (e.g., breakout above nearest resistance or pullback near support). "
    "Exit guidance should include numeric stops (e.g., just below support, ~0.5*ATR) and targets (e.g., next resistance). "
    "Default rubric (unless contradicted by facts): rating>=4 & confidence>=0.65 => buy; "
    "rating<=2 & confidence>=0.65 => sell; otherwise hold. "
    "Output must strictly match the schema when provided."
)

def _user_message(facts: Dict[str, Any], horizon: str, risk: str) -> str:
    # Keep the message compact and focused.
    return (
        f"HORIZON={horizon}\n"
        f"RISK={risk}\n"
        f"FACTS={json.dumps(facts, separators=(',',':'))}"
    )

# ──────────────────────────────────────────────────────────────────────────────
# Output schema used for Structured Outputs / Function Calling
# ──────────────────────────────────────────────────────────────────────────────
ANALYSIS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "rating": {"type": "integer", "minimum": 1, "maximum": 5},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string"},

        "action": {"type": "string", "enum": ["buy", "hold", "sell"]},  # NEW

        "trend": {
            "type": "object",
            "properties": {
                "dir": {"type": "string", "enum": ["up", "down", "side"]},
                "rsi": {"type": "number"},
                "sma20_above50": {"type": "boolean"},
                "price_vs_sma200": {"type": "string", "enum": ["above", "below"]}
            },
            "required": ["dir"],
            "additionalProperties": True
        },

        "levels": {  # tighten so model must give arrays
            "type": "object",
            "properties": {
                "support": {"type": "array", "items": {"type": "number"}},
                "resistance": {"type": "array", "items": {"type": "number"}}
            },
            "required": ["support", "resistance"],
            "additionalProperties": True
        },

        "entry_plan": {  # NEW
            "type": "object",
            "properties": {
                "method": {"type": "string"},                          # 'breakout' | 'pullback' | etc.
                "entries": {"type": "array", "items": {"type": "number"}, "maxItems": 2},
                "notes": {"type": "string"}
            },
            "required": ["method", "entries"],
            "additionalProperties": True
        },

        "exit_plan": {   # NEW
            "type": "object",
            "properties": {
                "stops": {"type": "array", "items": {"type": "number"}, "maxItems": 2},
                "targets": {"type": "array", "items": {"type": "number"}, "maxItems": 3},
                "notes": {"type": "string"}
            },
            "required": ["stops", "targets"],
            "additionalProperties": True
        },

        "signals_bull": {"type": "array", "items": {"type": "string"}},
        "signals_bear": {"type": "array", "items": {"type": "string"}},
        "derivs": {
            "type": "object",
            "properties": {
                "funding": {"type": "number"},
                "oi_chg_24h": {"type": "number"},
                "iv_rank": {"type": "number"}
            },
            "additionalProperties": True
        },
        "events": {
            "type": "object",
            "properties": {
                "next_earn": {"type": "string"},
                "div_ex": {"type": "string"}
            },
            "additionalProperties": True
        },
        "news": {"type": "array", "items": {"type": "string"}},
        "risk_notes": {"type": "array", "items": {"type": "string"}}
    },
    "required": [
        "symbol", "rating", "confidence", "summary",
        "action", "levels", "entry_plan", "exit_plan"  # NEW required fields
    ],
    "additionalProperties": True
}

# ──────────────────────────────────────────────────────────────────────────────
# Validation helpers
# ──────────────────────────────────────────────────────────────────────────────
def _validate_result(res: Dict[str, Any]) -> Dict[str, Any]:
    """
    Minimal runtime validation to make sure the cog can safely render an embed.
    Raises ValueError on critical issues.
    """
    if not isinstance(res, dict):
        raise ValueError("Result is not a JSON object")

    missing = [k for k in ("symbol", "rating", "confidence", "summary") if k not in res]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    try:
        rating = int(res["rating"])
    except Exception as e:
        raise ValueError(f"Invalid rating value: {e}")
    if not (1 <= rating <= 5):
        raise ValueError("Rating must be between 1 and 5")

    try:
        conf = float(res["confidence"])
    except Exception as e:
        raise ValueError(f"Invalid confidence value: {e}")
    if not (0.0 <= conf <= 1.0):
        raise ValueError("Confidence must be between 0 and 1")

    # Clip noisy arrays to keep Discord output tidy (non-fatal).
    for k in ("signals_bull", "signals_bear", "news", "risk_notes"):
        if isinstance(res.get(k), list) and len(res[k]) > 8:
            res[k] = res[k][:8]

    return res

def _debug_log(label: str, payload: Any) -> None:
    if AI_DEBUG:
        try:
            print(f"[AI DEBUG] {label}: {json.dumps(payload, indent=2) if not isinstance(payload, str) else payload}")
        except Exception:
            print(f"[AI DEBUG] {label}: <unserializable>")

# ──────────────────────────────────────────────────────────────────────────────
# Call strategies
# ──────────────────────────────────────────────────────────────────────────────
def _call_structured_outputs(client: OpenAI, model: str, user_msg: str) -> Dict[str, Any]:
    """
    Try 'Structured Outputs' (JSON Schema). If the model doesn't support it,
    the API will raise and we'll fall back to other methods.
    """
    resp = client.chat.completions.create(
        model=model,
        temperature=AI_TEMPERATURE,
        max_tokens=AI_MAX_TOKENS,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "analysis",
                "strict": True,
                "schema": ANALYSIS_SCHEMA
            }
        },
        messages=[
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user",   "content": user_msg},
        ],
    )
    txt = resp.choices[0].message.content
    _debug_log("StructuredOutputs.raw", txt)
    return json.loads(txt)

def _call_function_calling(client: OpenAI, model: str, user_msg: str) -> Dict[str, Any]:
    """
    Use function calling to force the shape of the result. We expect exactly one call.
    """
    tools = [{
        "type": "function",
        "function": {
            "name": "return_analysis",
            "description": "Return structured market analysis fields",
            "parameters": ANALYSIS_SCHEMA,
        },
    }]

    resp = client.chat.completions.create(
        model=model,
        temperature=AI_TEMPERATURE,
        max_tokens=AI_MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user",   "content": user_msg},
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "return_analysis"}},
    )

    msg = resp.choices[0].message
    calls = getattr(msg, "tool_calls", None) or []
    if not calls or calls[0].function.name != "return_analysis":
        raise ValueError("Model did not call return_analysis")

    args = calls[0].function.arguments
    _debug_log("FunctionCalling.args", args)
    return json.loads(args)

def _call_json_mode(client: OpenAI, model: str, user_msg: str) -> Dict[str, Any]:
    """
    Final fallback: JSON mode (valid JSON, but shape not enforced).
    """
    resp = client.chat.completions.create(
        model=model,
        temperature=AI_TEMPERATURE,
        max_tokens=AI_MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user",   "content": user_msg},
        ],
    )
    txt = resp.choices[0].message.content
    _debug_log("JsonMode.raw", txt)
    return json.loads(txt)

# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────
def analyze(facts: Dict[str, Any], *, horizon: str = "swing", risk: str = "medium") -> Dict[str, Any]:
    """
    Returns a dict with fields:
      symbol, rating(1..5), confidence(0..1), summary, trend, levels,
      signals_bull, signals_bear, derivs, events, news, risk_notes
    Raises an Exception if parsing/validation fails across all strategies.
    """
    client = OpenAI()
    user_msg = _user_message(facts, horizon, risk)

    def try_all(model_name: str) -> Dict[str, Any]:
        # 1) Structured Outputs (strict JSON Schema)
        try:
            res = _call_structured_outputs(client, model_name, user_msg)
            return _validate_result(res)
        except Exception as e:
            _debug_log(f"{model_name}.StructuredOutputs.error", str(e))

        # 2) Function Calling
        try:
            res = _call_function_calling(client, model_name, user_msg)
            return _validate_result(res)
        except Exception as e:
            _debug_log(f"{model_name}.FunctionCalling.error", str(e))

        # 3) JSON Mode (valid JSON, no enforced shape)
        res = _call_json_mode(client, model_name, user_msg)
        return _validate_result(res)

    # Try PRIMARY, then FALLBACK
    try:
        return try_all(PRIMARY_MODEL)
    except Exception as e1:
        _debug_log("PRIMARY.failure", str(e1))

    return try_all(FALLBACK_MODEL)
