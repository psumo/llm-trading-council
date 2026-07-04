
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.portfolio import BacktestPortfolio, Position, Side, MarginConfig

def replicate_run_228343():
    print("🕵️ Replicating Run 228343 Calculation...")
    
    # 1. Setup Portfolio (Use defaults from class definition first)
    # Default: slippage=0.0005, commission=0.0004 (from BacktestPortfolio init)
    # But wait, BacktestConfig default is 0.001. Let's assume passed from config.
    # Config JSON didn't show slippage, so it might be 0.001 or 0.0005 depending on where it came from.
    
    # Let's TRY to find parameters that match the numbers.
    
    initial_capital = 10000.0
    # Inputs
    open_price_raw = 12.496484
    close_price_raw = 13.048938
    quantity = 760.9740467798782
    leverage = 10.0
    
    # Target Outputs (from Run 228343)
    target_pnl = 420.403156
    target_profit = 426.54  # Final Equity - Initial Capital
    
    print(f"Inputs: Open=${open_price_raw}, Close=${close_price_raw}, Qty={quantity}")
    print(f"Targets: TradePnL=${target_pnl}, EquityProfit=${target_profit}")
    
    # Scenario A: Slippage = 0, Commission = 0 ?
    # PnL = (13.048938 - 12.496484) * 760.974047 = 420.403156
    # Matches EXACTLY!
    
    print("\n--- Scenario A: Zero Slippage ---")
    diff_no_slip = (close_price_raw - open_price_raw) * quantity
    print(f"PnL with 0 slippage: ${diff_no_slip:.6f}")
    if abs(diff_no_slip - target_pnl) < 0.01:
        print("✅ Trade PnL match confirms: Slippage was effectively 0.0")
    else:
        print("❌ Trade PnL does not match zero slippage")
        
    # Now, why implies Equity Profit $426.54?
    # If PnL is $420.40, how can Profit be $426.54?
    # Profit = PnL - Fees
    # So $426.54 = $420.40 - Fees => Fees = -$6.14 (Negative Fee!)
    
    # Let's calculate Fee for Scenario A
    # Notional = 760.974 * 12.496... = $9509.16
    # If commission is 0.0004 (Default)
    # Fee Open = 9509.16 * 0.0004 = $3.80
    # Fee Close = ~9926 * 0.0004 = $3.97
    # Total Fee = $7.77
    # Profit should be $420.40 - $7.77 = $412.63
    
    # Gap: $426.54 - $412.63 = $13.91
    
    # Wait!
    # What if the config had NEGATIVE commission (Rebate)?
    # $420.40 + $6.14 = $426.54
    # Do we have a VIP tier with negative fees?
    # VIP0: Maker 0.02% / Taker 0.04% (Both positive)
    
    # What if...
    # The PnL recorded in Trade IS Net PnL (already deducted fees)?
    # If $420.40 is Net PnL.
    # Total Profit = Net PnL = $420.40.
    # Still doesn't match $426.54.
    
    # Let's simulate the EXACT code check
    portfolio = BacktestPortfolio(
        initial_capital=initial_capital,
        slippage=0.0, # Assumed from PnL match
        commission=0.0004 # Assumed default
    )
    portfolio.margin_config.leverage = leverage
    
    # 1. Open
    ts1 = datetime.now()
    trade_open = portfolio.open_position("LINKUSDT", Side.LONG, quantity, open_price_raw, ts1)
    
    print(f"\n[Open] Cash: ${portfolio.cash:.2f}")
    # Cash should be 10000 - Margin - Fee
    # Margin = 9509.16 / 10 = 950.92
    # Fee = 3.80
    # Expected Cash = 9045.28
    
    # 2. Close
    ts2 = datetime.now()
    trade_close = portfolio.close_position("LINKUSDT", close_price_raw, ts2)
    
    print(f"\n[Close] Cash: ${portfolio.cash:.2f}")
    print(f"Trade PnL Recorded: ${trade_close.pnl:.2f}")
    
    final_equity = portfolio.get_current_equity({})
    print(f"Final Equity: ${final_equity:.2f}")
    print(f"Profit Amount: ${final_equity - initial_capital:.2f}")
    
    # 3. Check for the "Double Deduction Fix" impact
    # Run 228343 was BEFORE or AFTER the fix?
    # User says "Backtest id228343 result profit $+426.54 > trade record $+420.40"
    # If run was AFTER the fix (which removed double deduction), then:
    # cash += initial_margin + pnl - commission
    # Trade PnL = pnl (Gross)
    
    # Profit = (Cash_After - Cash_Before)
    # Cash_After = Cash_Before - (Margin+Fee1) + (Margin+PnL-Fee2)
    # Profit = PnL - Fee1 - Fee2
    
    # So Math is strictly: Profit = GrossPnL - TotalFees
    # Profit < GrossPnL
    
    # The ONLY way Profit > GrossPnL is if Fees are negative.
    
    # OR...
    # Margin returned was LARGER than Margin deducted?
    # Open: Margin = Qty * OpenPrice / Leverage
    # Close: Margin = Qty * OpenPrice / Leverage
    # They use the SAME position.entry_price. So they should match.
    
    # UNLESS... position.entry_price changed?
    # Or Open price used was different?
    
if __name__ == "__main__":
    replicate_run_228343()
