from __future__ import annotations
import pandas as pd
from intel.contract import Bar




def bars_to_df(bars: list[Bar]) -> pd.DataFrame:
    """Convert list of Bar into time-indexed DataFrame: columns [o,h,l,c,v]."""
    if not bars:
        return pd.DataFrame(columns=["o","h","l","c","v"]).astype({
        "o": float, "h": float, "l": float, "c": float, "v": int
        })
    df = pd.DataFrame([{ "t": b.t, "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v } for b in bars])
    df["dt"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df = df.set_index("dt").sort_index()
    return df[["o","h","l","c","v"]]
