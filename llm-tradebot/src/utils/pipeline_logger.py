"""
完整交易流程日志记录器
记录从原始数据获取 -> 数据处理 -> 特征提取 -> 大模型决策 -> 交易执行的全过程
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from src.utils.json_utils import safe_json_dump


class TradingPipelineLogger:
    """交易流程完整日志记录器"""
    
    def __init__(self, log_dir: str = "logs/pipeline"):
        """初始化流程日志记录器"""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 当前会话信息
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_start = datetime.now()
        
        # 流程记录
        self.pipeline_steps = []
        self.current_cycle = 0
        
        print(f"\n{'='*100}")
        print(f"📊 交易流程日志记录器已启动")
        print(f"会话ID: {self.session_id}")
        print(f"日志目录: {self.log_dir}")
        print(f"{'='*100}\n")
    
    def start_new_cycle(self, symbol: str):
        """开始新的交易周期"""
        self.current_cycle += 1
        self.current_cycle_data = {
            "cycle_id": self.current_cycle,
            "symbol": symbol,
            "start_time": datetime.now().isoformat(),
            "steps": []
        }
        
        print(f"\n{'='*100}")
        print(f"🔄 开始新的交易周期 #{self.current_cycle} - {symbol}")
        print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*100}\n")
    
    def log_step(self, 
                 step_name: str, 
                 step_type: str,
                 input_data: Any, 
                 processing: str, 
                 output_data: Any,
                 metadata: Optional[Dict] = None):
        """
        记录单个处理步骤
        
        Args:
            step_name: 步骤名称
            step_type: 步骤类型 (data_fetch|data_process|feature_extract|llm_decision|risk_check|execution)
            input_data: 输入数据
            processing: 处理逻辑说明
            output_data: 输出数据
            metadata: 额外元数据
        """
        timestamp = datetime.now().isoformat()
        
        step_log = {
            "timestamp": timestamp,
            "step_name": step_name,
            "step_type": step_type,
            "input": self._serialize_data(input_data),
            "processing": processing,
            "output": self._serialize_data(output_data),
            "metadata": metadata or {}
        }
        
        self.current_cycle_data["steps"].append(step_log)
        
        # 打印到控制台
        self._print_step(step_name, step_type, input_data, processing, output_data)
    
    def log_raw_data(self, timeframe: str, klines: List[Dict], metadata: Optional[Dict] = None):
        """记录原始K线数据"""
        self.log_step(
            step_name=f"1. 获取{timeframe}原始K线数据",
            step_type="data_fetch",
            input_data={
                "symbol": self.current_cycle_data["symbol"],
                "interval": timeframe,
                "limit": len(klines)
            },
            processing=f"调用 Binance API 获取最近{len(klines)}根{timeframe}K线",
            output_data={
                "data_type": "List[Dict]",
                "count": len(klines),
                "first_kline": klines[0] if klines else None,
                "last_kline": klines[-1] if klines else None,
                "fields": list(klines[0].keys()) if klines else []
            },
            metadata=metadata
        )
    
    def log_data_processing(self, timeframe: str, raw_count: int, df: pd.DataFrame, 
                           anomalies: int, metadata: Optional[Dict] = None):
        """记录数据处理步骤"""
        self.log_step(
            step_name=f"2. 处理{timeframe}数据并计算技术指标",
            step_type="data_process",
            input_data={
                "raw_kline_count": raw_count,
                "timeframe": timeframe
            },
            processing=f"""
数据处理流程:
1. 将K线列表转为DataFrame
2. 异常值检测 (Z-score方法)
3. 异常值清洗 (检测到{anomalies}个异常)
4. 计算技术指标:
   - 移动平均: SMA(20, 50), EMA(12, 26)
   - 动量指标: RSI(14), MACD(12, 26, 9)
   - 波动指标: Bollinger Bands(20, 2), ATR(14)
   - 成交量指标: Volume SMA(20), Volume Ratio
5. 数据验证与快照生成
            """.strip(),
            output_data={
                "dataframe": df,
                "shape": df.shape,
                "columns": list(df.columns),
                "anomaly_count": anomalies
            },
            metadata=metadata
        )
    
    def log_feature_extraction(self, timeframe: str, features: Dict, metadata: Optional[Dict] = None):
        """记录特征提取步骤"""
        self.log_step(
            step_name=f"3. 提取{timeframe}关键特征",
            step_type="feature_extract",
            input_data={
                "timeframe": timeframe,
                "data_source": "processed_dataframe"
            },
            processing=f"""
从{timeframe} DataFrame最后一行提取关键特征:
- 价格数据: open, high, low, close
- 成交量: volume, volume_ratio
- 趋势指标: SMA20, SMA50, EMA12, EMA26
- 动量指标: RSI, MACD, MACD_signal
- 波动指标: Bollinger Bands (upper, middle, lower), ATR
- 计算指标: trend, momentum, volatility
            """.strip(),
            output_data=features,
            metadata=metadata
        )
    
    def log_multi_timeframe_context(self, context: Dict, metadata: Optional[Dict] = None):
        """记录多周期上下文构建"""
        self.log_step(
            step_name="4. 构建多周期市场上下文",
            step_type="feature_extract",
            input_data={
                "timeframes": list(context.keys()),
                "features_per_tf": [len(context[tf]) for tf in context.keys()]
            },
            processing="""
合并多个时间周期的特征:
1. 整合各周期的价格、指标、趋势
2. 计算周期间的一致性
3. 判断多周期趋势方向
4. 评估市场状态（trending/ranging/volatile）
            """.strip(),
            output_data=context,
            metadata=metadata
        )
    
    def log_llm_input(self, prompt_text: str, context_data: Dict, metadata: Optional[Dict] = None):
        """记录大模型输入"""
        self.log_step(
            step_name="5. 准备大模型输入数据",
            step_type="llm_decision",
            input_data={
                "market_context": context_data,
                "prompt_length": len(prompt_text),
                "timeframes_analyzed": list(context_data.keys()) if isinstance(context_data, dict) else None
            },
            processing="""
构建大模型输入:
1. 将市场数据格式化为文本
2. 添加系统提示词（交易规则、风险管理）
3. 添加用户提示词（当前市场状态）
4. 设置响应格式为JSON
            """.strip(),
            output_data={
                "prompt_preview": prompt_text[:500] + "..." if len(prompt_text) > 500 else prompt_text,
                "full_prompt_length": len(prompt_text)
            },
            metadata=metadata
        )
    
    def log_llm_output(self, decision: Dict, raw_response: str, metadata: Optional[Dict] = None):
        """记录大模型输出"""
        self.log_step(
            step_name="6. 大模型决策结果",
            step_type="llm_decision",
            input_data={
                "model": decision.get('model', 'unknown'),
                "response_length": len(raw_response)
            },
            processing="""
解析大模型响应:
1. 接收JSON格式的决策结果
2. 验证决策格式完整性
3. 提取关键决策字段:
   - action (交易动作)
   - confidence (置信度)
   - position_size_pct (仓位比例)
   - leverage (杠杆)
   - stop_loss_pct / take_profit_pct (止盈止损)
   - reasoning (决策理由)
   - analysis (详细分析)
            """.strip(),
            output_data={
                "decision": decision,
                "action": decision.get('action'),
                "confidence": decision.get('confidence'),
                "reasoning": decision.get('reasoning', '')[:200]  # 截取前200字符
            },
            metadata=metadata
        )
    
    def log_risk_check(self, decision: Dict, risk_result: Dict, metadata: Optional[Dict] = None):
        """记录风险检查"""
        self.log_step(
            step_name="7. 风险管理验证",
            step_type="risk_check",
            input_data={
                "original_decision": decision.get('action'),
                "position_size_pct": decision.get('position_size_pct'),
                "leverage": decision.get('leverage')
            },
            processing="""
风险管理检查:
1. 验证仓位大小是否超出限制
2. 验证杠杆倍数是否合规
3. 计算实际风险敞口
4. 检查账户余额是否足够
5. 验证止损止盈设置是否合理
6. 检查是否违反风控规则
            """.strip(),
            output_data=risk_result,
            metadata=metadata
        )
    
    def log_execution(self, action: str, result: Dict, metadata: Optional[Dict] = None):
        """记录交易执行"""
        self.log_step(
            step_name="8. 交易执行",
            step_type="execution",
            input_data={
                "action": action,
                "timestamp": datetime.now().isoformat()
            },
            processing=f"""
执行交易操作: {action}
1. 调用币安API下单
2. 设置止损止盈订单
3. 记录交易日志
4. 更新持仓状态
            """.strip(),
            output_data=result,
            metadata=metadata
        )
    
    def end_cycle(self, final_result: Optional[Dict] = None):
        """结束当前交易周期"""
        self.current_cycle_data["end_time"] = datetime.now().isoformat()
        self.current_cycle_data["duration_seconds"] = (
            datetime.fromisoformat(self.current_cycle_data["end_time"]) - 
            datetime.fromisoformat(self.current_cycle_data["start_time"])
        ).total_seconds()
        self.current_cycle_data["final_result"] = final_result
        
        # 保存到流程记录
        self.pipeline_steps.append(self.current_cycle_data)
        
        # 保存单个周期日志
        self._save_cycle_log(self.current_cycle_data)
        
        print(f"\n{'='*100}")
        print(f"✅ 交易周期 #{self.current_cycle} 完成")
        print(f"⏱️  耗时: {self.current_cycle_data['duration_seconds']:.2f}秒")
        print(f"📊 总步骤数: {len(self.current_cycle_data['steps'])}")
        print(f"{'='*100}\n")
    
    def _serialize_data(self, data: Any) -> Any:
        """序列化数据以便JSON保存"""
        import numpy as np
        
        # 处理pandas.Timestamp
        if isinstance(data, pd.Timestamp):
            return str(data)
        
        # 处理numpy类型（必须在其他检查之前）
        if hasattr(data, 'item'):
            return data.item()
        
        # 处理DataFrame
        if isinstance(data, pd.DataFrame):
            df_copy = data.copy()
            df_copy.index = df_copy.index.astype(str)
            
            # 转换所有numpy类型为Python原生类型
            for col in df_copy.columns:
                if df_copy[col].dtype == 'object':
                    continue
                df_copy[col] = df_copy[col].apply(lambda x: x.item() if hasattr(x, 'item') else x)
            
            df_dict = df_copy.reset_index().to_dict('records')
            return {
                "type": "DataFrame",
                "shape": list(data.shape),
                "columns": list(data.columns),
                "head_3": df_dict[:3] if len(df_dict) > 0 else [],
                "tail_3": df_dict[-3:] if len(df_dict) > 0 else [],
                "summary": {
                    "row_count": len(data),
                    "column_count": len(data.columns),
                    "latest_values": self._get_latest_row_values(data)
                }
            }
        
        # 处理字典
        elif isinstance(data, dict):
            return {str(k): self._serialize_data(v) for k, v in data.items()}
        
        # 处理列表
        elif isinstance(data, list):
            if len(data) <= 5:
                return [self._serialize_data(item) for item in data]
            else:
                return {
                    "type": "list",
                    "length": len(data),
                    "first_3": [self._serialize_data(item) for item in data[:3]],
                    "last_3": [self._serialize_data(item) for item in data[-3:]]
                }
        
        # 其他类型
        else:
            return data
    
    def _get_latest_row_values(self, df: pd.DataFrame) -> Dict:
        """获取DataFrame最后一行的关键值"""
        if df.empty:
            return {}
        
        latest = df.iloc[-1]
        result = {}
        
        # 只保留数值列
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                val = latest[col]
                if hasattr(val, 'item'):
                    result[col] = val.item()
                else:
                    result[col] = val
        
        return result
    
    def _print_step(self, step_name: str, step_type: str, input_data: Any, 
                    processing: str, output_data: Any):
        """打印步骤信息到控制台"""
        
        # 步骤类型图标
        type_icons = {
            "data_fetch": "🔽",
            "data_process": "⚙️",
            "feature_extract": "📊",
            "llm_decision": "🤖",
            "risk_check": "🛡️",
            "execution": "⚡"
        }
        
        icon = type_icons.get(step_type, "📌")
        
        print(f"\n{'='*100}")
        print(f"{icon} 步骤: {step_name}")
        print(f"⏰ 时间: {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*100}")
        
        print(f"\n📥 输入数据:")
        self._print_data_summary(input_data, indent=3)
        
        print(f"\n⚙️  处理逻辑:")
        for line in processing.split('\n'):
            print(f"   {line}")
        
        print(f"\n📤 输出数据:")
        self._print_data_summary(output_data, indent=3)
        
        print(f"\n{'='*100}")
    
    def _print_data_summary(self, data: Any, indent: int = 3):
        """打印数据摘要"""
        prefix = " " * indent
        
        if isinstance(data, pd.DataFrame):
            print(f"{prefix}类型: DataFrame")
            print(f"{prefix}形状: {data.shape}")
            print(f"{prefix}列数: {len(data.columns)}")
            
        elif isinstance(data, dict):
            print(f"{prefix}类型: Dict")
            print(f"{prefix}键数量: {len(data)}")
            for key, value in list(data.items())[:10]:  # 只显示前10个
                if isinstance(value, (dict, list)):
                    print(f"{prefix}{key}: {type(value).__name__} (长度={len(value)})")
                elif isinstance(value, (int, float)):
                    if isinstance(value, float):
                        print(f"{prefix}{key}: {value:.6f}")
                    else:
                        print(f"{prefix}{key}: {value}")
                else:
                    val_str = str(value)
                    if len(val_str) > 100:
                        val_str = val_str[:100] + "..."
                    print(f"{prefix}{key}: {val_str}")
        
        elif isinstance(data, list):
            print(f"{prefix}类型: List")
            print(f"{prefix}长度: {len(data)}")
        
        else:
            print(f"{prefix}{data}")
    
    def _save_cycle_log(self, cycle_data: Dict):
        """保存单个周期的日志"""
        cycle_file = self.log_dir / f"cycle_{self.session_id}_{cycle_data['cycle_id']:03d}.json"
        
        with open(cycle_file, 'w', encoding='utf-8') as f:
            safe_json_dump(cycle_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 周期日志已保存: {cycle_file}")
    
    def save_session_summary(self):
        """保存会话总结"""
        summary = {
            "session_id": self.session_id,
            "start_time": self.session_start.isoformat(),
            "end_time": datetime.now().isoformat(),
            "total_cycles": len(self.pipeline_steps),
            "total_duration_seconds": (datetime.now() - self.session_start).total_seconds(),
            "cycles": self.pipeline_steps
        }
        
        summary_file = self.log_dir / f"session_{self.session_id}_summary.json"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            safe_json_dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*100}")
        print(f"💾 会话总结已保存: {summary_file}")
        print(f"   总周期数: {summary['total_cycles']}")
        print(f"   总耗时: {summary['total_duration_seconds']:.2f}秒")
        print(f"{'='*100}\n")
        
        return str(summary_file)
