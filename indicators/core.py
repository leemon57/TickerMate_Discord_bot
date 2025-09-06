from __future__ import annotations
import pandas as pd
from .helpers import require_cols, typical_price, safe_ewm

# --- Moving Averages ---
def sma(df: pd.DataFrame, n: int = 20, col: str = "c") -> pd.Series:
    if col not in df.columns: raise ValueError(f"missing column {col}")
    return df[col].rolling(n, min_periods=n).mean()

def ema(df: pd.DataFrame, n: int = 20, col: str = "c") -> pd.Series:
    if col not in df.columns: raise ValueError(f"missing column {col}")
    return df[col].ewm(span=n, adjust=False, min_periods=n).mean()

def vol_sma(df: pd.DataFrame, n: int = 20) -> pd.Series:
    require_cols(df, ["v"])
    return df["v"].rolling(n, min_periods=n).mean()

# --- RSI (Wilder 14 by default) ---
def rsi(df: pd.DataFrame, n: int = 14, col: str = "c") -> pd.Series:
    if col not in df.columns: raise ValueError(f"missing column {col}")
    delta = df[col].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-12)
    return 100 - (100 / (1 + rs))

# --- MACD ---
def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9, col: str = "c"):
    if col not in df.columns: raise ValueError(f"missing column {col}")
    fast_ = df[col].ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_ = df[col].ewm(span=slow, adjust=False, min_periods=slow).mean()
    line = fast_ - slow_
    signal_line = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = line - signal_line
    return line, signal_line, hist

# --- Bollinger Bands ---
def bollinger_bands(df: pd.DataFrame, n: int = 20, k: float = 2.0, col: str = "c") -> pd.DataFrame:
    if col not in df.columns: raise ValueError(f"missing column {col}")
    ma = df[col].rolling(n, min_periods=n).mean()
    std = df[col].rolling(n, min_periods=n).std(ddof=0)
    upper = ma + k * std
    lower = ma - k * std
    return pd.DataFrame({"mid": ma, "upper": upper, "lower": lower})

# --- ATR (Wilder) ---
def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    require_cols(df, ["h", "l", "c"])
    # true range with previous close
    prev_close = df["c"].shift(1)
    tr = pd.concat([
        (df["h"] - df["l"]).abs(),
        (df["h"] - prev_close).abs(),
        (df["l"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

# --- Stochastic (fast %K and %D) ---
def stoch(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
    require_cols(df, ["h", "l", "c"])
    low_k = df["l"].rolling(k, min_periods=k).min()
    high_k = df["h"].rolling(k, min_periods=k).max()
    pct_k = 100 * (df["c"] - low_k) / (high_k - low_k).replace(0, 1e-12)
    pct_d = pct_k.rolling(d, min_periods=d).mean()
    return pd.DataFrame({"%K": pct_k, "%D": pct_d})

# --- VWAP (session-agnostic, cumulative) ---
def vwap(df: pd.DataFrame) -> pd.Series:
    require_cols(df, ["h", "l", "c", "v"])
    tp = typical_price(df)
    pv = tp * df["v"]
    cum_pv = pv.cumsum()
    cum_v = df["v"].cumsum().replace(0, 1e-12)
    return cum_pv / cum_v

# --- On-Balance Volume ---
def obv(df: pd.DataFrame) -> pd.Series:
    require_cols(df, ["c", "v"])
    direction = df["c"].diff().fillna(0).clip(-1, 1)
    return (direction.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["v"]).cumsum()
