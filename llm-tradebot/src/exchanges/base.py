"""
Exchange Abstraction Layer - Base Classes and Data Models

This module provides a unified interface for trading across multiple exchanges.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum
from datetime import datetime
import uuid


class ExchangeType(Enum):
    """Supported exchange types"""
    BINANCE = "binance"
    BYBIT = "bybit"
    OKX = "okx"
    BITGET = "bitget"
    HYPERLIQUID = "hyperliquid"


@dataclass
class Position:
    """Represents an open trading position"""
    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: float
    entry_price: float
    unrealized_pnl: float
    leverage: int
    mark_price: float = 0.0
    liquidation_price: float = 0.0
    margin_type: str = "cross"  # "cross" or "isolated"
    
    @property
    def notional_value(self) -> float:
        """Calculate position notional value"""
        return self.quantity * self.mark_price if self.mark_price else self.quantity * self.entry_price


@dataclass
class AccountBalance:
    """Represents account balance information"""
    total_equity: float
    available_balance: float
    unrealized_pnl: float
    wallet_balance: float = 0.0
    margin_balance: float = 0.0
    
    @property
    def used_margin(self) -> float:
        """Calculate used margin"""
        return self.total_equity - self.available_balance


@dataclass
class OrderResult:
    """Represents the result of an order execution"""
    success: bool
    order_id: str = ""
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    status: str = ""
    error: str = ""
    raw_response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExchangeAccount:
    """Configuration for an exchange account"""
    id: str = ""
    user_id: str = "default"
    exchange_type: ExchangeType = ExchangeType.BINANCE
    account_name: str = "Default Account"
    enabled: bool = True
    
    # CEX credentials
    api_key: str = ""
    secret_key: str = ""
    passphrase: str = ""  # OKX/Bitget specific
    
    # DEX credentials
    private_key: str = ""
    wallet_addr: str = ""
    
    testnet: bool = False
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding sensitive info)"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "exchange_type": self.exchange_type.value,
            "account_name": self.account_name,
            "enabled": self.enabled,
            "testnet": self.testnet,
            "has_api_key": bool(self.api_key),
            "has_private_key": bool(self.private_key),
            "wallet_addr": self.wallet_addr[:10] + "..." if self.wallet_addr else "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BaseTrader(ABC):
    """
    Abstract base class for exchange traders.
    
    All exchange-specific implementations must inherit from this class
    and implement all abstract methods.
    """
    
    def __init__(self, account: ExchangeAccount):
        """
        Initialize trader with account configuration.
        
        Args:
            account: ExchangeAccount configuration object
        """
        self.account = account
        self.account_id = account.id
        self.account_name = account.account_name
        self.exchange_type = account.exchange_type
        self._initialized = False
    
    @property
    def is_testnet(self) -> bool:
        """Check if running on testnet"""
        return self.account.testnet
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the exchange client connection.
        Should be called after construction.
        
        Returns:
            True if initialization successful
        """
        pass
    
    @abstractmethod
    async def get_balance(self) -> AccountBalance:
        """
        Get account balance information.
        
        Returns:
            AccountBalance object with equity, available balance, etc.
        """
        pass
    
    @abstractmethod
    async def get_positions(self, symbol: str = None) -> List[Position]:
        """
        Get open positions.
        
        Args:
            symbol: Optional symbol filter. If None, returns all positions.
            
        Returns:
            List of Position objects
        """
        pass
    
    @abstractmethod
    async def get_market_price(self, symbol: str) -> float:
        """
        Get current market price for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            
        Returns:
            Current price as float
        """
        pass
    
    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Trading pair symbol
            leverage: Leverage multiplier (1-125)
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def open_long(
        self, 
        symbol: str, 
        quantity: float, 
        leverage: int = 1,
        reduce_only: bool = False
    ) -> OrderResult:
        """
        Open a long position.
        
        Args:
            symbol: Trading pair symbol
            quantity: Position size
            leverage: Leverage multiplier
            reduce_only: If True, only reduces existing position
            
        Returns:
            OrderResult with execution details
        """
        pass
    
    @abstractmethod
    async def open_short(
        self, 
        symbol: str, 
        quantity: float, 
        leverage: int = 1,
        reduce_only: bool = False
    ) -> OrderResult:
        """
        Open a short position.
        
        Args:
            symbol: Trading pair symbol
            quantity: Position size
            leverage: Leverage multiplier
            reduce_only: If True, only reduces existing position
            
        Returns:
            OrderResult with execution details
        """
        pass
    
    @abstractmethod
    async def close_position(
        self, 
        symbol: str, 
        quantity: float = 0
    ) -> OrderResult:
        """
        Close an existing position.
        
        Args:
            symbol: Trading pair symbol
            quantity: Amount to close. If 0, closes entire position.
            
        Returns:
            OrderResult with execution details
        """
        pass
    
    @abstractmethod
    async def set_stop_loss(
        self, 
        symbol: str, 
        stop_price: float,
        position_side: str = "LONG"
    ) -> OrderResult:
        """
        Set stop-loss order for a position.
        
        Args:
            symbol: Trading pair symbol
            stop_price: Stop-loss trigger price
            position_side: "LONG" or "SHORT"
            
        Returns:
            OrderResult with order details
        """
        pass
    
    @abstractmethod
    async def set_take_profit(
        self, 
        symbol: str, 
        take_profit_price: float,
        position_side: str = "LONG"
    ) -> OrderResult:
        """
        Set take-profit order for a position.
        
        Args:
            symbol: Trading pair symbol
            take_profit_price: Take-profit trigger price
            position_side: "LONG" or "SHORT"
            
        Returns:
            OrderResult with order details
        """
        pass
    
    @abstractmethod
    async def cancel_all_orders(self, symbol: str) -> bool:
        """
        Cancel all open orders for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def get_klines(
        self, 
        symbol: str, 
        interval: str, 
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Get candlestick/kline data.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe (e.g., "1m", "5m", "1h")
            limit: Number of candles to fetch
            
        Returns:
            List of kline dictionaries with OHLCV data
        """
        pass
    
    async def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """
        Get funding rate for a symbol (futures only).
        Default implementation returns empty dict.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Dict with funding rate info
        """
        return {}
    
    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        """
        Get open interest for a symbol.
        Default implementation returns empty dict.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Dict with open interest info
        """
        return {}
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} account='{self.account_name}' exchange={self.exchange_type.value}>"
