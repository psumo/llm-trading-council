#!/usr/bin/env python3
"""
数据目录迁移脚本
将现有 data/ 结构迁移到新的 live/backtest/kline 结构

新目录结构:
data/
├── kline/      # 共享 K 线缓存 (实盘和回测共用)
├── live/       # 实盘数据 (agents, trades, analytics 等)
└── backtest/   # 回测数据 (agents, trades, results 等)

用法:
    python scripts/migrate_data.py [--dry-run]
"""

import os
import shutil
from pathlib import Path
import argparse
from datetime import datetime


def log(msg: str, level: str = "INFO"):
    """打印日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "ℹ️", "WARN": "⚠️", "OK": "✅", "MOVE": "📦", "SKIP": "⏭️", "CREATE": "📁"}
    icon = icons.get(level, "•")
    print(f"[{timestamp}] {icon} {msg}")


def migrate(dry_run: bool = False):
    """执行数据迁移"""
    data_dir = Path("data")
    
    if not data_dir.exists():
        log("data/ 目录不存在，无需迁移", "WARN")
        return
    
    log(f"开始迁移 {'(DRY RUN - 不实际移动文件)' if dry_run else ''}")
    
    # 1. 创建新目录结构
    new_dirs = [
        data_dir / "kline",
        data_dir / "live",
        data_dir / "live" / "agents",
        data_dir / "live" / "analytics",
        data_dir / "live" / "execution",
        data_dir / "live" / "execution" / "trades",
        data_dir / "live" / "execution" / "orders",
        data_dir / "live" / "risk",
        data_dir / "live" / "market_data",
        data_dir / "live" / "oi_history",
        data_dir / "backtest",
        data_dir / "backtest" / "agents",
        data_dir / "backtest" / "results",
        data_dir / "backtest" / "trades",
    ]
    
    for d in new_dirs:
        if not d.exists():
            log(f"创建目录: {d}", "CREATE")
            if not dry_run:
                d.mkdir(parents=True, exist_ok=True)
    
    # 2. 迁移 kline_cache -> kline
    kline_cache = data_dir / "kline_cache"
    kline_new = data_dir / "kline"
    if kline_cache.exists() and kline_cache.is_dir():
        log(f"迁移 kline_cache/ -> kline/", "MOVE")
        if not dry_run:
            for item in kline_cache.iterdir():
                dest = kline_new / item.name
                if dest.exists():
                    log(f"目标已存在，跳过: {dest}", "SKIP")
                else:
                    shutil.move(str(item), str(dest))
            # 删除空目录
            try:
                kline_cache.rmdir()
            except OSError:
                log(f"无法删除非空目录: {kline_cache}", "WARN")
    
    # 3. 迁移实盘数据到 live/
    live_mappings = {
        "agents": "live/agents",
        "analytics": "live/analytics",
        "execution": "live/execution",
        "market_data": "live/market_data",
        "risk": "live/risk",
        "oi_history": "live/oi_history",
        "execution_engine": "live/execution",  # 合并到 execution
    }
    
    for src_name, dest_path in live_mappings.items():
        src = data_dir / src_name
        dest = data_dir / dest_path
        if src.exists() and src.is_dir():
            log(f"迁移 {src_name}/ -> {dest_path}/", "MOVE")
            if not dry_run:
                # 如果目标存在，合并内容
                if dest.exists():
                    for item in src.iterdir():
                        item_dest = dest / item.name
                        if item_dest.exists():
                            log(f"目标已存在，跳过: {item_dest}", "SKIP")
                        else:
                            shutil.move(str(item), str(item_dest))
                    try:
                        src.rmdir()
                    except OSError:
                        log(f"无法删除非空目录: {src}", "WARN")
                else:
                    shutil.move(str(src), str(dest))
    
    # 4. 迁移旧架构数据 (the_* 目录) 到 live/agents/legacy/
    legacy_dirs = ["the_critic", "the_executor", "the_guardian", "the_oracle", "the_prophet", "the_strategist"]
    legacy_dest = data_dir / "live" / "agents" / "legacy"
    
    has_legacy = any((data_dir / d).exists() for d in legacy_dirs)
    if has_legacy:
        log(f"迁移旧架构数据 the_* -> live/agents/legacy/", "MOVE")
        if not dry_run:
            legacy_dest.mkdir(parents=True, exist_ok=True)
            for d in legacy_dirs:
                src = data_dir / d
                if src.exists():
                    dest = legacy_dest / d
                    if dest.exists():
                        log(f"目标已存在，跳过: {dest}", "SKIP")
                    else:
                        shutil.move(str(src), str(dest))
    
    # 5. 迁移回测数据到 backtest/
    backtest_mappings = {
        "backtest_cache": "backtest/cache",
        "backtest": "backtest/results",  # 原 backtest 目录重命名
    }
    
    # 特殊处理: 原 backtest 目录如果存在
    old_backtest = data_dir / "backtest"
    if old_backtest.exists() and old_backtest.is_dir():
        # 检查是否是旧结构 (包含回测结果而非新结构)
        if not (old_backtest / "agents").exists() and not (old_backtest / "results").exists():
            log(f"迁移原 backtest/ 内容到 backtest/results/", "MOVE")
            results_dir = data_dir / "backtest_temp_results"
            if not dry_run:
                results_dir.mkdir(parents=True, exist_ok=True)
                for item in old_backtest.iterdir():
                    if item.name not in ["agents", "results", "trades", "cache"]:
                        shutil.move(str(item), str(results_dir / item.name))
                # 重新创建 backtest 结构并移回
                (old_backtest / "results").mkdir(exist_ok=True)
                for item in results_dir.iterdir():
                    shutil.move(str(item), str(old_backtest / "results" / item.name))
                results_dir.rmdir()
    
    # 迁移 backtest_cache
    backtest_cache = data_dir / "backtest_cache"
    if backtest_cache.exists():
        dest = data_dir / "backtest" / "cache"
        log(f"迁移 backtest_cache/ -> backtest/cache/", "MOVE")
        if not dry_run:
            if dest.exists():
                for item in backtest_cache.iterdir():
                    item_dest = dest / item.name
                    if not item_dest.exists():
                        shutil.move(str(item), str(item_dest))
                try:
                    backtest_cache.rmdir()
                except OSError:
                    pass
            else:
                shutil.move(str(backtest_cache), str(dest))
    
    # 迁移 backtest_analytics.db
    db_file = data_dir / "backtest_analytics.db"
    if db_file.exists():
        dest = data_dir / "backtest" / "backtest_analytics.db"
        log(f"迁移 backtest_analytics.db -> backtest/", "MOVE")
        if not dry_run:
            shutil.move(str(db_file), str(dest))
    
    # 6. 清理空目录
    if not dry_run:
        for item in data_dir.iterdir():
            if item.is_dir() and item.name not in ["kline", "live", "backtest"]:
                try:
                    # 尝试删除空目录
                    item.rmdir()
                    log(f"删除空目录: {item}", "OK")
                except OSError:
                    # 目录非空，保留
                    pass
    
    log("迁移完成!" if not dry_run else "DRY RUN 完成 - 未实际移动文件", "OK")
    
    # 打印新结构
    print("\n📂 新目录结构预览:")
    print("data/")
    for d in ["kline", "live", "backtest"]:
        path = data_dir / d
        if path.exists():
            count = sum(1 for _ in path.rglob("*") if _.is_file())
            print(f"├── {d}/ ({count} files)")


def main():
    parser = argparse.ArgumentParser(description="数据目录迁移脚本")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际移动文件")
    args = parser.parse_args()
    
    print("=" * 50)
    print("📦 LLM-TradeBot 数据目录迁移工具")
    print("=" * 50)
    
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
