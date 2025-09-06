from __future__ import annotations
import pandas as pd

def require_cols(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing columns: {missing}")

def typical_price(df: pd.DataFrame) -> pd.Series:
    require_cols(df, ["h", "l", "c"])
    return (df["h"] + df["l"] + df["c"]) / 3.0

def safe_ewm(s: pd.Series, span: int):
    return s.ewm(span=span, adjust=False, min_periods=span)
