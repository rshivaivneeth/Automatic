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
import atexit
import signal
import sys
from collections import deque
import statistics
import gc

warnings.filterwarnings('ignore')

# ============================
# CONFIGURATION
# ============================

# Telegram Configuration
TELEGRAM_BOT_TOKEN = '7933607173:AAFND1Z_GxNdvKwOc4Y_LUuX327eEpc2KIE'
TELEGRAM_CHAT_ID = ['1012793457','1209666577']

# Trading Configuration - Extended ticker list
TICKERS = [
    # Top 50 Indian stocks
    'RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ITC.NS', 
    'BHARTIARTL.NS', 'SBIN.NS', 'LT.NS', 'HCLTECH.NS', 'WIPRO.NS',
    'HINDUNILVR.NS', 'BAJFINANCE.NS', 'MARUTI.NS', 'KOTAKBANK.NS', 'ASIANPAINT.NS',
    'NESTLEIND.NS', 'DMART.NS', 'BAJAJFINSV.NS', 'TITAN.NS', 'ADANIPORTS.NS',
    'AXISBANK.NS', 'ICICIBANK.NS', 'SUNPHARMA.NS', 'ULTRACEMCO.NS', 'NTPC.NS',
    'POWERGRID.NS', 'TECHM.NS', 'M&M.NS', 'TATAMOTORS.NS', 'COALINDIA.NS',
    'JSWSTEEL.NS', 'TATASTEEL.NS', 'INDUSINDBK.NS', 'GRASIM.NS', 'DRREDDY.NS',
    'BRITANNIA.NS', 'CIPLA.NS', 'DIVISLAB.NS', 'EICHERMOT.NS', 'HEROMOTOCO.NS',
    'HINDALCO.NS', 'BAJAJ-AUTO.NS', 'SHREE.NS', 'APOLLOHOSP.NS', 'ONGC.NS',
    'IOC.NS', 'BPCL.NS', 'HDFCLIFE.NS', 'SBILIFE.NS', 'VEDL.NS',
    # Additional 50 stocks
    'ADANIGREEN.NS', 'ADANIENT.NS', 'ADANITRANS.NS', 'GODREJCP.NS', 'PIDILITIND.NS',
    'DABUR.NS', 'MARICO.NS', 'COLPAL.NS', 'MCDOWELL-N.NS', 'BERGEPAINT.NS',
    'AMBUJACEM.NS', 'ACC.NS', 'SHREECEM.NS', 'RAMCO.NS', 'DALBHARAT.NS',
    'SAIL.NS', 'NMDC.NS', 'MOIL.NS', 'GMRINFRA.NS', 'IRCTC.NS',
    'ZOMATO.NS', 'NYKAA.NS', 'PAYTM.NS', 'POLICYBZR.NS', 'TATACONSUM.NS',
    'MUTHOOTFIN.NS', 'BAJAJHLDNG.NS', 'CHOLAFIN.NS', 'LTF.NS', 'MANAPPURAM.NS',
    'RECLTD.NS', 'PFC.NS', 'LICHSGFIN.NS', 'HUDCO.NS', 'CANBK.NS',
    'PNB.NS', 'BANKBARODA.NS', 'UNIONBANK.NS', 'IDFCFIRSTB.NS', 'FEDERALBNK.NS',
    'RBLBANK.NS', 'BANDHANBNK.NS', 'AUBANK.NS', 'YESBANK.NS', 'IDBI.NS',
    'IDEA.NS', 'BHARTI.NS', 'RCOM.NS', 'MTNL.NS', 'BSNL.NS',
    'RELCAPITAL.NS', 'RPOWER.NS', 'ADANIPOWER.NS', 'TATAPOWER.NS', 'NHPC.NS'
]

CHECK_INTERVAL = 60 * 5  # 5 minutes
SHARES_TO_BUY = 2
ATR_MULTIPLIER = 2.0
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75

# Bulk API Configuration
BULK_FETCH_SIZE = 50  # Fetch 50 stocks at once
API_DELAY = 2  # 2 seconds between bulk calls
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

# Advanced Configuration
MIN_VOLUME_SPIKE = 1.8
TREND_CONFIRMATION_PERIODS = 3
VOLATILITY_FILTER = 0.03
CORRELATION_THRESHOLD = 0.7
STRENGTH_THRESHOLD = 65

# Market Hours (IST)
MARKET_START = "00:15"
MARKET_END = "23:30"
ALIVE_CHECK_MORNING = "09:15"
ALIVE_CHECK_EVENING = "15:00"

# ============================
# MEMORY OPTIMIZED DATA STRUCTURES
# ============================

class MinimalStockData:
    """Minimal memory footprint stock data storage"""
    def __init__(self):
        # Only store essential data, no history
        self.current_positions = {}  # {ticker: {'shares': int, 'entry_price': float, 'entry_time': datetime}}
        self.stop_losses = {}  # {ticker: float}
        self.signal_strengths = {}  # {ticker: float}
        self.last_status = {}  # {ticker: str}
        
        # Session statistics (minimal)
        self.session_start = datetime.now()
        self.total_trades = 0
        self.profitable_trades = 0
        self.session_pnl = 0.0
        self.last_alive_check = None

# Single global instance
stock_data = MinimalStockData()

# ============================
# BULK DATA FETCHING FUNCTIONS
# ============================

def bulk_fetch_stock_data(ticker_list: List[str], period: str = "6mo") -> Dict[str, pd.DataFrame]:
    """Fetch stock data in bulk with retry mechanism"""
    stock_data_dict = {}
    
    # Split tickers into chunks
    ticker_chunks = [ticker_list[i:i + BULK_FETCH_SIZE] for i in range(0, len(ticker_list), BULK_FETCH_SIZE)]
    
    for chunk_idx, ticker_chunk in enumerate(ticker_chunks):
        print(f"Fetching bulk data chunk {chunk_idx + 1}/{len(ticker_chunks)} ({len(ticker_chunk)} stocks)...")
        
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                # Create ticker string for bulk download
                ticker_string = ' '.join(ticker_chunk)
                
                # Bulk download using yfinance
                bulk_data = yf.download(
                    tickers=ticker_string,
                    period=period,
                    group_by='ticker',
                    auto_adjust=True,
                    prepost=True,
                    threads=True,
                    progress=False,
                    timeout=REQUEST_TIMEOUT
                )
                
                if bulk_data.empty:
                    print(f"Warning: No data received for chunk {chunk_idx + 1}")
                    break
                
                # Process each ticker from bulk data
                for ticker in ticker_chunk:
                    try:
                        if len(ticker_chunk) == 1:
                            # Single ticker case
                            ticker_data = bulk_data
                        else:
                            # Multi-ticker case
                            ticker_data = bulk_data[ticker] if ticker in bulk_data.columns.get_level_values(0) else None
                        
                        if ticker_data is not None and not ticker_data.empty:
                            # Clean the data
                            ticker_data = ticker_data.dropna()
                            if len(ticker_data) > 0:
                                stock_data_dict[ticker] = ticker_data
                                print(f"  ✓ {ticker}: {len(ticker_data)} records")
                            else:
                                print(f"  ⚠ {ticker}: No valid data")
                        else:
                            print(f"  ✗ {ticker}: Failed to fetch")
                            
                    except Exception as e:
                        print(f"  ✗ {ticker}: Error processing - {e}")
                        continue
                
                print(f"Chunk {chunk_idx + 1} completed. Waiting {API_DELAY}s...")
                time.sleep(API_DELAY)
                break
                
            except Exception as e:
                retry_count += 1
                print(f"  Retry {retry_count}/{MAX_RETRIES} for chunk {chunk_idx + 1}: {e}")
                if retry_count < MAX_RETRIES:
                    time.sleep(API_DELAY * retry_count)
                else:
                    print(f"  Failed to fetch chunk {chunk_idx + 1} after {MAX_RETRIES} retries")
    
    print(f"Bulk fetch complete: {len(stock_data_dict)}/{len(ticker_list)} stocks successfully fetched")
    return stock_data_dict

def bulk_fetch_realtime_data(ticker_list: List[str]) -> Dict[str, Dict]:
    """Fetch real-time data in bulk"""
    realtime_data_dict = {}
    
    # Split tickers into chunks for real-time data
    ticker_chunks = [ticker_list[i:i + BULK_FETCH_SIZE] for i in range(0, len(ticker_list), BULK_FETCH_SIZE)]
    
    for chunk_idx, ticker_chunk in enumerate(ticker_chunks):
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                # Create ticker string for bulk download
                ticker_string = ' '.join(ticker_chunk)
                
                # Fetch recent data (2 days, 5-minute intervals)
                bulk_data = yf.download(
                    tickers=ticker_string,
                    period="2d",
                    interval="5m",
                    group_by='ticker',
                    auto_adjust=True,
                    prepost=True,
                    threads=True,
                    progress=False,
                    timeout=REQUEST_TIMEOUT
                )
                
                if bulk_data.empty:
                    print(f"Warning: No real-time data for chunk {chunk_idx + 1}")
                    break
                
                # Process each ticker from bulk data
                for ticker in ticker_chunk:
                    try:
                        if len(ticker_chunk) == 1:
                            ticker_data = bulk_data
                        else:
                            ticker_data = bulk_data[ticker] if ticker in bulk_data.columns.get_level_values(0) else None
                        
                        if ticker_data is not None and not ticker_data.empty:
                            ticker_data = ticker_data.dropna()
                            if len(ticker_data) > 0:
                                current_price = float(ticker_data['Close'].iloc[-1])
                                current_volume = float(ticker_data['Volume'].iloc[-1])
                                day_high = float(ticker_data['High'].max())
                                day_low = float(ticker_data['Low'].min())
                                day_open = float(ticker_data['Open'].iloc[0])
                                day_change = ((current_price - day_open) / day_open) * 100 if day_open > 0 else 0
                                
                                realtime_data_dict[ticker] = {
                                    'price': current_price,
                                    'volume': current_volume,
                                    'high': float(ticker_data['High'].iloc[-1]),
                                    'low': float(ticker_data['Low'].iloc[-1]),
                                    'day_high': day_high,
                                    'day_low': day_low,
                                    'day_open': day_open,
                                    'day_change': day_change
                                }
                    
                    except Exception as e:
                        print(f"  Error processing real-time data for {ticker}: {e}")
                        continue
                
                time.sleep(API_DELAY / 2)  # Shorter delay for real-time data
                break
                
            except Exception as e:
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    time.sleep(API_DELAY * retry_count / 2)
                else:
                    print(f"Failed to fetch real-time data for chunk {chunk_idx + 1}")
    
    return realtime_data_dict

# ============================
# MEMORY OPTIMIZED TECHNICAL INDICATORS
# ============================

def calculate_essential_indicators(df: pd.DataFrame) -> Dict:
    """Calculate only essential indicators to save memory"""
    try:
        if len(df) < 50:
            return {}
            
        close_prices = df['Close'].values
        high_prices = df['High'].values
        low_prices = df['Low'].values
        volume = df['Volume'].values
        
        indicators = {}
        
        # Only calculate essential indicators
        indicators['sma_20'] = talib.SMA(close_prices, timeperiod=20)
        indicators['sma_50'] = talib.SMA(close_prices, timeperiod=50)
        indicators['ema_12'] = talib.EMA(close_prices, timeperiod=12)
        indicators['ema_26'] = talib.EMA(close_prices, timeperiod=26)
        
        # MACD
        macd, macd_signal, _ = talib.MACD(close_prices, fastperiod=12, slowperiod=26, signalperiod=9)
        indicators['macd'] = macd
        indicators['macd_signal'] = macd_signal
        
        # RSI
        indicators['rsi_14'] = talib.RSI(close_prices, timeperiod=14)
        
        # ATR
        indicators['atr_14'] = talib.ATR(high_prices, low_prices, close_prices, timeperiod=14)
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = talib.BBANDS(close_prices, timeperiod=20, nbdevup=2, nbdevdn=2)
        indicators['bb_upper'] = bb_upper
        indicators['bb_lower'] = bb_lower
        
        # Volume indicators
        indicators['volume_sma_10'] = talib.SMA(volume.astype(float), timeperiod=10)
        
        # Support/Resistance (simple)
        indicators['pivot_point'] = (high_prices[-1] + low_prices[-1] + close_prices[-1]) / 3
        indicators['support_1'] = 2 * indicators['pivot_point'] - high_prices[-1]
        
        # 52-week levels
        indicators['52w_high'] = float(df['High'].max())
        indicators['distance_from_52w_high'] = ((indicators['52w_high'] - close_prices[-1]) / indicators['52w_high']) * 100
        
        # Volatility ratio (simplified)
        if len(close_prices) >= 20:
            recent_vol = np.std(close_prices[-10:]) / np.mean(close_prices[-10:])
            hist_vol = np.std(close_prices[-20:-10]) / np.mean(close_prices[-20:-10])
            indicators['volatility_ratio'] = recent_vol / hist_vol if hist_vol > 0 else 1
        
        return indicators
        
    except Exception as e:
        print(f"Error calculating indicators: {e}")
        return {}

def safe_extract(value, fallback=None):
    """Memory-efficient value extraction"""
    if value is None:
        return fallback
    
    try:
        if hasattr(value, 'iloc') and len(value) > 0:
            result = float(value.iloc[-1])
            return result if not np.isnan(result) else fallback
        elif hasattr(value, 'shape') and value.size > 0:
            result = float(value.flat[-1])
            return result if not np.isnan(result) else fallback
        elif isinstance(value, (list, tuple)) and len(value) > 0:
            return float(value[-1])
        else:
            result = float(value)
            return result if not np.isnan(result) else fallback
    except:
        return fallback

def calculate_signal_strength(ticker: str, indicators: Dict, current_price: float, realtime_data: Dict) -> float:
    """Simplified signal strength calculation"""
    try:
        if not indicators:
            return 0.0
        
        score = 0.0
        
        # Trend (30 points)
        sma_20 = safe_extract(indicators.get('sma_20'))
        sma_50 = safe_extract(indicators.get('sma_50'))
        if sma_20 and sma_50 and current_price > sma_20 > sma_50:
            score += 30
        elif sma_20 and current_price > sma_20:
            score += 15
        
        # RSI (25 points)
        rsi = safe_extract(indicators.get('rsi_14'))
        if rsi and 30 < rsi < 70:
            score += 25
        elif rsi and 25 < rsi < 75:
            score += 15
        
        # MACD (20 points)
        macd = safe_extract(indicators.get('macd'))
        macd_signal = safe_extract(indicators.get('macd_signal'))
        if macd and macd_signal and macd > macd_signal:
            score += 20
        
        # Volume (15 points)
        volume_sma = safe_extract(indicators.get('volume_sma_10'))
        current_volume = realtime_data.get('volume', 0)
        if volume_sma and current_volume > volume_sma * MIN_VOLUME_SPIKE:
            score += 15
        elif volume_sma and current_volume > volume_sma * 1.2:
            score += 10
        
        # Bollinger Bands (10 points)
        bb_lower = safe_extract(indicators.get('bb_lower'))
        bb_upper = safe_extract(indicators.get('bb_upper'))
        if bb_lower and bb_upper and bb_lower < current_price < bb_upper:
            score += 10
        
        return min(score, 100.0)
        
    except Exception as e:
        return 0.0

# ============================
# SIMPLIFIED TRADING LOGIC
# ============================

def should_buy_simple(ticker: str, indicators: Dict, current_price: float, realtime_data: Dict) -> Tuple[bool, str]:
    """Simplified buy logic"""
    if ticker in stock_data.current_positions and stock_data.current_positions[ticker].get('shares', 0) > 0:
        return False, "Position exists"
    
    signal_strength = stock_data.signal_strengths.get(ticker, 0)
    if signal_strength < 65:
        return False, f"Weak signal ({signal_strength:.0f})"
    
    # Simple conditions
    rsi = safe_extract(indicators.get('rsi_14'))
    sma_20 = safe_extract(indicators.get('sma_20'))
    macd = safe_extract(indicators.get('macd'))
    macd_signal = safe_extract(indicators.get('macd_signal'))
    
    conditions_met = 0
    if rsi and 25 < rsi < 65:
        conditions_met += 1
    if sma_20 and current_price > sma_20:
        conditions_met += 1
    if macd and macd_signal and macd > macd_signal:
        conditions_met += 1
    
    if conditions_met >= 2:
        return True, f"Buy signal ({conditions_met}/3)"
    
    return False, f"Conditions not met ({conditions_met}/3)"

def should_sell_simple(ticker: str, indicators: Dict, current_price: float) -> Tuple[bool, str]:
    """Simplified sell logic"""
    if ticker not in stock_data.current_positions or stock_data.current_positions[ticker].get('shares', 0) == 0:
        return False, "No position"
    
    entry_price = stock_data.current_positions[ticker].get('entry_price', 0)
    pnl = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
    
    # Stop loss
    if ticker in stock_data.stop_losses and current_price <= stock_data.stop_losses[ticker]:
        return True, f"Stop-loss (PnL: {pnl:+.1f}%)"
    
    # Profit taking
    if pnl > 8:
        rsi = safe_extract(indicators.get('rsi_14'))
        if rsi and rsi > 75:
            return True, f"Profit-take (PnL: {pnl:+.1f}%)"
    
    # Simple trend reversal
    sma_20 = safe_extract(indicators.get('sma_20'))
    if sma_20 and current_price < sma_20 * 0.98:
        return True, f"Trend reversal (PnL: {pnl:+.1f}%)"
    
    return False, f"Hold (PnL: {pnl:+.1f}%)"

def execute_buy_simple(ticker: str, current_price: float, indicators: Dict, reason: str):
    """Execute buy with minimal logging"""
    try:
        atr = safe_extract(indicators.get('atr_14'), current_price * 0.02)
        
        stock_data.current_positions[ticker] = {
            'shares': SHARES_TO_BUY,
            'entry_price': current_price,
            'entry_time': datetime.now()
        }
        
        stop_loss = current_price - (ATR_MULTIPLIER * atr)
        stock_data.stop_losses[ticker] = stop_loss
        
        stock_data.total_trades += 1
        
        symbol = ticker.replace('.NS', '')
        message = f"🟢 BUY: {symbol} @ ₹{current_price:.2f} | Stop: ₹{stop_loss:.2f} | {reason}"
        send_telegram_message(message)
        print(f"[BUY] {symbol} @ ₹{current_price:.2f}")
        
    except Exception as e:
        print(f"Buy execution error for {ticker}: {e}")

def execute_sell_simple(ticker: str, current_price: float, reason: str):
    """Execute sell with minimal logging"""
    try:
        if ticker not in stock_data.current_positions:
            return
        
        shares = stock_data.current_positions[ticker].get('shares', 0)
        entry_price = stock_data.current_positions[ticker].get('entry_price', 0)
        
        if shares == 0:
            return
        
        pnl = (current_price - entry_price) * shares
        pnl_percent = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
        
        stock_data.session_pnl += pnl
        if pnl > 0:
            stock_data.profitable_trades += 1
        
        # Clear position
        stock_data.current_positions[ticker] = {'shares': 0, 'entry_price': 0}
        if ticker in stock_data.stop_losses:
            del stock_data.stop_losses[ticker]
        
        symbol = ticker.replace('.NS', '')
        profit_emoji = "💚" if pnl >= 0 else "❌"
        message = f"🔴 SELL: {symbol} @ ₹{current_price:.2f} | {profit_emoji} ₹{pnl:.1f} ({pnl_percent:+.1f}%) | {reason}"
        send_telegram_message(message)
        print(f"[SELL] {symbol} @ ₹{current_price:.2f} | P&L: ₹{pnl:.1f}")
        
    except Exception as e:
        print(f"Sell execution error for {ticker}: {e}")

# ============================
# BULK ANALYSIS FUNCTION
# ============================

def bulk_analyze_stocks():
    """Analyze all stocks in bulk"""
    try:
        print(f"\n🔄 Starting bulk analysis of {len(TICKERS)} stocks...")
        
        # Bulk fetch historical data
        print("📊 Fetching historical data...")
        historical_data = bulk_fetch_stock_data(TICKERS, period="3mo")  # Reduced period to save memory
        
        # Force garbage collection
        gc.collect()
        
        # Bulk fetch real-time data
        print("⚡ Fetching real-time data...")
        realtime_data = bulk_fetch_realtime_data(TICKERS)
        
        print(f"✅ Data fetched for {len(historical_data)} stocks with historical and {len(realtime_data)} with real-time data")
        
        # Process each stock
        analysis_results = []
        
        for ticker in TICKERS:
            try:
                symbol = ticker.replace('.NS', '')
                
                # Get data
                hist_df = historical_data.get(ticker)
                rt_data = realtime_data.get(ticker)
                
                if hist_df is None or rt_data is None:
                    analysis_results.append([symbol, "NO DATA", "N/A", "--", "--", "--", "--", "0", "--", "--", "--", "ERROR"])
                    continue
                
                current_price = rt_data['price']
                day_change = rt_data.get('day_change', 0.0)
                
                # Calculate indicators
                indicators = calculate_essential_indicators(hist_df)
                
                # Calculate signal strength
                signal_strength = calculate_signal_strength(ticker, indicators, current_price, rt_data)
                stock_data.signal_strengths[ticker] = signal_strength
                
                # Trading decisions
                should_sell, sell_reason = should_sell_simple(ticker, indicators, current_price)
                if should_sell:
                    execute_sell_simple(ticker, current_price, sell_reason)
                    stock_data.last_status[ticker] = 'SELL_SIGNAL'
                else:
                    should_buy, buy_reason = should_buy_simple(ticker, indicators, current_price, rt_data)
                    if should_buy:
                        execute_buy_simple(ticker, current_price, indicators, buy_reason)
                        stock_data.last_status[ticker] = 'BUY_SIGNAL'
                    else:
                        if ticker in stock_data.current_positions and stock_data.current_positions[ticker].get('shares', 0) > 0:
                            stock_data.last_status[ticker] = f'HOLD'
                        else:
                            stock_data.last_status[ticker] = f'WAIT'
                
                # Prepare table data
                rsi = safe_extract(indicators.get('rsi_14'), 0.0)
                macd = safe_extract(indicators.get('macd'), 0.0)
                atr = safe_extract(indicators.get('atr_14'), 0.0)
                
                entry_price = 0.0
                sell_threshold = 0.0
                change_percent = 0.0
                position_value = 0.0
                
                if ticker in stock_data.current_positions and stock_data.current_positions[ticker].get('shares', 0) > 0:
                    shares = stock_data.current_positions[ticker]['shares']
                    entry_price = stock_data.current_positions[ticker]['entry_price']
                    sell_threshold = stock_data.stop_losses.get(ticker, 0.0)
                    position_value = shares * current_price
                    if entry_price > 0:
                        change_percent = ((current_price - entry_price) / entry_price) * 100
                
                # Format for table
                current_price_str = f"₹{current_price:.2f}"
                day_change_str = f"{day_change:+.2f}%"
                entry_price_str = f"₹{entry_price:.2f}" if entry_price > 0 else "--"
                rsi_str = f"{rsi:.1f}" if rsi > 0 else "N/A"
                macd_str = f"{macd:.3f}" if macd != 0 else "N/A"
                atr_str = f"{atr:.2f}" if atr > 0 else "N/A"
                
                signal_strength_str = f"{signal_strength:.0f}"
                if signal_strength >= 75:
                    signal_strength_str = f"🟢{signal_strength_str}"
                elif signal_strength >= 50:
                    signal_strength_str = f"🟡{signal_strength_str}"
                else:
                    signal_strength_str = f"🔴{signal_strength_str}"
                
                sell_threshold_str = f"₹{sell_threshold:.2f}" if sell_threshold > 0 else "--"
                change_percent_str = f"{change_percent:+.2f}%" if change_percent != 0 else "--"
                position_value_str = f"₹{position_value:.0f}" if position_value > 0 else "--"
                
                status = stock_data.last_status.get(ticker, 'WAIT')
                display_status = status[:12] + "..." if len(status) > 12 else status
                
                analysis_results.append([
                    symbol, current_price_str, day_change_str, entry_price_str,
                    rsi_str, macd_str, atr_str, signal_strength_str,
                    sell_threshold_str, change_percent_str, position_value_str, display_status
                ])
                
            except Exception as e:
                symbol = ticker.replace('.NS', '')
                print(f"Error analyzing {symbol}: {e}")
                analysis_results.append([symbol, "ERROR", "N/A", "--", "--", "--", "--", "0", "--", "--", "--", "ERROR"])
        
        # Print results table
        print_bulk_analysis_table(analysis_results)
        
        # Force cleanup
        del historical_data
        del realtime_data
        gc.collect()
        
        return len(analysis_results)
        
    except Exception as e:
        print(f"Error in bulk analysis: {e}")
        return 0

def print_bulk_analysis_table(analysis_results):
    """Print optimized bulk analysis results"""
    try:
        # Calculate summary statistics
        total_positions = len([row for row in analysis_results if "₹" in row[10] and row[10] != "--"])
        waiting_positions = len(TICKERS) - total_positions
        strong_signals = len([row for row in analysis_results if "🟢" in row[7]])
        medium_signals = len([row for row in analysis_results if "🟡" in row[7]])
        weak_signals = len([row for row in analysis_results if "🔴" in row[7]])
        errors = len([row for row in analysis_results if row[1] == "ERROR"])
        
        print("\n" + "="*130)
        print("BULK STOCK TRADING BOT - OPTIMIZED FOR 100+ STOCKS")
        print("="*130)
        print(tabulate(analysis_results, headers=[
            "Stock", "Price", "Day%", "Entry", "RSI", "MACD", "ATR", 
            "Signal", "Stop", "P&L%", "Value", "Status"
        ], tablefmt="grid"))
        print("="*130)
        
        print(f"📊 ANALYSIS: {len(analysis_results)} stocks | {errors} errors")
        print(f"💼 POSITIONS: {total_positions} active | {waiting_positions} waiting")
        print(f"🎯 SIGNALS: {strong_signals} strong 🟢 | {medium_signals} medium 🟡 | {weak_signals} weak 🔴")
        print(f"💰 SESSION P&L: ₹{stock_data.session_pnl:.2f}")
        print(f"📈 WIN RATE: {(stock_data.profitable_trades/stock_data.total_trades*100):.1f}%" if stock_data.total_trades > 0 else "📈 WIN RATE: 0%")
        print(f"⏰ LAST UPDATED: {datetime.now().strftime('%H:%M:%S')}")
        print("="*130)
        
    except Exception as e:
        print(f"Error printing table: {e}")

# ============================
# TELEGRAM FUNCTIONS (SIMPLIFIED)
# ============================

def send_telegram_message(message: str):
    """Send message to Telegram with error handling"""
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
            response = requests.post(url, data=data, timeout=5)
            if response.status_code != 200:
                print(f"Telegram failed: {response.status_code}")
        except Exception as e:
            print(f"Telegram error: {e}")

def send_bulk_alive_notification():
    """Send bulk trading bot alive notification"""
    current_time = datetime.now().strftime("%H:%M")
    active_positions = sum(1 for pos in stock_data.current_positions.values() if pos.get('shares', 0) > 0)
    strong_signals = sum(1 for strength in stock_data.signal_strengths.values() if strength > 70)
    
    message = f"✅ *Bulk Trading Bot ALIVE* - {current_time}\n"
    message += f"📊 Monitoring {len(TICKERS)} stocks\n"
    message += f"💼 Active positions: {active_positions}\n"
    message += f"🎯 Strong signals: {strong_signals}\n"
    message += f"💰 Session P&L: ₹{stock_data.session_pnl:.2f}\n"
    message += f"🔄 Bulk API optimization enabled"
    
    send_telegram_message(message)
    stock_data.last_alive_check = datetime.now()

# ============================
# EXIT HANDLERS (SIMPLIFIED)
# ============================

def cleanup_and_exit():
    """Clean exit with summary"""
    print("\n🛑 Bulk Trading Bot shutting down...")
    print_final_summary()
    send_telegram_message("🛑 *Bulk Trading Bot Stopped*\nSession ended")
    sys.exit(0)

def setup_exit_handlers():
    """Setup graceful exit handlers"""
    def signal_handler(sig, frame):
        cleanup_and_exit()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(print_final_summary)

def print_final_summary():
    """Print final session summary"""
    try:
        session_duration = datetime.now() - stock_data.session_start
        active_positions = sum(1 for pos in stock_data.current_positions.values() if pos.get('shares', 0) > 0)
        
        print("\n" + "="*60)
        print("BULK TRADING SESSION SUMMARY")
        print("="*60)
        print(f"Session Duration: {session_duration}")
        print(f"Total Trades: {stock_data.total_trades}")
        print(f"Profitable Trades: {stock_data.profitable_trades}")
        print(f"Win Rate: {(stock_data.profitable_trades/stock_data.total_trades*100):.1f}%" if stock_data.total_trades > 0 else "Win Rate: 0%")
        print(f"Total P&L: ₹{stock_data.session_pnl:.2f}")
        print(f"Active Positions: {active_positions}")
        print(f"Stocks Monitored: {len(TICKERS)}")
        print("="*60)
    except Exception as e:
        print(f"Error in final summary: {e}")

# ============================
# TIME MANAGEMENT (SIMPLIFIED)
# ============================

def is_market_hours() -> bool:
    """Check if market is open"""
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    if now.weekday() >= 5:  # Weekend
        return False
    
    return MARKET_START <= current_time <= MARKET_END

def is_alive_check_time() -> bool:
    """Check if it's time for alive notification"""
    current_time = datetime.now().strftime("%H:%M")
    morning_range = "09:15" <= current_time <= "09:30"
    evening_range = "15:00" <= current_time <= "15:15"
    
    return morning_range or evening_range

# ============================
# MAIN BULK TRADING LOOP
# ============================

def main_bulk_trading_loop():
    """Main bulk trading loop optimized for 100+ stocks"""
    print("🚀 Bulk Stock Trading Bot Started!")
    print(f"📊 Optimized for {len(TICKERS)} stocks with bulk API calls")
    
    send_telegram_message(f"🚀 *Bulk Stock Trading Bot Started!*\n📊 Monitoring {len(TICKERS)} stocks\n⚡ Bulk API optimization enabled\n💾 Memory optimized for free instance")
    
    loop_count = 0
    
    while True:
        try:
            current_time = datetime.now()
            loop_count += 1
            
            # Send alive notifications
            if is_alive_check_time():
                if (stock_data.last_alive_check is None or 
                    (current_time - stock_data.last_alive_check).total_seconds() > 3600):
                    send_bulk_alive_notification()
            
            # Only trade during market hours
            if not is_market_hours():
                print(f"[{current_time.strftime('%H:%M:%S')}] Market closed. Waiting...")
                time.sleep(CHECK_INTERVAL)
                continue
            
            print(f"\n[{current_time.strftime('%H:%M:%S')}] Bulk Analysis Cycle #{loop_count}")
            print(f"🔄 Processing {len(TICKERS)} stocks in bulk...")
            
            # Perform bulk analysis
            start_time = time.time()
            processed_count = bulk_analyze_stocks()
            end_time = time.time()
            
            processing_time = end_time - start_time
            print(f"✅ Bulk analysis complete: {processed_count} stocks in {processing_time:.1f}s")
            print(f"⚡ Average: {processing_time/len(TICKERS):.2f}s per stock")
            
            # Send periodic summary to Telegram
            if loop_count % 6 == 0:  # Every 30 minutes during market
                active_positions = sum(1 for pos in stock_data.current_positions.values() if pos.get('shares', 0) > 0)
                strong_signals = sum(1 for strength in stock_data.signal_strengths.values() if strength > 70)
                
                summary_msg = f"📊 *30min Bulk Summary*\n"
                summary_msg += f"💼 Active: {active_positions}/{len(TICKERS)} stocks\n"
                summary_msg += f"🎯 Strong signals: {strong_signals}\n"
                summary_msg += f"💰 P&L: ₹{stock_data.session_pnl:.2f}\n"
                summary_msg += f"🚀 Processed in {processing_time:.1f}s"
                
                send_telegram_message(summary_msg)
            
            print(f"[{current_time.strftime('%H:%M:%S')}] Next bulk analysis in {CHECK_INTERVAL//60} minutes...")
            
            # Force garbage collection after each cycle
            gc.collect()
            
        except KeyboardInterrupt:
            print("\n🛑 Bulk Bot stopped by user")
            cleanup_and_exit()
            break
        except Exception as e:
            print(f"Error in main bulk loop: {e}")
            error_msg = f"❌ *Bulk Bot Error*\nCycle #{loop_count}\nError: {str(e)[:100]}\nBot continuing..."
            send_telegram_message(error_msg)
        
        time.sleep(CHECK_INTERVAL)

# ============================
# MEMORY MONITORING (OPTIONAL)
# ============================

def get_memory_usage():
    """Get current memory usage (if psutil available)"""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        return memory_info.rss / 1024 / 1024  # MB
    except ImportError:
        return 0

def print_memory_info():
    """Print memory usage info"""
    try:
        memory_mb = get_memory_usage()
        if memory_mb > 0:
            print(f"💾 Memory usage: {memory_mb:.1f} MB")
            if memory_mb > 450:  # Warn if approaching 512MB limit
                print("⚠️  Memory usage high - forcing garbage collection")
                gc.collect()
    except:
        pass

# ============================
# HEALTH CHECK FUNCTION
# ============================

def perform_health_check():
    """Perform system health check"""
    print("\n🏥 System Health Check:")
    print(f"  📊 Tickers configured: {len(TICKERS)}")
    print(f"  🔧 Bulk fetch size: {BULK_FETCH_SIZE}")
    print(f"  ⏰ API delay: {API_DELAY}s")
    print(f"  🔄 Check interval: {CHECK_INTERVAL//60} minutes")
    
    # Test API connectivity
    try:
        test_ticker = TICKERS[0]
        test_data = yf.download(test_ticker, period="1d", progress=False, timeout=10)
        if not test_data.empty:
            print(f"  ✅ API connectivity: OK (tested with {test_ticker})")
        else:
            print(f"  ⚠️  API connectivity: No data received")
    except Exception as e:
        print(f"  ❌ API connectivity: Error - {e}")
    
    # Check Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE':
        print(f"  ✅ Telegram: Configured")
    else:
        print(f"  ⚠️  Telegram: Not configured (console mode)")
    
    print_memory_info()
    print("🏥 Health check complete\n")

# ============================
# ENTRY POINT
# ============================

if __name__ == "__main__":
    # Set up exit handlers first
    setup_exit_handlers()
    
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
        sys.exit(1)
    
    # Configuration check
    if TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("⚠️  WARNING: Telegram bot token not configured. Messages will print to console.")
    
    print("🔧 Bulk Trading Configuration:")
    print(f"   📊 Total stocks: {len(TICKERS)}")
    print(f"   📦 Bulk fetch size: {BULK_FETCH_SIZE}")
    print(f"   ⏰ Check interval: {CHECK_INTERVAL//60} minutes")
    print(f"   🚀 API delay: {API_DELAY} seconds")
    print(f"   🔄 Max retries: {MAX_RETRIES}")
    print(f"   📈 ATR Multiplier: {ATR_MULTIPLIER}")
    print(f"   🎯 Signal threshold: {STRENGTH_THRESHOLD}")
    print(f"   💾 Memory optimized: YES")
    
    # Perform initial health check
    perform_health_check()
    
    # Initial system test
    print("🔍 Testing bulk API with first 5 stocks...")
    try:
        test_tickers = TICKERS[:5]
        test_data = bulk_fetch_stock_data(test_tickers, period="1mo")
        print(f"✅ Bulk API test successful: {len(test_data)}/{len(test_tickers)} stocks")
    except Exception as e:
        print(f"❌ Bulk API test failed: {e}")
        print("Please check your internet connection and try again.")
        sys.exit(1)
    
    # Start the bulk trading bot
    try:
        main_bulk_trading_loop()
    except Exception as e:
        print(f"Fatal error: {e}")
        cleanup_and_exit()
    finally:
        print_final_summary()