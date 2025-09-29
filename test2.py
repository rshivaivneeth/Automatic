import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
import warnings
from datetime import datetime, timedelta
import talib
import schedule
import threading
from typing import Dict, List, Optional, Tuple
from tabulate import tabulate
import json
from dataclasses import dataclass
from enum import Enum

warnings.filterwarnings('ignore')

# ============================
# ENHANCED CONFIGURATION
# ============================

# Telegram Configuration
TELEGRAM_BOT_TOKEN = '7933607173:AAFND1Z_GxNdvKwOc4Y_LUuX327eEpc2KIE'
TELEGRAM_CHAT_ID = ['1012793457','1209666577']

# Trading Configuration
TICKERS = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ITC.NS', 
           'BHARTIARTL.NS', 'SBIN.NS', 'LT.NS', 'HCLTECH.NS', 'WIPRO.NS']

CHECK_INTERVAL = 60 * 5  # Keep 5 minutes like bulk.py for consistent alerts
SHARES_TO_BUY = 2
ATR_MULTIPLIER = 1.5  # Keep same as bulk.py
RSI_OVERSOLD = 30      # Keep same as bulk.py
RSI_OVERBOUGHT = 70

# Enhanced parameters
VOLUME_SPIKE_THRESHOLD = 1.5  # Reduced from 2.0 for more sensitivity
BREAKOUT_LOOKBACK = 20
TREND_STRENGTH_PERIOD = 10
MOMENTUM_THRESHOLD = 0.02

# Market Hours (IST)
MARKET_START = "00:15"
MARKET_END = "23:45"
ALIVE_CHECK_MORNING = "09:15"
ALIVE_CHECK_EVENING = "15:00"

# ============================
# ENHANCED DATA STRUCTURES
# ============================

class SignalStrength(Enum):
    VERY_WEAK = 1
    WEAK = 2
    MODERATE = 3
    STRONG = 4
    VERY_STRONG = 5

@dataclass
class TradingSignal:
    action: str  # BUY, SELL, HOLD
    strength: SignalStrength
    confidence: float  # 0-100
    reasons: List[str]
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None

@dataclass
class AdvancedIndicators:
    # Basic indicators (keep compatibility with bulk.py)
    sma_20: float = 0.0
    sma_50: float = 0.0
    rsi: float = 0.0
    atr: float = 0.0
    volume_spike: bool = False
    volume_sma: float = 0.0
    
    # Enhanced indicators
    ema_12: float = 0.0
    ema_26: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    stoch_k: float = 0.0
    stoch_d: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    
    # Price levels
    price_52w_high: float = 0.0
    price_52w_low: float = 0.0
    support_level: float = 0.0
    resistance_level: float = 0.0
    
    # Pattern detection
    is_breakout: bool = False
    breakout_direction: str = "NONE"
    trend_strength: float = 0.0

class EnhancedStockMemory:
    def __init__(self):
        self.holdings = {}  # Same structure as bulk.py
        self.sell_thresholds = {}
        self.highest_prices = {}
        self.alerts_sent = {}
        self.last_action_status = {}
        self.last_alive_check = None
        
        # Enhanced memory
        self.price_history = {}
        self.signal_history = {}
        self.performance_metrics = {}

memory = EnhancedStockMemory()

# ============================
# TELEGRAM FUNCTIONS (Compatible with bulk.py)
# ============================

def send_telegram_message(message: str):
    """Send message to all configured Telegram chats (same as bulk.py)"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print(f"[TELEGRAM] {message}")
        return
    
    for chat_id in TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, data=data, timeout=10)
            if response.status_code != 200:
                print(f"Failed to send telegram message: {response.text}")
        except Exception as e:
            print(f"Telegram error: {e}")

def send_alive_notification():
    """Send bot alive notification (same as bulk.py)"""
    current_time = datetime.now().strftime("%H:%M")
    
    # Calculate active positions
    active_positions = sum(1 for ticker in memory.holdings if memory.holdings[ticker].get('shares', 0) > 0)
    
    message = f"✅ *Stock Trading Bot is ALIVE* - {current_time}\n"
    message += f"📊 Monitoring {len(TICKERS)} stocks\n"
    message += f"💼 Active positions: {active_positions}\n"
    message += f"🚀 Enhanced with advanced indicators"
    
    send_telegram_message(message)
    memory.last_alive_check = datetime.now()

# ============================
# DATA FETCHING (Same as bulk.py)
# ============================

def get_stock_data(ticker: str, period: str = "3mo") -> Optional[pd.DataFrame]:
    """Fetch stock data from Yahoo Finance"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)
        if df.empty:
            print(f"No data for {ticker}")
            return None
        return df
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None

def get_realtime_data(ticker: str) -> Optional[Dict]:
    """Get real-time stock data"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1d", interval="1m")
        if df.empty:
            return None
        
        current_price = df['Close'].iloc[-1]
        return {
            'price': current_price,
            'volume': df['Volume'].iloc[-1],
            'high': df['High'].iloc[-1],
            'low': df['Low'].iloc[-1]
        }
    except Exception as e:
        print(f"Error getting real-time data for {ticker}: {e}")
        return None

def has_earnings_soon(ticker: str) -> bool:
    """Check if stock has earnings in next 2 days"""
    try:
        stock = yf.Ticker(ticker)
        calendar = stock.calendar
        if calendar is not None and not calendar.empty:
            next_earnings = pd.to_datetime(calendar.index[0])
            days_until = (next_earnings - datetime.now()).days
            return days_until <= 2
    except:
        pass
    return False

# ============================
# ENHANCED TECHNICAL INDICATORS
# ============================

def safe_extract(arr, default=0.0):
    """Safely extract last value from array"""
    if arr is None or len(arr) == 0:
        return default
    val = arr[-1]
    return float(val) if not np.isnan(val) else default

def calculate_enhanced_indicators(df: pd.DataFrame) -> AdvancedIndicators:
    """Calculate enhanced technical indicators while maintaining bulk.py compatibility"""
    try:
        if len(df) < 50:
            return AdvancedIndicators()
        
        close = df['Close'].values
        high = df['High'].values
        low = df['Low'].values
        volume = df['Volume'].values
        
        indicators = AdvancedIndicators()
        
        # Basic indicators (same as bulk.py)
        indicators.sma_20 = safe_extract(talib.SMA(close, 20))
        indicators.sma_50 = safe_extract(talib.SMA(close, 50))
        indicators.rsi = safe_extract(talib.RSI(close, 14))
        indicators.atr = safe_extract(talib.ATR(high, low, close, 14))
        
        # Volume analysis (same logic as bulk.py)
        volume_float = volume.astype(float)
        indicators.volume_sma = safe_extract(talib.SMA(volume_float, 20))
        if indicators.volume_sma > 0 and len(volume) > 0:
            indicators.volume_spike = volume[-1] > (indicators.volume_sma * VOLUME_SPIKE_THRESHOLD)
        
        # Enhanced indicators
        indicators.ema_12 = safe_extract(talib.EMA(close, 12))
        indicators.ema_26 = safe_extract(talib.EMA(close, 26))
        
        # MACD
        macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        indicators.macd = safe_extract(macd)
        indicators.macd_signal = safe_extract(macd_signal)
        indicators.macd_histogram = safe_extract(macd_hist)
        
        # Stochastic
        indicators.stoch_k, indicators.stoch_d = talib.STOCH(high, low, close)
        indicators.stoch_k = safe_extract(indicators.stoch_k)
        indicators.stoch_d = safe_extract(indicators.stoch_d)
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
        indicators.bb_upper = safe_extract(bb_upper)
        indicators.bb_middle = safe_extract(bb_middle)
        indicators.bb_lower = safe_extract(bb_lower)
        
        # Price levels (same as bulk.py)
        indicators.price_52w_high = float(df['High'].max())
        indicators.price_52w_low = float(df['Low'].min())
        
        # Support/Resistance
        indicators.support_level, indicators.resistance_level = calculate_support_resistance(df)
        
        # Pattern detection
        indicators.is_breakout, indicators.breakout_direction = detect_breakout(df, close[-1])
        indicators.trend_strength = calculate_trend_strength(df)
        
        return indicators
        
    except Exception as e:
        print(f"Error calculating enhanced indicators: {e}")
        return AdvancedIndicators()

def calculate_support_resistance(df: pd.DataFrame) -> Tuple[float, float]:
    """Calculate support and resistance levels"""
    try:
        recent_data = df.tail(20)
        resistance = recent_data['High'].max()
        support = recent_data['Low'].min()
        return float(support), float(resistance)
    except:
        return 0.0, 0.0

def detect_breakout(df: pd.DataFrame, current_price: float) -> Tuple[bool, str]:
    """Detect breakout patterns"""
    try:
        recent_high = df['High'].tail(20).max()
        recent_low = df['Low'].tail(20).min()
        
        if current_price > recent_high * 1.01:  # 1% above recent high
            return True, "BULLISH"
        elif current_price < recent_low * 0.99:  # 1% below recent low
            return True, "BEARISH"
        
        return False, "NONE"
    except:
        return False, "NONE"

def calculate_trend_strength(df: pd.DataFrame) -> float:
    """Calculate trend strength"""
    try:
        returns = df['Close'].pct_change().tail(20)
        positive_days = (returns > 0).sum()
        return float(positive_days / len(returns))
    except:
        return 0.0

# ============================
# ENHANCED TRADING LOGIC (Compatible with bulk.py structure)
# ============================

def should_buy_enhanced(ticker: str, indicators: AdvancedIndicators, current_price: float) -> bool:
    """Enhanced buy logic while maintaining bulk.py compatibility"""
    # Don't buy if already holding (same as bulk.py)
    if ticker in memory.holdings and memory.holdings[ticker].get('shares', 0) > 0:
        return False
    
    # Skip if earnings soon (same as bulk.py)
    if has_earnings_soon(ticker):
        return False
    
    # Enhanced conditions with fallback to bulk.py logic
    try:
        # Basic trend condition (same as bulk.py)
        if indicators.sma_20 > 0 and indicators.sma_50 > 0:
            trend_bullish = indicators.sma_20 > indicators.sma_50
        else:
            trend_bullish = False
        
        # RSI condition (same range as bulk.py)
        rsi_good = RSI_OVERSOLD < indicators.rsi < RSI_OVERBOUGHT
        
        # Enhanced conditions
        macd_bullish = indicators.macd > indicators.macd_signal
        volume_support = indicators.volume_spike or True  # Allow without volume spike
        
        # Combine conditions
        basic_conditions = trend_bullish and rsi_good
        enhanced_conditions = macd_bullish and volume_support
        
        return basic_conditions and enhanced_conditions
        
    except Exception as e:
        print(f"Error in enhanced buy logic for {ticker}: {e}")
        # Fallback to basic logic
        if indicators.sma_20 > indicators.sma_50 and RSI_OVERSOLD < indicators.rsi < RSI_OVERBOUGHT:
            return True
        return False

def should_sell_enhanced(ticker: str, current_price: float) -> bool:
    """Enhanced sell logic (same structure as bulk.py)"""
    if ticker not in memory.holdings or memory.holdings[ticker].get('shares', 0) == 0:
        return False
    
    # Check trailing stop-loss (same as bulk.py)
    if ticker in memory.sell_thresholds:
        return current_price <= memory.sell_thresholds[ticker]
    
    return False

def execute_buy_enhanced(ticker: str, current_price: float, indicators: AdvancedIndicators):
    """Execute buy with enhanced features but same notification as bulk.py"""
    atr = indicators.atr
    if atr <= 0:
        atr = current_price * 0.02
    
    # Initialize memory (same structure as bulk.py)
    memory.holdings[ticker] = {
        'shares': SHARES_TO_BUY,
        'entry_price': current_price
    }
    
    memory.sell_thresholds[ticker] = current_price - (ATR_MULTIPLIER * atr)
    memory.highest_prices[ticker] = current_price
    
    if ticker not in memory.alerts_sent:
        memory.alerts_sent[ticker] = {'52w_high': False}
    
    # Send notification (same format as bulk.py but with enhanced info)
    symbol = ticker.replace('.NS', '').replace('.BO', '')
    
    message = f"🟢 *BUY SIGNAL* (Enhanced)\n"
    message += f"📈 {symbol} - ₹{current_price:.2f}\n"
    message += f"💰 Bought {SHARES_TO_BUY} shares\n"
    message += f"🛑 Stop-loss: ₹{memory.sell_thresholds[ticker]:.2f}\n"
    message += f"📊 RSI: {indicators.rsi:.1f}\n"
    message += f"📈 MACD: {indicators.macd:.3f}\n"
    message += f"🔥 Volume Spike: {'Yes' if indicators.volume_spike else 'No'}"
    
    send_telegram_message(message)
    print(f"[ENHANCED BUY] {symbol} @ ₹{current_price:.2f}")

def execute_sell_enhanced(ticker: str, current_price: float, reason: str = "Stop-loss"):
    """Execute sell (same as bulk.py with enhanced info)"""
    if ticker not in memory.holdings:
        return
    
    shares = memory.holdings[ticker].get('shares', 0)
    entry_price = memory.holdings[ticker].get('entry_price', 0)
    
    if shares == 0:
        return
    
    # Calculate P&L (same as bulk.py)
    total_change = (current_price - entry_price) * shares
    change_percent = ((current_price - entry_price) / entry_price) * 100
    
    # Clear position (same as bulk.py)
    memory.holdings[ticker] = {'shares': 0, 'entry_price': 0}
    if ticker in memory.sell_thresholds:
        del memory.sell_thresholds[ticker]
    if ticker in memory.highest_prices:
        del memory.highest_prices[ticker]
    
    memory.alerts_sent[ticker] = {'52w_high': False}
    
    # Send notification (same format as bulk.py)
    symbol = ticker.replace('.NS', '').replace('.BO', '')
    profit_emoji = "💚" if total_change >= 0 else "❌"
    
    message = f"🔴 *SELL SIGNAL* - {reason}\n"
    message += f"📉 {symbol} - ₹{current_price:.2f}\n"
    message += f"💼 Sold {shares} shares\n"
    message += f"{profit_emoji} P&L: ₹{total_change:.2f} ({change_percent:+.2f}%)"
    
    send_telegram_message(message)
    print(f"[ENHANCED SELL] {symbol} @ ₹{current_price:.2f} | P&L: ₹{total_change:.2f}")

def update_trailing_stop(ticker: str, current_price: float, atr: float):
    """Update trailing stop (same as bulk.py)"""
    if ticker not in memory.holdings or memory.holdings[ticker].get('shares', 0) == 0:
        return
    
    if atr <= 0:
        atr = current_price * 0.02
    
    if ticker not in memory.highest_prices:
        memory.highest_prices[ticker] = current_price
    else:
        memory.highest_prices[ticker] = max(memory.highest_prices[ticker], current_price)
    
    new_stop = memory.highest_prices[ticker] - (ATR_MULTIPLIER * atr)
    
    if ticker not in memory.sell_thresholds:
        memory.sell_thresholds[ticker] = new_stop
    else:
        memory.sell_thresholds[ticker] = max(memory.sell_thresholds[ticker], new_stop)

def check_52w_high_alert(ticker: str, current_price: float, indicators: AdvancedIndicators):
    """Check 52-week high alert (same as bulk.py with enhanced info)"""
    if ticker not in memory.holdings or memory.holdings[ticker].get('shares', 0) == 0:
        return
    
    if ticker not in memory.alerts_sent:
        memory.alerts_sent[ticker] = {'52w_high': False}
    
    high_52w = indicators.price_52w_high
    if high_52w > 0 and abs(current_price - high_52w) <= 0.5:
        if not memory.alerts_sent[ticker]['52w_high']:
            symbol = ticker.replace('.NS', '').replace('.BO', '')
            message = f"📈 *52-WEEK HIGH ALERT*\n"
            message += f"🔥 {symbol} reached ₹{current_price:.2f}\n"
            message += f"📊 52W High: ₹{high_52w:.2f}\n"
            message += f"💭 Consider SELL or HOLD decision"
            
            send_telegram_message(message)
            memory.alerts_sent[ticker]['52w_high'] = True

# ============================
# MAIN ANALYSIS FUNCTION
# ============================

def analyze_stock_enhanced(ticker: str):
    """Enhanced stock analysis with better error handling"""
    try:
        # Get historical data
        historical_df = get_stock_data(ticker, period="3mo")
        if historical_df is None or historical_df.empty:
            print(f"No historical data for {ticker}")
            return
        
        # Calculate enhanced indicators
        indicators = calculate_enhanced_indicators(historical_df)
        
        # Get real-time price
        realtime_data = get_realtime_data(ticker)
        if not realtime_data:
            print(f"No real-time data for {ticker}")
            return
        
        current_price = realtime_data['price']
        
        # Update trailing stop if holding
        if ticker in memory.holdings and memory.holdings[ticker].get('shares', 0) > 0:
            update_trailing_stop(ticker, current_price, indicators.atr)
            check_52w_high_alert(ticker, current_price, indicators)
        
        # Trading decisions
        if should_sell_enhanced(ticker, current_price):
            execute_sell_enhanced(ticker, current_price)
        elif should_buy_enhanced(ticker, indicators, current_price):
            execute_buy_enhanced(ticker, current_price, indicators)
        
        # Update status
        new_status = "HOLD" if (ticker in memory.holdings and memory.holdings[ticker].get('shares', 0) > 0) else "WAIT"
        memory.last_action_status[ticker] = new_status
        
    except Exception as e:
        print(f"Error analyzing {ticker}: {e}")
        import traceback
        traceback.print_exc()

# ============================
# CONSOLE OUTPUT (Same as bulk.py)
# ============================

def print_enhanced_status_table():
    """Print enhanced status table (same format as bulk.py with extra columns)"""
    table_data = []
    
    for ticker in TICKERS:
        try:
            symbol = ticker.replace('.NS', '').replace('.BO', '')
            
            # Get current price
            realtime_data = get_realtime_data(ticker)
            current_price = realtime_data['price'] if realtime_data else 0.0
            
            # Get indicators
            historical_df = get_stock_data(ticker, period="3mo")
            if historical_df is not None and not historical_df.empty:
                indicators = calculate_enhanced_indicators(historical_df)
            else:
                indicators = AdvancedIndicators()
            
            # Position details (same as bulk.py)
            status = memory.last_action_status.get(ticker, 'WAIT')
            entry_price = 0.0
            sell_threshold = 0.0
            change_percent = 0.0
            
            if ticker in memory.holdings and memory.holdings[ticker].get('shares', 0) > 0:
                entry_price = memory.holdings[ticker]['entry_price']
                sell_threshold = memory.sell_thresholds.get(ticker, 0.0)
                if entry_price > 0:
                    change_percent = ((current_price - entry_price) / entry_price) * 100
                status = 'HOLD'
            else:
                status = 'WAIT'
            
            # Format values
            current_price_str = f"₹{current_price:.2f}" if current_price > 0 else "N/A"
            entry_price_str = f"₹{entry_price:.2f}" if entry_price > 0 else "--"
            sma_20_str = f"₹{indicators.sma_20:.2f}" if indicators.sma_20 > 0 else "N/A"
            sma_50_str = f"₹{indicators.sma_50:.2f}" if indicators.sma_50 > 0 else "N/A"
            atr_str = f"{indicators.atr:.2f}" if indicators.atr > 0 else "N/A"
            rsi_str = f"{indicators.rsi:.1f}" if indicators.rsi > 0 else "N/A"
            macd_str = f"{indicators.macd:.3f}" if indicators.macd != 0 else "N/A"
            sell_threshold_str = f"₹{sell_threshold:.2f}" if sell_threshold > 0 else "--"
            change_percent_str = f"{change_percent:+.2f}%" if change_percent != 0 else "--"
            volume_str = "🔥" if indicators.volume_spike else "📊"
            
            table_data.append([
                symbol,
                current_price_str,
                entry_price_str,
                sma_20_str,
                sma_50_str,
                atr_str,
                rsi_str,
                macd_str,
                sell_threshold_str,
                change_percent_str,
                volume_str,
                status
            ])
            
        except Exception as e:
            table_data.append([
                symbol, "ERROR", "--", "--", "--", "--", "--", "--", "--", "--", "❌", "ERROR"
            ])
            print(f"Error processing {ticker}: {e}")
    
    # Print table
    print("\n" + "="*140)
    print("ENHANCED STOCK TRADING BOT - DETAILED STATUS")
    print("="*140)
    print(tabulate(table_data, headers=[
        "Ticker", "Current Price", "Entry Price", "20-SMA", "50-SMA",
        "ATR", "RSI", "MACD", "Sell Threshold", "Change %", "Vol", "Action"
    ], tablefmt="grid"))
    print("="*140)
    
    # Summary
    total_positions = len([row for row in table_data if row[11] == 'HOLD'])
    waiting_positions = len([row for row in table_data if row[11] == 'WAIT'])
    print(f"SUMMARY: {total_positions} HOLD | {waiting_positions} WAIT | Last Updated: {datetime.now().strftime('%H:%M:%S')}")
    print("="*140)

# ============================
# TIME MANAGEMENT (Same as bulk.py)
# ============================

def is_market_hours() -> bool:
    """Check if market is open"""
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    if now.weekday() >= 5:
        return False
    
    return MARKET_START <= current_time <= MARKET_END

def is_alive_check_time() -> bool:
    """Check if it's time for alive notification"""
    current_time = datetime.now().strftime("%H:%M")
    morning_range = "09:15" <= current_time <= "09:30"
    evening_range = "15:00" <= current_time <= "15:15"
    
    return morning_range or evening_range

# ============================
# MAIN LOOP
# ============================

def main_enhanced_trading_loop():
    """Enhanced main trading loop with same structure as bulk.py"""
    print("🚀 Enhanced Stock Trading Bot Started!")
    send_telegram_message("🚀 *Enhanced Stock Trading Bot Started!*\n📊 Enhanced with advanced indicators\n⚡ Monitoring stocks every 5 minutes")
    
    while True:
        try:
            current_time = datetime.now()
            
            # Send alive notifications
            if is_alive_check_time():
                if (memory.last_alive_check is None or 
                    (current_time - memory.last_alive_check).total_seconds() > 3600):
                    send_alive_notification()
            
            # Only trade during market hours
            if not is_market_hours():
                print(f"[{current_time.strftime('%H:%M:%S')}] Market closed. Waiting...")
                time.sleep(CHECK_INTERVAL)
                continue
            
            print(f"\n[{current_time.strftime('%H:%M:%S')}] Analyzing stocks with enhanced indicators...")
            
            # Analyze all stocks
            for ticker in TICKERS:
                analyze_stock_enhanced(ticker)
                time.sleep(1)  # Small delay between stocks
            
            # Print enhanced status table every 15 minutes or during alive check
            if current_time.minute % 15 == 0 and current_time.second < 30:
                print_enhanced_status_table()
            elif is_alive_check_time():
                print_enhanced_status_table()
            
            print(f"[{current_time.strftime('%H:%M:%S')}] Enhanced analysis complete. Waiting {CHECK_INTERVAL//60} minutes...")
            
        except KeyboardInterrupt:
            print("\n🛑 Enhanced Bot stopped by user")
            send_telegram_message("🛑 *Enhanced Bot Stopped*\nTrading bot has been manually stopped")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            send_telegram_message(f"❌ *Bot Error*\nError: {str(e)}\nBot continuing...")
            import traceback
            traceback.print_exc()
        
        time.sleep(CHECK_INTERVAL)

# ============================
# ENTRY POINT
# ============================

if __name__ == "__main__":
    # Verify required libraries
    try:
        import talib
        from tabulate import tabulate
        print("✅ All required libraries verified")
    except ImportError as e:
        if 'talib' in str(e):
            print("ERROR: TA-Lib not installed. Install with: pip install TA-Lib")
            print("On Windows, you might need to download the wheel from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib")
        elif 'tabulate' in str(e):
            print("ERROR: tabulate not installed. Install with: pip install tabulate")
        exit(1)
    
    # Configuration check
    if TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("⚠️  WARNING: Telegram bot token not configured. Messages will print to console.")
    
    print("🔧 Enhanced Configuration:")
    print(f"• Check Interval: {CHECK_INTERVAL//60} minutes")
    print(f"• ATR Multiplier: {ATR_MULTIPLIER}")
    print(f"• Volume Spike Threshold: {VOLUME_SPIKE_THRESHOLD}x")
    print(f"• RSI Levels: {RSI_OVERSOLD}-{RSI_OVERBOUGHT}")
    print(f"• Monitoring {len(TICKERS)} stocks")
    print(f"• Enhanced with MACD, Stochastic, Bollinger Bands")
    
    # Start the enhanced trading bot
    main_enhanced_trading_loop()