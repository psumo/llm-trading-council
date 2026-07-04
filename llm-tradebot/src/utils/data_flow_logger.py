"""
数据流转详细日志记录器
记录从原始数据到最终决策的每一步处理过程
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd


class DataFlowLogger:
    """数据流转日志记录器"""
    
    def __init__(self, log_dir: str = "logs/data_flow"):
        """初始化日志记录器"""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 当前会话的日志
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_log = []
        
        print(f"\n{'='*100}")
        print(f"📊 数据流转详细日志记录器已启动")
        print(f"会话ID: {self.session_id}")
        print(f"日志目录: {self.log_dir}")
        print(f"{'='*100}\n")
    
    def log_step(self, step_name: str, input_data: Any, processing: str, output_data: Any):
        """
        记录单个处理步骤
        
        Args:
            step_name: 步骤名称
            input_data: 输入数据
            processing: 处理逻辑说明
            output_data: 输出数据
        """
        timestamp = datetime.now().isoformat()
        
        step_log = {
            "timestamp": timestamp,
            "step": step_name,
            "input": self._serialize_data(input_data),
            "processing": processing,
            "output": self._serialize_data(output_data)
        }
        
        self.session_log.append(step_log)
        
        # 打印到控制台
        print(f"\n{'='*100}")
        print(f"🔄 步骤: {step_name}")
        print(f"⏰ 时间: {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*100}")
        
        print(f"\n📥 输入数据:")
        self._print_data(input_data)
        
        print(f"\n⚙️  处理逻辑:")
        print(f"   {processing}")
        
        print(f"\n📤 输出数据:")
        self._print_data(output_data)
        
        print(f"\n{'='*100}")
    
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
            # 转换DataFrame为可序列化格式
            # 先将索引转为字符串，然后转换所有值
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
                "tail_3": df_dict[-3:] if len(df_dict) > 0 else []
            }
        
        # 处理字典
        elif isinstance(data, dict):
            return {str(k): self._serialize_data(v) for k, v in data.items()}
        
        # 处理列表
        elif isinstance(data, list) and len(data) > 0:
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
    
    def _print_data(self, data: Any, indent: int = 3):
        """打印数据到控制台"""
        prefix = " " * indent
        
        if isinstance(data, pd.DataFrame):
            print(f"{prefix}类型: DataFrame")
            print(f"{prefix}形状: {data.shape} (行数={data.shape[0]}, 列数={data.shape[1]})")
            print(f"{prefix}列名: {list(data.columns)}")
            
            if not data.empty:
                print(f"\n{prefix}前3行:")
                print(data.head(3).to_string(index=False).replace('\n', f'\n{prefix}'))
                
                print(f"\n{prefix}后3行:")
                print(data.tail(3).to_string(index=False).replace('\n', f'\n{prefix}'))
                
                # 数值列统计
                numeric_cols = data.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    print(f"\n{prefix}数值列统计:")
                    latest = data.iloc[-1]
                    for col in numeric_cols:
                        if col in latest:
                            print(f"{prefix}  - {col}: {latest[col]:.6f}")
        
        elif isinstance(data, dict):
            print(f"{prefix}类型: Dict")
            print(f"{prefix}键数量: {len(data)}")
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    print(f"{prefix}{key}: {type(value).__name__} (长度={len(value)})")
                elif isinstance(value, (int, float)):
                    print(f"{prefix}{key}: {value:.6f}" if isinstance(value, float) else f"{prefix}{key}: {value}")
                else:
                    print(f"{prefix}{key}: {value}")
        
        elif isinstance(data, list):
            print(f"{prefix}类型: List")
            print(f"{prefix}长度: {len(data)}")
            if len(data) <= 5:
                for i, item in enumerate(data):
                    print(f"{prefix}[{i}]: {item}")
            else:
                print(f"{prefix}前3项: {data[:3]}")
                print(f"{prefix}后3项: {data[-3:]}")
        
        else:
            print(f"{prefix}{data}")
    
    def save_session_log(self):
        """保存当前会话的完整日志"""
        log_file = self.log_dir / f"session_{self.session_id}.json"
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump({
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "total_steps": len(self.session_log),
                "steps": self.session_log
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*100}")
        print(f"💾 数据流转日志已保存: {log_file}")
        print(f"   总步骤数: {len(self.session_log)}")
        print(f"{'='*100}\n")
        
        return str(log_file)
    
    def create_summary(self):
        """创建数据流转摘要"""
        summary = {
            "session_id": self.session_id,
            "total_steps": len(self.session_log),
            "steps_summary": []
        }
        
        for step in self.session_log:
            summary["steps_summary"].append({
                "step": step["step"],
                "timestamp": step["timestamp"],
                "processing": step["processing"]
            })
        
        print(f"\n{'='*100}")
        print(f"📋 数据流转摘要")
        print(f"{'='*100}")
        print(f"会话ID: {self.session_id}")
        print(f"总步骤数: {len(self.session_log)}")
        print(f"\n处理流程:")
        for i, step in enumerate(summary["steps_summary"], 1):
            print(f"  {i}. {step['step']}")
            print(f"     处理: {step['processing']}")
        print(f"{'='*100}\n")
        
        return summary


# 全局实例
data_flow_logger = DataFlowLogger()
