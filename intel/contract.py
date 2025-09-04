from dataclasses import dataclass
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
class IntelBundle:
    symbol: str
    quote: Optional[Quote]
    bars: List[Bar]
    news: List[NewsItem]
    dividends: List[Dividend]           # NEW
    splits: List[Split]                 # NEW
    earnings: List[Earnings]            # NEW
    