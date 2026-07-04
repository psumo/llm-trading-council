"""
CLI Terminal Display Module for LLM-TradeBot
=============================================

Provides rich terminal output for headless mode, displaying:
- Real-time trading status
- Price updates
- Agent decisions
- Position and PnL tracking
"""

from datetime import datetime
from typing import Dict, Optional, List
import sys
import os

# Check if rich is available
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.style import Style
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("⚠️  Warning: 'rich' library not installed. Using basic terminal output.")
    print("   Install with: pip install rich")


class TerminalDisplay:
    """
    Terminal-based display for CLI/headless mode.
    Uses rich library for formatted output with fallback to basic print.
    """
    
    def __init__(self, symbols: List[str] = None):
        self.symbols = symbols or []
        self.console = Console() if HAS_RICH else None
        self.last_update = None
        self.cycle_count = 0
        
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self, test_mode: bool = True):
        """Print startup header"""
        mode_str = "🧪 TEST MODE" if test_mode else "🔴 LIVE TRADING"
        
        if HAS_RICH:
            header = Panel(
                f"[bold cyan]🤖 LLM-TradeBot CLI[/bold cyan]\n"
                f"[yellow]{mode_str}[/yellow]\n"
                f"[dim]Press Ctrl+C to stop[/dim]",
                box=box.DOUBLE,
                border_style="cyan"
            )
            self.console.print(header)
        else:
            print("=" * 60)
            print("🤖 LLM-TradeBot CLI")
            print(mode_str)
            print("Press Ctrl+C to stop")
            print("=" * 60)
    
    def print_cycle_start(self, cycle_num: int, symbols: List[str]):
        """Print cycle start banner"""
        self.cycle_count = cycle_num
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if HAS_RICH:
            self.console.print()
            self.console.rule(f"[bold blue]Cycle #{cycle_num}[/bold blue] | {', '.join(symbols)}", style="blue")
            self.console.print(f"[dim]{timestamp}[/dim]")
        else:
            print()
            print("=" * 60)
            print(f"🔄 Cycle #{cycle_num} | {', '.join(symbols)}")
            print(f"   {timestamp}")
            print("=" * 60)
    
    def print_price_update(self, symbol: str, price: float, change_pct: float = 0.0):
        """Print price update"""
        arrow = "↑" if change_pct > 0 else ("↓" if change_pct < 0 else "→")
        color = "green" if change_pct > 0 else ("red" if change_pct < 0 else "white")
        
        if HAS_RICH:
            self.console.print(f"  💰 [{color}]{symbol}[/{color}]: ${price:,.2f} {arrow} {change_pct:+.2f}%")
        else:
            print(f"  💰 {symbol}: ${price:,.2f} {arrow} {change_pct:+.2f}%")
    
    def print_decision(self, decision: Dict):
        """Print trading decision with details"""
        action = decision.get('action', 'UNKNOWN').upper()
        symbol = decision.get('symbol', 'N/A')
        confidence = decision.get('confidence', 0)
        reason = decision.get('reason', '')[:80]  # Truncate long reasons
        
        # Color based on action
        if action == 'LONG':
            action_style = "bold green"
            action_icon = "🟢"
        elif action == 'SHORT':
            action_style = "bold red"
            action_icon = "🔴"
        elif action in ['CLOSE', 'CLOSE_POSITION']:
            action_style = "bold yellow"
            action_icon = "🟡"
        else:  # HOLD/WAIT
            action_style = "dim"
            action_icon = "⏸️"
        
        if HAS_RICH:
            self.console.print()
            self.console.print(f"  {action_icon} [{action_style}]{action}[/{action_style}] | Confidence: {confidence:.1f}%")
            if reason:
                self.console.print(f"     [dim]{reason}[/dim]")
        else:
            print()
            print(f"  {action_icon} {action} | Confidence: {confidence:.1f}%")
            if reason:
                print(f"     {reason}")
    
    def print_position(self, position: Dict):
        """Print current position status"""
        if not position:
            if HAS_RICH:
                self.console.print("  📊 Position: [dim]None[/dim]")
            else:
                print("  📊 Position: None")
            return
        
        side = position.get('side', 'N/A').upper()
        entry = position.get('entry_price', 0)
        current = position.get('current_price', 0)
        pnl = position.get('unrealized_pnl', 0)
        pnl_pct = position.get('pnl_pct', 0)
        
        side_color = "green" if side == 'LONG' else "red"
        pnl_color = "green" if pnl >= 0 else "red"
        
        if HAS_RICH:
            self.console.print(
                f"  📊 Position: [{side_color}]{side}[/{side_color}] | "
                f"Entry: ${entry:,.2f} | Current: ${current:,.2f} | "
                f"PnL: [{pnl_color}]${pnl:+.2f} ({pnl_pct:+.2f}%)[/{pnl_color}]"
            )
        else:
            print(f"  📊 Position: {side} | Entry: ${entry:,.2f} | PnL: ${pnl:+.2f}")
    
    def print_account_summary(self, equity: float, available: float, pnl: float, initial: float = 0,
                               cycle: int = 0, positions: Dict = None, symbols: List[str] = None):
        """Print account summary with key trading information
        
        Args:
            equity: Total account equity
            available: Available balance
            pnl: Total PnL
            initial: Initial balance for PnL calculation
            cycle: Current cycle number
            positions: Dict of current positions {symbol: {side, entry_price, quantity, unrealized_pnl}}
            symbols: List of trading symbols
        """
        pnl_pct = (pnl / initial * 100) if initial > 0 else 0
        pnl_color = "green" if pnl >= 0 else "red"
        
        if HAS_RICH:
            self.console.print()
            table = Table(show_header=False, box=box.SIMPLE)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")
            
            # Cycle info
            table.add_row("🔄 Cycle", str(cycle) if cycle > 0 else "-")
            
            # Trading symbols
            if symbols:
                table.add_row("📊 Symbols", ", ".join(symbols))
            
            table.add_row("", "")  # Separator
            
            # Account info
            table.add_row("💰 Total Equity", f"${equity:,.2f}")
            table.add_row("📊 Available", f"${available:,.2f}")
            
            pnl_text = Text(f"${pnl:+,.2f} ({pnl_pct:+.2f}%)")
            pnl_text.stylize("green" if pnl >= 0 else "red")
            table.add_row("📈 Total PnL", pnl_text)
            
            # Position info
            if positions:
                table.add_row("", "")  # Separator
                for symbol, pos in positions.items():
                    side = pos.get('side', 'N/A')
                    entry_price = pos.get('entry_price', 0)
                    quantity = pos.get('quantity', 0)
                    unrealized_pnl = pos.get('unrealized_pnl', 0)
                    pnl_pct_pos = pos.get('pnl_pct', 0)
                    position_value = entry_price * quantity
                    
                    side_icon = "🟢" if side == 'LONG' else "🔴"
                    side_text = Text(f"{side_icon} {side}")
                    side_text.stylize("green" if side == 'LONG' else "red")
                    table.add_row(f"📍 {symbol}", side_text)
                    table.add_row("   Entry", f"${entry_price:,.2f}")
                    table.add_row("   Value", f"${position_value:,.2f}")
                    
                    pos_pnl_text = Text(f"${unrealized_pnl:+,.2f} ({pnl_pct_pos:+.1f}%)")
                    pos_pnl_text.stylize("green" if unrealized_pnl >= 0 else "red")
                    table.add_row("   PnL", pos_pnl_text)
            else:
                table.add_row("", "")  # Separator
                table.add_row("📍 Positions", "[dim]None[/dim]")
            
            self.console.print(Panel(table, title="Account Summary", border_style="cyan"))
        else:
            print()
            print("┌─ Account Summary ─────────────────────┐")
            if cycle > 0:
                print(f"│ 🔄 Cycle:     #{cycle:<24} │")
            if symbols:
                print(f"│ 📊 Symbols:   {', '.join(symbols):<24} │")
            print(f"│ 💰 Equity:    ${equity:>20,.2f} │")
            print(f"│ 📊 Available: ${available:>20,.2f} │")
            print(f"│ 📈 PnL:       ${pnl:>+20,.2f} │")
            if positions:
                for symbol, pos in positions.items():
                    side = pos.get('side', 'N/A')
                    position_value = pos.get('entry_price', 0) * pos.get('quantity', 0)
                    print(f"│ 📍 {symbol}: {side} ${position_value:>12,.2f} │")
            else:
                print(f"│ 📍 Positions: {'None':<22} │")
            print("└───────────────────────────────────────┘")
    
    def print_trade_executed(self, trade: Dict):
        """Print trade execution notification"""
        action = trade.get('action', 'TRADE')
        symbol = trade.get('symbol', 'N/A')
        price = trade.get('price', 0)
        quantity = trade.get('quantity', 0)
        
        if HAS_RICH:
            self.console.print()
            self.console.print(
                f"  🚀 [bold]TRADE EXECUTED[/bold]: {action} {symbol} | "
                f"Price: ${price:,.2f} | Qty: {quantity:.4f}",
                style="yellow"
            )
        else:
            print()
            print(f"  🚀 TRADE EXECUTED: {action} {symbol} @ ${price:,.2f}")
    
    def print_trade_closed(self, trade: Dict):
        """Print trade close notification with PnL"""
        symbol = trade.get('symbol', 'N/A')
        pnl = trade.get('pnl', 0)
        pnl_pct = trade.get('pnl_pct', 0)
        reason = trade.get('close_reason', 'manual')
        
        pnl_color = "green" if pnl >= 0 else "red"
        result_icon = "✅" if pnl >= 0 else "❌"
        
        if HAS_RICH:
            self.console.print(
                f"  {result_icon} [bold]POSITION CLOSED[/bold]: {symbol} | "
                f"PnL: [{pnl_color}]${pnl:+.2f} ({pnl_pct:+.2f}%)[/{pnl_color}] | "
                f"Reason: {reason}",
                style="yellow"
            )
        else:
            print(f"  {result_icon} POSITION CLOSED: {symbol} | PnL: ${pnl:+.2f} | {reason}")
    
    def print_waiting(self, minutes: float):
        """Print waiting message"""
        if HAS_RICH:
            self.console.print(f"\n  ⏳ [dim]Next cycle in {minutes:.1f} minutes...[/dim]")
        else:
            print(f"\n  ⏳ Next cycle in {minutes:.1f} minutes...")
    
    def print_log(self, message: str, level: str = "INFO"):
        """Print a log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        level_styles = {
            "INFO": "white",
            "WARNING": "yellow",
            "ERROR": "red",
            "SUCCESS": "green"
        }
        style = level_styles.get(level.upper(), "white")
        
        if HAS_RICH:
            self.console.print(f"  [{style}][{timestamp}] {message}[/{style}]")
        else:
            print(f"  [{timestamp}] {message}")
    
    def print_agent_status(self, agent_name: str, status: str, details: str = ""):
        """Print agent status update"""
        agent_icons = {
            "oracle": "🕵️",
            "strategist": "👨‍🔬",
            "prophet": "🔮",
            "bull": "🐂",
            "bear": "🐻",
            "critic": "⚖️",
            "guardian": "🛡️",
            "executor": "🚀"
        }
        icon = agent_icons.get(agent_name.lower(), "🤖")
        
        if HAS_RICH:
            self.console.print(f"  {icon} [cyan]{agent_name}[/cyan]: {status}", end="")
            if details:
                self.console.print(f" [dim]({details})[/dim]")
            else:
                self.console.print()
        else:
            print(f"  {icon} {agent_name}: {status}" + (f" ({details})" if details else ""))
    
    def print_four_layer_status(self, layer_results: Dict):
        """Print four-layer strategy status"""
        layers = [
            ("Layer 1 (Trend)", layer_results.get('layer1_pass')),
            ("Layer 2 (AI)", layer_results.get('layer2_pass')),
            ("Layer 3 (Setup)", layer_results.get('layer3_pass')),
            ("Layer 4 (Trigger)", layer_results.get('layer4_pass'))
        ]
        
        if HAS_RICH:
            status_line = "  📊 Strategy: "
            for name, passed in layers:
                icon = "✅" if passed else "❌"
                status_line += f"{icon} "
            self.console.print(status_line)
        else:
            status = " ".join(["✅" if p else "❌" for _, p in layers])
            print(f"  📊 Strategy: {status}")
    
    def print_shutdown(self, stats: Dict = None):
        """Print shutdown summary"""
        if HAS_RICH:
            self.console.print()
            self.console.rule("[bold red]Shutdown[/bold red]", style="red")
            
            if stats:
                table = Table(show_header=False, box=box.SIMPLE)
                table.add_column("Stat", style="cyan")
                table.add_column("Value", justify="right")
                
                table.add_row("Total Cycles", str(stats.get('cycles', 0)))
                table.add_row("Total Trades", str(stats.get('trades', 0)))
                
                pnl = stats.get('total_pnl', 0)
                pnl_style = "green" if pnl >= 0 else "red"
                table.add_row("Total PnL", f"[{pnl_style}]${pnl:+,.2f}[/{pnl_style}]")
                
                self.console.print(Panel(table, title="Session Summary", border_style="red"))
            
            self.console.print("\n[bold]👋 Goodbye![/bold]\n")
        else:
            print()
            print("=" * 40)
            print("⏹️  SHUTDOWN")
            if stats:
                print(f"   Cycles: {stats.get('cycles', 0)}")
                print(f"   Trades: {stats.get('trades', 0)}")
                print(f"   PnL: ${stats.get('total_pnl', 0):+,.2f}")
            print("=" * 40)
            print("👋 Goodbye!")


# Singleton instance for easy access
_display_instance = None

def get_display(symbols: List[str] = None) -> TerminalDisplay:
    """Get or create the singleton terminal display"""
    global _display_instance
    if _display_instance is None:
        _display_instance = TerminalDisplay(symbols)
    return _display_instance
