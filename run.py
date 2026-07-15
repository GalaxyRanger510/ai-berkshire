#!/usr/bin/env python3
"""
AI Berkshire — 命令行快速分析入口
==================================
用法: python run.py AAPL
     python run.py 600519.SS
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.fetcher import fetch_stock_data, get_market_phase
from masters.analysts import analyze_duan, analyze_buffett, analyze_munger, analyze_lilu
from core.aggregator import run_adversarial_analysis


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    
    print(f"\n{'='*60}")
    print(f"  🏰 AI Berkshire · 个人投顾")
    print(f"  标的: {ticker}")
    print(f"{'='*60}\n")
    
    # Step 0: 市场阶段
    phase = get_market_phase()
    print(f"📡 当前模式: {phase}\n")
    
    # 拉取数据
    print(f"📊 拉取数据中...")
    data = fetch_stock_data(ticker)
    print(f"  名称: {data.name}")
    print(f"  价格: {data.price}")
    print(f"  市值: {data.market_cap}")
    print(f"  P/E:  {data.pe_ttm}")
    print()
    
    # 四大师分析
    print("🧠 四大师分析中...\n")
    duan = analyze_duan(data)
    buffett = analyze_buffett(data)
    munger = analyze_munger(data, duan, buffett)
    lilu = analyze_lilu(data)
    
    # 聚合
    report = run_adversarial_analysis(data, duan, buffett, munger, lilu, phase)
    
    # 输出结论
    print(f"{'='*60}")
    print(f"  {report.verdict}")
    print(f"{'='*60}")
    
    conclusion = report.conclusion
    for k, v in conclusion.items():
        if isinstance(v, list):
            print(f"  {k}: {', '.join(v)}")
        else:
            print(f"  {k}: {v}")
    
    print(f"\n  Lollapalooza: {conclusion.get('lollapalooza_score', 0):.2f}")
    print(f"  仓位档位: {conclusion.get('lollapalooza_tier', 'N/A')}")
    
    # 冲突点
    if report.conflicts:
        print(f"\n  ⚡ 冲突点:")
        for c in report.conflicts:
            print(f"    [{c['severity']}] {c['core_issue']}")
    
    print(f"\n⚠️ 历史收益不代表未来，DYOR\n")


if __name__ == "__main__":
    main()
