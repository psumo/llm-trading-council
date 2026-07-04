"""
策略开发完整工作流程
从数据研究 -> 策略开发 -> 回测验证 -> 实时运行

这个脚本演示了完整的策略开发流程
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from typing import Dict
import time


def step1_data_research():
    """步骤1: 数据研究 - 探索历史数据，发现市场规律"""
    print("\n" + "="*80)
    print("📊 步骤 1/4: 数据研究")
    print("="*80)
    print("\n目标: 探索历史市场数据，发现可利用的交易规律\n")
    
    from research.data_explorer import DataExplorer
    
    explorer = DataExplorer()
    
    # 获取历史数据
    df = explorer.fetch_historical_data(
        symbol="BTCUSDT",
        interval="1h",
        days=30
    )
    
    if df.empty:
        print("❌ 数据获取失败")
        return None
    
    # 统计分析
    stats = explorer.analyze_data(df)
    
    # 模式识别
    patterns = explorer.find_patterns(df)
    
    # 可视化
    try:
        explorer.visualize_data(df)
    except Exception as e:
        print(f"⚠️  可视化跳过 (需要安装 matplotlib): {e}")
    
    # 生成报告
    explorer.generate_report(df, stats, patterns)
    
    print("\n✅ 数据研究完成")
    print("💡 下一步: 基于研究结果开发交易策略")
    
    return {'stats': stats, 'patterns': patterns, 'data': df}


def step2_strategy_development(research_results: Dict):
    """步骤2: 策略开发 - 基于研究结果开发交易策略"""
    print("\n" + "="*80)
    print("🎯 步骤 2/4: 策略开发")
    print("="*80)
    print("\n目标: 基于数据研究结果，开发可执行的交易策略\n")
    
    # 根据研究结果给出策略建议
    stats = research_results.get('stats', {})
    patterns = research_results.get('patterns', {})
    
    print("📋 策略开发建议（基于数据研究）:")
    
    # 分析波动性
    volatility = stats.get('volatility', {})
    if volatility.get('std_change', 0) > 2:
        print("  ✓ 市场波动大 -> 建议使用趋势跟随或突破策略")
        strategy_type = "trend_following"
    else:
        print("  ✓ 市场波动小 -> 建议使用均值回归策略")
        strategy_type = "mean_reversion"
    
    # 分析趋势
    trend = stats.get('trend', {})
    if trend.get('bullish_pct', 0) > 60:
        print("  ✓ 上升趋势为主 -> 偏向做多")
    elif trend.get('bearish_pct', 0) > 60:
        print("  ✓ 下降趋势为主 -> 偏向做空或观望")
    else:
        print("  ✓ 震荡市场 -> 使用区间交易")
    
    # 分析信号频率
    ma_cross = patterns.get('ma_cross', {})
    print(f"  ✓ 均线交叉信号: 金叉{ma_cross.get('golden', 0)}次, 死叉{ma_cross.get('death', 0)}次")
    
    rsi_signals = patterns.get('rsi', {})
    print(f"  ✓ RSI信号: 超买{rsi_signals.get('overbought', 0)}次, 超卖{rsi_signals.get('oversold', 0)}次")
    
    print(f"\n💡 推荐策略类型: {strategy_type}")
    print("\n✅ 策略开发完成")
    print("💡 下一步: 回测验证策略性能")
    
    return strategy_type


def step3_backtesting(strategy_type: str):
    """步骤3: 策略回测 - 验证策略的历史表现"""
    print("\n" + "="*80)
    print("🔄 步骤 3/4: 策略回测")
    print("="*80)
    print("\n目标: 在历史数据上验证策略的盈利能力和风险水平\n")
    
    from research.backtester import Backtester, simple_ma_crossover_strategy, rsi_mean_reversion_strategy
    
    backtester = Backtester()
    
    # 根据策略类型选择回测策略
    if strategy_type == "mean_reversion":
        print("【回测策略: RSI均值回归】")
        strategy_func = rsi_mean_reversion_strategy
    else:
        print("【回测策略: 均线交叉趋势跟随】")
        strategy_func = simple_ma_crossover_strategy
    
    # 运行回测
    results = backtester.run_backtest(
        strategy_func=strategy_func,
        symbol="BTCUSDT",
        interval="1h",
        days=30,
        initial_capital=10000.0,
        position_size=0.3  # 30%仓位，控制风险
    )
    
    # 保存结果
    backtester.save_results(results)
    
    # 评估回测结果
    print("\n📊 回测评估:")
    
    if results['total_return_pct'] > 0:
        print(f"  ✅ 策略盈利: {results['total_return_pct']:+.2f}%")
    else:
        print(f"  ❌ 策略亏损: {results['total_return_pct']:+.2f}%")
    
    if results['win_rate'] > 50:
        print(f"  ✅ 胜率良好: {results['win_rate']:.1f}%")
    else:
        print(f"  ⚠️  胜率偏低: {results['win_rate']:.1f}%")
    
    if results['max_drawdown'] > -20:
        print(f"  ✅ 回撤可控: {results['max_drawdown']:.2f}%")
    else:
        print(f"  ⚠️  回撤较大: {results['max_drawdown']:.2f}%")
    
    # 决定是否可以实盘
    can_go_live = (
        results['total_return_pct'] > 0 and
        results['win_rate'] > 40 and
        results['max_drawdown'] > -30
    )
    
    if can_go_live:
        print("\n✅ 回测通过，策略可以进入实盘测试")
    else:
        print("\n⚠️  回测结果不理想，建议优化策略参数或更换策略")
    
    print("\n✅ 策略回测完成")
    print("💡 下一步: 实时运行策略（小额测试）")
    
    return results, can_go_live


def step4_live_trading(strategy_type: str, can_go_live: bool):
    """步骤4: 实时交易 - 在实盘环境中运行策略"""
    print("\n" + "="*80)
    print("🚀 步骤 4/4: 实时策略运行")
    print("="*80)
    print("\n目标: 在实时市场中运行策略，生成交易信号\n")
    
    if not can_go_live:
        print("⚠️  回测结果不理想，建议先优化策略")
        print("💡 您仍然可以运行实时信号生成来观察策略表现")
        response = input("\n是否继续运行实时策略? (y/n): ")
        if response.lower() != 'y':
            print("❌ 已取消实时运行")
            return
    
    print("📡 启动实时策略监控...")
    print("⚠️  这是演示模式，不会执行真实交易\n")
    
    # 导入实时运行脚本
    from run_strategy_live import main as run_live
    
    # 运行几次实时信号生成
    for i in range(3):
        print(f"\n--- 第 {i+1} 次信号生成 ---")
        run_live()
        
        if i < 2:
            print("\n⏳ 等待60秒后再次检查...")
            time.sleep(60)
    
    print("\n✅ 实时策略运行演示完成")
    print("\n📋 后续步骤建议:")
    print("  1. 持续监控策略表现")
    print("  2. 记录所有交易信号和结果")
    print("  3. 定期回测和优化参数")
    print("  4. 严格执行风险管理（止损、仓位控制）")
    print("  5. 考虑多策略组合以分散风险")


def main():
    """运行完整的策略开发工作流程"""
    print("\n" + "="*80)
    print("🎓 AI Trader - 策略开发完整工作流程")
    print("="*80)
    print("\n这个流程将引导您完成:")
    print("  1. 数据研究 - 探索市场规律")
    print("  2. 策略开发 - 设计交易策略")
    print("  3. 回测验证 - 验证策略性能")
    print("  4. 实时运行 - 生成交易信号")
    print("\n" + "="*80)
    
    try:
        # 步骤1: 数据研究
        research_results = step1_data_research()
        
        if research_results is None:
            print("\n❌ 数据研究失败，工作流程终止")
            return
        
        input("\n按 Enter 继续到下一步...")
        
        # 步骤2: 策略开发
        strategy_type = step2_strategy_development(research_results)
        
        input("\n按 Enter 继续到下一步...")
        
        # 步骤3: 回测验证
        backtest_results, can_go_live = step3_backtesting(strategy_type)
        
        input("\n按 Enter 继续到下一步...")
        
        # 步骤4: 实时运行
        step4_live_trading(strategy_type, can_go_live)
        
        print("\n" + "="*80)
        print("🎉 完整工作流程演示完成!")
        print("="*80)
        print("\n📚 相关文档:")
        print("  - STRATEGY_DEVELOPMENT_GUIDE.md - 策略开发指南")
        print("  - DATA_PIPELINE.md - 数据流转文档")
        print("  - research/outputs/ - 研究和回测结果")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  工作流程被用户中断")
    except Exception as e:
        print(f"\n\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
