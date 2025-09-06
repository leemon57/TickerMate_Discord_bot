from __future__ import annotations
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from charts.adapters import bars_to_df
from indicators.core import sma, ema, rsi, macd, bollinger_bands, atr, vwap, vol_sma

def _round(x, n=3):
    try:
        return None if x is None else float(round(float(x), n))
    except Exception:
        return None

def _pct(a, b):
    try:
        if a is None or b in (None, 0): return None
        return float((a - b) / b)
    except Exception:
        return None

def _levels(df, lookback=60):
    if df.empty: return [], []
    tail = df.tail(lookback)
    support = [_round(tail["l"].min(), 2)]
    resistance = [_round(tail["h"].max(), 2)]
    return support, resistance

def build_fact_pack(bundle, *, horizon="swing", risk="medium") -> Dict[str, Any]:
    """
    Convert IntelBundle -> compact JSON for the model.
    Works for both stocks and crypto bundles.
    """
    sym = bundle.symbol
    df = bars_to_df(bundle.bars)

    last = float(df["c"].iloc[-1]) if not df.empty else (bundle.quote.prevClose if bundle.quote else None)
    prev = bundle.quote.prevClose if bundle.quote else None
    chg = _pct(last, prev)

    # Indicators (richer signal set for accuracy)
    s20 = s50 = s200 = e21 = r14 = macd_line = macd_sig = macd_hist = bbw = atr14 = vwap_last = vol20 = None
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
        atr14 = atr(df, 14).iloc[-1]
        vwap_last = vwap(df).iloc[-1]
        vol20 = vol_sma(df, 20).iloc[-1]

    # Simple regime classification
    regime = "side"
    if s50 and s200:
        regime = "up" if s50 > s200 else "down" if s50 < s200 else "side"
    px_vs_200 = ("above" if (s200 and last and last > s200) else
                 "below" if (s200 and last and last < s200) else None)
    s20_gt_s50 = (s20 is not None and s50 is not None and s20 > s50)

    sup, res = _levels(df)
    news_titles = [n.title for n in (bundle.news or [])][:3]

    # Equity events (optional)
    next_earn = None
    div_ex = None
    if getattr(bundle, "earnings", None):
        future = [e for e in bundle.earnings if e.report_date and e.report_date > datetime.now(timezone.utc)]
        future.sort(key=lambda x: x.report_date)
        if future:
            next_earn = future[0].report_date.date().isoformat()
    if getattr(bundle, "dividends", None):
        future = [d for d in bundle.dividends if d.ex_dividend_date and d.ex_dividend_date > datetime.now(timezone.utc)]
        future.sort(key=lambda x: x.ex_dividend_date)
        if future:
            div_ex = future[0].ex_dividend_date.date().isoformat()

    # Crypto derivatives (optional)
    funding = bundle.funding.rate if getattr(bundle, "funding", None) else None
    oi_amt = bundle.open_interest.amount if getattr(bundle, "open_interest", None) else None
    oi_notional = (oi_amt * last) if (oi_amt and last) else None

    facts = {
        "symbol": sym,
        "horizon": horizon,           # intraday | swing | position
        "risk": risk,                 # low | medium | high
        "price": {"last": _round(last,2), "prev": _round(prev,2), "chg": _round(chg,3)},
        "trend": {
            "dir": regime,
            "rsi": _round(r14,1),
            "macd": {"line": _round(macd_line,3), "sig": _round(macd_sig,3), "hist": _round(macd_hist,3)} if macd_line is not None else None,
            "sma": {"s20": _round(s20,2), "s50": _round(s50,2), "s200": _round(s200,2)},
            "ema": {"e21": _round(e21,2)},
            "vwap": _round(vwap_last,2),
            "atr": _round(atr14,2),
            "bbw": _round(bbw,3),
            "vol20": _round(vol20,0),
            "s20_gt_s50": bool(s20_gt_s50),
            "px_vs_200": px_vs_200,
        },
        "levels": {"support": sup, "resistance": res},
        "derivs": {"funding": _round(funding,5), "oi": _round(oi_amt,2), "oi_notional": _round(oi_notional,0)} if (funding or oi_amt) else None,
        "events": {"next_earn": next_earn, "div_ex": div_ex},
        "news": news_titles,
    }
    # prune empties to reduce tokens
    facts = {k: v for k, v in facts.items() if v not in (None, [], {}, "")}
    # also inside nested:
    if "trend" in facts:
        facts["trend"] = {k: v for k, v in facts["trend"].items() if v not in (None, [], {}, "")}
    return facts
