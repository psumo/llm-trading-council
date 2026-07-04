"""
数据保存工具模块 - 按日期组织数据文件 (Multi-Agent Refactor)
"""
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional
from src.utils.logger import log


class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON Encoder to handle datetime and numpy types"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(obj, (np.integer, np.int32, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        return super().default(obj)


class DataSaver:
    """数据保存工具类 - 按Agent和业务领域自动组织文件
    
    新目录结构 (Multi-Agent Framework with Live/Backtest Separation):
    data/
      kline/               (共享 K 线缓存，实盘和回测都优先读取)
      live/                (实盘数据)
        agents/            (所有LLM Agent的日志)
          trend_agent/
          setup_agent/
          trigger_agent/
          bull_bear/
          strategy_engine/
          reflection/
        market_data/       (原始市场数据)
        analytics/         (量化分析)
        execution/         (交易执行)
        risk/              (风控审计)
      backtest/            (回测数据)
        agents/
        analytics/
        results/
        trades/
    """
    
    def __init__(self, base_dir: str = 'data', mode: str = 'live'):
        """
        初始化数据保存工具
        
        Args:
            base_dir: 数据根目录，默认为 'data'
            mode: 运行模式 - 'live' (实盘) 或 'backtest' (回测)
        """
        self.base_dir = base_dir
        self.mode = mode
        
        # 模式目录: data/live 或 data/backtest
        self.mode_dir = os.path.join(base_dir, mode)
        
        # 共享 K 线目录 (实盘和回测共用)
        self.kline_dir = os.path.join(base_dir, 'kline')
        
        # 定义业务目录映射 (Agent-Based Structure)
        self.dirs = {
            # Agent层 - 所有LLM Agent日志
            'trend_agent': os.path.join(self.mode_dir, 'agents', 'trend_agent'),
            'setup_agent': os.path.join(self.mode_dir, 'agents', 'setup_agent'),
            'trigger_agent': os.path.join(self.mode_dir, 'agents', 'trigger_agent'),
            'bull_bear': os.path.join(self.mode_dir, 'agents', 'bull_bear'),
            'strategy_engine': os.path.join(self.mode_dir, 'agents', 'strategy_engine'),
            'reflection': os.path.join(self.mode_dir, 'agents', 'reflection'),
            
            # 数据层
            'market_data': os.path.join(self.mode_dir, 'market_data'),
            'kline': self.kline_dir,  # 共享 K 线目录
            
            # 分析层
            'indicators': os.path.join(self.mode_dir, 'analytics', 'indicators'),
            'predictions': os.path.join(self.mode_dir, 'analytics', 'predictions'),
            'regime': os.path.join(self.mode_dir, 'analytics', 'regime'),
            'analytics': os.path.join(self.mode_dir, 'analytics'),
            
            # 执行层
            'orders': os.path.join(self.mode_dir, 'execution', 'orders'),
            'trades': os.path.join(self.mode_dir, 'execution', 'trades'),
            
            # 风控层
            'risk_audits': os.path.join(self.mode_dir, 'risk', 'audits'),
            
            # 兼容旧路径 (向后兼容)
            'llm_logs': os.path.join(self.mode_dir, 'agents', 'strategy_engine'),  # 兼容旧代码
            'decisions': os.path.join(self.mode_dir, 'agents', 'strategy_engine'),
        }
        
        # 兼容旧路径映射
        self.dirs['agent_context'] = self.dirs['analytics']
        self.dirs['executions'] = self.dirs['orders']
        self.dirs['features'] = self.dirs['analytics']  # features合并到analytics
    
    def clear_live_data(self) -> int:
        """清除 data/live 下所有历史数据（每次启动新周期时调用）
        
        清除范围:
        - agents/     (所有Agent日志)
        - analytics/  (分析数据)
        - execution/  (交易执行日志，包括 all_trades.csv)
        - market_data/(市场数据)
        - oi_history/ (持仓历史)
        - risk/       (风控审计)
        
        不受影响:
        - data/kline/    (K线缓存，共享数据)
        - data/backtest/ (回测数据)
        
        Returns:
            int: 删除的文件数量
        """
        live_dir = os.path.join(self.base_dir, 'live')
        if not os.path.exists(live_dir):
            log.info("📁 data/live 目录不存在，跳过清理")
            return 0
        
        files_deleted = 0
        dirs_cleaned = []
        
        # 遍历 live 目录下的所有子目录
        for subdir in os.listdir(live_dir):
            subdir_path = os.path.join(live_dir, subdir)
            if not os.path.isdir(subdir_path):
                continue
            
            # 递归删除目录内容，但保留目录本身
            for root, dirs, files in os.walk(subdir_path, topdown=False):
                # 删除文件
                for file in files:
                    # 🆕 始终保留交易历史汇总 CSV，用于反思代理
                    if file == 'all_trades.csv':
                        continue
                        
                    file_path = os.path.join(root, file)
                    try:
                        os.remove(file_path)
                        files_deleted += 1
                    except Exception as e:
                        log.warning(f"无法删除文件 {file_path}: {e}")
                
                # 删除空子目录（保留顶级子目录）
                for d in dirs:
                    dir_path = os.path.join(root, d)
                    try:
                        if os.path.isdir(dir_path) and not os.listdir(dir_path):
                            os.rmdir(dir_path)
                    except Exception as e:
                        log.warning(f"无法删除目录 {dir_path}: {e}")
            
            dirs_cleaned.append(subdir)
        
        if files_deleted > 0:
            log.info(f"🧹 清理完成: 删除 {files_deleted} 个历史文件 ({', '.join(dirs_cleaned)})")
        else:
            log.info("🧹 data/live 目录已为空，无需清理")
        
        return files_deleted
            
    def _get_date_folder(self, category: str, symbol: Optional[str] = None, date: Optional[str] = None) -> str:
        """获取或创建指定类别的日期文件夹 (支持按币种嵌套)"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        category_dir = self.dirs.get(category)
        if not category_dir:
            category_dir = os.path.join(self.base_dir, category)
            os.makedirs(category_dir, exist_ok=True)
            
        if symbol:
            target_folder = os.path.join(category_dir, symbol, date)
        else:
            target_folder = os.path.join(category_dir, date)
            
        os.makedirs(target_folder, exist_ok=True)
        return target_folder
    
    def save_market_data(
        self,
        klines: List[Dict],
        symbol: str,
        timeframe: str,
        save_formats: List[str] = ['json', 'csv'],
        cycle_id: str = None
    ) -> Dict[str, str]:
        """保存原始K线数据 (原 save_step1_klines)"""
        if not klines:
            log.warning("K线数据为空，跳过保存")
            return {}
        
        date_folder = self._get_date_folder('market_data', symbol=symbol)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 元数据
        df = pd.DataFrame(klines)
        try:
            first_ts = pd.to_datetime(klines[0]['timestamp'], unit='ms')
            last_ts = pd.to_datetime(klines[-1]['timestamp'], unit='ms')
        except:
            first_ts = "unknown"
            last_ts = "unknown"
            
        metadata = {
            'symbol': symbol,
            'timeframe': timeframe,
            'count': len(klines),
            'timestamp': timestamp
        }
        
        saved_files = {}
        if cycle_id:
            filename_base = f'market_data_{symbol}_{timeframe}_{timestamp}_cycle_{cycle_id}'
        else:
            filename_base = f'market_data_{symbol}_{timeframe}_{timestamp}'
        
        if 'json' in save_formats:
            path = os.path.join(date_folder, f'{filename_base}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'metadata': metadata, 'klines': klines}, f, indent=2, cls=CustomJSONEncoder)
            saved_files['json'] = path
            
        if 'csv' in save_formats:
            path = os.path.join(date_folder, f'{filename_base}.csv')
            df.to_csv(path, index=False)
            saved_files['csv'] = path
            
            
            
        # Parquet usage removed by user request

        log.debug(f"保存市场数据: {symbol} {timeframe}")
        return saved_files

    def save_indicators(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        snapshot_id: str,
        cycle_id: str = None
    ) -> Dict[str, str]:
        """保存技术指标数据 (原 save_step2_indicators)"""
        date_folder = self._get_date_folder('indicators', symbol=symbol)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if cycle_id:
            filename = f'indicators_{symbol}_{timeframe}_{timestamp}_cycle_{cycle_id}_snap_{snapshot_id}.csv'
        else:
            filename = f'indicators_{symbol}_{timeframe}_{timestamp}_{snapshot_id}.csv'
        path = os.path.join(date_folder, filename)
        
        try:
            df.to_csv(path, index=False)
            log.debug(f"保存技术指标: {path}")
            return {'csv': path}
        except Exception as e:
            log.error(f"Failed to save indicators: {e}")
            return {}

    def save_features(
        self,
        features: pd.DataFrame,
        symbol: str,
        timeframe: str,
        snapshot_id: str,
        version: str = 'v1',
        cycle_id: str = None
    ) -> Dict[str, str]:
        """保存特征数据 (原 save_step3_features)"""
        date_folder = self._get_date_folder('features', symbol=symbol)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if cycle_id:
            filename = f'features_{symbol}_{timeframe}_{timestamp}_cycle_{cycle_id}_snap_{snapshot_id}_{version}.csv'
        else:
            filename = f'features_{symbol}_{timeframe}_{timestamp}_{snapshot_id}_{version}.csv'
        path = os.path.join(date_folder, filename)
        
        try:
            features.to_csv(path, index=False)
            log.debug(f"保存特征数据: {path}")
            return {'csv': path}
        except Exception as e:
            log.error(f"Failed to save features: {e}")
            return {}

    def save_context(
        self,
        context: Dict,
        symbol: str,
        identifier: str,
        snapshot_id: str,
        cycle_id: str = None
    ) -> Dict[str, str]:
        """保存Agent上下文/分析结果 (原 save_step4_context)"""
        date_folder = self._get_date_folder('agent_context', symbol=symbol)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if cycle_id:
            filename = f'context_{symbol}_{identifier}_{timestamp}_cycle_{cycle_id}_snap_{snapshot_id}.json'
        else:
            filename = f'context_{symbol}_{identifier}_{timestamp}_{snapshot_id}.json'
        path = os.path.join(date_folder, filename)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(context, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
            
        log.debug(f"保存Agent上下文: {path}")
        return {'json': path}

    def save_llm_log(
        self,
        content: str,
        symbol: str,
        snapshot_id: str,
        cycle_id: str = None
    ) -> Dict[str, str]:
        """保存LLM交互日志 (按币种分文件夹)
        
        路径结构: data/agents/strategy_engine/{SYMBOL}/{YYYYMMDD}/llm_log_{timestamp}.md
        """
        # Get symbol-specific subfolder using central helper
        symbol_date_folder = self._get_date_folder('llm_logs', symbol=symbol)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Include cycle_id in filename if provided
        if cycle_id:
            filename = f'llm_log_{timestamp}_{cycle_id}_{snapshot_id}.md'
        else:
            filename = f'llm_log_{timestamp}_{snapshot_id}.md'
        path = os.path.join(symbol_date_folder, filename)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        log.debug(f"保存LLM日志: {path}")
        return {'md': path}
    
    def save_trend_analysis(
        self,
        analysis: str,
        input_data: Dict,
        symbol: str,
        cycle_id: str,
        model: str = 'deepseek-chat'
    ) -> Dict[str, str]:
        """保存TrendAgent分析日志"""
        symbol_date_folder = self._get_date_folder('trend_agent', symbol=symbol)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'trend_{timestamp}_{cycle_id}.json'
        path = os.path.join(symbol_date_folder, filename)
        
        data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cycle_id': cycle_id,
            'symbol': symbol,
            'input_data': input_data,
            'analysis': analysis,
            'model': model,
            'temperature': 0.3
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
        
        log.debug(f"保存Trend分析: {path}")
        return {'json': path}
    
    def save_setup_analysis(
        self,
        analysis: str,
        input_data: Dict,
        symbol: str,
        cycle_id: str,
        model: str = 'deepseek-chat'
    ) -> Dict[str, str]:
        """保存SetupAgent分析日志"""
        symbol_date_folder = self._get_date_folder('setup_agent', symbol=symbol)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'setup_{timestamp}_{cycle_id}.json'
        path = os.path.join(symbol_date_folder, filename)
        
        data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cycle_id': cycle_id,
            'symbol': symbol,
            'input_data': input_data,
            'analysis': analysis,
            'model': model,
            'temperature': 0.3
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
        
        log.debug(f"保存Setup分析: {path}")
        return {'json': path}
    
    def save_trigger_analysis(
        self,
        analysis: str,
        input_data: Dict,
        symbol: str,
        cycle_id: str,
        model: str = 'deepseek-chat'
    ) -> Dict[str, str]:
        """保存TriggerAgent分析日志"""
        symbol_date_folder = self._get_date_folder('trigger_agent', symbol=symbol)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'trigger_{timestamp}_{cycle_id}.json'
        path = os.path.join(symbol_date_folder, filename)
        
        data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cycle_id': cycle_id,
            'symbol': symbol,
            'input_data': input_data,
            'analysis': analysis,
            'model': model,
            'temperature': 0.3
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
        
        log.debug(f"保存Trigger分析: {path}")
        return {'json': path}
    
    def save_bull_bear_perspectives(
        self,
        bull: Dict,
        bear: Dict,
        symbol: str,
        cycle_id: str
    ) -> Dict[str, str]:
        """保存Bull/Bear对抗分析日志"""
        symbol_date_folder = self._get_date_folder('bull_bear', symbol=symbol)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'perspectives_{timestamp}_{cycle_id}.json'
        path = os.path.join(symbol_date_folder, filename)
        
        data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cycle_id': cycle_id,
            'symbol': symbol,
            'bull_perspective': bull,
            'bear_perspective': bear
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
        
        log.debug(f"保存Bull/Bear分析: {path}")
        return {'json': path}
    
    def save_reflection(
        self,
        reflection: str,
        trades_analyzed: int,
        timestamp: str
    ) -> Dict[str, str]:
        """保存ReflectionAgent反思日志"""
        date_folder = self._get_date_folder('reflection')
        
        filename = f'reflection_{timestamp}.json'
        path = os.path.join(date_folder, filename)
        
        data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'trades_analyzed': trades_analyzed,
            'reflection': reflection
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
        
        log.debug(f"保存Reflection: {path}")
        return {'json': path}

    def save_decision(
        self,
        decision: Dict,
        symbol: str,
        snapshot_id: str,
        cycle_id: str = None
    ) -> Dict[str, str]:
        """保存决策结果 (原 save_step6_decision)"""
        date_folder = self._get_date_folder('decisions', symbol=symbol)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Use cycle_id if provided, otherwise fall back to snapshot_id
        if cycle_id:
            filename = f'decision_{symbol}_{timestamp}_{cycle_id}.json'
            decision['cycle_id'] = cycle_id  # Ensure it's in the content too
        else:
            filename = f'decision_{symbol}_{timestamp}_{snapshot_id}.json'
        path = os.path.join(date_folder, filename)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(decision, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
            
        log.debug(f"保存决策结果: {path}")
        return {'json': path}

    def save_execution(
        self,
        record: Dict,
        symbol: str,
        cycle_id: str = None
    ) -> Dict[str, str]:
        """保存执行记录"""
        date_folder = self._get_date_folder('orders', symbol=symbol)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if cycle_id:
            filename = f'execution_{symbol}_{timestamp}_{cycle_id}.json'
            record['cycle_id'] = cycle_id
        else:
            filename = f'order_{symbol}_{timestamp}.json'
        path = os.path.join(date_folder, filename)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(record, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
        
        # 追加CSV
        csv_path = os.path.join(date_folder, f'orders_{symbol}.csv')
        df = pd.DataFrame([record])
        if os.path.exists(csv_path):
            df.to_csv(csv_path, mode='a', header=False, index=False)
        else:
            df.to_csv(csv_path, index=False)
            
        log.debug(f"保存执行记录: {path}")
        return {'json': path, 'csv': csv_path}

    def save_risk_audit(
        self,
        audit_result: Dict,
        symbol: str,
        snapshot_id: str,
        cycle_id: str = None
    ) -> Dict[str, str]:
        """保存风控审计结果"""
        date_folder = self._get_date_folder('risk_audits', symbol=symbol)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if cycle_id:
            filename = f'audit_{symbol}_{timestamp}_{cycle_id}_{snapshot_id}.json'
            audit_result['cycle_id'] = cycle_id
        else:
            filename = f'risk_audit_{symbol}_{timestamp}_{snapshot_id}.json'
        path = os.path.join(date_folder, filename)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(audit_result, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
            
        log.debug(f"保存风控审计记录: {path}")
        return {'json': path}

    def save_prediction(
        self,
        prediction: Dict,
        symbol: str,
        snapshot_id: str,
        cycle_id: str = None
    ) -> Dict[str, str]:
        """保存预测预言家(The Prophet)的预测结果"""
        date_folder = self._get_date_folder('predictions', symbol=symbol)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if cycle_id:
            filename = f'prediction_{symbol}_{timestamp}_{cycle_id}_{snapshot_id}.json'
            prediction['cycle_id'] = cycle_id
        else:
            filename = f'prediction_{symbol}_{timestamp}_{snapshot_id}.json'
        path = os.path.join(date_folder, filename)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(prediction, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
            
        log.debug(f"保存预测结果: {path}")
        return {'json': path}

    def list_files(self, category: str, symbol: Optional[str] = None, date: Optional[str] = None) -> List[str]:
        """列出文件"""
        folder = self._get_date_folder(category, symbol=symbol, date=date)
        if not os.path.exists(folder):
            return []
        return [os.path.join(folder, f) for f in os.listdir(folder)]

    # 兼容性别名 (Adapters for old code if any remains)
    save_step1_klines = save_market_data
    save_step2_indicators = save_indicators
    save_step3_features = save_features
    save_step4_context = save_context
    save_step5_markdown = save_llm_log
    save_step6_decision = save_decision
    save_step7_execution = save_execution

    # --- 交易历史记录扩展 ---
    TRADE_COLUMNS = [
        'record_time', 'open_cycle', 'close_cycle', 'action', 'symbol', 'price', 'quantity', 
        'cost', 'exit_price', 'pnl', 'confidence', 'status'
    ]

    def save_trade(self, trade_data: Dict):
        """保存交易记录（持久化追加至单一CSV，标准化 Schema）"""
        try:
            category = 'trades'
            base_path = self.dirs.get(category)
            if not os.path.exists(base_path):
                os.makedirs(base_path, exist_ok=True)
            
            file_path = os.path.join(base_path, 'all_trades.csv')
            
            # 1. 完善基础字段
            trade_data['record_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if 'cycle_id' not in trade_data and 'cycle' in trade_data:
                trade_data['cycle_id'] = trade_data['cycle']
            
            # 2. 补全缺失字段 (Schema 稳定性)
            for col in self.TRADE_COLUMNS:
                if col not in trade_data:
                    trade_data[col] = 0.0 if col in ['cost', 'pnl', 'exit_price', 'price', 'quantity'] else 'N/A'
            
            # 3. 按标准顺序转换为 DataFrame
            df = pd.DataFrame([{col: trade_data[col] for col in self.TRADE_COLUMNS}])
            
            # 4. 保存
            if os.path.exists(file_path):
                df.to_csv(file_path, mode='a', header=False, index=False)
            else:
                df.to_csv(file_path, mode='w', header=True, index=False)
            
            log.debug(f"交易记录已保存 (标准化): {file_path}")
        except Exception as e:
            log.error(f"保存标准化交易记录失败: {e}")

    def get_recent_trades(self, limit: int = 10, days: int = 30) -> List[Dict]:
        """获取最近的交易记录
        
        Args:
            limit: 返回的最大记录数（默认10条）
            days: 只返回最近N天内的记录（默认30天）
        """
        try:
            file_path = os.path.join(self.dirs.get('trades'), 'all_trades.csv')
            if not os.path.exists(file_path):
                return []
            
            df = pd.read_csv(file_path)
            if df.empty:
                return []
            
            # 时间过滤: 只保留最近 N 天内的数据
            if 'record_time' in df.columns:
                df['record_time'] = pd.to_datetime(df['record_time'], errors='coerce')
                cutoff_time = datetime.now() - pd.Timedelta(days=days)
                df = df[df['record_time'] >= cutoff_time]
            
            if df.empty:
                return []
            
            # 获取最后N条并按时间反序（或者保持原序由展示层决定）
            recent = df.tail(limit).to_dict('records')
            return recent
        except Exception as e:
            log.error(f"获取最近交易记录失败: {e}")
            return []

    def update_trade_exit(
        self,
        symbol: str,
        exit_price: float,
        pnl: float,
        exit_time: str,
        close_cycle: int = 0
    ) -> bool:
        """
        更新交易记录的平仓信息 (原地更新)
        
        查找该 symbol 最近一条非 CLOSED 状态的记录，更新其 Exit Price 和 PnL。
        这样可以保持 Trade History 表格的一致性（Round-Trip View）。
        """
        try:
            file_path = os.path.join(self.dirs.get('trades'), 'all_trades.csv')
            if not os.path.exists(file_path):
                log.warning("交易记录文件不存在，无法更新平仓信息")
                return False
            
            df = pd.read_csv(file_path)
            if df.empty:
                return False
            
            # 反向查找该 symbol 的 Open 记录
            # 假设 Open 记录的 status 通常为 SENT, EXECUTED, SIMULATED 等，且 exit_price 为 0 或 NaN
            # 我们查找 exit_price <= 0 或 NaN 的行
            
            # convert exit_price to numeric just in case
            df['exit_price'] = pd.to_numeric(df['exit_price'], errors='coerce').fillna(0)
            
            # Find matching rows: symbol match AND (exit_price is 0)
            mask = (df['symbol'] == symbol) & (df['exit_price'] == 0)
            
            if not mask.any():
                log.warning(f"未找到 {symbol} 的活跃持仓记录，无法更新平仓")
                return False
            
            # Get index of the LAST matching row
            target_idx = df[mask].index[-1]
            
            # Update values
            df.at[target_idx, 'exit_price'] = exit_price
            df.at[target_idx, 'pnl'] = pnl
            df.at[target_idx, 'close_cycle'] = close_cycle
            df.at[target_idx, 'status'] = 'CLOSED'
            
            # Save back
            df.to_csv(file_path, index=False)
            log.info(f"✅ 已更新交易记录: {symbol} Closed @ ${exit_price:.2f}, PnL: ${pnl:.2f}, Cycle: {close_cycle}")
            return True
            
        except Exception as e:
            log.error(f"更新交易记录失败: {e}")
            return False
            
        except Exception as e:
            log.error(f"更新交易记录失败: {e}")
            return False
    def save_virtual_account(self, balance: float, positions: Dict):
        """持久化模拟账户状态"""
        try:
            path = os.path.join(self.base_dir, 'agents', 'virtual_account.json')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {
                'balance': balance,
                'positions': positions,
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, cls=CustomJSONEncoder)
            log.debug(f"模拟账户已持久化: {path}")
        except Exception as e:
            log.error(f"持久化模拟账户失败: {e}")

    def load_virtual_account(self) -> Optional[Dict]:
        """加载模拟账户状态"""
        try:
            path = os.path.join(self.base_dir, 'agents', 'virtual_account.json')
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            log.error(f"加载模拟账户失败: {e}")
            return None
