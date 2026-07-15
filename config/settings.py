"""
AI Berkshire — 全局配置
=======================
市场阶段判定、大师参数、Lollapalooza 权重、仓位档位映射
"""
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Dict, List

# ─── 市场阶段判定阈值 ───
MARKET_PHASE = {
    "sp500_pe_panic": Decimal("15"),      # PE < 15 → 恐慌
    "sp500_pe_normal": Decimal("20"),     # PE 15-20 → 正常
    "hsi_pe_panic": Decimal("9"),         # 恒指 PE < 9 → 恐慌
    "csi300_pe_panic": Decimal("11"),     # 沪深300 PE < 11 → 恐慌
}

# ─── 四大师权重（对抗聚合用） ───
MASTER_WEIGHTS = {
    "DuanYongping": Decimal("0.25"),      # 段永平
    "Buffett":     Decimal("0.25"),       # 巴菲特
    "Munger":      Decimal("0.30"),       # 芒格（权重略高，风控导向）
    "LiLu":        Decimal("0.20"),       # 李录
}

# ─── Lollapalooza 五维评分权重 ───
LOLLAPALOOZA_WEIGHTS = {
    "valuation":   Decimal("0.25"),   # 估值
    "quality":     Decimal("0.25"),   # 质量 ROIC
    "moat":        Decimal("0.25"),   # 护城河
    "catalyst":    Decimal("0.25"),   # 催化剂
    "contrarian":  Decimal("0.00"),   # 逆向扣减（单独处理）
}

# ─── 仓位档位映射 ───
POSITION_TIERS = {
    "超级":  {"min": Decimal("0.80"), "max": Decimal("1.00"), "pct": "30-40%"},
    "强":    {"min": Decimal("0.65"), "max": Decimal("0.79"), "pct": "15-25%"},
    "标准":  {"min": Decimal("0.50"), "max": Decimal("0.64"), "pct": "5-15%"},
    "准":    {"min": Decimal("0.35"), "max": Decimal("0.49"), "pct": "1-5%"},
    "不投":  {"min": Decimal("0.00"), "max": Decimal("0.34"), "pct": "0%"},
}

# ─── DCF 三情景参数 ───
DCF_SCENARIOS = {
    "bull": {"growth": Decimal("0.12"), "terminal": Decimal("0.04"), "years": 10},
    "base": {"growth": Decimal("0.08"), "terminal": Decimal("0.03"), "years": 10},
    "bear": {"growth": Decimal("0.04"), "terminal": Decimal("0.02"), "years": 10},
}

DISCOUNT_RATE = Decimal("0.10")  # WACC / 要求回报率

# ─── 仪表盘配色 ───
COLORS = {
    "bg":          "#0a0e27",
    "card_bg":     "#111633",
    "header_bar":  "#070b1f",
    "accent":      "#3b82f6",
    "green":       "#10b981",
    "red":         "#ef4444",
    "yellow":      "#f59e0b",
    "text":        "#e2e8f0",
    "text_dim":    "#94a3b8",
    "border":      "#1e293b",
    "duan":        "#8b5cf6",   # 紫色 - 段永平
    "buffett":     "#3b82f6",   # 蓝色 - 巴菲特
    "munger":      "#f59e0b",   # 黄色 - 芒格
    "lilu":        "#10b981",   # 绿色 - 李录
}

# ─── 本土风控检查项 ───
CN_RISK_CHECKS = [
    "非经常性损益占比 > 30% 告警",
    "经销商库存周转天数同比 > 20% 告警",
    "地方政府财政依赖度（应收中政府占比）",
    "大股东质押率 > 50% 告警",
    "商誉/净资产 > 30% 告警",
]

# ─── 默认标的列表 ───
DEFAULT_TICKERS = {
    "美股": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "BRK-B", "JPM", "V", "COST", "MA"],
    "A股": ["600519", "000858", "601318", "600036", "000333"],
    "港股": ["0700.HK", "9988.HK", "3690.HK", "2318.HK", "0388.HK"],
}
