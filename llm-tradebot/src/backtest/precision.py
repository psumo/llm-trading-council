"""
金融计算精度工具 (Financial Precision Utils)
=============================================

使用 Decimal 类型进行金融计算，避免浮点数精度问题

Author: AI Trader Team
Date: 2025-12-31
"""

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, getcontext
from typing import Union
from dataclasses import dataclass
from enum import Enum

# 设置全局精度
getcontext().prec = 18


class ContractType(Enum):
    """合约类型"""
    LINEAR = "linear"      # U本位 (USDT-Margined)
    INVERSE = "inverse"    # 币本位 (Coin-Margined)


@dataclass
class ContractSpec:
    """
    合约规格
    
    不同交易所和币种的合约面值不同：
    - Binance BTC 币本位: 1 张 = 100 USD
    - Binance ETH 币本位: 1 张 = 10 USD
    - OKX BTC 币本位: 1 张 = 100 USD
    """
    contract_type: ContractType
    contract_size: float = 1.0  # 合约乘数
    tick_size: float = 0.1      # 最小价格变动
    min_qty: float = 0.001      # 最小交易数量
    qty_step: float = 0.001     # 数量步长
    
    # 预设规格
    @classmethod
    def binance_btc_linear(cls) -> 'ContractSpec':
        """Binance BTCUSDT U本位"""
        return cls(
            contract_type=ContractType.LINEAR,
            contract_size=1.0,
            tick_size=0.1,
            min_qty=0.001,
            qty_step=0.001
        )
    
    @classmethod
    def binance_btc_inverse(cls) -> 'ContractSpec':
        """Binance BTCUSD 币本位"""
        return cls(
            contract_type=ContractType.INVERSE,
            contract_size=100.0,  # 1张 = 100 USD
            tick_size=0.1,
            min_qty=1,  # 最小1张
            qty_step=1
        )
    
    @classmethod
    def binance_eth_inverse(cls) -> 'ContractSpec':
        """Binance ETHUSD 币本位"""
        return cls(
            contract_type=ContractType.INVERSE,
            contract_size=10.0,  # 1张 = 10 USD
            tick_size=0.01,
            min_qty=1,
            qty_step=1
        )


class PrecisionCalc:
    """
    高精度金融计算类
    
    所有金融相关计算使用 Decimal 避免浮点误差累积
    """
    
    PRECISION = 8  # 小数位精度
    
    @staticmethod
    def to_decimal(value: Union[float, str, int, Decimal]) -> Decimal:
        """转换为 Decimal"""
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    
    @staticmethod
    def to_float(value: Decimal) -> float:
        """转换回 float (用于显示)"""
        return float(value)
    
    @classmethod
    def round_price(cls, price: Union[float, Decimal], tick_size: float = 0.01) -> Decimal:
        """按照 tick size 取整价格"""
        d_price = cls.to_decimal(price)
        d_tick = cls.to_decimal(tick_size)
        return (d_price / d_tick).quantize(Decimal('1'), rounding=ROUND_DOWN) * d_tick
    
    @classmethod
    def round_qty(cls, qty: Union[float, Decimal], qty_step: float = 0.001) -> Decimal:
        """按照 qty step 取整数量"""
        d_qty = cls.to_decimal(qty)
        d_step = cls.to_decimal(qty_step)
        return (d_qty / d_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * d_step
    
    @classmethod
    def calculate_linear_pnl(
        cls,
        entry_price: float,
        exit_price: float,
        quantity: float,
        is_long: bool
    ) -> Decimal:
        """
        计算 U 本位 (Linear) 合约 PnL
        
        公式：PnL = (exit_price - entry_price) * quantity
        """
        d_entry = cls.to_decimal(entry_price)
        d_exit = cls.to_decimal(exit_price)
        d_qty = cls.to_decimal(quantity)
        
        if is_long:
            return (d_exit - d_entry) * d_qty
        else:
            return (d_entry - d_exit) * d_qty
    
    @classmethod
    def calculate_inverse_pnl(
        cls,
        entry_price: float,
        exit_price: float,
        contracts: int,
        contract_size: float,
        is_long: bool
    ) -> Decimal:
        """
        计算币本位 (Inverse) 合约 PnL
        
        公式：PnL = (1/entry - 1/exit) * contracts * contract_size
        
        注意：币本位合约的 PnL 单位是币 (BTC/ETH)，非 USDT
        """
        d_entry = cls.to_decimal(entry_price)
        d_exit = cls.to_decimal(exit_price)
        d_contracts = cls.to_decimal(contracts)
        d_size = cls.to_decimal(contract_size)
        
        if is_long:
            # 多头：价格上涨盈利
            pnl = (Decimal('1') / d_entry - Decimal('1') / d_exit) * d_contracts * d_size
        else:
            # 空头：价格下跌盈利
            pnl = (Decimal('1') / d_exit - Decimal('1') / d_entry) * d_contracts * d_size
        
        return pnl
    
    @classmethod
    def calculate_inverse_pnl_usd(
        cls,
        entry_price: float,
        exit_price: float,
        contracts: int,
        contract_size: float,
        is_long: bool,
        settlement_price: float = None
    ) -> Decimal:
        """
        计算币本位合约 PnL (以 USD 计价)
        
        Args:
            settlement_price: 结算价格 (默认使用 exit_price)
        """
        pnl_coin = cls.calculate_inverse_pnl(
            entry_price, exit_price, contracts, contract_size, is_long
        )
        
        # 转换为 USD
        settle = cls.to_decimal(settlement_price or exit_price)
        return pnl_coin * settle
    
    @classmethod
    def calculate_liquidation_price(
        cls,
        entry_price: float,
        leverage: int,
        is_long: bool,
        maintenance_margin_rate: float = 0.004,
        contract_type: ContractType = ContractType.LINEAR
    ) -> Decimal:
        """
        计算强平价格
        
        U本位多头强平: entry * (1 - 1/leverage + mmr)
        U本位空头强平: entry * (1 + 1/leverage - mmr)
        """
        d_entry = cls.to_decimal(entry_price)
        d_lev = cls.to_decimal(leverage)
        d_mmr = cls.to_decimal(maintenance_margin_rate)
        
        if contract_type == ContractType.LINEAR:
            if is_long:
                # 多头强平价 < 开仓价
                liq_price = d_entry * (Decimal('1') - Decimal('1') / d_lev + d_mmr)
            else:
                # 空头强平价 > 开仓价
                liq_price = d_entry * (Decimal('1') + Decimal('1') / d_lev - d_mmr)
        else:
            # 币本位计算略有不同，这里简化处理
            if is_long:
                liq_price = d_entry * (Decimal('1') - Decimal('1') / d_lev + d_mmr)
            else:
                liq_price = d_entry * (Decimal('1') + Decimal('1') / d_lev - d_mmr)
        
        return liq_price


# 快捷函数
def pnl_linear(entry: float, exit: float, qty: float, is_long: bool) -> float:
    """快捷计算 U 本位 PnL"""
    return float(PrecisionCalc.calculate_linear_pnl(entry, exit, qty, is_long))


def pnl_inverse(entry: float, exit: float, contracts: int, size: float, is_long: bool) -> float:
    """快捷计算币本位 PnL (以币计价)"""
    return float(PrecisionCalc.calculate_inverse_pnl(entry, exit, contracts, size, is_long))


def pnl_inverse_usd(entry: float, exit: float, contracts: int, size: float, is_long: bool) -> float:
    """快捷计算币本位 PnL (以 USD 计价)"""
    return float(PrecisionCalc.calculate_inverse_pnl_usd(entry, exit, contracts, size, is_long))


# 测试
if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Testing PrecisionCalc")
    print("=" * 50)
    
    # U本位测试
    print("\n📊 U本位 (Linear) PnL:")
    pnl = pnl_linear(50000, 51000, 0.1, is_long=True)
    print(f"   BTC 50000->51000, 0.1 BTC Long: ${pnl:.2f}")
    
    pnl = pnl_linear(50000, 49000, 0.1, is_long=False)
    print(f"   BTC 50000->49000, 0.1 BTC Short: ${pnl:.2f}")
    
    # 币本位测试
    print("\n📊 币本位 (Inverse) PnL:")
    pnl_btc = pnl_inverse(50000, 51000, 100, 100, is_long=True)
    pnl_usd = pnl_inverse_usd(50000, 51000, 100, 100, is_long=True)
    print(f"   BTC 50000->51000, 100张 Long: {pnl_btc:.6f} BTC (${pnl_usd:.2f})")
    
    # 强平价格
    print("\n📊 强平价格计算:")
    liq = PrecisionCalc.calculate_liquidation_price(50000, 10, True)
    print(f"   BTC 50000 10x Long 强平价: ${float(liq):.2f}")
    
    liq = PrecisionCalc.calculate_liquidation_price(50000, 10, False)
    print(f"   BTC 50000 10x Short 强平价: ${float(liq):.2f}")
    
    print("\n✅ PrecisionCalc test complete!")
