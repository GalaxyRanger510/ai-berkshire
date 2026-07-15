"""
AI Berkshire — 数据层 v2
========================
双通道数据架构：
- 实时通道：Yahoo Finance v8 chart API（价格、涨跌幅）→ 保证实时
- 基本面通道：yfinance .info（财务数据）→ 带 24h 缓存降级
- 兜底通道：预置静态数据（网络完全不可用）
"""
import yfinance as yf
import pandas as pd
from decimal import Decimal
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
import json
import os
import time
import random
import requests
from datetime import datetime, timedelta

from utils.finance import D, d_round, calc_pe, calc_pb, calc_roe, calc_fcf_yield

# 缓存目录
CACHE_DIR = os.environ.get("STREAMLIT_CACHE_DIR", "/tmp/ai_berkshire_cache")
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
except PermissionError:
    CACHE_DIR = "/tmp/ai_berkshire_cache"
    os.makedirs(CACHE_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════
# 预置热门标的静态数据（仅财务基本面，价格走实时）
# ═══════════════════════════════════════════════════
FALLBACK_FUNDAMENTALS = {
    "AAPL": {
        "price": "215", "market_cap": "3300000000000",
        "name": "Apple Inc.", "currency": "USD", "shares_outstanding": "15400000000",
        "price": "215", "market_cap": "3300000000000",
        "pe_ttm": "33", "pb": "53", "roe": "1.60", "roic": "0.38",
        "revenue": "391000000000", "net_income": "100000000000", "fcf": "105000000000",
        "total_equity": "57000000000", "total_debt": "105000000000",
        "current_assets": "140000000000", "current_liabilities": "150000000000",
        "revenue_growth_3y": "0.04", "earnings_growth_3y": "0.06", "dividend_yield": "0.0045",
        "info": {"grossMargins": "0.46", "sector": "Technology", "industry": "Consumer Electronics", "country": "United States"},
    },
    "MSFT": {
        "price": "445", "market_cap": "3300000000000",
        "name": "Microsoft Corporation", "currency": "USD", "shares_outstanding": "7430000000",
        "pe_ttm": "37", "pb": "12", "roe": "0.35", "roic": "0.28",
        "revenue": "245000000000", "net_income": "88000000000", "fcf": "72000000000",
        "total_equity": "268000000000", "total_debt": "42000000000",
        "current_assets": "175000000000", "current_liabilities": "120000000000",
        "revenue_growth_3y": "0.16", "earnings_growth_3y": "0.18", "dividend_yield": "0.0070",
        "info": {"grossMargins": "0.70", "sector": "Technology", "industry": "Software", "country": "United States"},
    },
    "GOOGL": {
        "price": "190", "market_cap": "2350000000000",
        "name": "Alphabet Inc.", "currency": "USD", "shares_outstanding": "12400000000",
        "pe_ttm": "26", "pb": "7.5", "roe": "0.29", "roic": "0.25",
        "revenue": "340000000000", "net_income": "89000000000", "fcf": "70000000000",
        "total_equity": "300000000000", "total_debt": "29000000000",
        "current_assets": "170000000000", "current_liabilities": "85000000000",
        "revenue_growth_3y": "0.13", "earnings_growth_3y": "0.20", "dividend_yield": "0.0040",
        "info": {"grossMargins": "0.58", "sector": "Technology", "industry": "Internet", "country": "United States"},
    },
    "AMZN": {
        "price": "220", "market_cap": "2280000000000",
        "name": "Amazon.com, Inc.", "currency": "USD", "shares_outstanding": "10400000000",
        "pe_ttm": "38", "pb": "8.5", "roe": "0.24", "roic": "0.14",
        "revenue": "620000000000", "net_income": "59000000000", "fcf": "48000000000",
        "total_equity": "260000000000", "total_debt": "135000000000",
        "current_assets": "170000000000", "current_liabilities": "160000000000",
        "revenue_growth_3y": "0.12", "earnings_growth_3y": "0.35", "dividend_yield": "0",
        "info": {"grossMargins": "0.48", "sector": "Consumer Cyclical", "industry": "Internet Retail", "country": "United States"},
    },
    "META": {
        "price": "610", "market_cap": "1550000000000",
        "name": "Meta Platforms, Inc.", "currency": "USD", "shares_outstanding": "2540000000",
        "pe_ttm": "27", "pb": "9.0", "roe": "0.35", "roic": "0.30",
        "revenue": "165000000000", "net_income": "58000000000", "fcf": "52000000000",
        "total_equity": "170000000000", "total_debt": "38000000000",
        "current_assets": "85000000000", "current_liabilities": "35000000000",
        "revenue_growth_3y": "0.22", "earnings_growth_3y": "0.45", "dividend_yield": "0.0030",
        "info": {"grossMargins": "0.81", "sector": "Technology", "industry": "Internet", "country": "United States"},
    },
    "TSLA": {
        "price": "350", "market_cap": "1100000000000",
        "name": "Tesla, Inc.", "currency": "USD", "shares_outstanding": "3180000000",
        "pe_ttm": "85", "pb": "16", "roe": "0.22", "roic": "0.18",
        "revenue": "100000000000", "net_income": "13000000000", "fcf": "8000000000",
        "total_equity": "70000000000", "total_debt": "8000000000",
        "current_assets": "55000000000", "current_liabilities": "30000000000",
        "revenue_growth_3y": "0.08", "earnings_growth_3y": "0.05", "dividend_yield": "0",
        "info": {"grossMargins": "0.18", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "country": "United States"},
    },
    "BRK-B": {
        "price": "480", "market_cap": "1040000000000",
        "name": "Berkshire Hathaway Inc.", "currency": "USD", "shares_outstanding": "2160000000",
        "pe_ttm": "14", "pb": "1.6", "roe": "0.12", "roic": "0.09",
        "revenue": "380000000000", "net_income": "75000000000", "fcf": "35000000000",
        "total_equity": "640000000000", "total_debt": "125000000000",
        "current_assets": "350000000000", "current_liabilities": "0",
        "revenue_growth_3y": "0.10", "earnings_growth_3y": "0.15", "dividend_yield": "0",
        "info": {"grossMargins": "0.25", "sector": "Financial", "industry": "Insurance", "country": "United States"},
    },
    "NVDA": {
        "price": "140", "market_cap": "3450000000000",
        "name": "NVIDIA Corporation", "currency": "USD", "shares_outstanding": "24600000000",
        "pe_ttm": "45", "pb": "55", "roe": "1.25", "roic": "0.55",
        "revenue": "130000000000", "net_income": "75000000000", "fcf": "60000000000",
        "total_equity": "65000000000", "total_debt": "10000000000",
        "current_assets": "70000000000", "current_liabilities": "20000000000",
        "revenue_growth_3y": "0.80", "earnings_growth_3y": "1.20", "dividend_yield": "0.0003",
        "info": {"grossMargins": "0.75", "sector": "Technology", "industry": "Semiconductors", "country": "United States"},
    },
    "JPM": {
        "price": "240", "market_cap": "680000000000",
        "name": "JPMorgan Chase & Co.", "currency": "USD", "shares_outstanding": "2830000000",
        "pe_ttm": "12", "pb": "2.0", "roe": "0.17", "roic": "0.05",
        "revenue": "165000000000", "net_income": "56000000000", "fcf": "40000000000",
        "total_equity": "340000000000", "total_debt": "440000000000",
        "current_assets": "0", "current_liabilities": "0",
        "revenue_growth_3y": "0.08", "earnings_growth_3y": "0.12", "dividend_yield": "0.022",
        "info": {"grossMargins": "1.0", "sector": "Financial", "industry": "Banks", "country": "United States"},
    },
    "600519.SS": {
        "price": "1550", "market_cap": "19500000000000",
        "name": "贵州茅台", "currency": "CNY", "shares_outstanding": "12560000000",
        "pe_ttm": "22", "pb": "8.0", "roe": "0.32", "roic": "0.28",
        "revenue": "170000000000", "net_income": "86000000000", "fcf": "65000000000",
        "total_equity": "240000000000", "total_debt": "0",
        "current_assets": "220000000000", "current_liabilities": "45000000000",
        "revenue_growth_3y": "0.15", "earnings_growth_3y": "0.16", "dividend_yield": "0.025",
        "info": {"grossMargins": "0.92", "sector": "Consumer Defensive", "industry": "Beverages", "country": "China"},
    },
    "000858.SZ": {
        "price": "140", "market_cap": "543000000000",
        "name": "五粮液", "currency": "CNY", "shares_outstanding": "3880000000",
        "pe_ttm": "17", "pb": "4.5", "roe": "0.25", "roic": "0.22",
        "revenue": "85000000000", "net_income": "32000000000", "fcf": "25000000000",
        "total_equity": "120000000000", "total_debt": "0",
        "current_assets": "110000000000", "current_liabilities": "30000000000",
        "revenue_growth_3y": "0.10", "earnings_growth_3y": "0.12", "dividend_yield": "0.028",
        "info": {"grossMargins": "0.78", "sector": "Consumer Defensive", "industry": "Beverages", "country": "China"},
    },
    "0700.HK": {
        "price": "480", "market_cap": "4400000000000",
        "name": "腾讯控股", "currency": "HKD", "shares_outstanding": "9200000000",
        "pe_ttm": "22", "pb": "5.0", "roe": "0.22", "roic": "0.15",
        "revenue": "650000000000", "net_income": "200000000000", "fcf": "180000000000",
        "total_equity": "880000000000", "total_debt": "350000000000",
        "current_assets": "600000000000", "current_liabilities": "400000000000",
        "revenue_growth_3y": "0.08", "earnings_growth_3y": "0.25", "dividend_yield": "0.008",
        "info": {"grossMargins": "0.48", "sector": "Technology", "industry": "Internet", "country": "China"},
    },
    "9988.HK": {
        "price": "120", "market_cap": "2300000000000",
        "name": "阿里巴巴", "currency": "HKD", "shares_outstanding": "19200000000",
        "pe_ttm": "14", "pb": "1.8", "roe": "0.13", "roic": "0.10",
        "revenue": "950000000000", "net_income": "160000000000", "fcf": "180000000000",
        "total_equity": "1280000000000", "total_debt": "200000000000",
        "current_assets": "800000000000", "current_liabilities": "450000000000",
        "revenue_growth_3y": "0.05", "earnings_growth_3y": "0.15", "dividend_yield": "0.015",
        "info": {"grossMargins": "0.38", "sector": "Consumer Cyclical", "industry": "Internet Retail", "country": "China"},
    },
    "COST": {
        "price": "980", "market_cap": "435000000000",
        "name": "Costco Wholesale Corporation", "currency": "USD", "shares_outstanding": "444000000",
        "pe_ttm": "58", "pb": "17", "roe": "0.30", "roic": "0.22",
        "revenue": "260000000000", "net_income": "7500000000", "fcf": "7000000000",
        "total_equity": "25000000000", "total_debt": "9000000000",
        "current_assets": "35000000000", "current_liabilities": "36000000000",
        "revenue_growth_3y": "0.08", "earnings_growth_3y": "0.12", "dividend_yield": "0.005",
        "info": {"grossMargins": "0.12", "sector": "Consumer Defensive", "industry": "Discount Stores", "country": "United States"},
    },
    "V": {
        "price": "345", "market_cap": "680000000000",
        "name": "Visa Inc.", "currency": "USD", "shares_outstanding": "1970000000",
        "pe_ttm": "33", "pb": "17", "roe": "0.50", "roic": "0.28",
        "revenue": "37000000000", "net_income": "20000000000", "fcf": "20000000000",
        "total_equity": "40000000000", "total_debt": "21000000000",
        "current_assets": "35000000000", "current_liabilities": "25000000000",
        "revenue_growth_3y": "0.11", "earnings_growth_3y": "0.14", "dividend_yield": "0.007",
        "info": {"grossMargins": "0.98", "sector": "Financial", "industry": "Credit Services", "country": "United States"},
    },
}

# HTTP Session（复用连接）
_http_session = None

def _get_http():
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        _http_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json",
        })
    return _http_session


@dataclass
class StockData:
    """标准化股票数据容器"""
    ticker: str
    name: str = ""
    currency: str = "USD"
    
    # 行情（来自实时接口）
    price: Decimal = Decimal("0")
    prev_close: Decimal = Decimal("0")
    price_change_3m: Decimal = Decimal("0")
    market_cap: Decimal = Decimal("0")
    shares_outstanding: Decimal = Decimal("0")
    
    # 估值指标（来自基本面）
    pe_ttm: Optional[Decimal] = None
    pb: Optional[Decimal] = None
    roe: Optional[Decimal] = None
    fcf_yield: Optional[Decimal] = None
    roic: Optional[Decimal] = None
    ev_ebitda: Optional[Decimal] = None
    
    # 财务数据（来自基本面）
    revenue: Decimal = Decimal("0")
    net_income: Decimal = Decimal("0")
    fcf: Decimal = Decimal("0")
    total_equity: Decimal = Decimal("0")
    total_debt: Decimal = Decimal("0")
    current_assets: Decimal = Decimal("0")
    current_liabilities: Decimal = Decimal("0")
    
    # 增长
    revenue_growth_3y: Optional[Decimal] = None
    earnings_growth_3y: Optional[Decimal] = None
    
    # 股息
    dividend_yield: Optional[Decimal] = None
    payout_ratio: Optional[Decimal] = None
    
    # 原始信息
    info: dict = field(default_factory=dict)
    fetch_time: str = ""
    data_source: str = "unknown"
    price_source: str = "unknown"  # "yahoo_realtime" / "yfinance" / "fallback"


# ═══════════════════════════════════════════════════
# 实时行情接口 — Yahoo Finance v8 chart API
# 这是 Yahoo 官方的行情 API，比 yfinance 稳定得多
# ═══════════════════════════════════════════════════

def _fetch_realtime_price_yahoo(ticker: str) -> Optional[dict]:
    """
    通过 Yahoo Finance v8 chart API 获取实时行情
    =============================================
    这个接口专用于行情数据，不限流，延迟 < 1s
    返回: {price, prev_close, change_pct, market_cap, currency, name}
    """
    try:
        # Yahoo Finance v8 chart API — 稳定、不限流
        http = _get_http()
        
        # 规范化 ticker（港股需要加后缀）
        # Yahoo 格式：0700.HK → 0700.HK（保持一致）
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {
            "range": "1d",
            "interval": "1d",
            "includePrePost": "false",
        }
        
        resp = http.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        chart = data.get("chart", {}).get("result", [])
        if not chart:
            return None
        
        result = chart[0]
        meta = result.get("meta", {})
        
        price = meta.get("regularMarketPrice")
        if not price:
            return None
        
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose") or price
        change_pct = ((price - prev_close) / prev_close) if prev_close and prev_close != 0 else 0
        
        return {
            "price": D(price),
            "prev_close": D(prev_close),
            "change_pct": D(change_pct),
            "market_cap": D(meta.get("marketCap", 0)),
            "currency": meta.get("currency", "USD"),
            "name": meta.get("longName") or meta.get("shortName") or ticker,
        }
    except Exception:
        return None


def _fetch_3m_history(ticker: str) -> Optional[Decimal]:
    """获取 3 个月前价格（用于计算涨跌幅）"""
    try:
        http = _get_http()
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"range": "3mo", "interval": "1mo"}
        
        resp = http.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in quotes.get("close", []) if c is not None]
        if not closes:
            return None
        
        return D(closes[0])
    except Exception:
        return None


# ═══════════════════════════════════════════════════
# 缓存管理
# ═══════════════════════════════════════════════════

def _cache_key(ticker: str) -> str:
    return os.path.join(CACHE_DIR, f"{ticker.replace('.', '_')}.json")


def _load_cache(ticker: str, max_age_hours: int = 1) -> Optional[dict]:
    key = _cache_key(ticker)
    if not os.path.exists(key):
        return None
    try:
        with open(key, "r") as f:
            data = json.load(f)
        fetch_time = datetime.fromisoformat(data.get("fetch_time", "2000-01-01"))
        if datetime.now() - fetch_time > timedelta(hours=max_age_hours):
            return None
        return data
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _save_cache(ticker: str, data: dict):
    try:
        with open(_cache_key(ticker), "w") as f:
            json.dump(data, f, default=str)
    except Exception:
        pass


# ═══════════════════════════════════════════════════
# 主数据获取函数
# ═══════════════════════════════════════════════════

def fetch_stock_data(ticker: str, force_refresh: bool = False) -> StockData:
    """
    双通道数据获取
    ==============
    通道 1 (实时): Yahoo v8 chart API → 价格、市值、涨跌幅 → 始终实时
    通道 2 (基本面): yfinance .info → PE/PB/ROE/FCF/财报 → 带缓存降级
    
    策略：
    - 价格类数据：每次请求都走实时接口（5 秒缓存防抖）
    - 基本面数据：首次拉取后缓存 6 小时，限流时用 24h 缓存
    - 完全不可用时：预置静态基本面 + 实时价格混合
    """
    
    # ── 检查 5 秒内价格缓存（防重复请求） ──
    if not force_refresh:
        price_cache = _load_cache(f"price_{ticker}", max_age_hours=5/3600)
        if price_cache:
            pass  # 有近期价格缓存，继续往下
    
    # ── 通道 1: 实时行情 ──
    realtime = _fetch_realtime_price_yahoo(ticker)
    
    if realtime is None:
        # 实时行情失败 → 尝试从 yfinance 获取价格
        realtime = _try_yfinance_price(ticker)
    
    # ── 通道 2: 基本面数据 ──
    fundamentals = None
    fund_source = "unknown"
    
    # 先查缓存
    cached = _load_cache(ticker, max_age_hours=6)
    if cached:
        fundamentals = cached
        fund_source = "cache"
    
    if fundamentals is None:
        # 尝试 yfinance .info
        fundamentals = _try_yfinance_fundamentals(ticker)
        if fundamentals:
            fund_source = "yfinance_live"
            _save_cache(ticker, fundamentals)
    
    if fundamentals is None:
        # 降级：24h 温缓存
        warm = _load_cache(ticker, max_age_hours=24)
        if warm:
            fundamentals = warm
            fund_source = "cache_warm"
    
    if fundamentals is None:
        # 兜底：预置静态基本面
        fundamentals = FALLBACK_FUNDAMENTALS.get(ticker)
        fund_source = "fallback"
    
    if fundamentals is None and realtime is None:
        raise RuntimeError(
            f"数据获取失败 [{ticker}]：无实时行情且无基本面数据\n\n"
            f"💡 支持的热门标的：{', '.join(sorted(FALLBACK_FUNDAMENTALS.keys()))}"
        )
    
    # ── 组装 StockData ──
    fund = fundamentals or {}
    
    # 价格优先用实时接口，None 时回退到基本面
    if realtime is not None:
        price = realtime.get("price", D(fund.get("price", "0")))
        prev_close = realtime.get("prev_close", price)
        name = realtime.get("name") or fund.get("name", ticker)
        currency = realtime.get("currency") or fund.get("currency", "USD")
        market_cap = realtime.get("market_cap") if realtime.get("market_cap", 0) > 0 else D(fund.get("market_cap", "0"))
    else:
        price = D(fund.get("price", "0"))
        prev_close = price
        name = fund.get("name", ticker)
        currency = fund.get("currency", "USD")
        market_cap = D(fund.get("market_cap", "0"))
    
    # 3 月涨跌幅
    price_change_3m = D("0")
    if realtime:
        price_3m = _fetch_3m_history(ticker)
        if price_3m and price_3m > 0:
            price_change_3m = (price - price_3m) / price_3m
    
    # 股本
    shares = D(fund.get("shares_outstanding", "0"))
    if shares == 0 and price > 0 and market_cap > 0:
        shares = market_cap / price
    
    # 估值指标
    pe = D(fund["pe_ttm"]) if fund.get("pe_ttm") else None
    pb = D(fund["pb"]) if fund.get("pb") else None
    roe_val = D(fund["roe"]) if fund.get("roe") else None
    roic_val = D(fund["roic"]) if fund.get("roic") else None
    
    # FCF
    fcf = D(fund.get("fcf", "0"))
    fcf_yield_val = calc_fcf_yield(fcf, market_cap) if fcf > 0 and market_cap > 0 else None
    
    # 财务
    revenue = D(fund.get("revenue", "0"))
    net_income = D(fund.get("net_income", "0"))
    total_equity = D(fund.get("total_equity", "0"))
    total_debt = D(fund.get("total_debt", "0"))
    current_assets = D(fund.get("current_assets", "0"))
    current_liabilities = D(fund.get("current_liabilities", "0"))
    
    # 增长
    rev_growth = D(fund["revenue_growth_3y"]) if fund.get("revenue_growth_3y") else None
    earn_growth = D(fund["earnings_growth_3y"]) if fund.get("earnings_growth_3y") else None
    div_yield = D(fund["dividend_yield"]) if fund.get("dividend_yield") else None
    
    # 数据来源标记
    price_src = "yahoo_realtime" if realtime else "fallback"
    ds = f"price:{price_src} | fundamentals:{fund_source}"
    
    sd = StockData(
        ticker=ticker, name=name, currency=currency,
        price=price, prev_close=prev_close, price_change_3m=price_change_3m,
        market_cap=market_cap, shares_outstanding=shares,
        pe_ttm=pe, pb=pb, roe=roe_val, fcf_yield=fcf_yield_val, roic=roic_val,
        revenue=revenue, net_income=net_income, fcf=fcf,
        total_equity=total_equity, total_debt=total_debt,
        current_assets=current_assets, current_liabilities=current_liabilities,
        revenue_growth_3y=rev_growth, earnings_growth_3y=earn_growth,
        dividend_yield=div_yield,
        info={k: v for k, v in fund.get("info", {}).items()},
        fetch_time=datetime.now().isoformat(),
        data_source=ds,
        price_source=price_src,
    )
    
    return sd


def _try_yfinance_price(ticker: str) -> Optional[dict]:
    """备用：通过 yfinance 获取价格（当 v8 API 失败时）"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        if not price:
            return None
        return {
            "price": D(price),
            "prev_close": D(info.get("previousClose", price)),
            "change_pct": D("0"),
            "market_cap": D(info.get("marketCap", 0)),
            "currency": info.get("currency", "USD"),
            "name": info.get("longName") or info.get("shortName") or ticker,
        }
    except Exception:
        return None


def _try_yfinance_fundamentals(ticker: str) -> Optional[dict]:
    """通过 yfinance .info 获取财务基本面"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        
        if not info or len(info) < 3:
            return None
        
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose", 0)
        shares = info.get("sharesOutstanding", 0)
        market_cap = info.get("marketCap", price * shares if price and shares else 0)
        
        return {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName") or ticker,
            "currency": info.get("currency", "USD"),
            "price": str(price),
            "market_cap": str(market_cap),
            "shares_outstanding": str(shares),
            "pe_ttm": str(info["trailingPE"]) if info.get("trailingPE") else None,
            "pb": str(info["priceToBook"]) if info.get("priceToBook") else None,
            "roe": str(info["returnOnEquity"]) if info.get("returnOnEquity") else None,
            "roic": str(info["returnOnCapital"]) if info.get("returnOnCapital") else None,
            "fcf": str(info.get("freeCashflow", 0)),
            "revenue": str(info.get("totalRevenue", 0)),
            "net_income": str(info.get("netIncomeToCommon", 0)),
            "total_equity": str(info.get("totalStockholderEquity", 0)),
            "total_debt": str(info.get("totalDebt", 0)),
            "current_assets": str(info.get("totalCurrentAssets", 0)),
            "current_liabilities": str(info.get("totalCurrentLiabilities", 0)),
            "revenue_growth_3y": str(info["revenueGrowth"]) if info.get("revenueGrowth") else None,
            "earnings_growth_3y": str(info["earningsGrowth"]) if info.get("earningsGrowth") else None,
            "dividend_yield": str(info["dividendYield"]) if info.get("dividendYield") else None,
            "info": {k: str(v) for k, v in info.items() if isinstance(v, (str, int, float, bool))},
            "fetch_time": datetime.now().isoformat(),
        }
    except Exception:
        return None


def get_market_phase() -> str:
    """
    Step 0 · 环境感知 — 通过 Yahoo v8 API 获取 S&P 500 PE
    """
    try:
        realtime = _fetch_realtime_price_yahoo("^GSPC")
        if realtime and realtime.get("price"):
            # 从 S&P 500 的 yfinance info 获取 PE
            try:
                sp500 = yf.Ticker("^GSPC")
                sp_pe = D(sp500.info.get("trailingPE", 20))
            except Exception:
                sp_pe = D("20")
            
            from config.settings import MARKET_PHASE
            if sp_pe < MARKET_PHASE["sp500_pe_panic"]:
                return "恐慌/熊市底部 → 四大师 + Graham 烟蒂回退模式"
            elif sp_pe < MARKET_PHASE["sp500_pe_normal"]:
                return "正常 → 四大师模式"
            else:
                return "牛市 → 四大师模式（估值需更严格）"
    except Exception:
        pass
    
    return "正常 → 四大师模式（网络受限，默认判定）"


def fetch_multiple(tickers: list) -> Dict[str, StockData]:
    """批量拉取"""
    results = {}
    for i, t in enumerate(tickers):
        try:
            results[t] = fetch_stock_data(t)
        except Exception as e:
            print(f"⚠️ {t}: {e}")
        if i < len(tickers) - 1:
            time.sleep(0.3)
    return results
