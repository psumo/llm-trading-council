"""
交易日志记录器 - 记录每次开仓、平仓的详细数据
"""
import json
import os
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path
from src.utils.json_utils import safe_json_dump, safe_json_dumps


class TradeLogger:
    """交易日志记录器"""
    
    def __init__(self, log_dir: str = "data/live/execution/tracking"):
        """
        初始化交易日志记录器
        
        Args:
            log_dir: 日志目录
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        (self.log_dir / "daily").mkdir(exist_ok=True)
        (self.log_dir / "positions").mkdir(exist_ok=True)
        (self.log_dir / "summary").mkdir(exist_ok=True)
    
    def log_open_position(
        self,
        symbol: str,
        side: str,  # LONG or SHORT
        decision: Dict,
        execution_result: Dict,
        market_state: Dict,
        account_info: Dict
    ) -> str:
        """
        记录开仓信息
        
        Args:
            symbol: 交易对
            side: 方向 (LONG/SHORT)
            decision: 决策信息
            execution_result: 执行结果
            market_state: 市场状态
            account_info: 账户信息
            
        Returns:
            日志文件路径
        """
        timestamp = datetime.now()
        trade_id = f"{symbol}_{side}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        # 构建完整的交易记录
        trade_record = {
            # 基本信息
            "trade_id": trade_id,
            "timestamp": timestamp.isoformat(),
            "date": timestamp.strftime('%Y-%m-%d'),
            "time": timestamp.strftime('%H:%M:%S'),
            
            # 交易信息
            "symbol": symbol,
            "side": side,
            "action": "OPEN",
            
            # 决策信息
            "decision": {
                "action": decision.get('action'),
                "position_size_pct": decision.get('position_size_pct'),
                "leverage": decision.get('leverage'),
                "stop_loss_pct": decision.get('stop_loss_pct'),
                "take_profit_pct": decision.get('take_profit_pct'),
            },
            
            # 执行结果
            "execution": {
                "success": execution_result.get('success'),
                "entry_price": execution_result.get('entry_price'),
                "quantity": execution_result.get('quantity'),
                "stop_loss": execution_result.get('stop_loss'),
                "take_profit": execution_result.get('take_profit'),
                "order_id": execution_result.get('order_id'),
                "orders": execution_result.get('orders', [])
            },
            
            # 市场状态（精简版）
            "market_state": self._extract_market_summary(market_state),
            
            # 账户信息
            "account": {
                "balance_before": account_info.get('available_balance'),
                "position_value": execution_result.get('entry_price', 0) * execution_result.get('quantity', 0),
                "margin_used": (execution_result.get('entry_price', 0) * execution_result.get('quantity', 0)) / decision.get('leverage', 1),
            },
            
            # 风险评估
            "risk": {
                "max_loss_usd": self._calculate_max_loss(execution_result, decision),
                "max_loss_pct": decision.get('stop_loss_pct'),
                "potential_profit_usd": self._calculate_potential_profit(execution_result, decision),
                "potential_profit_pct": decision.get('take_profit_pct'),
                "risk_reward_ratio": decision.get('take_profit_pct', 0) / max(decision.get('stop_loss_pct', 1), 0.1),
            },
            
            # 状态
            "status": "OPEN",
            "close_info": None
        }
        
        # 保存到单独的持仓文件
        position_file = self.log_dir / "positions" / f"{trade_id}.json"
        with open(position_file, 'w', encoding='utf-8') as f:
            safe_json_dump(trade_record, f, indent=2, ensure_ascii=False)
        
        # 追加到当日交易日志
        daily_file = self.log_dir / "daily" / f"trades_{timestamp.strftime('%Y%m%d')}.jsonl"
        with open(daily_file, 'a', encoding='utf-8') as f:
            f.write(safe_json_dumps(trade_record, ensure_ascii=False) + '\n')
        
        print(f"✅ 交易日志已保存: {position_file}")
        
        return str(position_file)
    
    def log_close_position(
        self,
        trade_id: str,
        close_price: float,
        close_reason: str,  # STOP_LOSS, TAKE_PROFIT, MANUAL
        pnl: float,
        pnl_pct: float,
        account_balance_after: float
    ) -> str:
        """
        记录平仓信息
        
        Args:
            trade_id: 交易ID
            close_price: 平仓价格
            close_reason: 平仓原因
            pnl: 盈亏金额
            pnl_pct: 盈亏百分比
            account_balance_after: 平仓后账户余额
            
        Returns:
            日志文件路径
        """
        timestamp = datetime.now()
        
        # 读取原始持仓记录
        position_file = self.log_dir / "positions" / f"{trade_id}.json"
        
        if not position_file.exists():
            print(f"⚠️  警告: 未找到持仓记录 {trade_id}")
            return ""
        
        with open(position_file, 'r', encoding='utf-8') as f:
            trade_record = json.load(f)
        
        # 更新平仓信息
        trade_record["status"] = "CLOSED"
        trade_record["close_info"] = {
            "close_timestamp": timestamp.isoformat(),
            "close_date": timestamp.strftime('%Y-%m-%d'),
            "close_time": timestamp.strftime('%H:%M:%S'),
            "close_price": close_price,
            "close_reason": close_reason,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "account_balance_after": account_balance_after,
            "holding_duration_seconds": (timestamp - datetime.fromisoformat(trade_record["timestamp"])).total_seconds()
        }
        
        # 更新持仓文件
        with open(position_file, 'w', encoding='utf-8') as f:
            safe_json_dump(trade_record, f, indent=2, ensure_ascii=False)
        
        # 追加到当日交易日志
        daily_file = self.log_dir / "daily" / f"trades_{timestamp.strftime('%Y%m%d')}.jsonl"
        with open(daily_file, 'a', encoding='utf-8') as f:
            f.write(safe_json_dumps(trade_record, ensure_ascii=False) + '\n')
        
        # 更新交易汇总
        self._update_summary(trade_record)
        
        print(f"✅ 平仓日志已保存: {position_file}")
        print(f"   盈亏: ${pnl:+.2f} ({pnl_pct:+.2f}%)")
        
        return str(position_file)
    
    def _extract_market_summary(self, market_state: Dict) -> Dict:
        """提取市场状态摘要"""
        timeframes = market_state.get('timeframes', {})
        
        summary = {
            "current_price": market_state.get('current_price'),
            "timeframes": {}
        }
        
        for tf, data in timeframes.items():
            summary["timeframes"][tf] = {
                "price": data.get('price'),
                "rsi": data.get('rsi'),
                "macd": data.get('macd'),
                "trend": data.get('trend')
            }
        
        return summary
    
    def _calculate_max_loss(self, execution_result: Dict, decision: Dict) -> float:
        """计算最大损失"""
        entry_price = execution_result.get('entry_price', 0)
        quantity = execution_result.get('quantity', 0)
        leverage = decision.get('leverage', 1)
        stop_loss_pct = decision.get('stop_loss_pct', 0)
        
        position_value = entry_price * quantity
        max_loss = position_value * leverage * (stop_loss_pct / 100)
        
        return max_loss
    
    def _calculate_potential_profit(self, execution_result: Dict, decision: Dict) -> float:
        """计算潜在收益"""
        entry_price = execution_result.get('entry_price', 0)
        quantity = execution_result.get('quantity', 0)
        leverage = decision.get('leverage', 1)
        take_profit_pct = decision.get('take_profit_pct', 0)
        
        position_value = entry_price * quantity
        potential_profit = position_value * leverage * (take_profit_pct / 100)
        
        return potential_profit
    
    def _update_summary(self, trade_record: Dict):
        """更新交易汇总统计"""
        summary_file = self.log_dir / "summary" / "trading_summary.json"
        
        # 读取现有汇总
        if summary_file.exists():
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary = json.load(f)
        else:
            summary = {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0,
                "total_pnl_pct": 0,
                "best_trade": None,
                "worst_trade": None,
                "last_updated": None
            }
        
        # 只统计已平仓的交易
        if trade_record["status"] == "CLOSED" and trade_record["close_info"]:
            close_info = trade_record["close_info"]
            pnl = close_info["pnl"]
            
            summary["total_trades"] += 1
            summary["total_pnl"] += pnl
            
            if pnl > 0:
                summary["winning_trades"] += 1
            elif pnl < 0:
                summary["losing_trades"] += 1
            
            # 更新最佳/最差交易
            if summary["best_trade"] is None or pnl > summary["best_trade"]["pnl"]:
                summary["best_trade"] = {
                    "trade_id": trade_record["trade_id"],
                    "pnl": pnl,
                    "pnl_pct": close_info["pnl_pct"],
                    "timestamp": close_info["close_timestamp"]
                }
            
            if summary["worst_trade"] is None or pnl < summary["worst_trade"]["pnl"]:
                summary["worst_trade"] = {
                    "trade_id": trade_record["trade_id"],
                    "pnl": pnl,
                    "pnl_pct": close_info["pnl_pct"],
                    "timestamp": close_info["close_timestamp"]
                }
            
            # 计算胜率
            summary["win_rate"] = (summary["winning_trades"] / summary["total_trades"]) * 100 if summary["total_trades"] > 0 else 0
            
            # 计算平均盈亏
            summary["avg_pnl"] = summary["total_pnl"] / summary["total_trades"] if summary["total_trades"] > 0 else 0
            
            summary["last_updated"] = datetime.now().isoformat()
        
        # 保存更新后的汇总
        with open(summary_file, 'w', encoding='utf-8') as f:
            safe_json_dump(summary, f, indent=2, ensure_ascii=False)
    
    def get_open_positions(self) -> list:
        """获取所有未平仓的持仓"""
        positions_dir = self.log_dir / "positions"
        open_positions = []
        
        for position_file in positions_dir.glob("*.json"):
            with open(position_file, 'r', encoding='utf-8') as f:
                trade_record = json.load(f)
                if trade_record["status"] == "OPEN":
                    open_positions.append(trade_record)
        
        return open_positions
    
    def get_daily_summary(self, date: Optional[str] = None) -> Dict:
        """
        获取当日交易汇总
        
        Args:
            date: 日期 (YYYYMMDD)，默认今天
            
        Returns:
            当日交易统计
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        daily_file = self.log_dir / "daily" / f"trades_{date}.jsonl"
        
        if not daily_file.exists():
            return {
                "date": date,
                "total_trades": 0,
                "trades": []
            }
        
        trades = []
        with open(daily_file, 'r', encoding='utf-8') as f:
            for line in f:
                trades.append(json.loads(line))
        
        return {
            "date": date,
            "total_trades": len(trades),
            "trades": trades
        }
    
    def export_to_csv(self, output_file: str):
        """
        导出交易记录为CSV格式，方便Excel分析
        
        Args:
            output_file: 输出文件路径
        """
        import csv
        
        positions_dir = self.log_dir / "positions"
        trades = []
        
        for position_file in positions_dir.glob("*.json"):
            with open(position_file, 'r', encoding='utf-8') as f:
                trade = json.load(f)
                trades.append(trade)
        
        # 按时间排序
        trades.sort(key=lambda x: x["timestamp"])
        
        # 写入CSV
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            
            # 表头
            writer.writerow([
                '交易ID', '日期', '时间', '交易对', '方向', '状态',
                '入场价', '数量', '杠杆', '止损价', '止盈价',
                '平仓价', '平仓原因', '盈亏', '盈亏%',
                '持仓时长(秒)', '最大损失', '潜在收益', '风险收益比'
            ])
            
            # 数据行
            for trade in trades:
                close_info = trade.get("close_info") or {}
                
                writer.writerow([
                    trade["trade_id"],
                    trade["date"],
                    trade["time"],
                    trade["symbol"],
                    trade["side"],
                    trade["status"],
                    trade["execution"]["entry_price"],
                    trade["execution"]["quantity"],
                    trade["decision"]["leverage"],
                    trade["execution"]["stop_loss"],
                    trade["execution"]["take_profit"],
                    close_info.get("close_price", ""),
                    close_info.get("close_reason", ""),
                    close_info.get("pnl", ""),
                    close_info.get("pnl_pct", ""),
                    close_info.get("holding_duration_seconds", ""),
                    trade["risk"]["max_loss_usd"],
                    trade["risk"]["potential_profit_usd"],
                    trade["risk"]["risk_reward_ratio"]
                ])
        
        print(f"✅ 交易记录已导出到: {output_file}")


# 全局实例
trade_logger = TradeLogger()
