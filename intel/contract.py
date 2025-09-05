from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class Quote:
    symbol: str
    prevClose: float
    high: float
    low: float
    volume: int
    as_of: datetime


@dataclass(frozen=True)
class OptionContract:
    contract_symbol: str     # e.g., AAPL240920C00190000
    underlying: str          # e.g., AAPL
    right: str               # "C" or "P"
    strike: float
    expiration: datetime
    in_the_money: bool

@dataclass(frozen=True)
class OptionQuote:
    last: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    implied_vol: Optional[float]

@dataclass(frozen=True)
class OptionSnapshot:
    contract: OptionContract
    quote: OptionQuote

@dataclass(frozen=True)
class OptionChain:
    underlying: str
    expiration: datetime
    calls: List[OptionSnapshot]
    puts: List[OptionSnapshot]

@dataclass
class Bar:
    t: int   # ms since epoch
    o: float
    h: float
    l: float
    c: float
    v: int

@dataclass
class NewsItem:
    publisher: str
    title: str
    url: str
    published_at: datetime
    sentiment: Optional[str] = None
    importance: Optional[bool] = None
    kind: Optional[str] = None
    currencies: List[str] = field(default_factory=list)
    score: Optional[int] = None

@dataclass
class Dividend:
    cash_amount: float                  # per share
    declaration_date: Optional[datetime]
    ex_dividend_date: Optional[datetime]
    payment_date: Optional[datetime]
    record_date: Optional[datetime]
    frequency: Optional[int]            # 1=annual, 4=quarterly, etc.

@dataclass
class Split:
    ratio: str                          # e.g. "4/1"
    execution_date: Optional[datetime]

@dataclass
class Earnings:
    fiscal_period: Optional[str]        # e.g. "Q2 2025"
    eps: Optional[float]
    consensus_eps: Optional[float]
    report_date: Optional[datetime]
    surprise: Optional[float]           # eps - consensus_eps
    revenue: Optional[float]            # total revenue if provided

@dataclass
class OpenInterest:
    symbol: str           # e.g. "BTCUSDT" on Binance
    amount: float         # notional OI (contracts or base coin; see provider note)
    ts: Optional[datetime]
    currency: Optional[str] = None  # e.g. "USDT" or base coin

@dataclass
class Funding:
    symbol: str
    rate: float                         # e.g. 0.0001 means 0.01%
    next_funding_time: Optional[datetime]

@dataclass
class IntelBundle:
    symbol: str
    quote: Optional[Quote]
    bars: list[Bar]
    news: list[NewsItem]
    dividends: list[Dividend]
    splits: list[Split]
    earnings: list[Earnings]
    open_interest: Optional[OpenInterest] = None
    funding: Optional[Funding] = None
    