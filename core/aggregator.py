"""
AI Berkshire — 对抗聚合器
=========================
四大师结论冲突暴露 + 强制三档结论
"""
from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from utils.finance import D, d_round


@dataclass
class AdversarialReport:
    """对抗式分析报告"""
    ticker: str
    name: str
    market_phase: str
    
    # 四大师结论
    duan: dict = field(default_factory=dict)
    buffett: dict = field(default_factory=dict)
    munger: dict = field(default_factory=dict)
    lilu: dict = field(default_factory=dict)
    
    # 冲突点
    conflicts: list = field(default_factory=list)
    
    # 财务验算
    verification: dict = field(default_factory=dict)
    
    # 强制结论
    conclusion: dict = field(default_factory=dict)
    verdict: str = ""  # ✅ / ⚠️ / ❌


def run_adversarial_analysis(
    data,
    duan_result: dict,
    buffett_result: dict,
    munger_result: dict,
    lilu_result: dict,
    market_phase: str,
) -> AdversarialReport:
    """
    Step 2 · 冲突暴露 + Step 4 · 强制结论
    ======================================
    四大师结论矛盾不许和稀泥，必须暴露真冲突
    强制三档结论：✅ / ⚠️ / ❌
    """
    report = AdversarialReport(
        ticker=data.ticker,
        name=data.name,
        market_phase=market_phase,
        duan=duan_result,
        buffett=buffett_result,
        munger=munger_result,
        lilu=lilu_result,
    )
    
    # ── 冲突暴露 ──
    conflicts = []
    
    # 冲突 1: 段说生意好 vs 芒说会死
    duan_pass = duan_result.get("right_business") == "Y"
    munger_death_count = len(munger_result.get("death_scenarios", []))
    if duan_pass and munger_death_count >= 2:
        conflicts.append({
            "id": "CONFLICT_01",
            "parties": "段永平 ↔ Munger",
            "duan_says": "生意本质优良",
            "munger_says": f"识别 {munger_death_count} 个死亡情景",
            "core_issue": "好生意是否具有持久性？还是阶段性繁荣？",
            "severity": "🟡 待确认",
        })
    
    # 冲突 2: 巴说便宜 vs 李说赛道萎缩
    buffett_moat = buffett_result.get("moat_count", 0) >= 2
    lilu_decline = "衰退" in lilu_result.get("civilization_stage", "")
    if buffett_moat and lilu_decline:
        conflicts.append({
            "id": "CONFLICT_02",
            "parties": "Buffett ↔ Li Lu",
            "buffett_says": f"护城河深（{buffett_result.get('moat_count')}条）",
            "lilu_says": f"赛道处于{lilu_result.get('civilization_stage')}",
            "core_issue": "护城河 vs 赛道萎缩——是 α 还是 β？",
            "severity": "🔴 严重冲突",
        })
    
    # 冲突 3: 段说价格合理 vs 芒格估值分低
    duan_price_ok = duan_result.get("right_price") in ("Y", "⚠️")
    lp_valuation = munger_result.get("lollapalooza", {}).get("valuation", Decimal("0.25"))
    if duan_price_ok and lp_valuation < Decimal("0.10"):
        conflicts.append({
            "id": "CONFLICT_03",
            "parties": "段永平 ↔ Munger",
            "duan_says": "价格尚可接受",
            "munger_says": f"估值维度得分仅 {lp_valuation}",
            "core_issue": "估值分歧——安全边际是否足够？",
            "severity": "🟡 待确认",
        })
    
    # 冲突 4: 巴说 FCF 可预测 vs 李说政策风险高
    buffett_fcf = buffett_result.get("fcf_predictable", False)
    lilu_policy = len(lilu_result.get("policy_risks", [])) >= 2
    if buffett_fcf and lilu_policy:
        conflicts.append({
            "id": "CONFLICT_04",
            "parties": "Buffett ↔ Li Lu",
            "buffett_says": "FCF 可预测",
            "lilu_says": f"政策风险较多（{len(lilu_result.get('policy_risks', []))}项）",
            "core_issue": "政策干预是否破坏 FCF 可预测性？",
            "severity": "🔴 严重冲突",
        })
    
    report.conflicts = conflicts
    
    # ── 财务验算（Step 3） ──
    from utils.finance import verify_market_cap, cross_validate
    from utils.finance import benford_check
    
    verification = {}
    
    # 市值验算
    verification["market_cap_check"] = verify_market_cap(
        data.price, data.shares_outstanding, data.market_cap
    )
    
    # 交叉验证
    metrics = {
        "pe": data.pe_ttm or Decimal("0"),
        "eps": (data.net_income / data.shares_outstanding) if data.shares_outstanding > 0 else Decimal("0"),
        "pb": data.pb or Decimal("0"),
        "bvps": (data.total_equity / data.shares_outstanding) if data.shares_outstanding > 0 else Decimal("0"),
        "price": data.price,
    }
    verification["cross_checks"] = cross_validate(metrics)
    
    report.verification = verification
    
    # ── 强制结论（Step 4） ──
    lp = munger_result.get("lollapalooza", {})
    lp_total = lp.get("total", Decimal("0"))
    lp_tier = lp.get("tier", "不投")
    
    # DCF 目标价
    dcf = buffett_result.get("dcf", {})
    bear_price = dcf.get("bear", {}).get("per_share", data.price)
    base_price = dcf.get("base", {}).get("per_share", data.price)
    bull_price = dcf.get("bull", {}).get("per_share", data.price)
    
    severe_conflicts = [c for c in conflicts if c["severity"].startswith("🔴")]
    yellow_conflicts = [c for c in conflicts if c["severity"].startswith("🟡")]
    
    if lp_total >= Decimal("0.65") and len(severe_conflicts) == 0:
        # ✅ 通过
        report.verdict = "✅ 通过"
        report.conclusion = {
            "verdict": "✅ 通过",
            "price_range": f"¥{d_round(bear_price, 2)} 至 ¥{d_round(bull_price, 2)}",
            "first_position": "10-15%",
            "add_position": "回调至 ¥{:.2f} 加至 25%".format(float(base_price)) if isinstance(base_price, Decimal) else "",
            "lollapalooza_score": float(lp_total),
            "lollapalooza_tier": lp_tier,
            "rationale": f"四大师共识度高，Lollapalooza {lp_total}（{lp_tier}档），护城河坚实，估值合理",
        }
    elif lp_total >= Decimal("0.50") and len(severe_conflicts) <= 1:
        # ⚠️ 灰色地带
        core_issues = [c["core_issue"] for c in yellow_conflicts + severe_conflicts]
        report.verdict = "⚠️ 灰色地带"
        report.conclusion = {
            "verdict": "⚠️ 灰色地带",
            "conflicts": core_issues,
            "pending_items": ["待确认管理层质量", "待确认行业周期位置"],
            "watch_price": f"¥{d_round(data.price * Decimal('0.85'), 2)}",
            "lollapalooza_score": float(lp_total),
            "lollapalooza_tier": lp_tier,
            "rationale": f"存在 {len(severe_conflicts)} 个严重冲突 + {len(yellow_conflicts)} 个待确认点，建议观望",
        }
    else:
        # ❌ 不通过
        rejection_reasons = []
        if lp_total < Decimal("0.35"):
            rejection_reasons.append(f"Lollapalooza 总分 {lp_total} < 0.35")
        for c in severe_conflicts:
            rejection_reasons.append(c["core_issue"])
        if data.fcf <= 0:
            rejection_reasons.append("FCF 为负")
        
        report.verdict = "❌ 不通过"
        report.conclusion = {
            "verdict": "❌ 不通过",
            "reasons": rejection_reasons,
            "even_at": f"¥{d_round(data.price * Decimal('0.5'), 2)}",
            "lollapalooza_score": float(lp_total),
            "lollapalooza_tier": lp_tier,
            "rationale": "四大师中存在严重分歧 + 基本面风险，不纳入投资范围",
        }
    
    return report
