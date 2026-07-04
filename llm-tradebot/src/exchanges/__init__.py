"""
Exchange Trading Abstraction Layer

Provides a unified interface for trading across multiple exchanges.
"""

from .base import (
    BaseTrader,
    ExchangeAccount,
    ExchangeType,
    Position,
    AccountBalance,
    OrderResult
)
from .factory import (
    create_trader,
    create_and_initialize_trader,
    get_supported_exchanges
)
from .account_manager import AccountManager
from .binance_trader import BinanceTrader


__all__ = [
    # Base classes
    'BaseTrader',
    'ExchangeAccount', 
    'ExchangeType',
    'Position',
    'AccountBalance',
    'OrderResult',
    
    # Factory
    'create_trader',
    'create_and_initialize_trader',
    'get_supported_exchanges',
    
    # Manager
    'AccountManager',
    
    # Implementations
    'BinanceTrader',
]
