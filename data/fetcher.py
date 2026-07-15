"""
AI Berkshire — 数据层 v3
========================
多源实时行情聚合：
- 源1: 东方财富 push2 API（A股/港股/美股全覆盖，中国大陆IP最优）
- 源2: Yahoo Finance v8 chart API（海外IP最优，美股/港股）
- 源3: yfinance .info（备用，获取基本面+价格）
- 兜底: 预置静态数据

自动择优：并发请求，取第一个成功返回的实时数据
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
# HTTP Session
# ═══════════════════════════════════════════════════
_http_session = None

def _get_http():
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        _http_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })
    return _http_session


# ═══════════════════════════════════════════════════
# Ticker 转换：统一格式 → 各数据源的代码格式
# ═══════════════════════════════════════════════════

def _parse_ticker(ticker: str) -> dict:
    """
    解析 ticker，返回各数据源对应的代码
    =====================================
    输入格式：
      - 美股: AAPL
      - A股: 600519.SS / 000858.SZ / 600519 / 000858
      - 港股: 0700.HK / 00700
    
    返回:
      {
        "market": "US" / "CN" / "HK",
        "eastmoney_secid": "1.600519" / "116.00700" / "105.AAPL",
        "yahoo_ticker": "AAPL" / "600519.SS" / "0700.HK",
        "code": "600519" / "AAPL" / "00700",
      }
    """
    t = ticker.strip().upper()
    
    # A股：.SS 后缀或 6 位纯数字以 6 开头
    if ".SS" in t or (t.isdigit() and len(t) == 6 and t.startswith("6")):
        code = t.replace(".SS", "")
        return {
            "market": "CN",
            "eastmoney_secid": f"1.{code}",
            "yahoo_ticker": f"{code}.SS",
            "code": code,
        }
    
    # A股：.SZ 后缀或 6 位纯数字以 0/3 开头
    if ".SZ" in t or (t.isdigit() and len(t) == 6 and t.startswith(("0", "3"))):
        code = t.replace(".SZ", "")
        return {
            "market": "CN",
            "eastmoney_secid": f"0.{code}",
            "yahoo_ticker": f"{code}.SZ",
            "code": code,
        }
    
    # 港股：.HK 后缀或 5 位纯数字
    if ".HK" in t:
        code = t.replace(".HK", "").lstrip("0") or "0"
        # 东方财富港股代码补齐 5 位
        em_code = t.replace(".HK", "").zfill(5)
        return {
            "market": "HK",
            "eastmoney_secid": f"116.{em_code}",
            "yahoo_ticker": f"{code.zfill(4)}.HK",
            "code": em_code,
        }
    if t.isdigit() and len(t) == 5:
        return {
            "market": "HK",
            "eastmoney_secid": f"116.{t}",
            "yahoo_ticker": f"{t}.HK",
            "code": t,
        }
    
    # 默认美股
    return {
        "market": "US",
        "eastmoney_secid": f"105.{t}",
        "yahoo_ticker": t,
        "code": t,
    }


# ═══════════════════════════════════════════════════
# 源1: 东方财富实时行情
# ═══════════════════════════════════════════════════

def _fetch_eastmoney_realtime(secid: str) -> Optional[dict]:
    """
    东方财富 push2 实时行情 API
    ============================
    覆盖 A股/港股/美股，无需 API Key
    中国大陆 IP 最稳定，海外 IP 可能不可达
    
    字段映射:
      f43 → 当前价（需除以 100 或 price_precision）
      f44 → 最高价
      f45 → 最低价
      f46 → 开盘价
      f47 → 成交量
      f48 → 成交额
      f57 → 代码
      f58 → 名称
      f60 → 昨收
      f170 → 涨跌幅（%）
      f171 → 涨跌额
    """
    try:
        http = _get_http()
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f170,f171",
            "fltt": "2",  # 返回浮点数
        }
        # 东方财富需要 Referer
        headers = {
            "Referer": "https://quote.eastmoney.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        
        resp = http.get(url, params=params, headers=headers, timeout=6)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        if not data or data.get("rc") != 0:
            return None
        
        d = data.get("data", {})
        if not d or d.get("f43") is None:
            return None
        
        price = D(str(d["f43"]))
        if price <= 0:
            return None
        
        prev_close = D(str(d.get("f60", price)))
        change_pct = D(str(d.get("f170", 0))) / D("100") if d.get("f170") else D("0")
        
        return {
            "price": price,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "name": d.get("f58", ""),
            "high": D(str(d.get("f44", 0))),
            "low": D(str(d.get("f45", 0))),
            "open": D(str(d.get("f46", 0))),
            "volume": D(str(d.get("f47", 0))),
            "amount": D(str(d.get("f48", 0))),
            "source": "eastmoney",
        }
    except Exception:
        return None


def _fetch_eastmoney_market_cap(secid: str) -> Optional[Decimal]:
    """东方财富获取总市值"""
    try:
        http = _get_http()
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {"secid": secid, "fields": "f116,f117", "fltt": "2"}
        headers = {"Referer": "https://quote.eastmoney.com/"}
        
        resp = http.get(url, params=params, headers=headers, timeout=6)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        if data.get("rc") != 0:
            return None
        
        # f116 = 总市值, f117 = 流通市值
        cap = data.get("data", {}).get("f116")
        if cap:
            return D(str(cap))
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════
# 源2: Yahoo Finance v8 chart API
# ═══════════════════════════════════════════════════

def _fetch_yahoo_realtime(yahoo_ticker: str) -> Optional[dict]:
    """
    Yahoo Finance v8 chart API
    ==========================
    海外 IP 最稳定，美股/港股/部分 A股
    """
    try:
        http = _get_http()
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}"
        params = {"range": "1d", "interval": "1d", "includePrePost": "false"}
        
        resp = http.get(url, params=params, timeout=6)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        
        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        if not price:
            return None
        
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose") or price
        change_pct = ((price - prev_close) / prev_close) if prev_close else 0
        
        return {
            "price": D(str(price)),
            "prev_close": D(str(prev_close)),
            "change_pct": D(str(change_pct)),
            "name": meta.get("longName") or meta.get("shortName") or yahoo_ticker,
            "market_cap": D(str(meta.get("marketCap", 0))),
            "currency": meta.get("currency", "USD"),
            "source": "yahoo",
        }
    except Exception:
        return None


def _fetch_yahoo_3m_change(yahoo_ticker: str, current_price: Decimal) -> Decimal:
    """通过 Yahoo 获取 3 个月涨跌幅"""
    try:
        http = _get_http()
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}"
        params = {"range": "3mo", "interval": "1mo"}
        
        resp = http.get(url, params=params, timeout=6)
        if resp.status_code != 200:
            return D("0")
        
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return D("0")
        
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in quotes.get("close", []) if c is not None]
        if not closes:
            return D("0")
        
        price_3m_ago = D(str(closes[0]))
        if price_3m_ago > 0:
            return (current_price - price_3m_ago) / price_3m_ago
        return D("0")
    except Exception:
        return D("0")


# ═══════════════════════════════════════════════════
# 源3: yfinance .info（备用，同时获取基本面）
# ═══════════════════════════════════════════════════

def _try_yfinance_all(ticker: str) -> Tuple[Optional[dict], Optional[dict]]:
    """
    通过 yfinance 获取价格和基本面
    返回: (realtime_dict, fundamentals_dict)
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        
        if not info or len(info) < 3:
            return None, None
        
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        shares = info.get("sharesOutstanding", 0)
        market_cap = info.get("marketCap", price * shares if price and shares else 0)
        
        realtime = None
        if price:
            prev_close = info.get("previousClose", price)
            realtime = {
                "price": D(str(price)),
                "prev_close": D(str(prev_close)),
                "change_pct": D("0"),
                "name": info.get("longName") or info.get("shortName") or ticker,
                "market_cap": D(str(market_cap)) if market_cap else D("0"),
                "currency": info.get("currency", "USD"),
                "source": "yfinance",
            }
        
        fundamentals = {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName") or ticker,
            "currency": info.get("currency", "USD"),
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
        
        return realtime, fundamentals
    except Exception:
        return None, None


# ═══════════════════════════════════════════════════
# 预置静态数据兜底
# ═══════════════════════════════════════════════════

FALLBACK_FUNDAMENTALS = {
    "AAPL": {
        "price": "215", "market_cap": "3300000000000",
        "name": "Apple Inc.", "currency": "USD", "shares_outstanding": "15400000000",
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
    "601127.SS": {
        "price": "55.89", "market_cap": "96000000000",
        "name": "赛力斯", "currency": "CNY", "shares_outstanding": "1718000000",
        "pe_ttm": "16.33", "pb": "2.36", "roe": "0.2353", "roic": "0.12",
        "revenue": "165100000000", "net_income": "59570000000", "fcf": "16700000000",
        "total_equity": "40700000000", "total_debt": "26800000000",
        "current_assets": "43000000000", "current_liabilities": "40200000000",
        "revenue_growth_3y": "0.1369", "earnings_growth_3y": "0.0018", "dividend_yield": "0",
        "info": {"grossMargins": "0.2914", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "country": "China"},
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


# ═══════════════════════════════════════════════════
# StockData 容器
# ═══════════════════════════════════════════════════

@dataclass
class StockData:
    ticker: str
    name: str = ""
    currency: str = "USD"
    price: Decimal = Decimal("0")
    prev_close: Decimal = Decimal("0")
    price_change_3m: Decimal = Decimal("0")
    market_cap: Decimal = Decimal("0")
    shares_outstanding: Decimal = Decimal("0")
    pe_ttm: Optional[Decimal] = None
    pb: Optional[Decimal] = None
    roe: Optional[Decimal] = None
    fcf_yield: Optional[Decimal] = None
    roic: Optional[Decimal] = None
    ev_ebitda: Optional[Decimal] = None
    revenue: Decimal = Decimal("0")
    net_income: Decimal = Decimal("0")
    fcf: Decimal = Decimal("0")
    total_equity: Decimal = Decimal("0")
    total_debt: Decimal = Decimal("0")
    current_assets: Decimal = Decimal("0")
    current_liabilities: Decimal = Decimal("0")
    revenue_growth_3y: Optional[Decimal] = None
    earnings_growth_3y: Optional[Decimal] = None
    dividend_yield: Optional[Decimal] = None
    payout_ratio: Optional[Decimal] = None
    info: dict = field(default_factory=dict)
    fetch_time: str = ""
    data_source: str = "unknown"
    price_source: str = "unknown"


# ═══════════════════════════════════════════════════
# 缓存
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
        ft = datetime.fromisoformat(data.get("fetch_time", "2000-01-01"))
        if datetime.now() - ft > timedelta(hours=max_age_hours):
            return None
        return data
    except Exception:
        return None

def _save_cache(ticker: str, data: dict):
    try:
        with open(_cache_key(ticker), "w") as f:
            json.dump(data, f, default=str)
    except Exception:
        pass


# ═══════════════════════════════════════════════════
# 主函数：多源聚合获取实时数据
# ═══════════════════════════════════════════════════

def fetch_stock_data(ticker: str, force_refresh: bool = False) -> StockData:
    """
    多源实时数据获取
    =================
    1. 东方财富 API（优先，A股/港股/美股全覆盖）
    2. Yahoo v8 API（备用，海外服务器首选）
    3. yfinance .info（备用，同时获取基本面）
    4. 预置静态数据（兜底）
    
    价格类数据：始终从实时接口获取
    基本面数据：yfinance → 6h缓存 → 24h缓存 → 静态兜底
    """
    parsed = _parse_ticker(ticker)
    
    # ── 步骤1: 尝试东方财富实时行情 ──
    realtime = _fetch_eastmoney_realtime(parsed["eastmoney_secid"])
    rt_source = "eastmoney" if realtime else None
    
    # ── 步骤2: 东方财富失败 → 尝试 Yahoo v8 ──
    if realtime is None:
        realtime = _fetch_yahoo_realtime(parsed["yahoo_ticker"])
        rt_source = "yahoo" if realtime else None
    
    # ── 步骤3: 都失败 → 尝试 yfinance（同时获取基本面） ──
    yf_realtime = None
    yf_fundamentals = None
    if realtime is None:
        yf_realtime, yf_fundamentals = _try_yfinance_all(parsed["yahoo_ticker"])
        if yf_realtime:
            realtime = yf_realtime
            rt_source = "yfinance"
    
    # ── 获取基本面数据 ──
    fund = None
    fund_source = "unknown"
    
    # 如果 yfinance 已经返回了基本面
    if yf_fundamentals:
        fund = yf_fundamentals
        fund_source = "yfinance_live"
        _save_cache(ticker, fund)
    
    # 先查缓存
    if fund is None:
        cached = _load_cache(ticker, max_age_hours=6)
        if cached:
            fund = cached
            fund_source = "cache"
    
    # 再次尝试 yfinance（如果上面没试过）
    if fund is None:
        _, yf_fund = _try_yfinance_all(parsed["yahoo_ticker"])
        if yf_fund:
            fund = yf_fund
            fund_source = "yfinance_live"
            _save_cache(ticker, fund)
    
    # 24h 温缓存
    if fund is None:
        warm = _load_cache(ticker, max_age_hours=24)
        if warm:
            fund = warm
            fund_source = "cache_warm"
    
    # 静态兜底
    if fund is None:
        # 尝试多种 key 格式匹配
        for key in [ticker, ticker.upper(), parsed["yahoo_ticker"], parsed.get("code", "")]:
            if key in FALLBACK_FUNDAMENTALS:
                fund = FALLBACK_FUNDAMENTALS[key]
                fund_source = "fallback"
                break
        if fund is None:
            fund = {}
            fund_source = "fallback"
    
    # ── 组装 StockData ──
    if realtime is not None:
        price = realtime.get("price", D("0"))
        prev_close = realtime.get("prev_close", price)
        name = realtime.get("name") or fund.get("name", ticker)
        currency = realtime.get("currency", fund.get("currency", "USD"))
        market_cap = realtime.get("market_cap", D("0"))
        if market_cap == 0:
            # 尝试东方财富市值
            em_cap = _fetch_eastmoney_market_cap(parsed["eastmoney_secid"])
            if em_cap and em_cap > 0:
                market_cap = em_cap
            elif fund.get("market_cap"):
                market_cap = D(str(fund["market_cap"]))
    else:
        price = D(str(fund.get("price", "0")))
        prev_close = price
        name = fund.get("name", ticker)
        currency = fund.get("currency", "USD")
        market_cap = D(str(fund.get("market_cap", "0")))
        rt_source = "fallback"
    
    # 3 月涨跌幅
    price_change_3m = D("0")
    if realtime and rt_source != "fallback":
        price_change_3m = _fetch_yahoo_3m_change(parsed["yahoo_ticker"], price)
    
    # 股本
    shares = D(str(fund.get("shares_outstanding", "0")))
    if shares == 0 and price > 0 and market_cap > 0:
        shares = market_cap / price
    
    # 估值
    pe = D(str(fund["pe_ttm"])) if fund.get("pe_ttm") else None
    pb = D(str(fund["pb"])) if fund.get("pb") else None
    roe_val = D(str(fund["roe"])) if fund.get("roe") else None
    roic_val = D(str(fund["roic"])) if fund.get("roic") else None
    
    fcf = D(str(fund.get("fcf", "0")))
    fcf_yield_val = calc_fcf_yield(fcf, market_cap) if fcf > 0 and market_cap > 0 else None
    
    revenue = D(str(fund.get("revenue", "0")))
    net_income = D(str(fund.get("net_income", "0")))
    total_equity = D(str(fund.get("total_equity", "0")))
    total_debt = D(str(fund.get("total_debt", "0")))
    current_assets = D(str(fund.get("current_assets", "0")))
    current_liabilities = D(str(fund.get("current_liabilities", "0")))
    
    rev_growth = D(str(fund["revenue_growth_3y"])) if fund.get("revenue_growth_3y") else None
    earn_growth = D(str(fund["earnings_growth_3y"])) if fund.get("earnings_growth_3y") else None
    div_yield = D(str(fund["dividend_yield"])) if fund.get("dividend_yield") else None
    
    source_labels = {
        "eastmoney": "东方财富实时",
        "yahoo": "Yahoo实时",
        "yfinance": "yfinance",
        "fallback": "离线兜底",
    }
    
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
        data_source=f"price:{source_labels.get(rt_source, rt_source)} | 基本面:{source_labels.get(fund_source, fund_source)}",
        price_source=rt_source or "fallback",
    )
    
    return sd


def get_market_phase() -> str:
    """Step 0 · 环境感知"""
    try:
        rt = _fetch_eastmoney_realtime("1.000001")  # 上证指数
        if rt and rt.get("price", 0) > 0:
            return f"正常 → 四大师模式（上证 {rt['price']}）"
    except Exception:
        pass
    
    try:
        rt = _fetch_yahoo_realtime("^GSPC")
        if rt:
            return "正常 → 四大师模式（S&P 500 实时）"
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
