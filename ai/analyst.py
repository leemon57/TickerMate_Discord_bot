from __future__ import annotations
from typing import Dict, Any
from datetime import datetime, timezone
import numpy as np
import pandas as pd

from charts.adapters import bars_to_df
from indicators.core import (
    sma, ema, rsi, macd, bollinger_bands, atr, vwap, vol_sma
)

def _round(x, n=3):
    try:
        return None if x is None else float(round(float(x), n))
    except Exception:
        return None

def _pct(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return float((a - b) / b)
    except Exception:
        return None

def _as_utc(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

def _levels(df: pd.DataFrame, lookback: int = 180, n: int = 3):
    """
    Heuristic S/R:
      - swing points (window=3) get a score boost
      - histogram of prices (ATR-sized bins) to find popular price areas
      - pick top <= n supports and resistances around last price
    """
    if df.empty:
        return [], []

    tail = df.tail(lookback).copy()
    w = 3
    lows  = tail["l"].rolling(w, center=True).min()
    highs = tail["h"].rolling(w, center=True).max()
    swing_lows  = tail[tail["l"] == lows]
    swing_highs = tail[tail["h"] == highs]

    try:
        atr14_val = float(atr(tail, 14).iloc[-1])
    except Exception:
        atr14_val = float((tail["h"] - tail["l"]).mean())
    step = max(atr14_val, float(tail["c"].iloc[-1]) * 0.005)  # ~0.5% fallback

    prices = pd.concat([tail["c"], tail["h"], tail["l"]]).values
    if not np.isfinite(step) or step <= 0:
        step = max(float(tail["c"].iloc[-1]) * 0.005, 0.01)

    bins = np.arange(prices.min(), prices.max() + step, step)
    hist, edges = np.histogram(prices, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2

    df_scores = pd.DataFrame({"price": centers, "score": hist.astype(float)})

    def _boost(swings: pd.DataFrame, weight: float):
        if swings is None or swings.empty:
            return
        pts = pd.concat([swings["h"], swings["l"]]).dropna().values
        idx = np.clip(((pts - centers[0]) / step).round().astype(int), 0, len(centers) - 1)
        for i in idx:
            df_scores.loc[i, "score"] += weight

    _boost(swing_highs, 3.0)
    _boost(swing_lows, 3.0)

    last = float(tail["c"].iloc[-1])
    df_scores["dist"] = np.abs(df_scores["price"] - last)

    supports    = df_scores[df_scores["price"] <= last].nlargest(10, "score").sort_values("price")["price"].tolist()
    resistances = df_scores[df_scores["price"] >= last].nlargest(10, "score").sort_values("price")["price"].tolist()

    def _dedupe(arr):
        out = []
        for p in arr:
            if not out or abs(p - out[-1]) > (step * 0.5):
                out.append(p)
        return out

    supports    = _dedupe(supports)[:n]
    resistances = _dedupe(resistances)[:n]

    supports    = [float(round(p, 2)) for p in supports]
    resistances = [float(round(p, 2)) for p in resistances]
    return supports, resistances

def build_fact_pack(bundle, *, horizon="swing", risk="medium") -> Dict[str, Any]:
    """
    Convert IntelBundle -> compact JSON for the model.
    Works for both stocks and crypto bundles.
    """
    sym = bundle.symbol
    df = bars_to_df(bundle.bars)

    # price snapshot
    last = float(df["c"].iloc[-1]) if not df.empty else (bundle.quote.prevClose if bundle.quote else None)
    prev = bundle.quote.prevClose if bundle.quote else None
    chg = _pct(last, prev)

    # indicators
    s20 = s50 = s200 = e21 = r14 = macd_line = macd_sig = macd_hist = bbw = atr14_val = vwap_last = vol20 = None
    if not df.empty:
        s20 = sma(df, 20).iloc[-1]
        s50 = sma(df, 50).iloc[-1]
        s200 = sma(df, 200).iloc[-1]
        e21  = ema(df, 21).iloc[-1]
        r14  = rsi(df, 14).iloc[-1]
        ml, ms, mh = macd(df)
        macd_line, macd_sig, macd_hist = ml.iloc[-1], ms.iloc[-1], mh.iloc[-1]
        bb = bollinger_bands(df, 20, 2.0)
        bbw = ((bb["upper"].iloc[-1] - bb["lower"].iloc[-1]) / s20) if s20 else None
        atr14_val = atr(df, 14).iloc[-1]
        vwap_last = vwap(df).iloc[-1]
        vol20 = vol_sma(df, 20).iloc[-1]

    # regime flags
    regime = "side"
    if s50 and s200:
        regime = "up" if s50 > s200 else "down" if s50 < s200 else "side"
    px_vs_200 = ("above" if (s200 and last and last > s200)
                 else "below" if (s200 and last and last < s200)
                 else None)
    s20_gt_s50 = (s20 is not None and s50 is not None and s20 > s50)

    # S/R computed here (always present)
    sup, res = _levels(df)
    news_titles = [n.title for n in (bundle.news or [])][:3]

    # events (equity)
    next_earn = None
    div_ex = None
    today = datetime.now(timezone.utc).date()

    if getattr(bundle, "earnings", None):
        fut = []
        for e in bundle.earnings:
            d = _as_utc(e.report_date)
            if d and d.date() >= today:
                fut.append(d.date())
        if fut:
            next_earn = min(fut).isoformat()

    if getattr(bundle, "dividends", None):
        futd = []
        for d in bundle.dividends:
            x = _as_utc(d.ex_dividend_date)
            if x and x.date() >= today:
                futd.append(x.date())
        if futd:
            div_ex = min(futd).isoformat()

    # crypto derivatives (optional)
    funding = bundle.funding.rate if getattr(bundle, "funding", None) else None
    oi_amt = bundle.open_interest.amount if getattr(bundle, "open_interest", None) else None
    oi_notional = (oi_amt * last) if (oi_amt and last) else None

    facts = {
        "symbol": sym,
        "horizon": horizon,
        "risk": risk,
        "price": {"last": _round(last, 2), "prev": _round(prev, 2), "chg": _round(chg, 3)},
        "trend": {
            "dir": regime,
            "rsi": _round(r14, 1),
            "macd": (
                {"line": _round(macd_line, 3), "sig": _round(macd_sig, 3), "hist": _round(macd_hist, 3)}
                if macd_line is not None else None
            ),
            "sma": {"s20": _round(s20, 2), "s50": _round(s50, 2), "s200": _round(s200, 2)},
            "ema": {"e21": _round(e21, 2)},
            "vwap": _round(vwap_last, 2),
            "atr": _round(atr14_val, 2),
            "bbw": _round(bbw, 3),
            "vol20": _round(vol20, 0),
            "s20_gt_s50": bool(s20_gt_s50),
            "px_vs_200": px_vs_200,
        },
        "levels": {"support": sup, "resistance": res},  # <-- always present from our calc
        "derivs": (
            {"funding": _round(funding, 5), "oi": _round(oi_amt, 2), "oi_notional": _round(oi_notional, 0)}
            if (funding is not None or oi_amt is not None) else None
        ),
        "events": {"next_earn": next_earn, "div_ex": div_ex},
        "news": news_titles,
    }

    # prune empties to keep tokens focused
    facts = {k: v for k, v in facts.items() if v not in (None, [], {}, "")}
    if "trend" in facts:
        facts["trend"] = {k: v for k, v in facts["trend"].items() if v not in (None, [], {}, "")}
    if "events" in facts and not any(facts["events"].values()):
        facts.pop("events", None)
    if "derivs" in facts and (facts["derivs"] in (None, {}, [])):
        facts.pop("derivs", None)

    return facts
