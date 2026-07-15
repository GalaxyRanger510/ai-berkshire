"""
AI Berkshire — 数据层
=====================
yfinance 数据拉取 + 财务指标提取 + 多级缓存降级
- L1: 1 小时内热缓存
- L2: 24 小时内温缓存（限流时降级使用）
- L3: 预置静态数据（网络完全不可用时兜底）
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
from datetime import datetime, timedelta

from utils.finance import D, d_round, calc_pe, calc_pb, calc_roe, calc_fcf_yield

# 缓存目录：优先用 /tmp（Streamlit Cloud 有写权限），本地开发回退到项目目录
CACHE_DIR = os.environ.get("STREAMLIT_CACHE_DIR", "/tmp/ai_berkshire_cache")
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
except PermissionError:
    # Streamlit Cloud 只读文件系统，回退到 /tmp
    CACHE_DIR = "/tmp/ai_berkshire_cache"
    os.makedirs(CACHE_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════
# 预置热门标的静态数据（网络完全不可用时兜底）
# 数据时效：2025-2026 区间参考值，非实时
# ═══════════════════════════════════════════════════
FALLBACK_DATA = {
    "AAPL": {
        "ticker": "AAPL", "name": "Apple Inc.", "currency": "USD",
        "price": "215", "market_cap": "3300000000000", "shares_outstanding": "15400000000",
        "pe_ttm": "33", "pb": "53", "roe": "1.60", "roic": "0.38",
        "revenue": "391000000000", "net_income": "100000000000", "fcf": "105000000000",
        "total_equity": "57000000000", "total_debt": "105000000000",
        "current_assets": "140000000000", "current_liabilities": "150000000000",
        "revenue_growth_3y": "0.04", "earnings_growth_3y": "0.06",
        "dividend_yield": "0.0045", "price_change_3m": "0.05",
        "info": {"grossMargins": "0.46", "sector": "Technology", "industry": "Consumer Electronics", "country": "United States"},
    },
    "MSFT": {
        "ticker": "MSFT", "name": "Microsoft Corporation", "currency": "USD",
        "price": "445", "market_cap": "3300000000000", "shares_outstanding": "7430000000",
        "pe_ttm": "37", "pb": "12", "roe": "0.35", "roic": "0.28",
        "revenue": "245000000000", "net_income": "88000000000", "fcf": "72000000000",
        "total_equity": "268000000000", "total_debt": "42000000000",
        "current_assets": "175000000000", "current_liabilities": "120000000000",
        "revenue_growth_3y": "0.16", "earnings_growth_3y": "0.18",
        "dividend_yield": "0.0070", "price_change_3m": "0.08",
        "info": {"grossMargins": "0.70", "sector": "Technology", "industry": "Software", "country": "United States"},
    },
    "GOOGL": {
        "ticker": "GOOGL", "name": "Alphabet Inc.", "currency": "USD",
        "price": "190", "market_cap": "2350000000000", "shares_outstanding": "12400000000",
        "pe_ttm": "26", "pb": "7.5", "roe": "0.29", "roic": "0.25",
        "revenue": "340000000000", "net_income": "89000000000", "fcf": "70000000000",
        "total_equity": "300000000000", "total_debt": "29000000000",
        "current_assets": "170000000000", "current_liabilities": "85000000000",
        "revenue_growth_3y": "0.13", "earnings_growth_3y": "0.20",
        "dividend_yield": "0.0040", "price_change_3m": "0.10",
        "info": {"grossMargins": "0.58", "sector": "Technology", "industry": "Internet", "country": "United States"},
    },
    "AMZN": {
        "ticker": "AMZN", "name": "Amazon.com, Inc.", "currency": "USD",
        "price": "220", "market_cap": "2280000000000", "shares_outstanding": "10400000000",
        "pe_ttm": "38", "pb": "8.5", "roe": "0.24", "roic": "0.14",
        "revenue": "620000000000", "net_income": "59000000000", "fcf": "48000000000",
        "total_equity": "260000000000", "total_debt": "135000000000",
        "current_assets": "170000000000", "current_liabilities": "160000000000",
        "revenue_growth_3y": "0.12", "earnings_growth_3y": "0.35",
        "dividend_yield": "0", "price_change_3m": "0.15",
        "info": {"grossMargins": "0.48", "sector": "Consumer Cyclical", "industry": "Internet Retail", "country": "United States"},
    },
    "META": {
        "ticker": "META", "name": "Meta Platforms, Inc.", "currency": "USD",
        "price": "610", "market_cap": "1550000000000", "shares_outstanding": "2540000000",
        "pe_ttm": "27", "pb": "9.0", "roe": "0.35", "roic": "0.30",
        "revenue": "165000000000", "net_income": "58000000000", "fcf": "52000000000",
        "total_equity": "170000000000", "total_debt": "38000000000",
        "current_assets": "85000000000", "current_liabilities": "35000000000",
        "revenue_growth_3y": "0.22", "earnings_growth_3y": "0.45",
        "dividend_yield": "0.0030", "price_change_3m": "0.20",
        "info": {"grossMargins": "0.81", "sector": "Technology", "industry": "Internet", "country": "United States"},
    },
    "TSLA": {
        "ticker": "TSLA", "name": "Tesla, Inc.", "currency": "USD",
        "price": "350", "market_cap": "1100000000000", "shares_outstanding": "3180000000",
        "pe_ttm": "85", "pb": "16", "roe": "0.22", "roic": "0.18",
        "revenue": "100000000000", "net_income": "13000000000", "fcf": "8000000000",
        "total_equity": "70000000000", "total_debt": "8000000000",
        "current_assets": "55000000000", "current_liabilities": "30000000000",
        "revenue_growth_3y": "0.08", "earnings_growth_3y": "0.05",
        "dividend_yield": "0", "price_change_3m": "0.30",
        "info": {"grossMargins": "0.18", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "country": "United States"},
    },
    "BRK-B": {
        "ticker": "BRK-B", "name": "Berkshire Hathaway Inc.", "currency": "USD",
        "price": "480", "market_cap": "1040000000000", "shares_outstanding": "2160000000",
        "pe_ttm": "14", "pb": "1.6", "roe": "0.12", "roic": "0.09",
        "revenue": "380000000000", "net_income": "75000000000", "fcf": "35000000000",
        "total_equity": "640000000000", "total_debt": "125000000000",
        "current_assets": "350000000000", "current_liabilities": "0",
        "revenue_growth_3y": "0.10", "earnings_growth_3y": "0.15",
        "dividend_yield": "0", "price_change_3m": "0.06",
        "info": {"grossMargins": "0.25", "sector": "Financial", "industry": "Insurance", "country": "United States"},
    },
    "NVDA": {
        "ticker": "NVDA", "name": "NVIDIA Corporation", "currency": "USD",
        "price": "140", "market_cap": "3450000000000", "shares_outstanding": "24600000000",
        "pe_ttm": "45", "pb": "55", "roe": "1.25", "roic": "0.55",
        "revenue": "130000000000", "net_income": "75000000000", "fcf": "60000000000",
        "total_equity": "65000000000", "total_debt": "10000000000",
        "current_assets": "70000000000", "current_liabilities": "20000000000",
        "revenue_growth_3y": "0.80", "earnings_growth_3y": "1.20",
        "dividend_yield": "0.0003", "price_change_3m": "0.25",
        "info": {"grossMargins": "0.75", "sector": "Technology", "industry": "Semiconductors", "country": "United States"},
    },
    "JPM": {
        "ticker": "JPM", "name": "JPMorgan Chase & Co.", "currency": "USD",
        "price": "240", "market_cap": "680000000000", "shares_outstanding": "2830000000",
        "pe_ttm": "12", "pb": "2.0", "roe": "0.17", "roic": "0.05",
        "revenue": "165000000000", "net_income": "56000000000", "fcf": "40000000000",
        "total_equity": "340000000000", "total_debt": "440000000000",
        "current_assets": "0", "current_liabilities": "0",
        "revenue_growth_3y": "0.08", "earnings_growth_3y": "0.12",
        "dividend_yield": "0.022", "price_change_3m": "0.10",
        "info": {"grossMargins": "1.0", "sector": "Financial", "industry": "Banks", "country": "United States"},
    },
    "600519.SS": {
        "ticker": "600519.SS", "name": "贵州茅台", "currency": "CNY",
        "price": "1550", "market_cap": "19500000000000", "shares_outstanding": "12560000000",
        "pe_ttm": "22", "pb": "8.0", "roe": "0.32", "roic": "0.28",
        "revenue": "170000000000", "net_income": "86000000000", "fcf": "65000000000",
        "total_equity": "240000000000", "total_debt": "0",
        "current_assets": "220000000000", "current_liabilities": "45000000000",
        "revenue_growth_3y": "0.15", "earnings_growth_3y": "0.16",
        "dividend_yield": "0.025", "price_change_3m": "-0.05",
        "info": {"grossMargins": "0.92", "sector": "Consumer Defensive", "industry": "Beverages", "country": "China"},
    },
    "000858.SZ": {
        "ticker": "000858.SZ", "name": "五粮液", "currency": "CNY",
        "price": "140", "market_cap": "543000000000", "shares_outstanding": "3880000000",
        "pe_ttm": "17", "pb": "4.5", "roe": "0.25", "roic": "0.22",
        "revenue": "85000000000", "net_income": "32000000000", "fcf": "25000000000",
        "total_equity": "120000000000", "total_debt": "0",
        "current_assets": "110000000000", "current_liabilities": "30000000000",
        "revenue_growth_3y": "0.10", "earnings_growth_3y": "0.12",
        "dividend_yield": "0.028", "price_change_3m": "-0.08",
        "info": {"grossMargins": "0.78", "sector": "Consumer Defensive", "industry": "Beverages", "country": "China"},
    },
    "0700.HK": {
        "ticker": "0700.HK", "name": "腾讯控股", "currency": "HKD",
        "price": "480", "market_cap": "4400000000000", "shares_outstanding": "9200000000",
        "pe_ttm": "22", "pb": "5.0", "roe": "0.22", "roic": "0.15",
        "revenue": "650000000000", "net_income": "200000000000", "fcf": "180000000000",
        "total_equity": "880000000000", "total_debt": "350000000000",
        "current_assets": "600000000000", "current_liabilities": "400000000000",
        "revenue_growth_3y": "0.08", "earnings_growth_3y": "0.25",
        "dividend_yield": "0.008", "price_change_3m": "0.12",
        "info": {"grossMargins": "0.48", "sector": "Technology", "industry": "Internet", "country": "China"},
    },
    "9988.HK": {
        "ticker": "9988.HK", "name": "阿里巴巴", "currency": "HKD",
        "price": "120", "market_cap": "2300000000000", "shares_outstanding": "19200000000",
        "pe_ttm": "14", "pb": "1.8", "roe": "0.13", "roic": "0.10",
        "revenue": "950000000000", "net_income": "160000000000", "fcf": "180000000000",
        "total_equity": "1280000000000", "total_debt": "200000000000",
        "current_assets": "800000000000", "current_liabilities": "450000000000",
        "revenue_growth_3y": "0.05", "earnings_growth_3y": "0.15",
        "dividend_yield": "0.015", "price_change_3m": "0.18",
        "info": {"grossMargins": "0.38", "sector": "Consumer Cyclical", "industry": "Internet Retail", "country": "China"},
    },
    "COST": {
        "ticker": "COST", "name": "Costco Wholesale Corporation", "currency": "USD",
        "price": "980", "market_cap": "435000000000", "shares_outstanding": "444000000",
        "pe_ttm": "58", "pb": "17", "roe": "0.30", "roic": "0.22",
        "revenue": "260000000000", "net_income": "7500000000", "fcf": "7000000000",
        "total_equity": "25000000000", "total_debt": "9000000000",
        "current_assets": "35000000000", "current_liabilities": "36000000000",
        "revenue_growth_3y": "0.08", "earnings_growth_3y": "0.12",
        "dividend_yield": "0.005", "price_change_3m": "0.10",
        "info": {"grossMargins": "0.12", "sector": "Consumer Defensive", "industry": "Discount Stores", "country": "United States"},
    },
    "V": {
        "ticker": "V", "name": "Visa Inc.", "currency": "USD",
        "price": "345", "market_cap": "680000000000", "shares_outstanding": "1970000000",
        "pe_ttm": "33", "pb": "17", "roe": "0.50", "roic": "0.28",
        "revenue": "37000000000", "net_income": "20000000000", "fcf": "20000000000",
        "total_equity": "40000000000", "total_debt": "21000000000",
        "current_assets": "35000000000", "current_liabilities": "25000000000",
        "revenue_growth_3y": "0.11", "earnings_growth_3y": "0.14",
        "dividend_yield": "0.007", "price_change_3m": "0.08",
        "info": {"grossMargins": "0.98", "sector": "Financial", "industry": "Credit Services", "country": "United States"},
    },
}

# 全局 yfinance Session（复用连接，减少限流）
_yf_session = None


def _get_session():
    """获取或创建 yfinance 会话"""
    global _yf_session
    if _yf_session is None:
        import requests
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        _yf_session = session
    return _yf_session


@dataclass
class StockData:
    """标准化股票数据容器"""
    ticker: str
    name: str = ""
    currency: str = "USD"
    
    # 行情
    price: Decimal = Decimal("0")
    price_change_3m: Decimal = Decimal("0")
    market_cap: Decimal = Decimal("0")
    shares_outstanding: Decimal = Decimal("0")
    
    # 估值指标
    pe_ttm: Optional[Decimal] = None
    pb: Optional[Decimal] = None
    roe: Optional[Decimal] = None
    fcf_yield: Optional[Decimal] = None
    roic: Optional[Decimal] = None
    ev_ebitda: Optional[Decimal] = None
    
    # 财务数据
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
    data_source: str = "unknown"  # "live" / "cache" / "fallback"


def _cache_key(ticker: str) -> str:
    return os.path.join(CACHE_DIR, f"{ticker.replace('.', '_')}.json")


def _load_cache(ticker: str, max_age_hours: int = 1) -> Optional[dict]:
    """加载缓存（max_age_hours 小时内有效）"""
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
    """保存缓存"""
    try:
        with open(_cache_key(ticker), "w") as f:
            json.dump(data, f, default=str)
    except Exception:
        pass  # 缓存写入失败不阻塞主流程


def _load_fallback(ticker: str) -> Optional[dict]:
    """加载预置静态数据"""
    return FALLBACK_DATA.get(ticker)


def fetch_stock_data(ticker: str, force_refresh: bool = False) -> StockData:
    """
    从 yfinance 拉取股票数据（多级降级策略）
    ==========================================
    L1: 1 小时内热缓存 → 直接返回
    L2: 调用 yfinance API（带重试 + 指数退避）
    L3: 24 小时内温缓存（API 限流时降级）
    L4: 预置静态数据（网络完全不可用时兜底）
    """
    # ── L1: 热缓存 ──
    if not force_refresh:
        cached = _load_cache(ticker, max_age_hours=1)
        if cached:
            sd = _dict_to_stockdata(cached)
            sd.data_source = "cache_hot"
            return sd
    
    # ── L2: 调用 yfinance API（带重试） ──
    last_error = None
    for attempt in range(3):
        try:
            session = _get_session()
            stock = yf.Ticker(ticker, session=session)
            info = stock.info or {}
            
            # 检查 info 是否为空（限流时 yfinance 返回空 dict）
            if not info or len(info) < 3:
                raise RuntimeError("API 返回空数据，可能被限流")
            
            # ── 解析行情 ──
            price = D(info.get("currentPrice") or info.get("regularMarketPrice") 
                       or info.get("previousClose") or info.get("open", 0))
            
            if price == 0:
                raise RuntimeError("无法获取价格数据")
            
            # 3 月涨跌幅
            price_change_3m = D("0")
            try:
                hist = stock.history(period="3mo")
                if len(hist) > 0:
                    price_3m_ago = D(hist["Close"].iloc[0])
                    if price_3m_ago > 0:
                        price_change_3m = (price - price_3m_ago) / price_3m_ago
            except Exception:
                pass  # 3 月涨幅非关键，降级处理
            
            shares = D(info.get("sharesOutstanding", 0))
            market_cap = D(info.get("marketCap", price * shares if shares > 0 else 0))
            
            # 估值
            pe = D(info["trailingPE"]) if info.get("trailingPE") else None
            pb = D(info["priceToBook"]) if info.get("priceToBook") else None
            roe_val = D(info["returnOnEquity"]) if info.get("returnOnEquity") else None
            roic_val = D(info["returnOnCapital"]) if info.get("returnOnCapital") else None
            
            # FCF
            fcf = D(info.get("freeCashflow", 0))
            fcf_yield_val = calc_fcf_yield(fcf, market_cap) if fcf > 0 and market_cap > 0 else None
            
            # 财务
            revenue = D(info.get("totalRevenue", 0))
            net_income = D(info.get("netIncomeToCommon", 0))
            total_equity = D(info.get("totalStockholderEquity", 
                            info.get("bookValue", 0) * shares if info.get("bookValue") else 0))
            total_debt = D(info.get("totalDebt", 0))
            current_assets = D(info.get("totalCurrentAssets", 0))
            current_liabilities = D(info.get("totalCurrentLiabilities", 0))
            
            # 增长
            rev_growth = D(info["revenueGrowth"]) if info.get("revenueGrowth") else None
            earn_growth = D(info["earningsGrowth"]) if info.get("earningsGrowth") else None
            div_yield = D(info["dividendYield"]) if info.get("dividendYield") else None
            
            currency = info.get("currency", "USD")
            name = info.get("longName") or info.get("shortName") or ticker
            
            result = {
                "ticker": ticker, "name": name, "currency": currency,
                "price": str(price), "price_change_3m": str(price_change_3m),
                "market_cap": str(market_cap), "shares_outstanding": str(shares),
                "pe_ttm": str(pe) if pe else None,
                "pb": str(pb) if pb else None,
                "roe": str(roe_val) if roe_val else None,
                "fcf_yield": str(fcf_yield_val) if fcf_yield_val else None,
                "roic": str(roic_val) if roic_val else None,
                "revenue": str(revenue), "net_income": str(net_income),
                "fcf": str(fcf), "total_equity": str(total_equity),
                "total_debt": str(total_debt),
                "current_assets": str(current_assets),
                "current_liabilities": str(current_liabilities),
                "revenue_growth_3y": str(rev_growth) if rev_growth else None,
                "earnings_growth_3y": str(earn_growth) if earn_growth else None,
                "dividend_yield": str(div_yield) if div_yield else None,
                "info": {k: str(v) for k, v in info.items() if isinstance(v, (str, int, float, bool))},
                "fetch_time": datetime.now().isoformat(),
                "data_source": "live",
            }
            
            _save_cache(ticker, result)
            sd = _dict_to_stockdata(result)
            sd.data_source = "live"
            return sd
            
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            
            # 判断是否为限流错误
            is_rate_limit = any(kw in err_msg for kw in 
                ["rate limit", "too many", "429", "empty", "空数据"])
            
            if attempt < 2:
                wait = (2 ** attempt) + random.uniform(0.5, 2.0)
                if is_rate_limit:
                    wait = (3 ** attempt) * 2 + random.uniform(1, 4)  # 限流时等更久
                time.sleep(wait)
                continue
    
    # ── L3: 温缓存降级（24 小时内） ──
    warm_cache = _load_cache(ticker, max_age_hours=24)
    if warm_cache:
        sd = _dict_to_stockdata(warm_cache)
        sd.data_source = "cache_warm"
        return sd
    
    # ── L4: 预置静态数据兜底 ──
    fallback = _load_fallback(ticker)
    if fallback:
        sd = _dict_to_stockdata(fallback)
        sd.data_source = "fallback"
        sd.fetch_time = datetime.now().isoformat()
        return sd
    
    # ── 彻底失败 ──
    raise RuntimeError(
        f"数据获取失败 [{ticker}]：{last_error}\n\n"
        f"可能原因：\n"
        f"1. yfinance API 被限流（请稍后重试）\n"
        f"2. 股票代码格式不正确（A 股需加 .SS/.SZ，港股需加 .HK）\n"
        f"3. 网络连接问题\n\n"
        f"💡 支持的热门标的（含离线兜底）：{', '.join(sorted(FALLBACK_DATA.keys()))}"
    )


def _dict_to_stockdata(d: dict) -> StockData:
    """字典 → StockData"""
    def safe_d(key, default="0"):
        val = d.get(key)
        return D(str(val)) if val is not None else D(default)
    
    return StockData(
        ticker=d.get("ticker", ""),
        name=d.get("name", ""),
        currency=d.get("currency", "USD"),
        price=safe_d("price"),
        price_change_3m=safe_d("price_change_3m"),
        market_cap=safe_d("market_cap"),
        shares_outstanding=safe_d("shares_outstanding"),
        pe_ttm=D(d["pe_ttm"]) if d.get("pe_ttm") else None,
        pb=D(d["pb"]) if d.get("pb") else None,
        roe=D(d["roe"]) if d.get("roe") else None,
        fcf_yield=D(d["fcf_yield"]) if d.get("fcf_yield") else None,
        roic=D(d["roic"]) if d.get("roic") else None,
        revenue=safe_d("revenue"),
        net_income=safe_d("net_income"),
        fcf=safe_d("fcf"),
        total_equity=safe_d("total_equity"),
        total_debt=safe_d("total_debt"),
        current_assets=safe_d("current_assets"),
        current_liabilities=safe_d("current_liabilities"),
        revenue_growth_3y=D(d["revenue_growth_3y"]) if d.get("revenue_growth_3y") else None,
        earnings_growth_3y=D(d["earnings_growth_3y"]) if d.get("earnings_growth_3y") else None,
        dividend_yield=D(d["dividend_yield"]) if d.get("dividend_yield") else None,
        info={k: v for k, v in d.get("info", {}).items()},
        fetch_time=d.get("fetch_time", ""),
        data_source=d.get("data_source", "unknown"),
    )


def get_market_phase() -> str:
    """
    市场阶段判定
    ============
    Step 0 · 环境感知 — 通过 S&P 500 PE 判断市场状态
    带降级：网络不可用时默认正常模式
    """
    try:
        session = _get_session()
        sp500 = yf.Ticker("^GSPC", session=session)
        info = sp500.info or {}
        sp_pe = D(info.get("trailingPE", 20))
        
        from config.settings import MARKET_PHASE
        
        if sp_pe < MARKET_PHASE["sp500_pe_panic"]:
            return "恐慌/熊市底部 → 四大师 + Graham 烟蒂回退模式"
        elif sp_pe < MARKET_PHASE["sp500_pe_normal"]:
            return "正常 → 四大师模式"
        else:
            return "牛市 → 四大师模式（估值需更严格）"
    except Exception:
        return "正常 → 四大师模式（网络受限，默认判定）"


def fetch_multiple(tickers: list) -> Dict[str, StockData]:
    """批量拉取（每个间隔 0.5s 防限流）"""
    results = {}
    for i, t in enumerate(tickers):
        try:
            results[t] = fetch_stock_data(t)
        except Exception as e:
            print(f"⚠️ {t}: {e}")
        if i < len(tickers) - 1:
            time.sleep(0.5)
    return results
