"""
AI Berkshire — 工具函数
========================
Decimal 安全计算、Benford 定律、财务校验
"""
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import List, Tuple, Optional
import math

# 设置 Decimal 全局精度
getcontext().prec = 28

# ─── Decimal 工具 ───
def D(val) -> Decimal:
    """安全转 Decimal"""
    if isinstance(val, Decimal):
        return val
    if val is None:
        return Decimal("0")
    return Decimal(str(val))

def d_round(val: Decimal, places: int = 2) -> Decimal:
    """四舍五入"""
    return val.quantize(Decimal("0." + "0" * places), rounding=ROUND_HALF_UP)

def d_pct(val: Decimal) -> str:
    """Decimal 转百分比字符串"""
    return f"{float(val * 100):.2f}%"

# ─── 金融指标计算 ───
def calc_pe(price: Decimal, eps: Decimal) -> Optional[Decimal]:
    """市盈率"""
    if eps == 0:
        return None
    return d_round(price / eps, 2)

def calc_pb(price: Decimal, bvps: Decimal) -> Optional[Decimal]:
    """市净率"""
    if bvps == 0:
        return None
    return d_round(price / bvps, 2)

def calc_roe(net_income: Decimal, equity: Decimal) -> Optional[Decimal]:
    """ROE = 净利润 / 净资产"""
    if equity == 0:
        return None
    return d_round(net_income / equity, 4)

def calc_fcf_yield(fcf: Decimal, market_cap: Decimal) -> Optional[Decimal]:
    """FCF 收益率"""
    if market_cap == 0:
        return None
    return d_round(fcf / market_cap, 4)

def calc_roic(nopat: Decimal, invested_capital: Decimal) -> Optional[Decimal]:
    """ROIC = NOPAT / 投入资本"""
    if invested_capital == 0:
        return None
    return d_round(nopat / invested_capital, 4)

# ─── DCF 估值（Decimal 版） ───
def dcf_valuation(
    current_fcf: Decimal,
    growth_rate: Decimal,
    terminal_growth: Decimal,
    discount_rate: Decimal,
    years: int = 10,
    shares_outstanding: Decimal = Decimal("1"),
) -> dict:
    """
    DCF 估值计算
    =============
    [Buffett] 段：两阶段 DCF 模型
    阶段一：高增长期 (years 年)
    阶段二：永续增长期
    
    返回：{intrinsic_value_per_share, total_pv, terminal_pv, growth_pv}
    """
    total_pv = Decimal("0")
    fcf = current_fcf
    
    # 阶段一：预测期
    for i in range(1, years + 1):
        fcf = fcf * (Decimal("1") + growth_rate)
        pv = fcf / ((Decimal("1") + discount_rate) ** i)
        total_pv += pv
    
    # 阶段二：终值
    terminal_fcf = fcf * (Decimal("1") + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    terminal_pv = terminal_value / ((Decimal("1") + discount_rate) ** years)
    
    enterprise_value = total_pv + terminal_pv
    per_share = enterprise_value / shares_outstanding
    
    return {
        "per_share": d_round(per_share, 2),
        "enterprise_value": d_round(enterprise_value, 0),
        "growth_stage_pv": d_round(total_pv, 0),
        "terminal_pv": d_round(terminal_pv, 0),
    }

# ─── Cross Validation ───
def cross_validate(
    metrics: dict,
    tolerance: Decimal = Decimal("0.01"),
) -> List[dict]:
    """
    多指标交叉校验
    ===============
    [Buffett] 段：P/E, P/B, ROE, FCF Yield 四指标联动校验
    若 PE * EPS ≠ 股价 → 数据源误差告警
    """
    alerts = []
    
    # PE * EPS vs Price
    if all(k in metrics for k in ["pe", "eps", "price"]):
        implied = metrics["pe"] * metrics["eps"]
        actual = metrics["price"]
        if implied != 0:
            err = abs(implied - actual) / actual
            if err > tolerance:
                alerts.append({
                    "type": "PE_EPS_MISMATCH",
                    "implied": d_round(implied, 2),
                    "actual": d_round(actual, 2),
                    "error_pct": d_round(err * 100, 2),
                })
    
    # PB * BVPS vs Price
    if all(k in metrics for k in ["pb", "bvps", "price"]):
        implied = metrics["pb"] * metrics["bvps"]
        actual = metrics["price"]
        if implied != 0:
            err = abs(implied - actual) / actual
            if err > tolerance:
                alerts.append({
                    "type": "PB_BVPS_MISMATCH",
                    "implied": d_round(implied, 2),
                    "actual": d_round(actual, 2),
                    "error_pct": d_round(err * 100, 2),
                })
    
    return alerts

# ─── Benford 定律检测 ───
def benford_check(numbers: List[Decimal]) -> dict:
    """
    Benford 定律首位数分布检测
    ============================
    用于检测财务数据是否有异常
    """
    if len(numbers) < 30:
        return {"valid": False, "reason": "样本不足（需 ≥30）"}
    
    benford_dist = {
        1: Decimal("0.301"), 2: Decimal("0.176"), 3: Decimal("0.125"),
        4: Decimal("0.097"), 5: Decimal("0.079"), 6: Decimal("0.067"),
        7: Decimal("0.058"), 8: Decimal("0.051"), 9: Decimal("0.046"),
    }
    
    first_digits = {}
    for n in numbers:
        n_abs = abs(n)
        if n_abs == 0:
            continue
        # 取首位数字
        first = int(str(n_abs).lstrip("0.")[0])
        first_digits[first] = first_digits.get(first, 0) + 1
    
    total = sum(first_digits.values())
    if total == 0:
        return {"valid": False, "reason": "无有效数据"}
    
    # 计算偏差
    deviations = {}
    max_dev = Decimal("0")
    for d in range(1, 10):
        actual = Decimal(str(first_digits.get(d, 0))) / Decimal(str(total))
        expected = benford_dist[d]
        dev = abs(actual - expected)
        deviations[d] = {"actual": d_round(actual, 3), "expected": expected, "deviation": d_round(dev, 3)}
        if dev > max_dev:
            max_dev = dev
    
    # 最大偏差 > 0.15 视为异常
    suspicious = max_dev > Decimal("0.15")
    
    return {
        "valid": True,
        "total_samples": total,
        "max_deviation": d_round(max_dev, 3),
        "suspicious": suspicious,
        "deviations": deviations,
    }

# ─── 市值验算 ───
def verify_market_cap(price: Decimal, shares: Decimal, reported_cap: Decimal) -> dict:
    """市值验算：price × shares 是否等于报告市值"""
    calc_cap = d_round(price * shares, 0)
    err = abs(calc_cap - reported_cap) / reported_cap if reported_cap != 0 else Decimal("0")
    return {
        "calculated": calc_cap,
        "reported": reported_cap,
        "error_pct": d_round(err * 100, 2),
        "valid": err <= Decimal("0.01"),
    }
