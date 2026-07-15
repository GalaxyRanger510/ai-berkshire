"""
AI Berkshire — 投顾仪表盘
==========================
Streamlit + Plotly 7 模块仪表盘
所有计算用 Decimal，金融上下文禁用 float
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
from decimal import Decimal
from typing import Dict
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import COLORS, POSITION_TIERS, LOLLAPALOOZA_WEIGHTS
from data.fetcher import fetch_stock_data, get_market_phase
from masters.analysts import analyze_duan, analyze_buffett, analyze_munger, analyze_lilu
from core.aggregator import run_adversarial_analysis
from utils.finance import D, d_round


# ═══════════════════════════════════════════════════════════
# 页面配置
# ═══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="AI Berkshire · 个人投顾",
    page_icon="🏰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 自定义 CSS
st.markdown("""
<style>
    /* 深蓝主题 */
    .main { background-color: #0a0e27; }
    .stApp { background-color: #0a0e27; }
    section[data-testid="stSidebar"] { background-color: #111633; }
    
    /* 顶栏 */
    .header-bar {
        background: linear-gradient(135deg, #070b1f 0%, #1a1f3a 100%);
        padding: 1.2rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        border: 1px solid #1e293b;
    }
    .header-bar h1 {
        color: #e2e8f0;
        font-size: 1.8rem;
        margin: 0;
        font-weight: 700;
    }
    .header-bar .subtitle {
        color: #94a3b8;
        font-size: 0.9rem;
        margin-top: 0.3rem;
    }
    
    /* 指标卡片 */
    .metric-card {
        background: #111633;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        border: 1px solid #1e293b;
        text-align: center;
    }
    .metric-card .label {
        color: #94a3b8;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-card .value {
        color: #e2e8f0;
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0.3rem 0;
    }
    .metric-card .change {
        font-size: 0.85rem;
        font-weight: 600;
    }
    .up { color: #10b981; }
    .down { color: #ef4444; }
    
    /* 大师标签 */
    .master-tag {
        display: inline-block;
        padding: 0.15rem 0.6rem;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 0.3rem;
    }
    .master-duan { background: rgba(139,92,246,0.2); color: #a78bfa; }
    .master-buffett { background: rgba(59,130,246,0.2); color: #60a5fa; }
    .master-munger { background: rgba(245,158,11,0.2); color: #fbbf24; }
    .master-lilu { background: rgba(16,185,129,0.2); color: #34d399; }
    
    /* 结论卡片 */
    .verdict-pass { background: rgba(16,185,129,0.15); border: 1px solid #10b981; }
    .verdict-warn { background: rgba(245,158,11,0.15); border: 1px solid #f59e0b; }
    .verdict-fail { background: rgba(239,68,68,0.15); border: 1px solid #ef4444; }
    
    /* 冲突灯 */
    .conflict-red { color: #ef4444; font-weight: 700; }
    .conflict-yellow { color: #f59e0b; font-weight: 700; }
    .conflict-green { color: #10b981; font-weight: 700; }
    
    /* 滚动条 */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #0a0e27; }
    ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════

def fmt_price(val: Decimal, currency: str = "USD") -> str:
    """格式化价格"""
    if currency in ("USD", "HKD"):
        symbol = "$" if currency == "USD" else "HK$"
    else:
        symbol = "¥"
    return f"{symbol}{float(val):,.2f}"


def fmt_big(val: Decimal) -> str:
    """格式化大数"""
    v = float(val)
    if abs(v) >= 1e12:
        return f"{v/1e12:.2f}T"
    elif abs(v) >= 1e9:
        return f"{v/1e9:.2f}B"
    elif abs(v) >= 1e6:
        return f"{v/1e6:.2f}M"
    return f"{v:,.0f}"


def pct_str(val: Decimal) -> str:
    """百分比字符串"""
    return f"{float(val * 100):.2f}%"


# ═══════════════════════════════════════════════════════════
# 模块 1: 核心指标卡
# ═══════════════════════════════════════════════════════════
def render_metric_cards(data):
    """顶行 4 格核心指标卡"""
    cols = st.columns(4)
    
    metrics = [
        ("当前价", fmt_price(data.price, data.currency), data.price_change_3m),
        ("市值", fmt_big(data.market_cap), Decimal("0")),
        ("P/E (TTM)", f"{float(data.pe_ttm):.1f}" if data.pe_ttm else "N/A", Decimal("0")),
        ("ROE", pct_str(data.roe) if data.roe else "N/A", Decimal("0")),
    ]
    
    for i, (label, value, change) in enumerate(metrics):
        with cols[i]:
            arrow = ""
            css_class = ""
            if i == 0 and change != 0:  # 价格变动
                arrow = "▲" if change > 0 else "▼"
                css_class = "up" if change > 0 else "down"
            
            st.markdown(f"""
            <div class="metric-card">
                <div class="label">{label}</div>
                <div class="value">{value}</div>
                <div class="change {css_class}">{arrow} {pct_str(change) if i == 0 else ''}</div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 模块 2: 四大师共识雷达图
# ═══════════════════════════════════════════════════════════
def render_radar(duan, buffett, munger, lilu):
    """四大师共识雷达图 — 5 轴"""
    categories = ["生意本质", "护城河", "估值安全", "文明位", "逆向安全"]
    
    # 将四大师结论量化为 0-100 分
    duan_scores = [
        90 if duan.get("right_business") == "Y" else 50 if duan.get("right_business") == "⚠️" else 20,
        70 if duan.get("right_people") == "Y" else 30,
        80 if duan.get("right_price") == "Y" else 50 if duan.get("right_price") == "⚠️" else 20,
        60,  # 文明位非段的核心
        70 if duan.get("benfen_test") else 30,
    ]
    
    buffett_scores = [
        60,  # 生意本质非巴核心
        90 if buffett.get("moat_count", 0) >= 3 else 70 if buffett.get("moat_count", 0) >= 1 else 30,
        85 if buffett.get("fcf_predictable") else 30,
        50,
        60 if len(buffett.get("cross_validation", [])) == 0 else 40,
    ]
    
    lp = munger.get("lollapalooza", {})
    munger_scores = [
        int(float(lp.get("quality", Decimal("0.10"))) * 400),
        int(float(lp.get("moat", Decimal("0.10"))) * 400),
        int(float(lp.get("valuation", Decimal("0.10"))) * 400),
        int(float(lp.get("catalyst", Decimal("0.10"))) * 400),
        max(0, 100 + int(float(lp.get("contrarian", Decimal("0"))) * 400)),
    ]
    
    lilu_scores = [
        50,
        40,
        50,
        85 if "成长" in lilu.get("civilization_stage", "") else 50 if "成熟" in lilu.get("civilization_stage", "") else 20,
        70 if len(lilu.get("geopolitical_risks", [])) == 0 else 30,
    ]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=duan_scores, theta=categories, name="段永平",
        fill="toself", fillcolor="rgba(139,92,246,0.1)",
        line=dict(color=COLORS["duan"], width=2),
    ))
    fig.add_trace(go.Scatterpolar(
        r=buffett_scores, theta=categories, name="Buffett",
        fill="toself", fillcolor="rgba(59,130,246,0.1)",
        line=dict(color=COLORS["buffett"], width=2),
    ))
    fig.add_trace(go.Scatterpolar(
        r=munger_scores, theta=categories, name="Munger",
        fill="toself", fillcolor="rgba(245,158,11,0.1)",
        line=dict(color=COLORS["munger"], width=2),
    ))
    fig.add_trace(go.Scatterpolar(
        r=lilu_scores, theta=categories, name="Li Lu",
        fill="toself", fillcolor="rgba(16,185,129,0.1)",
        line=dict(color=COLORS["lilu"], width=2),
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(range=[0, 100], showticklabels=False, gridcolor="#1e293b"),
            angularaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#94a3b8", size=11)),
            bgcolor="#0a0e27",
        ),
        paper_bgcolor="#0a0e27",
        plot_bgcolor="#0a0e27",
        font=dict(color="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        margin=dict(l=40, r=40, t=40, b=60),
        height=420,
    )
    
    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════
# 模块 3: Lollapalooza 评分条
# ═══════════════════════════════════════════════════════════
def render_lollapalooza(munger_result):
    """Lollapalooza 五维横向进度条 + 总分 + 仓位档"""
    lp = munger_result.get("lollapalooza", {})
    dimensions = [
        ("估值", lp.get("valuation", Decimal("0")), Decimal("0.25")),
        ("质量 ROIC", lp.get("quality", Decimal("0")), Decimal("0.25")),
        ("护城河", lp.get("moat", Decimal("0")), Decimal("0.25")),
        ("催化剂", lp.get("catalyst", Decimal("0")), Decimal("0.25")),
        ("逆向扣减", lp.get("contrarian", Decimal("0")), Decimal("0")),
    ]
    
    st.markdown("### 🎯 Lollapalooza 五维评分")
    
    for label, score, max_val in dimensions:
        pct = float(score / Decimal("0.25") * 100) if max_val > 0 else float(score / Decimal("-0.25") * 100)
        pct = max(0, min(100, pct))
        color = "#10b981" if score >= Decimal("0.15") else "#f59e0b" if score >= Decimal("0.08") else "#ef4444"
        if label == "逆向扣减":
            color = "#ef4444" if score < 0 else "#10b981"
            pct = min(100, abs(float(score) * 400))
        
        st.markdown(f"""
        <div style="display:flex;align-items:center;margin-bottom:8px;">
            <div style="width:100px;color:#94a3b8;font-size:0.85rem;">{label}</div>
            <div style="flex:1;background:#1e293b;border-radius:6px;height:18px;margin:0 10px;">
                <div style="width:{pct}%;background:{color};height:100%;border-radius:6px;transition:width 0.5s;"></div>
            </div>
            <div style="width:50px;color:#e2e8f0;font-size:0.85rem;text-align:right;">{float(score):.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # 总分 + 仓位档
    total = lp.get("total", Decimal("0"))
    tier = lp.get("tier", "不投")
    pos = lp.get("position_pct", "0%")
    
    tier_colors = {"超级": "#10b981", "强": "#3b82f6", "标准": "#f59e0b", "准": "#94a3b8", "不投": "#ef4444"}
    tc = tier_colors.get(tier, "#94a3b8")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Lollapalooza 总分", f"{float(total):.2f}")
    with col2:
        st.markdown(f"**仓位档位**: <span style='color:{tc};font-size:1.2rem;'>{tier}</span>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"**建议仓位**: <span style='color:#e2e8f0;font-size:1.2rem;'>{pos}</span>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 模块 4: 冲突点红黄灯
# ═══════════════════════════════════════════════════════════
def render_conflicts(report):
    """冲突点红黄灯展示"""
    st.markdown("### 🚦 四大师冲突点")
    
    conflicts = report.conflicts
    if not conflicts:
        st.success("✅ 四大师无显著冲突，共识度高")
        return
    
    for c in conflicts:
        severity_icon = "🔴" if "严重" in c["severity"] else "🟡"
        bg = "rgba(239,68,68,0.1)" if "严重" in c["severity"] else "rgba(245,158,11,0.1)"
        border = "#ef4444" if "严重" in c["severity"] else "#f59e0b"
        
        st.markdown(f"""
        <div style="background:{bg};border:1px solid {border};border-radius:10px;padding:1rem;margin-bottom:0.8rem;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                <span style="font-size:1.2rem;">{severity_icon}</span>
                <span style="color:#e2e8f0;font-weight:700;">{c['parties']}</span>
                <span style="color:#94a3b8;font-size:0.8rem;">{c['severity']}</span>
            </div>
            <div style="color:#94a3b8;font-size:0.85rem;margin-bottom:4px;">
                <span class="master-tag master-duan">段</span> {c.get('duan_says', '')}<br/>
                <span class="master-tag master-munger">芒</span> {c.get('munger_says', '')}
                <span class="master-tag master-buffett">巴</span> {c.get('buffett_says', '')}
                <span class="master-tag master-lilu">李</span> {c.get('lilu_says', '')}
            </div>
            <div style="color:#f59e0b;font-size:0.85rem;font-weight:600;">
                ⚡ 核心冲突点：{c['core_issue']}
            </div>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 模块 5: 三情景目标价区间
# ═══════════════════════════════════════════════════════════
def render_target_prices(data, buffett_result):
    """三情景目标价区间 + 当前价箭头"""
    st.markdown("### 📊 三情景目标价区间 (DCF)")
    
    dcf = buffett_result.get("dcf", {})
    if not dcf:
        st.warning("DCF 估值数据不可用")
        return
    
    current_price = float(data.price)
    
    bear = dcf.get("bear", {}).get("per_share", data.price)
    base = dcf.get("base", {}).get("per_share", data.price)
    bull = dcf.get("bull", {}).get("per_share", data.price)
    
    bear_f = float(bear) if isinstance(bear, Decimal) else bear
    base_f = float(base) if isinstance(base, Decimal) else base
    bull_f = float(bull) if isinstance(bull, Decimal) else bull
    
    # 计算上下空间
    upside = (bull_f / current_price - 1) * 100 if current_price > 0 else 0
    downside = (1 - bear_f / current_price) * 100 if current_price > 0 else 0
    
    fig = go.Figure()
    
    # 熊/基/牛三根横线
    for scenario, price, color in [
        ("🐻 熊", bear_f, "#ef4444"),
        ("🎯 基准", base_f, "#f59e0b"),
        ("🐂 牛", bull_f, "#10b981"),
    ]:
        fig.add_trace(go.Scatter(
            x=[0, 1], y=[price, price],
            mode="lines", name=scenario,
            line=dict(color=color, width=3, dash="dash"),
            hovertemplate=f"{scenario}: ¥{price:,.2f}<extra></extra>",
        ))
        fig.add_annotation(x=1.02, y=price, text=f"{scenario}<br>¥{price:,.2f}",
                          showarrow=False, font=dict(color=color, size=11), xanchor="left")
    
    # 当前价箭头
    fig.add_trace(go.Scatter(
        x=[0.5], y=[current_price],
        mode="markers+text",
        marker=dict(size=18, color="#3b82f6", symbol="triangle-right"),
        text=[f" 当前 ¥{current_price:,.2f}"],
        textposition="middle right",
        textfont=dict(color="#3b82f6", size=13, family="monospace"),
        name="当前价",
        hovertemplate=f"当前价: ¥{current_price:,.2f}<extra></extra>",
    ))
    
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, range=[-0.1, 1.3]),
        yaxis=dict(title="目标价 (¥)", gridcolor="#1e293b", tickfont=dict(color="#94a3b8")),
        paper_bgcolor="#0a0e27",
        plot_bgcolor="#0a0e27",
        font=dict(color="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=60, r=160, t=40, b=40),
        height=350,
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 涨跌空间
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("下行风险", f"-{downside:.1f}%")
    with col2:
        st.metric("当前价", f"¥{current_price:,.2f}")
    with col3:
        st.metric("上行空间", f"+{upside:.1f}%")


# ═══════════════════════════════════════════════════════════
# 模块 6: 建仓建议卡
# ═══════════════════════════════════════════════════════════
def render_position_plan(data, report, buffett_result):
    """三档建仓建议卡"""
    st.markdown("### 💰 建仓建议卡")
    
    dcf = buffett_result.get("dcf", {})
    base_price = dcf.get("base", {}).get("per_share", data.price)
    base_f = float(base_price) if isinstance(base_price, Decimal) else float(data.price)
    current_f = float(data.price)
    
    # 首仓价 = 当前价或基准价的 90%，取较低
    first_entry = min(current_f, base_f * 0.90)
    add_entry = first_entry * 0.85    # 加仓位 = 首仓的 85%
    extreme_entry = first_entry * 0.70  # 极限位 = 首仓的 70%
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div style="background:rgba(59,130,246,0.1);border:1px solid #3b82f6;border-radius:12px;padding:1.2rem;text-align:center;">
            <div style="color:#60a5fa;font-size:0.8rem;text-transform:uppercase;margin-bottom:4px;">首仓</div>
            <div style="color:#e2e8f0;font-size:1.8rem;font-weight:700;">¥{first_entry:,.2f}</div>
            <div style="color:#94a3b8;font-size:0.9rem;margin-top:6px;">建议仓位 <b>10-15%</b></div>
            <div style="color:#3b82f6;font-size:0.8rem;margin-top:4px;">安全边际充足区</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="background:rgba(245,158,11,0.1);border:1px solid #f59e0b;border-radius:12px;padding:1.2rem;text-align:center;">
            <div style="color:#fbbf24;font-size:0.8rem;text-transform:uppercase;margin-bottom:4px;">加仓</div>
            <div style="color:#e2e8f0;font-size:1.8rem;font-weight:700;">¥{add_entry:,.2f}</div>
            <div style="color:#94a3b8;font-size:0.9rem;margin-top:6px;">回调加至 <b>20-25%</b></div>
            <div style="color:#f59e0b;font-size:0.8rem;margin-top:4px;">估值回归合理下沿</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div style="background:rgba(16,185,129,0.1);border:1px solid #10b981;border-radius:12px;padding:1.2rem;text-align:center;">
            <div style="color:#34d399;font-size:0.8rem;text-transform:uppercase;margin-bottom:4px;">极限</div>
            <div style="color:#e2e8f0;font-size:1.8rem;font-weight:700;">¥{extreme_entry:,.2f}</div>
            <div style="color:#94a3b8;font-size:0.9rem;margin-top:6px;">极限仓位 <b>30-40%</b></div>
            <div style="color:#10b981;font-size:0.8rem;margin-top:4px;">极端恐慌才触发</div>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 模块 7: 四大师详细分析
# ═══════════════════════════════════════════════════════════
def render_master_analysis(duan, buffett, munger, lilu):
    """四大师详细分析展开区"""
    st.markdown("### 🔍 四大师详细分析")
    
    tabs = st.tabs(["🟣 段永平", "🔵 Buffett", "🟡 Munger", "🟢 Li Lu"])
    
    with tabs[0]:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Right Business", duan.get("right_business", "N/A"))
            st.metric("Right People", duan.get("right_people", "N/A"))
        with col2:
            st.metric("Right Price", duan.get("right_price", "N/A"))
            st.metric("本分测试", "✅" if duan.get("benfen_test") else "❌")
        
        st.markdown(f"**生意本质**: {duan.get('business_essence', '')}")
        for w in duan.get("warnings", []):
            st.warning(w)
    
    with tabs[1]:
        st.markdown(f"**护城河数量**: {buffett.get('moat_count', 0)} 条")
        for m in buffett.get("moats", []):
            st.markdown(f"- 🏰 {m}")
        st.markdown(f"**FCF 可预测**: {'✅' if buffett.get('fcf_predictable') else '❌'}")
        
        dcf = buffett.get("dcf", {})
        if dcf:
            dcf_df = pd.DataFrame([
                {"情景": "🐻 熊", "目标价": float(dcf.get("bear", {}).get("per_share", 0)),
                 "终值PV": float(dcf.get("bear", {}).get("terminal_pv", 0))},
                {"情景": "🎯 基准", "目标价": float(dcf.get("base", {}).get("per_share", 0)),
                 "终值PV": float(dcf.get("base", {}).get("terminal_pv", 0))},
                {"情景": "🐂 牛", "目标价": float(dcf.get("bull", {}).get("per_share", 0)),
                 "终值PV": float(dcf.get("bull", {}).get("terminal_pv", 0))},
            ])
            st.dataframe(dcf_df, use_container_width=True)
        
        for alert in buffett.get("cross_validation", []):
            st.warning(f"⚠️ {alert['type']}: 误差 {float(alert['error_pct']):.1f}%")
    
    with tabs[2]:
        st.markdown("#### 💀 死亡情景分析")
        for ds in munger.get("death_scenarios", []):
            st.markdown(f"""
            > **{ds['scenario']}** `{ds['lens']}`  
            > {ds['detail']}
            """)
        
        if not munger.get("death_scenarios"):
            st.success("未识别到明显死亡情景")
        
        st.markdown("#### 🔍 盲区暴露")
        for bs in munger.get("blind_spots", []):
            st.warning(f"**{bs['conflict']}**: {bs['detail']}")
        
        if not munger.get("blind_spots"):
            st.info("未发现明显盲区")
    
    with tabs[3]:
        st.markdown(f"**文明阶段**: {lilu.get('civilization_stage', '')}")
        st.markdown(f"**赛道位置**: {lilu.get('track_position', '')}")
        st.markdown(f"**增长轨迹**: {lilu.get('growth_trajectory', '')}")
        
        if lilu.get("policy_risks"):
            st.markdown("#### ⚠️ 政策风险")
            for r in lilu["policy_risks"]:
                st.warning(r)
        
        if lilu.get("geopolitical_risks"):
            st.markdown("#### 🌍 地缘风险")
            for r in lilu["geopolitical_risks"]:
                st.warning(r)
        
        if lilu.get("supply_chain_risks"):
            st.markdown("#### 🔗 供应链风险")
            for r in lilu["supply_chain_risks"]:
                st.warning(r)


# ═══════════════════════════════════════════════════════════
# 主页面
# ═══════════════════════════════════════════════════════════
def main():
    # ── 顶栏 ──
    st.markdown("""
    <div class="header-bar">
        <h1>🏰 AI Berkshire · 个人投顾仪表盘</h1>
        <div class="subtitle">
            Warren Buffett · Charlie Munger · 段永平 · Li Lu — 四大师对抗式决策系统
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ── 侧边栏：输入区 ──
    with st.sidebar:
        st.markdown("### 📋 分析设置")
        ticker = st.text_input("股票代码", value="AAPL", 
                               help="美股直接输入代码，A股加后缀（如 600519.SS），港股加 .HK")
        
        col1, col2 = st.columns(2)
        with col1:
            analyze_btn = st.button("🔍 开始分析", type="primary", use_container_width=True)
        with col2:
            st.button("🔄 刷新数据", use_container_width=True)
        
        st.markdown("---")
        st.markdown("### 🎯 快速选择")
        quick_tickers = {
            "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Google",
            "600519.SS": "贵州茅台", "0700.HK": "腾讯控股",
        }
        for t, name in quick_tickers.items():
            if st.button(f"{name} ({t})", use_container_width=True):
                ticker = t
                analyze_btn = True
        
        st.markdown("---")
        st.markdown("### ℹ️ 关于")
        st.markdown("""
        **AI Berkshire** 将四位价值投资大师的思维方式编译为可执行决策系统。
        
        - 所有计算用 `Decimal`（禁用 float）
        - 四大师对抗式分析（不许和稀泥）
        - Lollapalooza 五维量化评分
        - 强制三档结论
        
        ⚠️ 历史收益不代表未来，DYOR
        """)
    
    # ── 主体区域 ──
    if not analyze_btn and "analysis_done" not in st.session_state:
        # 初始状态 — 展示空状态
        st.info("👈 在左侧输入股票代码，点击「开始分析」")
        st.markdown("""
        ### 支持的格式
        - **美股**: `AAPL`, `MSFT`, `GOOGL`, `NVDA`, `TSLA`, `META`, `BRK-B`
        - **A股**: `600519.SS`（上海）, `000858.SZ`（深圳）
        - **港股**: `0700.HK`, `9988.HK`
        
        ### 🛡️ 多级数据降级策略
        | 级别 | 说明 |
        |------|------|
        | 🔴 实时 | yfinance API 实时数据 |
        | 🟡 缓存 | 24 小时内温缓存降级 |
        | 🟢 离线 | 预置静态数据兜底（15+ 热门标的） |
        """)
        return
    
    if analyze_btn:
        st.session_state["ticker"] = ticker
        st.session_state["analysis_done"] = False
    
    ticker = st.session_state.get("ticker", "AAPL")
    
    # ── 加载数据 ──
    with st.spinner(f"📡 正在拉取 {ticker} 数据..."):
        try:
            # Step 0: 市场阶段
            market_phase = get_market_phase()
            
            # 数据拉取
            data = fetch_stock_data(ticker)
            
            # 数据来源提示
            ds = getattr(data, 'data_source', 'unknown')
            ps = getattr(data, 'price_source', 'unknown')
            
            # 价格来源
            if "realtime" in ps:
                st.success(f"📡 行情: 实时 (Yahoo Finance) — {data.fetch_time[:19]}")
            elif ps == "fallback":
                st.warning("⚠️ 行情: 离线参考价（非实时）")
            
            # 基本面来源
            if "fallback" in ds and "live" not in ds:
                st.info("📊 基本面: 预置参考数据（yfinance 不可用时的兜底值）")
            
            # Step 1: 四大师并行分析
            with st.spinner("🧠 四大师分析中..."):
                duan_result = analyze_duan(data)
                buffett_result = analyze_buffett(data)
                munger_result = analyze_munger(data, duan_result, buffett_result)
                lilu_result = analyze_lilu(data)
            
            # Step 2-4: 对抗聚合
            with st.spinner("⚔️ 对抗式聚合中..."):
                report = run_adversarial_analysis(
                    data, duan_result, buffett_result, munger_result, lilu_result, market_phase
                )
            
            st.session_state["report"] = report
            st.session_state["data"] = data
            st.session_state["duan"] = duan_result
            st.session_state["buffett"] = buffett_result
            st.session_state["munger"] = munger_result
            st.session_state["lilu"] = lilu_result
            st.session_state["market_phase"] = market_phase
            st.session_state["analysis_done"] = True
            
        except Exception as e:
            st.error(f"❌ 分析失败: {e}")
            st.markdown("""
            ### 🔧 排查建议
            1. **检查代码格式**: A 股需加后缀（`600519.SS` / `000858.SZ`），港股需加 `.HK`
            2. **yfinance 限流**: 免费 API 有频率限制，请等待 1-2 分钟后重试
            3. **使用离线兜底**: 以下标的支持离线分析（无需网络）：
               `AAPL` `MSFT` `GOOGL` `AMZN` `META` `TSLA` `NVDA` `BRK-B` `JPM` `COST` `V`
               `600519.SS` `000858.SZ` `0700.HK` `9988.HK`
            """)
            return
    
    # ── 渲染仪表盘 ──
    if st.session_state.get("analysis_done"):
        report = st.session_state["report"]
        data = st.session_state["data"]
        duan = st.session_state["duan"]
        buffett = st.session_state["buffett"]
        munger = st.session_state["munger"]
        lilu = st.session_state["lilu"]
        market_phase = st.session_state["market_phase"]
        
        # 市场阶段标签
        st.markdown(f"**当前模式**: `{market_phase}`")
        
        # 公司名称 + 最终结论
        verdict_color = {"✅ 通过": "#10b981", "⚠️ 灰色地带": "#f59e0b", "❌ 不通过": "#ef4444"}
        vc = verdict_color.get(report.verdict, "#94a3b8")
        
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1rem;">
            <h2 style="color:#e2e8f0;margin:0;">{data.name}</h2>
            <span style="color:#94a3b8;font-size:1rem;">{ticker}</span>
            <span style="background:{vc}22;color:{vc};padding:0.3rem 1rem;border-radius:20px;font-weight:700;font-size:1.1rem;">
                {report.verdict}
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        # ── 模块 1: 核心指标卡 ──
        render_metric_cards(data)
        st.markdown("---")
        
        # ── 模块 2 + 3: 雷达图 + Lollapalooza ──
        col1, col2 = st.columns([3, 2])
        with col1:
            render_radar(duan, buffett, munger, lilu)
        with col2:
            render_lollapalooza(munger)
        
        st.markdown("---")
        
        # ── 模块 4: 冲突点 ──
        render_conflicts(report)
        st.markdown("---")
        
        # ── 模块 5 + 6: 目标价 + 建仓 ──
        col1, col2 = st.columns([3, 2])
        with col1:
            render_target_prices(data, buffett)
        with col2:
            render_position_plan(data, report, buffett)
        
        st.markdown("---")
        
        # ── 强制结论卡 ──
        conclusion = report.conclusion
        verdict_class = {
            "✅ 通过": "verdict-pass",
            "⚠️ 灰色地带": "verdict-warn",
            "❌ 不通过": "verdict-fail",
        }.get(report.verdict, "")
        
        st.markdown(f"""
        <div class="metric-card {verdict_class}" style="text-align:left;padding:1.5rem;">
            <h3 style="color:{vc};margin-bottom:1rem;">{report.verdict} — 强制结论</h3>
        """, unsafe_allow_html=True)
        
        if report.verdict == "✅ 通过":
            st.markdown(f"""
            - **价格区间**: {conclusion.get('price_range', 'N/A')}
            - **建议首仓**: {conclusion.get('first_position', 'N/A')}
            - **回调加仓**: {conclusion.get('add_position', 'N/A')}
            - **Lollapalooza**: {conclusion.get('lollapalooza_score', 0):.2f}（{conclusion.get('lollapalooza_tier', '')}档）
            - **核心理由**: {conclusion.get('rationale', '')}
            """)
        elif report.verdict == "⚠️ 灰色地带":
            st.markdown(f"""
            - **冲突点**: {', '.join(conclusion.get('conflicts', []))}
            - **待确认**: {', '.join(conclusion.get('pending_items', []))}
            - **观望价**: {conclusion.get('watch_price', 'N/A')}
            - **Lollapalooza**: {conclusion.get('lollapalooza_score', 0):.2f}
            """)
        else:
            st.markdown(f"""
            - **否决理由**: {', '.join(conclusion.get('reasons', []))}
            - **即使跌到 {conclusion.get('even_at', 'N/A')} 也不买**
            - **Lollapalooza**: {conclusion.get('lollapalooza_score', 0):.2f}
            """)
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # ── 模块 7: 四大师详细分析 ──
        render_master_analysis(duan, buffett, munger, lilu)
        
        # ── 免责声明 ──
        st.markdown("---")
        st.caption("⚠️ 历史收益不代表未来，DYOR | AI Berkshire 不构成投资建议 | 所有计算基于公开数据，可能存在延迟")


if __name__ == "__main__":
    main()
