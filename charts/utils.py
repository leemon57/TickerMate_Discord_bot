from __future__ import annotations
import pandas as pd


_FREQ_MAP = {
"min": "T",
"hour": "H",
"day": "D",
"week": "W",
"month": "M",
}


def resample_df(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample OHLCV to a coarser frequency (e.g., 'H','D','W','M')."""
    if df.empty:
        return df
    f = _FREQ_MAP.get(freq.lower(), freq)
    o = df["o"].resample(f).first()
    h = df["h"].resample(f).max()
    l = df["l"].resample(f).min()
    c = df["c"].resample(f).last()
    v = df["v"].resample(f).sum()
    out = pd.concat([o,h,l,c,v], axis=1)
    out.columns = ["o","h","l","c","v"]
    return out.dropna(how="any")
