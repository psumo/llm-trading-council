"""
OI (Open Interest) 历史追踪器

存储历史 OI 数据，计算 24h 变化率
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from collections import defaultdict
from src.utils.logger import log


class OITracker:
    """
    OI 历史追踪器
    
    特性：
    1. 内存缓存 + 文件持久化
    2. 自动清理 48 小时以上的数据
    3. 计算 24h / 1h 变化率
    """
    
    def __init__(self, data_dir: str = "data/live/oi_history"):
        self.data_dir = data_dir
        self.history: Dict[str, List[Dict]] = defaultdict(list)  # {symbol: [{ts, oi}, ...]}
        self.max_history_hours = 48  # 保留最近 48 小时数据
        
        # 确保目录存在
        os.makedirs(data_dir, exist_ok=True)
        
        # 加载历史数据
        self._load_history()
        
        log.info(f"📊 OI Tracker initialized | Data dir: {data_dir}")
    
    def _get_file_path(self, symbol: str) -> str:
        """获取币种对应的历史文件路径"""
        return os.path.join(self.data_dir, f"{symbol}_oi.json")
    
    def _load_history(self):
        """从文件加载历史数据"""
        try:
            for filename in os.listdir(self.data_dir):
                if filename.endswith("_oi.json"):
                    symbol = filename.replace("_oi.json", "")
                    filepath = os.path.join(self.data_dir, filename)
                    
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        self.history[symbol] = data
                        
            total_records = sum(len(v) for v in self.history.values())
            if total_records > 0:
                log.info(f"📂 OI history loaded: {len(self.history)} symbols, {total_records} records")
        except Exception as e:
            log.warning(f"Failed to load OI history: {e}")
    
    def _save_history(self, symbol: str):
        """保存单个币种的历史数据"""
        try:
            filepath = self._get_file_path(symbol)
            with open(filepath, 'w') as f:
                json.dump(self.history[symbol], f)
        except Exception as e:
            log.error(f"Failed to save OI history ({symbol}): {e}")
    
    def _cleanup_old_data(self, symbol: str):
        """清理超过 48 小时的旧数据"""
        cutoff = datetime.now() - timedelta(hours=self.max_history_hours)
        cutoff_ts = cutoff.timestamp() * 1000
        
        original_count = len(self.history[symbol])
        self.history[symbol] = [
            record for record in self.history[symbol]
            if record.get('ts', 0) > cutoff_ts
        ]
        
        removed = original_count - len(self.history[symbol])
        if removed > 0:
            log.debug(f"清理 {symbol} 旧 OI 数据: {removed} 条")
    
    def record(self, symbol: str, oi_value: float, timestamp: Optional[int] = None):
        """
        记录一条 OI 数据
        
        Args:
            symbol: 交易对
            oi_value: OI 值
            timestamp: 时间戳（毫秒），默认当前时间
        """
        if timestamp is None:
            timestamp = int(datetime.now().timestamp() * 1000)
        
        # 避免短时间内重复记录（至少 5 分钟间隔）
        if self.history[symbol]:
            last_ts = self.history[symbol][-1].get('ts', 0)
            if timestamp - last_ts < 300000:  # 5 分钟
                return
        
        self.history[symbol].append({
            'ts': timestamp,
            'oi': oi_value
        })
        
        # 定期清理和保存
        self._cleanup_old_data(symbol)
        self._save_history(symbol)
    
    def get_change_pct(self, symbol: str, hours: int = 24) -> float:
        """
        计算指定时间段的 OI 变化百分比
        
        Args:
            symbol: 交易对
            hours: 回溯时间（小时）
            
        Returns:
            变化百分比（例如 5.2 表示上涨 5.2%）
        """
        if symbol not in self.history or len(self.history[symbol]) < 2:
            return 0.0
        
        now_ts = datetime.now().timestamp() * 1000
        target_ts = now_ts - (hours * 3600 * 1000)
        
        # 获取当前 OI
        current_oi = self.history[symbol][-1]['oi']
        
        # 找到最接近 target_ts 的历史记录
        past_oi = None
        for record in self.history[symbol]:
            if record['ts'] <= target_ts:
                past_oi = record['oi']
            else:
                break
        
        # 如果没有足够历史数据，使用最早的记录
        if past_oi is None and self.history[symbol]:
            past_oi = self.history[symbol][0]['oi']
        
        if past_oi is None or past_oi == 0:
            return 0.0
        
        change_pct = ((current_oi - past_oi) / past_oi) * 100
        return round(change_pct, 2)
    
    def get_current_oi(self, symbol: str) -> float:
        """获取当前 OI 值"""
        if symbol in self.history and self.history[symbol]:
            return self.history[symbol][-1]['oi']
        return 0.0
    
    def get_stats(self, symbol: str) -> Dict:
        """获取 OI 统计信息"""
        if symbol not in self.history or not self.history[symbol]:
            return {
                'current': 0,
                'change_1h': 0.0,
                'change_24h': 0.0,
                'records': 0
            }
        
        return {
            'current': self.get_current_oi(symbol),
            'change_1h': self.get_change_pct(symbol, hours=1),
            'change_24h': self.get_change_pct(symbol, hours=24),
            'records': len(self.history[symbol])
        }


# 全局单例
oi_tracker = OITracker()
