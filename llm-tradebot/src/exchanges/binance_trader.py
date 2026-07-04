"""
Binance Futures Trader Implementation

This module implements the BaseTrader interface for Binance Futures trading.
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime

from binance.client import Client
from binance.exceptions import BinanceAPIException

from .base import (
    BaseTrader, 
    ExchangeAccount, 
    AccountBalance, 
    Position, 
    OrderResult,
    ExchangeType
)
from src.utils.logger import log


class BinanceTrader(BaseTrader):
    """
    Binance Futures implementation of BaseTrader.
    
    Supports both mainnet and testnet trading.
    """
    
    def __init__(self, account: ExchangeAccount):
        """
        Initialize Binance trader.
        
        Args:
            account: ExchangeAccount with API credentials
        """
        super().__init__(account)
        self.client: Optional[Client] = None
        
        # Cache for funding rates
        self._funding_cache: Dict[str, tuple] = {}
        self._cache_duration = 3600  # 1 hour
    
    def _normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol format from TradingView to Binance API format.
        
        Converts formats like:
        - ETH/USDT.P -> ETHUSDT
        - BTC/USDT.P -> BTCUSDT
        - ETHUSDT -> ETHUSDT (unchanged)
        
        Args:
            symbol: Symbol in any supported format
            
        Returns:
            Normalized symbol for Binance API
        """
        # Remove .P suffix (TradingView perpetual contract indicator)
        if symbol.endswith(".P") or symbol.endswith(".PERP"):
            symbol = symbol.rsplit(".", 1)[0]
        
        # Remove slash separator
        symbol = symbol.replace("/", "")
        
        # Convert to uppercase
        return symbol.upper()
    
    async def initialize(self) -> bool:
        """Initialize Binance client connection."""
        try:
            if self.account.testnet:
                self.client = Client(
                    self.account.api_key,
                    self.account.secret_key,
                    testnet=True
                )
            else:
                self.client = Client(
                    self.account.api_key,
                    self.account.secret_key
                )
            
            self._initialized = True
            log.info(f"BinanceTrader initialized: {self.account_name} (testnet={self.account.testnet})")
            return True
            
        except Exception as e:
            log.error(f"Failed to initialize BinanceTrader: {e}")
            return False
    
    def _ensure_initialized(self):
        """Ensure client is initialized before operations."""
        if not self._initialized or not self.client:
            raise RuntimeError("BinanceTrader not initialized. Call initialize() first.")
    
    async def get_balance(self) -> AccountBalance:
        """Get futures account balance."""
        self._ensure_initialized()
        
        try:
            account = self.client.futures_account()
            
            return AccountBalance(
                total_equity=float(account['totalMarginBalance']),
                available_balance=float(account['availableBalance']),
                unrealized_pnl=float(account['totalUnrealizedProfit']),
                wallet_balance=float(account['totalWalletBalance']),
                margin_balance=float(account['totalMarginBalance'])
            )
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to get balance: {e}")
            raise
    
    async def get_positions(self, symbol: str = None) -> List[Position]:
        """Get open futures positions."""
        self._ensure_initialized()
        
        try:
            if symbol:
                positions = self.client.futures_position_information(symbol=symbol)
            else:
                positions = self.client.futures_position_information()
            
            result = []
            for pos in positions:
                position_amt = float(pos['positionAmt'])
                if position_amt != 0:
                    result.append(Position(
                        symbol=pos['symbol'],
                        side="LONG" if position_amt > 0 else "SHORT",
                        quantity=abs(position_amt),
                        entry_price=float(pos['entryPrice']),
                        unrealized_pnl=float(pos['unRealizedProfit']),
                        leverage=int(pos['leverage']),
                        mark_price=float(pos['markPrice']),
                        liquidation_price=float(pos['liquidationPrice']),
                        margin_type=pos['marginType'].lower()
                    ))
            
            return result
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to get positions: {e}")
            raise
    
    async def get_market_price(self, symbol: str) -> float:
        """Get current market price."""
        self._ensure_initialized()
        
        # Normalize symbol format (e.g., ETH/USDT.P -> ETHUSDT)
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            # Use futures API for perpetual contracts
            ticker = self.client.futures_symbol_ticker(symbol=normalized_symbol)
            return float(ticker['price'])
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to get price for {normalized_symbol}: {e}")
            raise
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            self.client.futures_change_leverage(
                symbol=normalized_symbol,
                leverage=leverage
            )
            log.info(f"[{self.account_name}] Set leverage for {normalized_symbol}: {leverage}x")
            return True
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to set leverage: {e}")
            return False
    
    async def open_long(
        self, 
        symbol: str, 
        quantity: float, 
        leverage: int = 1,
        reduce_only: bool = False
    ) -> OrderResult:
        """Open a long position."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            # Set leverage first
            await self.set_leverage(symbol, leverage)
            
            # Build order params
            order_params = {
                'symbol': normalized_symbol,
                'side': 'BUY',
                'type': 'MARKET',
                'quantity': quantity,
                'positionSide': 'BOTH'
            }
            
            if reduce_only:
                order_params['reduceOnly'] = True
            
            order = self.client.futures_create_order(**order_params)
            
            log.info(f"[{self.account_name}] Long opened: {quantity} {symbol}")
            
            return OrderResult(
                success=True,
                order_id=str(order.get('orderId', '')),
                symbol=symbol,
                side='BUY',
                quantity=quantity,
                price=float(order.get('avgPrice', 0)),
                status=order.get('status', 'FILLED'),
                raw_response=order
            )
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to open long: {e}")
            return OrderResult(success=False, error=str(e))
    
    async def open_short(
        self, 
        symbol: str, 
        quantity: float, 
        leverage: int = 1,
        reduce_only: bool = False
    ) -> OrderResult:
        """Open a short position."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            # Set leverage first
            await self.set_leverage(symbol, leverage)
            
            # Build order params
            order_params = {
                'symbol': normalized_symbol,
                'side': 'SELL',
                'type': 'MARKET',
                'quantity': quantity,
                'positionSide': 'BOTH'
            }
            
            if reduce_only:
                order_params['reduceOnly'] = True
            
            order = self.client.futures_create_order(**order_params)
            
            log.info(f"[{self.account_name}] Short opened: {quantity} {symbol}")
            
            return OrderResult(
                success=True,
                order_id=str(order.get('orderId', '')),
                symbol=symbol,
                side='SELL',
                quantity=quantity,
                price=float(order.get('avgPrice', 0)),
                status=order.get('status', 'FILLED'),
                raw_response=order
            )
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to open short: {e}")
            return OrderResult(success=False, error=str(e))
    
    async def close_position(self, symbol: str, quantity: float = 0) -> OrderResult:
        """Close an existing position."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            # Get current position
            positions = await self.get_positions(normalized_symbol)
            if not positions:
                return OrderResult(success=False, error="No position found")
            
            position = positions[0]
            close_qty = quantity if quantity > 0 else position.quantity
            
            # Determine close side
            close_side = 'SELL' if position.side == 'LONG' else 'BUY'
            
            order = self.client.futures_create_order(
                symbol=normalized_symbol,
                side=close_side,
                type='MARKET',
                quantity=close_qty,
                positionSide='BOTH',
                reduceOnly=True
            )
            
            log.info(f"[{self.account_name}] Position closed: {close_qty} {symbol}")
            
            return OrderResult(
                success=True,
                order_id=str(order.get('orderId', '')),
                symbol=symbol,
                side=close_side,
                quantity=close_qty,
                price=float(order.get('avgPrice', 0)),
                status=order.get('status', 'FILLED'),
                raw_response=order
            )
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to close position: {e}")
            return OrderResult(success=False, error=str(e))
    
    async def set_stop_loss(
        self, 
        symbol: str, 
        stop_price: float,
        position_side: str = "LONG"
    ) -> OrderResult:
        """Set stop-loss order."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            side = 'SELL' if position_side.upper() == 'LONG' else 'BUY'
            
            order = self.client.futures_create_order(
                symbol=normalized_symbol,
                side=side,
                type='STOP_MARKET',
                stopPrice=stop_price,
                closePosition=True,
                positionSide='BOTH'
            )
            
            log.info(f"[{self.account_name}] Stop-loss set: {symbol} @ {stop_price}")
            
            return OrderResult(
                success=True,
                order_id=str(order.get('orderId', '')),
                symbol=symbol,
                side=side,
                price=stop_price,
                status='NEW',
                raw_response=order
            )
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to set stop-loss: {e}")
            return OrderResult(success=False, error=str(e))
    
    async def set_take_profit(
        self, 
        symbol: str, 
        take_profit_price: float,
        position_side: str = "LONG"
    ) -> OrderResult:
        """Set take-profit order."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            side = 'SELL' if position_side.upper() == 'LONG' else 'BUY'
            
            order = self.client.futures_create_order(
                symbol=normalized_symbol,
                side=side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=take_profit_price,
                closePosition=True,
                positionSide='BOTH'
            )
            
            log.info(f"[{self.account_name}] Take-profit set: {symbol} @ {take_profit_price}")
            
            return OrderResult(
                success=True,
                order_id=str(order.get('orderId', '')),
                symbol=symbol,
                side=side,
                price=take_profit_price,
                status='NEW',
                raw_response=order
            )
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to set take-profit: {e}")
            return OrderResult(success=False, error=str(e))
    
    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders for a symbol."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            self.client.futures_cancel_all_open_orders(symbol=normalized_symbol)
            log.info(f"[{self.account_name}] Cancelled all orders for {symbol}")
            return True
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to cancel orders: {e}")
            return False
    
    async def get_klines(
        self, 
        symbol: str, 
        interval: str, 
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Get candlestick data with local cache priority."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            # Use KlineCache for local-first data fetching
            from src.utils.kline_cache import get_kline_cache
            cache = get_kline_cache()
            
            # Check cache first
            cached_df = cache.get_cached_data(normalized_symbol, interval)
            
            if cached_df is not None and len(cached_df) >= limit:
                # Cache sufficient - return cached data
                log.debug(f"📦 Cache hit: {normalized_symbol}/{interval} | {len(cached_df)} rows")
                
                # Convert DataFrame to list of dicts
                result = []
                for _, row in cached_df.tail(limit).iterrows():
                    result.append({
                        'timestamp': int(row['timestamp']),
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume']),
                    })
                return result
            
            # Cache miss or insufficient - fetch from API
            log.debug(f"📦 Cache miss: {normalized_symbol}/{interval} | Fetching from API")
            
            klines = self.client.futures_klines(
                symbol=normalized_symbol,
                interval=interval,
                limit=limit
            )
            
            formatted = []
            for k in klines:
                formatted.append({
                    'timestamp': k[0],
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5]),
                    'close_time': k[6],
                    'quote_volume': float(k[7]),
                    'trades': int(k[8]),
                    'taker_buy_base': float(k[9]),
                    'taker_buy_quote': float(k[10])
                })
            
            # Save to cache
            cache.append_data(normalized_symbol, interval, formatted)
            
            return formatted
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to get klines: {e}")
            raise
    
    async def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """Get funding rate for a symbol."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            # Check cache first
            now = datetime.now().timestamp()
            if normalized_symbol in self._funding_cache:
                rate, ts = self._funding_cache[normalized_symbol]
                if now - ts < self._cache_duration:
                    return {'symbol': normalized_symbol, 'funding_rate': rate, 'cached': True}
            
            funding = self.client.futures_mark_price(symbol=normalized_symbol)
            rate = float(funding['lastFundingRate'])
            
            # Update cache
            self._funding_cache[symbol] = (rate, now)
            
            return {
                'symbol': symbol,
                'funding_rate': rate,
                'funding_time': funding.get('nextFundingTime'),
                'cached': False
            }
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to get funding rate: {e}")
            return {'symbol': symbol, 'funding_rate': 0, 'error': str(e)}
    
    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        """Get open interest for a symbol."""
        self._ensure_initialized()
        
        normalized_symbol = self._normalize_symbol(symbol)
        
        try:
            oi = self.client.futures_open_interest(symbol=normalized_symbol)
            
            return {
                'symbol': oi['symbol'],
                'open_interest': float(oi['openInterest']),
                'timestamp': oi.get('time')
            }
            
        except BinanceAPIException as e:
            log.error(f"[{self.account_name}] Failed to get open interest: {e}")
            return {'symbol': symbol, 'open_interest': 0, 'error': str(e)}
