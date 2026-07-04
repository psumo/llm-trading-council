"""
Research Package - 策略研究和开发工具集

包含:
- data_explorer: 数据探索和分析工具
- backtester: 策略回测框架
- workflow: 完整策略开发流程
"""

from .data_explorer import DataExplorer
from .backtester import Backtester

__all__ = ['DataExplorer', 'Backtester']
