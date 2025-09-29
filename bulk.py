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
from typing import Dict, List, Optional
from tabulate import tabulate

warnings.filterwarnings('ignore')

# ============================
# CONFIGURATION
# ============================

# Telegram Configuration
TELEGRAM_BOT_TOKEN = '7933607173:AAFND1Z_GxNdvKwOc4Y_LUuX327eEpc2KIE'  # Replace with your bot token
TELEGRAM_CHAT_ID = ['1012793457','1209666577']    # Replace with your chat IDs

# Trading Configuration
TICKERS = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ITC.NS', 
           'BHARTIARTL.NS', 'SBIN.NS', 'LT.NS', 'HCLTECH.NS', 'WIPRO.NS']

CHECK_INTERVAL = 60 * 5  # 5 minutes
SHARES_TO_BUY = 2
ATR_MULTIPLIER = 1.5
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# Market Hours (IST)
MARKET_START = "00:15"
MARKET_END = "23:45"
ALIVE_CHECK_MORNING = "09:15"
ALIVE_CHECK_EVENING = "15:00"

# ============================
# GLOBAL VARIABLES
# ============================

class StockMemory:
    def __init__(self):
        self.holdings = {}  # {ticker: {'shares': int, 'entry_price': float}}
        self.sell_thresholds = {}  # {ticker: float}
        self.highest_prices = {}  # {ticker: float}
        self.alerts_sent = {}  # {ticker: {'52w_high': bool}}
        self.last_action_status = {}  # {ticker: 'HOLD'/'WAIT'}
        self.last_alive_check = None

memory = StockMemory()

# ============================
# TELEGRAM FUNCTIONS
# ============================

def send_telegram_message(message: str):
    """Send message to all configured Telegram chats"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print(f"[TELEGRAM] {message}")  # Print to console if no token
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
    """Send bot alive notification"""
    current_time = datetime.now().strftime("%H:%M")
    message = f"✅ *Stock Trading Bot is ALIVE* - {current_time}\n"
    message += f"📊 Monitoring {len(TICKERS)} stocks\n"
    message += f"💼 Active positions: {len([t for t in memory.holdings if memory.holdings[t]['shares'] > 0])}"
    send_telegram_message(message)
    memory.last_alive_check = datetime.now()

# ============================
# TECHNICAL INDICATORS
# ============================

def calculate_indicators(df: pd.DataFrame) -> Dict:
    """Calculate technical indicators"""
    try:
        close_prices = df['Close'].values
        high_prices = df['High'].values
        low_prices = df['Low'].values
        volume = df['Volume'].values
        
        # Ensure we have enough data
        if len(close_prices) < 50:
            print("Not enough data for indicators calculation")
            return {}
        
        # Simple Moving Averages
        sma_20 = talib.SMA(close_prices, timeperiod=20)
        sma_50 = talib.SMA(close_prices, timeperiod=50)
        
        # RSI
        rsi = talib.RSI(close_prices, timeperiod=14)
        
        # ATR
        atr = talib.ATR(high_prices, low_prices, close_prices, timeperiod=14)
        
        # Volume analysis
        volume_sma = talib.SMA(volume.astype(float), timeperiod=20)
        volume_spike = False
        if len(volume_sma) > 0 and not np.isnan(volume_sma[-1]) and volume_sma[-1] > 0:
            volume_spike = volume[-1] > (volume_sma[-1] * 1.5)
        
        # Safely extract values
        def safe_extract(arr, default=None):
            if arr is None or len(arr) == 0:
                return default
            val = arr[-1]
            return float(val) if not np.isnan(val) else default
        
        # Build result dictionary
        result = {
            'sma_20': safe_extract(sma_20),
            'sma_50': safe_extract(sma_50),
            'rsi': safe_extract(rsi),
            'atr': safe_extract(atr),
            'volume_spike': volume_spike,
            '52w_high': float(df['High'].max()),
            '52w_low': float(df['Low'].min())
        }
        
        return result
        
    except Exception as e:
        print(f"Error calculating indicators: {e}")
        import traceback
        traceback.print_exc()
        return {}

# ============================
# DATA FETCHING
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
        # Get 1-day data with 1-minute intervals for most recent price
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
    """Check if stock has earnings in next 2 days (simplified)"""
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
# TRADING LOGIC
# ============================

def should_buy(ticker: str, indicators: Dict, current_price: float) -> bool:
    """Determine if we should buy the stock"""
    try:
        # Don't buy if already holding
        if ticker in memory.holdings and memory.holdings[ticker]['shares'] > 0:
            return False
        
        # Skip if earnings soon
        if has_earnings_soon(ticker):
            return False
        
        # Technical conditions
        sma_20 = indicators.get('sma_20')
        sma_50 = indicators.get('sma_50')
        rsi = indicators.get('rsi')
        
        if None in [sma_20, sma_50, rsi]:
            return False
        
        # Buy conditions: SMA20 > SMA50 and RSI between 30-70
        trend_bullish = sma_20 > sma_50
        rsi_good = RSI_OVERSOLD < rsi < RSI_OVERBOUGHT
        
        return trend_bullish and rsi_good
        
    except Exception as e:
        print(f"Error in should_buy for {ticker}: {e}")
        return False

def should_sell(ticker: str, current_price: float) -> bool:
    """Determine if we should sell the stock"""
    if ticker not in memory.holdings or memory.holdings[ticker]['shares'] == 0:
        return False
    
    # Check trailing stop-loss
    if ticker in memory.sell_thresholds:
        return current_price <= memory.sell_thresholds[ticker]
    
    return False

def execute_buy(ticker: str, current_price: float, indicators: Dict):
    """Execute buy order"""
    atr = indicators.get('atr', 0)
    
    # Ensure ATR is valid
    if atr is None or atr <= 0:
        atr = current_price * 0.02  # Use 2% as fallback ATR
    
    # Initialize memory for this ticker
    memory.holdings[ticker] = {
        'shares': SHARES_TO_BUY,
        'entry_price': current_price
    }
    
    # Set initial trailing stop-loss
    memory.sell_thresholds[ticker] = current_price - (ATR_MULTIPLIER * atr)
    memory.highest_prices[ticker] = current_price
    
    # Initialize alerts
    if ticker not in memory.alerts_sent:
        memory.alerts_sent[ticker] = {'52w_high': False}
    
    # Send notification
    symbol = ticker.replace('.NS', '').replace('.BO', '')
    rsi_val = indicators.get('rsi', 0)
    rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "N/A"
    
    message = f"🟢 *BUY SIGNAL*\n"
    message += f"📈 {symbol} - ₹{current_price:.2f}\n"
    message += f"💰 Bought {SHARES_TO_BUY} shares\n"
    message += f"🛑 Stop-loss: ₹{memory.sell_thresholds[ticker]:.2f}\n"
    message += f"📊 RSI: {rsi_str}"
    
    send_telegram_message(message)
    print(f"[BUY] {symbol} @ ₹{current_price:.2f}")

def execute_sell(ticker: str, current_price: float, reason: str = "Stop-loss"):
    """Execute sell order"""
    if ticker not in memory.holdings:
        return
    
    shares = memory.holdings[ticker]['shares']
    entry_price = memory.holdings[ticker]['entry_price']
    
    # Calculate P&L
    total_change = (current_price - entry_price) * shares
    change_percent = ((current_price - entry_price) / entry_price) * 100
    
    # Clear position
    memory.holdings[ticker] = {'shares': 0, 'entry_price': 0}
    if ticker in memory.sell_thresholds:
        del memory.sell_thresholds[ticker]
    if ticker in memory.highest_prices:
        del memory.highest_prices[ticker]
    
    # Reset alerts
    memory.alerts_sent[ticker] = {'52w_high': False}
    
    # Send notification
    symbol = ticker.replace('.NS', '').replace('.BO', '')
    profit_emoji = "💚" if total_change >= 0 else "❌"
    
    message = f"🔴 *SELL SIGNAL* - {reason}\n"
    message += f"📉 {symbol} - ₹{current_price:.2f}\n"
    message += f"💼 Sold {shares} shares\n"
    message += f"{profit_emoji} P&L: ₹{total_change:.2f} ({change_percent:+.2f}%)"
    
    send_telegram_message(message)
    print(f"[SELL] {symbol} @ ₹{current_price:.2f} | P&L: ₹{total_change:.2f}")

def update_trailing_stop(ticker: str, current_price: float, atr: float):
    """Update trailing stop-loss"""
    if ticker not in memory.holdings or memory.holdings[ticker]['shares'] == 0:
        return
    
    # Ensure ATR is valid
    if atr is None or atr <= 0:
        atr = current_price * 0.02  # Use 2% as fallback ATR
    
    # Update highest price seen
    if ticker not in memory.highest_prices:
        memory.highest_prices[ticker] = current_price
    else:
        memory.highest_prices[ticker] = max(memory.highest_prices[ticker], current_price)
    
    # Update trailing stop
    new_stop = memory.highest_prices[ticker] - (ATR_MULTIPLIER * atr)
    
    if ticker not in memory.sell_thresholds:
        memory.sell_thresholds[ticker] = new_stop
    else:
        memory.sell_thresholds[ticker] = max(memory.sell_thresholds[ticker], new_stop)

def check_52w_high_alert(ticker: str, current_price: float, indicators: Dict):
    """Check and send 52-week high alert"""
    if ticker not in memory.holdings or memory.holdings[ticker]['shares'] == 0:
        return
    
    if ticker not in memory.alerts_sent:
        memory.alerts_sent[ticker] = {'52w_high': False}
    
    # Check if close to 52-week high
    high_52w = indicators.get('52w_high', 0)
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
# TIME MANAGEMENT
# ============================

def is_market_hours() -> bool:
    """Check if market is open"""
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    # Check if it's a weekday
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    return MARKET_START <= current_time <= MARKET_END

def is_alive_check_time() -> bool:
    """Check if it's time for alive notification"""
    current_time = datetime.now().strftime("%H:%M")
    morning_range = "09:15" <= current_time <= "09:30"
    evening_range = "15:00" <= current_time <= "15:15"
    
    return morning_range or evening_range

def is_friday_exit_time() -> bool:
    """Check if it's Friday 3:20 PM for position exit"""
    now = datetime.now()
    is_friday = now.weekday() == 4  # Friday = 4
    is_exit_time = now.strftime("%H:%M") == "15:20"
    
    return is_friday and is_exit_time

def close_all_positions():
    """Close all open positions (Friday exit)"""
    closed_positions = []
    
    for ticker in list(memory.holdings.keys()):
        if memory.holdings[ticker]['shares'] > 0:
            # Get current price
            realtime_data = get_realtime_data(ticker)
            if realtime_data:
                current_price = realtime_data['price']
                execute_sell(ticker, current_price, "Weekend Exit")
                closed_positions.append(ticker.replace('.NS', '').replace('.BO', ''))
    
    if closed_positions:
        message = f"📤 *WEEKEND EXIT*\n"
        message += f"🔄 Closed positions: {', '.join(closed_positions)}\n"
        message += f"📅 All positions cleared for weekend"
        send_telegram_message(message)

# ============================
# MAIN TRADING LOGIC
# ============================

def analyze_stock(ticker: str):
    """Analyze single stock and make trading decisions"""
    try:
        # Get historical data for indicators
        historical_df = get_stock_data(ticker, period="3mo")
        if historical_df is None or historical_df.empty:
            print(f"No historical data for {ticker}")
            return
        
        # Calculate indicators
        indicators = calculate_indicators(historical_df)
        
        if not indicators:
            print(f"Failed to calculate indicators for {ticker}")
            return
        
        # Get real-time price
        realtime_data = get_realtime_data(ticker)
        if not realtime_data:
            print(f"No real-time data for {ticker}")
            return
        
        current_price = realtime_data['price']
        atr = indicators.get('atr', 0)
        
        # Validate data
        if atr is None:
            atr = current_price * 0.02  # 2% fallback
        
        # Update trailing stop if holding
        if ticker in memory.holdings and memory.holdings[ticker]['shares'] > 0:
            update_trailing_stop(ticker, current_price, atr)
            check_52w_high_alert(ticker, current_price, indicators)
        
        # Trading decisions - FIXED PARAMETER ORDER
        if should_sell(ticker, current_price):
            execute_sell(ticker, current_price)
        elif should_buy(ticker, indicators, current_price):  # Fixed order: ticker, indicators, current_price
            execute_buy(ticker, current_price, indicators)
        
        # Update action status
        new_status = "HOLD" if (ticker in memory.holdings and memory.holdings[ticker]['shares'] > 0) else "WAIT"
        if ticker not in memory.last_action_status or memory.last_action_status[ticker] != new_status:
            memory.last_action_status[ticker] = new_status
            
    except Exception as e:
        print(f"Error analyzing {ticker}: {e}")
        import traceback
        traceback.print_exc()

def print_detailed_status_table():
    """Print comprehensive status table for all stocks using tabulate"""
    table_data = []
    
    for ticker in TICKERS:
        try:
            symbol = ticker.replace('.NS', '').replace('.BO', '')
            
            # Get current price and real-time data
            realtime_data = get_realtime_data(ticker)
            current_price = realtime_data['price'] if realtime_data else 0.0
            
            # Get historical data and indicators
            historical_df = get_stock_data(ticker, period="3mo")
            if historical_df is not None and not historical_df.empty:
                indicators = calculate_indicators(historical_df)
            else:
                indicators = {}
            
            # Extract indicator values
            sma_20 = indicators.get('sma_20', 0.0) or 0.0
            sma_50 = indicators.get('sma_50', 0.0) or 0.0
            atr = indicators.get('atr', 0.0) or 0.0
            rsi = indicators.get('rsi', 0.0) or 0.0
            
            # Get position details
            status = memory.last_action_status.get(ticker, 'WAIT')
            entry_price = 0.0
            sell_threshold = 0.0
            change_percent = 0.0
            
            if ticker in memory.holdings and memory.holdings[ticker]['shares'] > 0:
                entry_price = memory.holdings[ticker]['entry_price']
                sell_threshold = memory.sell_thresholds.get(ticker, 0.0)
                if entry_price > 0:
                    change_percent = ((current_price - entry_price) / entry_price) * 100
                status = 'HOLD'
            else:
                status = 'WAIT'
            
            # Format values for display
            current_price_str = f"₹{current_price:.2f}" if current_price > 0 else "N/A"
            entry_price_str = f"₹{entry_price:.2f}" if entry_price > 0 else "--"
            sma_20_str = f"₹{sma_20:.2f}" if sma_20 > 0 else "N/A"
            sma_50_str = f"₹{sma_50:.2f}" if sma_50 > 0 else "N/A"
            atr_str = f"{atr:.2f}" if atr > 0 else "N/A"
            rsi_str = f"{rsi:.1f}" if rsi > 0 else "N/A"
            sell_threshold_str = f"₹{sell_threshold:.2f}" if sell_threshold > 0 else "--"
            change_percent_str = f"{change_percent:+.2f}%" if change_percent != 0 else "--"
            
            table_data.append([
                symbol,
                current_price_str,
                entry_price_str,
                sma_20_str,
                sma_50_str,
                atr_str,
                rsi_str,
                sell_threshold_str,
                change_percent_str,
                status
            ])
            
        except Exception as e:
            # Add error row if data fetching fails
            table_data.append([
                symbol,
                "ERROR",
                "--",
                "--",
                "--",
                "--",
                "--",
                "--",
                "--",
                "ERROR"
            ])
            print(f"Error processing {ticker}: {e}")
    
    # Print the table
    print("\n" + "="*120)
    print("STOCK TRADING BOT - DETAILED STATUS")
    print("="*120)
    print(tabulate(table_data, headers=[
        "Ticker", "Current Price", "Entry Price", "20-SMA", "50-SMA",
        "ATR", "RSI", "Sell Threshold", "Change %", "Action"
    ], tablefmt="grid"))
    print("="*120)
    
    # Print summary
    total_positions = len([row for row in table_data if row[9] == 'HOLD'])
    waiting_positions = len([row for row in table_data if row[9] == 'WAIT'])
    print(f"SUMMARY: {total_positions} HOLD | {waiting_positions} WAIT | Last Updated: {datetime.now().strftime('%H:%M:%S')}")
    print("="*120)

def main_trading_loop():
    """Main trading loop"""
    print("🚀 Stock Trading Bot Started!")
    send_telegram_message("🚀 *Stock Trading Bot Started!*\n📊 Monitoring stocks every 5 minutes")
    
    while True:
        try:
            current_time = datetime.now()
            
            # Send alive notifications
            if is_alive_check_time():
                if (memory.last_alive_check is None or 
                    (current_time - memory.last_alive_check).total_seconds() > 3600):  # Once per hour max
                    send_alive_notification()
            
            # Only trade during market hours
            if not is_market_hours():
                print(f"[{current_time.strftime('%H:%M:%S')}] Market closed. Waiting...")
                time.sleep(CHECK_INTERVAL)
                continue
            
            print(f"\n[{current_time.strftime('%H:%M:%S')}] Analyzing stocks...")
            
            # Friday exit logic (commented by default)
            # if is_friday_exit_time():
            #     close_all_positions()
            
            # Analyze all stocks
            for ticker in TICKERS:
                analyze_stock(ticker)
                time.sleep(1)  # Small delay between stocks
            
            # Print detailed status table every 15 minutes during market hours
            if current_time.minute % 15 == 0 and current_time.second < 30:
                print_detailed_status_table()
            elif is_alive_check_time():
                print_detailed_status_table()
            
            print(f"[{current_time.strftime('%H:%M:%S')}] Analysis complete. Waiting {CHECK_INTERVAL//60} minutes...")
            
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user")
            send_telegram_message("🛑 *Bot Stopped*\nTrading bot has been manually stopped")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            send_telegram_message(f"❌ *Bot Error*\nError: {str(e)}\nBot continuing...")
        
        time.sleep(CHECK_INTERVAL)

# ============================
# ENTRY POINT
# ============================

if __name__ == "__main__":
    # Verify required libraries
    try:
        import talib
        from tabulate import tabulate
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
    
    # Start the trading bot
    main_trading_loop()