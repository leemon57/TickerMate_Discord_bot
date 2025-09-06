from __future__ import annotations
import io
import matplotlib
matplotlib.use("Agg") # headless-safe
import matplotlib.pyplot as plt




def render_line_close(df, *, width=1000, height=450, title: str = "") -> bytes:
    if df.empty:
        raise ValueError("No data to plot")
    fig = plt.figure(figsize=(width/100, height/100), dpi=100)
    ax = fig.add_subplot(111)
    ax.plot(df.index, df["c"], linewidth=1.5)
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()




def render_candles(df, *, width=1000, height=450, title: str = "") -> bytes:
    if df.empty:
        raise ValueError("No data to plot")
    fig = plt.figure(figsize=(width/100, height/100), dpi=100)
    ax = fig.add_subplot(111)
    # primitive candlesticks: wick via vlines, body via thick line
    for dt, row in df.iterrows():
        o, h, l, c = float(row.o), float(row.h), float(row.l), float(row.c)
        ax.vlines(dt, l, h)
        # up/down color will follow matplotlib defaults; no style forcing
        ax.plot([dt, dt], [o, c], linewidth=6)
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_line_with_overlays(df, overlays: dict[str, "pd.Series"], *, width=1000, height=450, title="") -> bytes:
    import io, matplotlib.pyplot as plt
    fig = plt.figure(figsize=(width/100, height/100), dpi=100)
    ax = fig.add_subplot(111)
    ax.plot(df.index, df["c"], linewidth=1.5, label="Close")
    for name, series in overlays.items():
        if series is None or series.dropna().empty: 
            continue
        ax.plot(series.index, series.values, linewidth=1.0, label=name)
    ax.grid(True, alpha=0.25)
    ax.set_title(title)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

def render_series(series, *, width=1000, height=300, title: str = "") -> bytes:
    import io
    import matplotlib.pyplot as plt
    if series is None or series.dropna().empty:
        raise ValueError("No data to plot")
    fig = plt.figure(figsize=(width/100, height/100), dpi=100)
    ax = fig.add_subplot(111)
    ax.plot(series.index, series.values, linewidth=1.5)
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

# --- NEW: render multiple Series on one axes ---
def render_multi_series(series_map: dict[str, "pd.Series"], *, width=1000, height=300, title: str = "") -> bytes:
    import io
    import matplotlib.pyplot as plt
    if not series_map or all(s is None or s.dropna().empty for s in series_map.values()):
        raise ValueError("No data to plot")
    fig = plt.figure(figsize=(width/100, height/100), dpi=100)
    ax = fig.add_subplot(111)
    for name, s in series_map.items():
        if s is None or s.dropna().empty:
            continue
        ax.plot(s.index, s.values, linewidth=1.2, label=name)
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
