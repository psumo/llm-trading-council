"""
简化日志工具 - 只显示关键交易信息
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

class SimpleLogger:
    """简化的日志记录器 - 只输出关键信息"""
    
    def __init__(self):
        self.logger = logging.getLogger('llm_tradebot')
        self.logger.setLevel(logging.INFO)
        
        # 静默的模式列表
        self.muted_patterns = [
            "保存 JSON", "保存 CSV", "保存 Parquet",
            "步骤1数据已保存", "步骤2数据已保存", "步骤3数据已保存",
            "特征工程完成", "开始特征工程",
            "Warm-up标记", "开始验证", "数据验证通过",
            "快照生成", "处理K线"
        ]
        
    def should_mute(self, message: str) -> bool:
        """检查消息是否应该被静音"""
        return any(pattern in message for pattern in self.muted_patterns)
    
    def info(self, message: str, force: bool = False):
        """输出INFO级别日志（关键信息会强制显示）"""
        if force or not self.should_mute(message):
            print(f"{datetime.now().strftime('%H:%M:%S')} | {message}")
    
    def warning(self, message: str):
        """输出WARNING级别日志"""
        print(f"⚠️  {datetime.now().strftime('%H:%M:%S')} | {message}")
    
    def error(self, message: str):
        """输出ERROR级别日志"""
        print(f"❌ {datetime.now().strftime('%H:%M:%S')} | {message}")
    
    def success(self, message: str):
        """输出成功消息"""
        print(f"✅ {datetime.now().strftime('%H:%M:%S')} | {message}")
    
    def section(self, title: str):
        """输出章节标题"""
        print(f"\n{'='*80}")
        print(f"🔄 {title} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")
    
    def step(self, step_name: str, details: Optional[dict] = None):
        """输出步骤信息（简化版）"""
        print(f"\n📊 {step_name}")
        if details:
            for key, value in details.items():
                print(f"   {key}: {value}")

# 全局实例
simple_log = SimpleLogger()
