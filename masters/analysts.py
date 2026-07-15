"""
四大师分析模块
===============
段永平 · Buffett · Munger · Li Lu
每位大师一个独立函数，返回结构化分析结果
"""

# ─── 段永平 · 生意本质 ───
def analyze_duan(data) -> dict:
    """
    段永平视角：Right Business / Right People / Right Price
    =======================================================
    核心问题：这家公司的"生意本质"过关吗？
    本分测试：商业模式是否简单、可理解、长期不变？
    """
    from decimal import Decimal
    from utils.finance import D, d_round

    result = {
        "master": "段永平",
        "right_business": "Y",
        "right_people": "Y",
        "right_price": "Y",
        "business_essence": "",
        "benfen_test": True,
        "warnings": [],
    }

    # ── Right Business ──
    # 判断标准：ROE 持续 > 15%，毛利率 > 30%，商业模式简单
    roe = data.roe or Decimal("0")
    gross_margin = Decimal("0")
    if data.info:
        gm = data.info.get("grossMargins", 0)
        gross_margin = D(gm) if gm else Decimal("0")

    if roe < Decimal("0.10"):
        result["right_business"] = "N"
        result["warnings"].append(f"ROE {d_round(roe*100,1)}% 偏低，生意本质可能不够好")

    # ── Right People ──
    # 管理层评估（简化：看管理层持股、ROIC 持续性）
    if data.roic and data.roic < Decimal("0.08"):
        result["right_people"] = "N"
        result["warnings"].append(f"ROIC {d_round(data.roic*100,1)}% 偏低，资本配置能力存疑")

    # ── Right Price ──
    # 价格合理：PE 不过分高
    if data.pe_ttm and data.pe_ttm > Decimal("40"):
        result["right_price"] = "N"
        result["warnings"].append(f"PE {data.pe_ttm} 偏高，安全边际不足")
    elif data.pe_ttm and data.pe_ttm > Decimal("25"):
        result["right_price"] = "⚠️"
        result["warnings"].append(f"PE {data.pe_ttm} 中等偏高，需等待更好价格")

    # ── 本分测试 ──
    # 业务是否简单可理解？
    if data.revenue_growth_3y and data.revenue_growth_3y < Decimal("-0.10"):
        result["benfen_test"] = False
        result["warnings"].append("营收 3 年负增长，生意可能面临结构性挑战")

    # 结论
    passes = sum(1 for k in ["right_business", "right_people", "right_price"]
                 if result[k] == "Y")
    if passes == 3:
        result["business_essence"] = "✅ 生意本质优良，三项全过"
    elif passes >= 2:
        result["business_essence"] = "⚠️ 生意本质尚可，但有改进空间"
    else:
        result["business_essence"] = "❌ 生意本质存疑，建议规避"

    return result


# ─── Buffett · 护城河 + DCF ───
def analyze_buffett(data) -> dict:
    """
    Buffett 视角：护城河 + DCF 估值
    ===============================
    核心问题：未来 10 年 FCF 可预测吗？护城河有多深？
    """
    from decimal import Decimal
    from utils.finance import D, d_round, dcf_valuation, cross_validate
    from config.settings import DCF_SCENARIOS, DISCOUNT_RATE

    result = {
        "master": "Buffett",
        "moat_count": 0,
        "moats": [],
        "fcf_predictable": True,
        "dcf": {},
        "cross_validation": [],
        "warnings": [],
    }

    # ── 护城河识别 ──
    # 品牌溢价（毛利率 > 40%）
    gross_margin = Decimal("0")
    if data.info:
        gm = data.info.get("grossMargins", 0)
        gross_margin = D(gm) if gm else Decimal("0")
    
    if gross_margin > Decimal("0.40"):
        result["moats"].append("品牌溢价护城河（毛利率 > 40%）")
        result["moat_count"] += 1

    # 规模效应（营收 > 100 亿 USD）
    if data.revenue > D("10000000000"):
        result["moats"].append("规模效应护城河（年营收 > $10B）")
        result["moat_count"] += 1

    # 转换成本（ROE 持续 > 20%）
    if data.roe and data.roe > Decimal("0.20"):
        result["moats"].append("高 ROE 暗示客户粘性/转换成本")
        result["moat_count"] += 1

    # 网络效应（毛利率 > 50% + 营收增长 > 15%）
    if gross_margin > Decimal("0.50") and data.revenue_growth_3y and data.revenue_growth_3y > Decimal("0.15"):
        result["moats"].append("潜在网络效应（高毛利 + 高增长）")
        result["moat_count"] += 1

    # ── FCF 可预测性 ──
    if data.fcf <= 0:
        result["fcf_predictable"] = False
        result["warnings"].append("FCF 为负，无法预测未来现金流")

    # ── DCF 三情景估值 ──
    if data.fcf > 0 and data.shares_outstanding > 0:
        for scenario, params in DCF_SCENARIOS.items():
            try:
                dcf_result = dcf_valuation(
                    current_fcf=data.fcf,
                    growth_rate=params["growth"],
                    terminal_growth=params["terminal"],
                    discount_rate=DISCOUNT_RATE,
                    years=params["years"],
                    shares_outstanding=data.shares_outstanding,
                )
                result["dcf"][scenario] = dcf_result
            except Exception as e:
                result["dcf"][scenario] = {"error": str(e)}
    else:
        result["warnings"].append("无法进行 DCF 估值（FCF 为负或股本数据缺失）")

    # ── 交叉验证 ──
    metrics = {
        "pe": data.pe_ttm or Decimal("0"),
        "eps": (data.net_income / data.shares_outstanding) if data.shares_outstanding > 0 else Decimal("0"),
        "pb": data.pb or Decimal("0"),
        "bvps": (data.total_equity / data.shares_outstanding) if data.shares_outstanding > 0 else Decimal("0"),
        "price": data.price,
    }
    result["cross_validation"] = cross_validate(metrics)

    return result


# ─── Munger · 逆向思维 + Lollapalooza ───
def analyze_munger(data, duan_result: dict, buffett_result: dict) -> dict:
    """
    Munger 视角：逆向挑战 + Lollapalooza 五维评分
    ==============================================
    核心问题："这家公司 10 年后最可能怎么死？"
    多元思维模型：数学/物理/生物/心理/经济
    """
    from decimal import Decimal
    from utils.finance import D, d_round

    result = {
        "master": "Munger",
        "death_scenarios": [],
        "blind_spots": [],              # 挑段+巴的盲区
        "lollapalooza": {
            "valuation": Decimal("0"),    # 估值 0-0.25
            "quality": Decimal("0"),      # 质量 ROIC 0-0.25
            "moat": Decimal("0"),         # 护城河 0-0.25
            "catalyst": Decimal("0"),     # 催化剂 0-0.25
            "contrarian": Decimal("0"),   # 逆向扣减（负分）
            "total": Decimal("0"),
            "tier": "不投",
        },
        "warnings": [],
    }

    # ── 死亡情景分析 ──
    death_scenarios = []

    # 1. 技术颠覆风险（物理/生物类比：生态位被入侵）
    if data.revenue_growth_3y and data.revenue_growth_3y < Decimal("-0.05"):
        death_scenarios.append({
            "scenario": "技术颠覆 / 生态位被入侵",
            "lens": "生物·生态位",
            "detail": "营收持续下滑，可能被新技术/新商业模式取代",
        })

    # 2. 债务危机（数学：杠杆效应）
    if data.total_equity > 0:
        debt_ratio = data.total_debt / data.total_equity
        if debt_ratio > Decimal("2"):
            death_scenarios.append({
                "scenario": "高杠杆爆雷",
                "lens": "数学·复利反向",
                "detail": f"负债/权益 = {d_round(debt_ratio,1)}，利率上升即危机",
            })

    # 3. 管理层失误（心理：过度自信）
    if data.roic and data.roic < Decimal("0.05"):
        death_scenarios.append({
            "scenario": "资本配置失误累积",
            "lens": "心理·过度自信",
            "detail": f"ROIC {d_round(data.roic*100,1)}% 远低于资本成本，价值毁灭",
        })

    # 4. 估值回归（经济：机会成本）
    if data.pe_ttm and data.pe_ttm > Decimal("50"):
        death_scenarios.append({
            "scenario": "估值泡沫破裂",
            "lens": "经济·均值回归",
            "detail": f"PE {data.pe_ttm}，回归合理区间意味着大幅下跌",
        })

    # 5. 现金流断裂
    if data.current_assets > 0 and data.current_liabilities > 0:
        current_ratio = data.current_assets / data.current_liabilities
        if current_ratio < Decimal("1"):
            death_scenarios.append({
                "scenario": "流动性危机",
                "lens": "数学·偿付能力",
                "detail": f"流动比率 {d_round(current_ratio,2)} < 1，短期偿债风险",
            })

    result["death_scenarios"] = death_scenarios

    # ── 挑段+巴的盲区 ──
    blind_spots = []

    # 段说生意好但芒格看会死
    if duan_result.get("right_business") == "Y" and len(death_scenarios) >= 2:
        blind_spots.append({
            "conflict": "段永平认为生意本质好，但芒格识别出多个死亡情景",
            "detail": "好生意也会被时代淘汰（柯达、诺基亚案例）",
        })

    # 巴说 FCF 可预测但增长为负
    if buffett_result.get("fcf_predictable") and data.revenue_growth_3y and data.revenue_growth_3y < 0:
        blind_spots.append({
            "conflict": "Buffett 认为 FCF 可预测，但营收实际在萎缩",
            "detail": "FCF 可能来自缩减投资而非真实盈利能力",
        })

    # 巴说护城河深但 ROIC 低
    if buffett_result.get("moat_count", 0) >= 2 and data.roic and data.roic < Decimal("0.10"):
        blind_spots.append({
            "conflict": "Buffett 识别多条护城河，但 ROIC 偏低",
            "detail": "护城河可能正在被侵蚀，只是尚未反映在财务上",
        })

    result["blind_spots"] = blind_spots

    # ── Lollapalooza 五维评分 ──
    lp = result["lollapalooza"]

    # 1. 估值 (0-0.25)
    pe = data.pe_ttm
    if pe and pe < Decimal("15"):
        lp["valuation"] = d_round(Decimal("0.25"), 2)
    elif pe and pe < Decimal("20"):
        lp["valuation"] = d_round(Decimal("0.20"), 2)
    elif pe and pe < Decimal("25"):
        lp["valuation"] = d_round(Decimal("0.15"), 2)
    elif pe and pe < Decimal("35"):
        lp["valuation"] = d_round(Decimal("0.08"), 2)
    else:
        lp["valuation"] = Decimal("0.03")

    # 2. 质量 ROIC (0-0.25)
    roic = data.roic
    if roic and roic > Decimal("0.20"):
        lp["quality"] = d_round(Decimal("0.25"), 2)
    elif roic and roic > Decimal("0.15"):
        lp["quality"] = d_round(Decimal("0.20"), 2)
    elif roic and roic > Decimal("0.10"):
        lp["quality"] = d_round(Decimal("0.13"), 2)
    elif roic and roic > Decimal("0.05"):
        lp["quality"] = d_round(Decimal("0.06"), 2)
    else:
        lp["quality"] = Decimal("0.02")

    # 3. 护城河 (0-0.25)
    moat_count = buffett_result.get("moat_count", 0)
    if moat_count >= 3:
        lp["moat"] = d_round(Decimal("0.25"), 2)
    elif moat_count == 2:
        lp["moat"] = d_round(Decimal("0.18"), 2)
    elif moat_count == 1:
        lp["moat"] = d_round(Decimal("0.10"), 2)
    else:
        lp["moat"] = Decimal("0.03")

    # 4. 催化剂 (0-0.25)
    rev_g = data.revenue_growth_3y
    earn_g = data.earnings_growth_3y
    catalyst_score = Decimal("0.10")  # 基础分
    if rev_g and rev_g > Decimal("0.15"):
        catalyst_score += Decimal("0.08")
    if earn_g and earn_g > Decimal("0.15"):
        catalyst_score += Decimal("0.07")
    lp["catalyst"] = d_round(min(catalyst_score, Decimal("0.25")), 2)

    # 5. 逆向扣减（负分）
    penalty = Decimal("0")
    for ds in death_scenarios:
        penalty += Decimal("0.05")
    lp["contrarian"] = d_round(-penalty, 2)

    # 总分
    total = lp["valuation"] + lp["quality"] + lp["moat"] + lp["catalyst"] + lp["contrarian"]
    lp["total"] = d_round(max(total, Decimal("0")), 2)

    # 仓位档
    from config.settings import POSITION_TIERS
    for tier, bounds in POSITION_TIERS.items():
        if bounds["min"] <= lp["total"] <= bounds["max"]:
            lp["tier"] = tier
            lp["position_pct"] = bounds["pct"]
            break

    return result


# ─── Li Lu · 文明演进坐标 ───
def analyze_lilu(data) -> dict:
    """
    Li Lu 视角：文明演进坐标 + 赛道分析
    ====================================
    核心问题：这条赛道在中国/全球的工业化-城市化-技术迭代位置？
    政策/地缘/供应链暗雷？
    """
    from decimal import Decimal
    from utils.finance import D, d_round

    result = {
        "master": "Li Lu",
        "civilization_stage": "",
        "track_position": "",
        "policy_risks": [],
        "geopolitical_risks": [],
        "supply_chain_risks": [],
        "growth_trajectory": "",
        "warnings": [],
    }

    # ── 赛道阶段判断（基于财务指标推断） ──
    rev_growth = data.revenue_growth_3y
    roic = data.roic
    pe = data.pe_ttm

    if rev_growth and rev_growth > Decimal("0.20") and roic and roic > Decimal("0.15"):
        result["civilization_stage"] = "成长期 — 技术迭代加速，市场快速扩张"
        result["track_position"] = "赛道处于工业化-城市化中段，渗透率快速提升"
    elif rev_growth and rev_growth > Decimal("0.05") and roic and roic > Decimal("0.10"):
        result["civilization_stage"] = "成熟期 — 增长稳健，护城河稳固"
        result["track_position"] = "赛道处于成熟阶段，市场格局基本稳定"
    elif rev_growth and rev_growth < Decimal("0"):
        result["civilization_stage"] = "衰退期 — 结构性萎缩"
        result["track_position"] = "赛道可能处于技术迭代末期或需求萎缩阶段"
    else:
        result["civilization_stage"] = "稳定期 — 低速增长"
        result["track_position"] = "赛道进入存量竞争阶段"

    # ── 政策风险（中国市场特别关注） ──
    sector = data.info.get("sector", "").lower() if data.info else ""
    industry = data.info.get("industry", "").lower() if data.info else ""

    policy_keywords = {
        "房地产": ["real estate", "property", "housing"],
        "教育": ["education", "training"],
        "医疗": ["healthcare", "pharma", "biotech"],
        "互联网平台": ["internet", "platform", "social media"],
        "金融": ["financial", "bank", "insurance"],
        "新能源": ["solar", "renewable", "electric vehicle"],
    }

    for category, keywords in policy_keywords.items():
        for kw in keywords:
            if kw in sector or kw in industry:
                result["policy_risks"].append(f"{category}行业受政策监管影响较大")
                break

    # ── 地缘风险 ──
    country = data.info.get("country", "").lower() if data.info else ""
    if "china" in country:
        result["geopolitical_risks"].append("中美科技竞争可能影响供应链与技术获取")
        result["geopolitical_risks"].append("出口管制与实体清单风险需持续跟踪")

    # ── 供应链风险 ──
    if data.total_debt > 0 and data.total_equity > 0:
        debt_eq = data.total_debt / data.total_equity
        if debt_eq > Decimal("1.5"):
            result["supply_chain_risks"].append(f"高杠杆运营 (D/E={d_round(debt_eq,1)})，供应链韧性存疑")

    if data.current_assets > 0 and data.current_liabilities > 0:
        quick_ratio = (data.current_assets - D(data.info.get("inventory", 0) or 0)) / data.current_liabilities
        if quick_ratio < Decimal("0.8"):
            result["supply_chain_risks"].append("速动比率偏低，供应链中断风险较高")

    # ── 增长轨迹 ──
    if rev_growth and rev_growth > Decimal("0.15"):
        result["growth_trajectory"] = "高增长赛道，有望受益于技术迭代与城市化深化"
    elif rev_growth and rev_growth > Decimal("0"):
        result["growth_trajectory"] = "稳定增长，与 GDP 增速趋同"
    else:
        result["growth_trajectory"] = "增长乏力，需寻找第二曲线"

    return result
