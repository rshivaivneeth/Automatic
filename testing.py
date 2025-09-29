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

CHECK_INTERVAL = 60 * 5  # Reduced to 3 minutes for faster response
SHARES_TO_BUY = 2
ATR_MULTIPLIER = 1.8  # Slightly increased for better risk management
RSI_OVERSOLD = 25      # More sensitive levels
RSI_OVERBOUGHT = 75

# Enhanced parameters
VOLUME_SPIKE_THRESHOLD = 2.0  # 2x average volume
BREAKOUT_LOOKBACK = 20
TREND_STRENGTH_PERIOD = 10
MOMENTUM_THRESHOLD = 0.02  # 2% momentum threshold

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
    # Trend indicators
    sma_20: float = 0.0
    sma_50: float = 0.0
    ema_12: float = 0.0
    ema_26: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    
    # Momentum indicators
    rsi: float = 0.0
    stoch_k: float = 0.0
    stoch_d: float = 0.0
    williams_r: float = 0.0
    roc: float = 0.0  # Rate of Change
    
    # Volatility indicators
    atr: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_width: float = 0.0
    
    # Volume indicators
    volume_sma: float = 0.0
    volume_spike: bool = False
    obv: float = 0.0  # On-Balance Volume
    ad_line: float = 0.0  # Accumulation/Distribution Line
    
    # Support/Resistance
    support_level: float = 0.0
    resistance_level: float = 0.0
    pivot_point: float = 0.0
    
    # Pattern recognition
    is_breakout: bool = False
    breakout_direction: str = "NONE"
    consolidation_detected: bool = False
    
    # Market structure
    higher_highs: bool = False
    higher_lows: bool = False
    trend_strength: float = 0.0
    
    # Advanced metrics
    sharpe_ratio: float = 0.0
    beta: float = 0.0
    alpha: float = 0.0
    
    # Price levels
    price_52w_high: float = 0.0
    price_52w_low: float = 0.0
    distance_from_52w_high: float = 0.0
    distance_from_52w_low: float = 0.0

class EnhancedStockMemory:
    def __init__(self):
        self.holdings = {}
        self.sell_thresholds = {}
        self.highest_prices = {}
        self.alerts_sent = {}
        self.last_action_status = {}
        self.last_alive_check = None
        
        # Enhanced memory
        self.price_history = {}  # Store price history for pattern analysis
        self.signal_history = {}  # Track signal accuracy
        self.performance_metrics = {}  # Track performance per stock
        self.false_signals = {}  # Track false signal count
        self.market_regime = "NEUTRAL"  # BULL, BEAR, NEUTRAL
        self.sector_strength = {}  # Track sector performance

memory = EnhancedStockMemory()

# ============================
# ENHANCED TELEGRAM FUNCTIONS
# ============================

def send_telegram_message(message: str, priority: str = "NORMAL"):
    """Enhanced telegram messaging with priority levels"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print(f"[TELEGRAM-{priority}] {message}")
        return
    
    # Add priority emoji
    priority_emoji = {
        "HIGH": "🚨",
        "MEDIUM": "⚠️",
        "NORMAL": "ℹ️",
        "LOW": "💭"
    }
    
    formatted_message = f"{priority_emoji.get(priority, 'ℹ️')} {message}"
    
    for chat_id in TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": formatted_message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, data=data, timeout=10)
            if response.status_code != 200:
                print(f"Failed to send telegram message: {response.text}")
        except Exception as e:
            print(f"Telegram error: {e}")

def send_detailed_signal(ticker: str, signal: TradingSignal, current_price: float, indicators: AdvancedIndicators):
    """Send detailed trading signal with analysis"""
    symbol = ticker.replace('.NS', '').replace('.BO', '')
    
    # Signal strength emoji
    strength_emoji = {
        SignalStrength.VERY_WEAK: "🔹",
        SignalStrength.WEAK: "🔸",
        SignalStrength.MODERATE: "🟡",
        SignalStrength.STRONG: "🟠",
        SignalStrength.VERY_STRONG: "🔴"
    }
    
    action_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}
    
    message = f"{action_emoji.get(signal.action, '⚪')} *{signal.action} SIGNAL* {strength_emoji.get(signal.strength, '⚪')}\n"
    message += f"📈 *{symbol}* - ₹{current_price:.2f}\n"
    message += f"💪 Strength: {signal.strength.name}\n"
    message += f"🎯 Confidence: {signal.confidence:.1f}%\n\n"
    
    message += f"📊 *Technical Analysis:*\n"
    message += f"• RSI: {indicators.rsi:.1f}\n"
    message += f"• MACD: {indicators.macd:.3f}\n"
    message += f"• BB Position: {((current_price - indicators.bb_lower) / (indicators.bb_upper - indicators.bb_lower) * 100):.1f}%\n"
    message += f"• Volume Spike: {'Yes' if indicators.volume_spike else 'No'}\n"
    message += f"• Trend Strength: {indicators.trend_strength:.2f}\n\n"
    
    message += f"📋 *Reasons:*\n"
    for reason in signal.reasons[:3]:  # Top 3 reasons
        message += f"• {reason}\n"
    
    if signal.price_target:
        message += f"\n🎯 Target: ₹{signal.price_target:.2f}"
    if signal.stop_loss:
        message += f"\n🛑 Stop Loss: ₹{signal.stop_loss:.2f}"
    
    priority = "HIGH" if signal.strength in [SignalStrength.STRONG, SignalStrength.VERY_STRONG] else "MEDIUM"
    send_telegram_message(message, priority)

# ============================
# ADVANCED TECHNICAL INDICATORS
# ============================

def calculate_advanced_indicators(df: pd.DataFrame) -> AdvancedIndicators:
    """Calculate comprehensive technical indicators"""
    try:
        if len(df) < 50:
            return AdvancedIndicators()
        
        close = df['Close'].values
        high = df['High'].values
        low = df['Low'].values
        volume = df['Volume'].values
        
        indicators = AdvancedIndicators()
        
        # Trend Indicators
        indicators.sma_20 = safe_extract(talib.SMA(close, 20))
        indicators.sma_50 = safe_extract(talib.SMA(close, 50))
        indicators.ema_12 = safe_extract(talib.EMA(close, 12))
        indicators.ema_26 = safe_extract(talib.EMA(close, 26))
        
        # MACD
        macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        indicators.macd = safe_extract(macd)
        indicators.macd_signal = safe_extract(macd_signal)
        indicators.macd_histogram = safe_extract(macd_hist)
        
        # Momentum Indicators
        indicators.rsi = safe_extract(talib.RSI(close, 14))
        indicators.stoch_k, indicators.stoch_d = talib.STOCH(high, low, close)
        indicators.stoch_k = safe_extract(indicators.stoch_k)
        indicators.stoch_d = safe_extract(indicators.stoch_d)
        indicators.williams_r = safe_extract(talib.WILLR(high, low, close, 14))
        indicators.roc = safe_extract(talib.ROC(close, 10))
        
        # Volatility Indicators
        indicators.atr = safe_extract(talib.ATR(high, low, close, 14))
        bb_upper, bb_middle, bb_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
        indicators.bb_upper = safe_extract(bb_upper)
        indicators.bb_middle = safe_extract(bb_middle)
        indicators.bb_lower = safe_extract(bb_lower)
        if indicators.bb_upper and indicators.bb_lower:
            indicators.bb_width = (indicators.bb_upper - indicators.bb_lower) / indicators.bb_middle * 100
        
        # Volume Indicators
        volume_float = volume.astype(float)
        indicators.volume_sma = safe_extract(talib.SMA(volume_float, 20))
        if indicators.volume_sma and len(volume) > 0:
            indicators.volume_spike = volume[-1] > (indicators.volume_sma * VOLUME_SPIKE_THRESHOLD)
        
        indicators.obv = safe_extract(talib.OBV(close, volume_float))
        indicators.ad_line = safe_extract(talib.AD(high, low, close, volume_float))
        
        # Support/Resistance Levels
        indicators.support_level, indicators.resistance_level = calculate_support_resistance(df)
        indicators.pivot_point = calculate_pivot_point(df)
        
        # Pattern Recognition
        indicators.is_breakout, indicators.breakout_direction = detect_breakout(df, indicators)
        indicators.consolidation_detected = detect_consolidation(df)
        
        # Market Structure
        indicators.higher_highs, indicators.higher_lows = analyze_market_structure(df)
        indicators.trend_strength = calculate_trend_strength(df)
        
        # Advanced Metrics
        indicators.sharpe_ratio = calculate_sharpe_ratio(df)
        
        # Price Levels
        indicators.price_52w_high = float(df['High'].max())
        indicators.price_52w_low = float(df['Low'].min())
        current_price = close[-1]
        indicators.distance_from_52w_high = (indicators.price_52w_high - current_price) / indicators.price_52w_high * 100
        indicators.distance_from_52w_low = (current_price - indicators.price_52w_low) / indicators.price_52w_low * 100
        
        return indicators
        
    except Exception as e:
        print(f"Error calculating advanced indicators: {e}")
        return AdvancedIndicators()

def safe_extract(arr, default=0.0):
    """Safely extract last value from array"""
    if arr is None or len(arr) == 0:
        return default
    val = arr[-1]
    return float(val) if not np.isnan(val) else default

def calculate_support_resistance(df: pd.DataFrame) -> Tuple[float, float]:
    """Calculate dynamic support and resistance levels"""
    try:
        highs = df['High'].rolling(window=10).max()
        lows = df['Low'].rolling(window=10).min()
        
        # Find recent significant levels
        resistance = highs.tail(20).max()
        support = lows.tail(20).min()
        
        return float(support), float(resistance)
    except:
        return 0.0, 0.0

def calculate_pivot_point(df: pd.DataFrame) -> float:
    """Calculate pivot point for the day"""
    try:
        last_day = df.tail(1)
        if len(last_day) > 0:
            high = last_day['High'].iloc[0]
            low = last_day['Low'].iloc[0]
            close = last_day['Close'].iloc[0]
            return float((high + low + close) / 3)
    except:
        pass
    return 0.0

def detect_breakout(df: pd.DataFrame, indicators: AdvancedIndicators) -> Tuple[bool, str]:
    """Detect breakout patterns"""
    try:
        current_price = df['Close'].iloc[-1]
        
        # Volume-confirmed breakout above resistance
        if (current_price > indicators.resistance_level and 
            indicators.volume_spike and 
            indicators.rsi < 80):
            return True, "BULLISH"
        
        # Breakdown below support
        if (current_price < indicators.support_level and 
            indicators.volume_spike):
            return True, "BEARISH"
            
        return False, "NONE"
    except:
        return False, "NONE"

def detect_consolidation(df: pd.DataFrame, period: int = 20) -> bool:
    """Detect consolidation patterns"""
    try:
        recent_data = df.tail(period)
        price_range = (recent_data['High'].max() - recent_data['Low'].min()) / recent_data['Close'].mean()
        return price_range < 0.05  # Less than 5% range indicates consolidation
    except:
        return False

def analyze_market_structure(df: pd.DataFrame) -> Tuple[bool, bool]:
    """Analyze if stock is making higher highs and higher lows"""
    try:
        recent_highs = df['High'].tail(10).values
        recent_lows = df['Low'].tail(10).values
        
        higher_highs = len(recent_highs) > 5 and recent_highs[-1] > recent_highs[-5]
        higher_lows = len(recent_lows) > 5 and recent_lows[-1] > recent_lows[-5]
        
        return higher_highs, higher_lows
    except:
        return False, False

def calculate_trend_strength(df: pd.DataFrame) -> float:
    """Calculate trend strength (0-1 scale)"""
    try:
        returns = df['Close'].pct_change().dropna()
        if len(returns) < 10:
            return 0.0
        
        # Calculate trend consistency
        positive_days = (returns > 0).sum()
        total_days = len(returns)
        trend_consistency = abs(positive_days / total_days - 0.5) * 2
        
        # Factor in price momentum
        price_momentum = abs(returns.tail(10).mean()) * 100
        
        return min(1.0, (trend_consistency + price_momentum) / 2)
    except:
        return 0.0

def calculate_sharpe_ratio(df: pd.DataFrame, risk_free_rate: float = 0.06) -> float:
    """Calculate Sharpe ratio"""
    try:
        returns = df['Close'].pct_change().dropna()
        if len(returns) < 20:
            return 0.0
        
        excess_return = returns.mean() * 252 - risk_free_rate  # Annualized
        volatility = returns.std() * np.sqrt(252)  # Annualized
        
        return excess_return / volatility if volatility > 0 else 0.0
    except:
        return 0.0

# ============================
# ENHANCED SIGNAL GENERATION
# ============================

def generate_trading_signal(ticker: str, current_price: float, indicators: AdvancedIndicators) -> TradingSignal:
    """Generate comprehensive trading signal with confidence scoring"""
    
    reasons = []
    buy_score = 0
    sell_score = 0
    confidence_factors = []
    
    # Trend Analysis (Weight: 25%)
    if indicators.sma_20 > indicators.sma_50 and indicators.ema_12 > indicators.ema_26:
        buy_score += 25
        reasons.append("Strong uptrend (SMA20>SMA50, EMA12>EMA26)")
        confidence_factors.append(15)
    elif indicators.sma_20 < indicators.sma_50 and indicators.ema_12 < indicators.ema_26:
        sell_score += 25
        reasons.append("Strong downtrend")
        confidence_factors.append(15)
    
    # MACD Analysis (Weight: 20%)
    if indicators.macd > indicators.macd_signal and indicators.macd_histogram > 0:
        buy_score += 20
        reasons.append("MACD bullish crossover")
        confidence_factors.append(12)
    elif indicators.macd < indicators.macd_signal and indicators.macd_histogram < 0:
        sell_score += 20
        reasons.append("MACD bearish crossover")
        confidence_factors.append(12)
    
    # RSI Analysis (Weight: 15%)
    if 30 < indicators.rsi < 50:
        buy_score += 15
        reasons.append(f"RSI oversold recovery ({indicators.rsi:.1f})")
        confidence_factors.append(10)
    elif indicators.rsi > 75:
        sell_score += 15
        reasons.append(f"RSI overbought ({indicators.rsi:.1f})")
        confidence_factors.append(10)
    
    # Volume Analysis (Weight: 15%)
    if indicators.volume_spike:
        if buy_score > sell_score:
            buy_score += 15
            reasons.append("High volume confirms move")
            confidence_factors.append(12)
        else:
            sell_score += 15
            reasons.append("High volume distribution")
            confidence_factors.append(12)
    
    # Bollinger Bands (Weight: 10%)
    bb_position = ((current_price - indicators.bb_lower) / 
                   (indicators.bb_upper - indicators.bb_lower)) if indicators.bb_upper > indicators.bb_lower else 0.5
    
    if bb_position < 0.2:  # Near lower band
        buy_score += 10
        reasons.append("Price near Bollinger lower band")
        confidence_factors.append(8)
    elif bb_position > 0.8:  # Near upper band
        sell_score += 10
        reasons.append("Price near Bollinger upper band")
        confidence_factors.append(8)
    
    # Breakout Analysis (Weight: 10%)
    if indicators.is_breakout and indicators.breakout_direction == "BULLISH":
        buy_score += 10
        reasons.append("Bullish breakout detected")
        confidence_factors.append(15)
    elif indicators.is_breakout and indicators.breakout_direction == "BEARISH":
        sell_score += 10
        reasons.append("Bearish breakdown detected")
        confidence_factors.append(15)
    
    # Market Structure (Weight: 5%)
    if indicators.higher_highs and indicators.higher_lows:
        buy_score += 5
        reasons.append("Higher highs and higher lows")
        confidence_factors.append(8)
    
    # Determine action and strength
    net_score = buy_score - sell_score
    
    if net_score >= 60:
        action = "BUY"
        strength = SignalStrength.VERY_STRONG
    elif net_score >= 40:
        action = "BUY"
        strength = SignalStrength.STRONG
    elif net_score >= 20:
        action = "BUY"
        strength = SignalStrength.MODERATE
    elif net_score <= -60:
        action = "SELL"
        strength = SignalStrength.VERY_STRONG
    elif net_score <= -40:
        action = "SELL"
        strength = SignalStrength.STRONG
    elif net_score <= -20:
        action = "SELL"
        strength = SignalStrength.MODERATE
    else:
        action = "HOLD"
        strength = SignalStrength.WEAK
    
    # Calculate confidence
    confidence = min(100, sum(confidence_factors))
    
    # Calculate price targets
    price_target = None
    stop_loss = None
    
    if action == "BUY":
        price_target = current_price * 1.08  # 8% target
        stop_loss = current_price - (indicators.atr * ATR_MULTIPLIER)
    elif action == "SELL":
        stop_loss = current_price + (indicators.atr * ATR_MULTIPLIER)
    
    return TradingSignal(
        action=action,
        strength=strength,
        confidence=confidence,
        reasons=reasons,
        price_target=price_target,
        stop_loss=stop_loss
    )

# ============================
# ENHANCED TRADING LOGIC
# ============================

def should_buy_enhanced(ticker: str, signal: TradingSignal, current_price: float) -> bool:
    """Enhanced buy decision with multiple criteria"""
    # Don't buy if already holding
    if ticker in memory.holdings and memory.holdings[ticker]['shares'] > 0:
        return False
    
    # Check signal strength and confidence
    if signal.action != "BUY":
        return False
    
    if signal.strength == SignalStrength.VERY_WEAK:
        return False
    
    # Minimum confidence threshold
    min_confidence = {
        SignalStrength.MODERATE: 60,
        SignalStrength.STRONG: 50,
        SignalStrength.VERY_STRONG: 40
    }
    
    required_confidence = min_confidence.get(signal.strength, 70)
    if signal.confidence < required_confidence:
        return False
    
    # Skip if earnings soon
    if has_earnings_soon(ticker):
        return False
    
    return True

def should_sell_enhanced(ticker: str, current_price: float, signal: TradingSignal) -> bool:
    """Enhanced sell decision"""
    if ticker not in memory.holdings or memory.holdings[ticker]['shares'] == 0:
        return False
    
    # Check trailing stop-loss
    if ticker in memory.sell_thresholds and current_price <= memory.sell_thresholds[ticker]:
        return True
    
    # Check signal-based sell
    if signal.action == "SELL" and signal.strength in [SignalStrength.STRONG, SignalStrength.VERY_STRONG]:
        return True
    
    # Check if hit price target
    entry_price = memory.holdings[ticker]['entry_price']
    profit_percent = (current_price - entry_price) / entry_price * 100
    
    if profit_percent >= 10:  # Take profit at 10%
        return True
    
    return False

def execute_buy_enhanced(ticker: str, current_price: float, signal: TradingSignal, indicators: AdvancedIndicators):
    """Execute enhanced buy order with detailed logging"""
    # Use signal's calculated stop loss or fallback to ATR
    stop_loss_price = signal.stop_loss or (current_price - (indicators.atr * ATR_MULTIPLIER))
    
    # Initialize memory
    memory.holdings[ticker] = {
        'shares': SHARES_TO_BUY,
        'entry_price': current_price,
        'entry_signal': signal,
        'entry_time': datetime.now()
    }
    
    memory.sell_thresholds[ticker] = stop_loss_price
    memory.highest_prices[ticker] = current_price
    
    if ticker not in memory.alerts_sent:
        memory.alerts_sent[ticker] = {'52w_high': False}
    
    # Send detailed signal
    send_detailed_signal(ticker, signal, current_price, indicators)
    
    symbol = ticker.replace('.NS', '').replace('.BO', '')
    print(f"[ENHANCED BUY] {symbol} @ ₹{current_price:.2f} | Confidence: {signal.confidence:.1f}%")

def execute_sell_enhanced(ticker: str, current_price: float, reason: str, signal: TradingSignal = None):
    """Execute enhanced sell order with performance tracking"""
    if ticker not in memory.holdings:
        return
    
    shares = memory.holdings[ticker]['shares']
    entry_price = memory.holdings[ticker]['entry_price']
    entry_time = memory.holdings[ticker].get('entry_time', datetime.now())
    
    # Calculate detailed P&L
    total_change = (current_price - entry_price) * shares
    change_percent = ((current_price - entry_price) / entry_price) * 100
    holding_period = (datetime.now() - entry_time).days
    
    # Store performance metrics
    if ticker not in memory.performance_metrics:
        memory.performance_metrics[ticker] = []
    
    memory.performance_metrics[ticker].append({
        'entry_price': entry_price,
        'exit_price': current_price,
        'pnl': total_change,
        'pnl_percent': change_percent,
        'holding_days': holding_period,
        'exit_reason': reason
    })
    
    # Clear position
    memory.holdings[ticker] = {'shares': 0, 'entry_price': 0}
    if ticker in memory.sell_thresholds:
        del memory.sell_thresholds[ticker]
    if ticker in memory.highest_prices:
        del memory.highest_prices[ticker]
    
    memory.alerts_sent[ticker] = {'52w_high': False}
    
    # Enhanced notification
    symbol = ticker.replace('.NS', '').replace('.BO', '')
    profit_emoji = "💚" if total_change >= 0 else "❌"
    
    message = f"🔴 *ENHANCED SELL* - {reason}\n"
    message += f"📉 {symbol} - ₹{current_price:.2f}\n"
    message += f"💼 Sold {shares} shares\n"
    message += f"{profit_emoji} P&L: ₹{total_change:.2f} ({change_percent:+.2f}%)\n"
    message += f"📅 Held for {holding_period} days"
    
    if signal:
        message += f"\n🎯 Exit Confidence: {signal.confidence:.1f}%"
    
    priority = "HIGH" if abs(change_percent) > 5 else "MEDIUM"
    send_telegram_message(message, priority)
    
    print(f"[ENHANCED SELL] {symbol} @ ₹{current_price:.2f} | P&L: ₹{total_change:.2f} ({change_percent:+.2f}%)")

# ============================
# ENHANCED MAIN LOGIC
# ============================

def analyze_stock_enhanced(ticker: str):
    """Enhanced stock analysis with comprehensive signals"""
    try:
        print(f"[DEBUG] Starting analysis for {ticker}")  # ADD THIS LINE

        # Get data
        historical_df = get_stock_data(ticker, period="6mo")  # Increased to 6 months
        if historical_df is None or historical_df.empty:
            print(f"No historical data for {ticker}")
            return

        # Calculate advanced indicators
        indicators = calculate_advanced_indicators(historical_df)
        print(f"[DEBUG] Calculated indicators for {ticker}")  # ADD THIS LINE

        # Get real-time price
        realtime_data = get_realtime_data(ticker)
        if not realtime_data:
            print(f"No real-time data for {ticker}")
            return
        
        current_price = realtime_data['price']
        print(f"[DEBUG] {ticker} current price: ₹{current_price:.2f}")  # ADD THIS LINE
        
        # Generate trading signal
        signal = generate_trading_signal(ticker, current_price, indicators)
        print(f"[DEBUG] {ticker} signal: {signal.action} (confidence: {signal.confidence:.1f}%)")  # ADD THIS LINE
        # Update trailing stop if holding
        if ticker in memory.holdings and memory.holdings[ticker]['shares'] > 0:
            update_trailing_stop(ticker, current_price, indicators.atr)
            check_52w_high_alert(ticker, current_price, indicators)
        
        # Trading decisions
        if should_sell_enhanced(ticker, current_price, signal):
            execute_sell_enhanced(ticker, current_price, "Enhanced Signal", signal)
        elif should_buy_enhanced(ticker, signal, current_price):
            execute_buy_enhanced(ticker, current_price, signal, indicators)
        
        # Update status
        new_status = "HOLD" if (ticker in memory.holdings and memory.holdings[ticker]['shares'] > 0) else "WAIT"
        memory.last_action_status[ticker] = new_status
        
        # Store price history for pattern analysis
        if ticker not in memory.price_history:
            memory.price_history[ticker] = []
        memory.price_history[ticker].append({
            'timestamp': datetime.now(),
            'price': current_price,
            'signal': signal.action,
            'confidence': signal.confidence
        })
        
        # Keep only last 100 records
        if len(memory.price_history[ticker]) > 100:
            memory.price_history[ticker] = memory.price_history[ticker][-100:]
            
    except Exception as e:
        print(f"Error in enhanced analysis for {ticker}: {e}")
        import traceback
        traceback.print_exc()

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

def update_trailing_stop(ticker: str, current_price: float, atr: float):
    """Update trailing stop-loss"""
    if ticker not in memory.holdings or memory.holdings[ticker]['shares'] == 0:
        return
    
    if atr is None or atr <= 0:
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
    """Enhanced 52-week high alert"""
    if ticker not in memory.holdings or memory.holdings[ticker]['shares'] == 0:
        return
    
    if ticker not in memory.alerts_sent:
        memory.alerts_sent[ticker] = {'52w_high': False}
    
    if indicators.distance_from_52w_high <= 2.0:  # Within 2% of 52W high
        if not memory.alerts_sent[ticker]['52w_high']:
            symbol = ticker.replace('.NS', '').replace('.BO', '')
            message = f"🚀 *52-WEEK HIGH ALERT*\n"
            message += f"🔥 {symbol} - ₹{current_price:.2f}\n"
            message += f"📊 Distance from 52W High: {indicators.distance_from_52w_high:.1f}%\n"
            message += f"💰 52W High: ₹{indicators.price_52w_high:.2f}\n"
            message += f"📈 Consider profit booking or trailing stop adjustment"
            
            send_telegram_message(message, "HIGH")
            memory.alerts_sent[ticker]['52w_high'] = True

def print_enhanced_status_table():
    """Print enhanced status table with advanced metrics"""
    table_data = []
    
    for ticker in TICKERS:
        try:
            symbol = ticker.replace('.NS', '').replace('.BO', '')
            
            # Get current data
            realtime_data = get_realtime_data(ticker)
            current_price = realtime_data['price'] if realtime_data else 0.0
            
            # Get indicators
            historical_df = get_stock_data(ticker, period="6mo")
            if historical_df is not None and not historical_df.empty:
                indicators = calculate_advanced_indicators(historical_df)
                signal = generate_trading_signal(ticker, current_price, indicators)
            else:
                indicators = AdvancedIndicators()
                signal = TradingSignal("HOLD", SignalStrength.WEAK, 0.0, [])
            
            # Position details
            status = memory.last_action_status.get(ticker, 'WAIT')
            entry_price = 0.0
            change_percent = 0.0
            days_held = 0
            
            if ticker in memory.holdings and memory.holdings[ticker]['shares'] > 0:
                entry_price = memory.holdings[ticker]['entry_price']
                entry_time = memory.holdings[ticker].get('entry_time', datetime.now())
                days_held = (datetime.now() - entry_time).days
                if entry_price > 0:
                    change_percent = ((current_price - entry_price) / entry_price) * 100
                status = 'HOLD'
            
            # Format values
            current_price_str = f"₹{current_price:.2f}" if current_price > 0 else "N/A"
            entry_price_str = f"₹{entry_price:.2f}" if entry_price > 0 else "--"
            rsi_str = f"{indicators.rsi:.1f}" if indicators.rsi > 0 else "N/A"
            macd_str = f"{indicators.macd:.3f}" if indicators.macd != 0 else "N/A"
            signal_str = f"{signal.action} ({signal.confidence:.0f}%)"
            change_str = f"{change_percent:+.2f}%" if change_percent != 0 else "--"
            trend_str = f"{indicators.trend_strength:.2f}" if indicators.trend_strength > 0 else "N/A"
            volume_str = "🔥" if indicators.volume_spike else "📊"
            days_str = f"{days_held}d" if days_held > 0 else "--"
            
            # Distance from 52W levels
            dist_high_str = f"{indicators.distance_from_52w_high:.1f}%" if indicators.distance_from_52w_high > 0 else "N/A"
            
            table_data.append([
                symbol,
                current_price_str,
                entry_price_str,
                days_str,
                rsi_str,
                macd_str,
                trend_str,
                volume_str,
                dist_high_str,
                signal_str,
                change_str,
                status
            ])
            
        except Exception as e:
            table_data.append([
                symbol, "ERROR", "--", "--", "--", "--", "--", "--", "--", "--", "--", "ERROR"
            ])
            print(f"Error processing {ticker}: {e}")
    
    # Print enhanced table
    print("\n" + "="*150)
    print("ENHANCED STOCK TRADING BOT - COMPREHENSIVE STATUS")
    print("="*150)
    print(tabulate(table_data, headers=[
        "Ticker", "Price", "Entry", "Days", "RSI", "MACD", "Trend", "Vol", 
        "Dist52H", "Signal (Conf%)", "Change%", "Status"
    ], tablefmt="grid"))
    print("="*150)
    
    # Enhanced summary
    total_positions = len([row for row in table_data if row[11] == 'HOLD'])
    waiting_positions = len([row for row in table_data if row[11] == 'WAIT'])
    strong_signals = len([row for row in table_data if 'STRONG' in row[9] or row[9].endswith('80%)') or row[9].endswith('90%)') or row[9].endswith('100%)')])
    
    print(f"ENHANCED SUMMARY: {total_positions} HOLD | {waiting_positions} WAIT | {strong_signals} Strong Signals")
    print(f"Last Updated: {datetime.now().strftime('%H:%M:%S')} | Market: {'OPEN' if is_market_hours() else 'CLOSED'}")
    print("="*150)

def print_performance_summary():
    """Print performance summary for all stocks"""
    if not any(memory.performance_metrics.values()):
        return
    
    print("\n" + "="*100)
    print("PERFORMANCE SUMMARY")
    print("="*100)
    
    total_pnl = 0
    total_trades = 0
    winning_trades = 0
    
    for ticker, trades in memory.performance_metrics.items():
        if not trades:
            continue
            
        symbol = ticker.replace('.NS', '').replace('.BO', '')
        ticker_pnl = sum([trade['pnl'] for trade in trades])
        ticker_trades = len(trades)
        ticker_wins = len([trade for trade in trades if trade['pnl'] > 0])
        
        total_pnl += ticker_pnl
        total_trades += ticker_trades
        winning_trades += ticker_wins
        
        win_rate = (ticker_wins / ticker_trades * 100) if ticker_trades > 0 else 0
        avg_pnl = ticker_pnl / ticker_trades if ticker_trades > 0 else 0
        
        print(f"{symbol}: ₹{ticker_pnl:.2f} | {ticker_trades} trades | {win_rate:.1f}% win rate | Avg: ₹{avg_pnl:.2f}")
    
    overall_win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    avg_pnl_per_trade = total_pnl / total_trades if total_trades > 0 else 0
    
    print("-" * 100)
    print(f"OVERALL: ₹{total_pnl:.2f} | {total_trades} trades | {overall_win_rate:.1f}% win rate | Avg: ₹{avg_pnl_per_trade:.2f}")
    print("="*100)

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

def send_alive_notification():
    """Send enhanced alive notification"""
    current_time = datetime.now().strftime("%H:%M")
    
    # Calculate active positions and today's performance
    active_positions = sum(1 for ticker in memory.holdings if memory.holdings[ticker]['shares'] > 0)
    
    # Calculate unrealized P&L
    unrealized_pnl = 0
    for ticker in memory.holdings:
        if memory.holdings[ticker]['shares'] > 0:
            realtime_data = get_realtime_data(ticker)
            if realtime_data:
                current_price = realtime_data['price']
                entry_price = memory.holdings[ticker]['entry_price']
                unrealized_pnl += (current_price - entry_price) * memory.holdings[ticker]['shares']
    
    message = f"✅ *ENHANCED TRADING BOT ALIVE* - {current_time}\n"
    message += f"📊 Monitoring {len(TICKERS)} stocks\n"
    message += f"💼 Active positions: {active_positions}\n"
    message += f"💰 Unrealized P&L: ₹{unrealized_pnl:.2f}\n"
    message += f"🎯 Enhanced signals with confidence scoring\n"
    message += f"⚡ 3-minute intervals for faster response"
    
    send_telegram_message(message, "NORMAL")
    memory.last_alive_check = datetime.now()

def main_enhanced_trading_loop():
    """Enhanced main trading loop"""
    print("🚀 ENHANCED Stock Trading Bot Started!")
    
    startup_message = "🚀 *ENHANCED TRADING BOT STARTED!*\n"
    startup_message += "✨ *New Features:*\n"
    startup_message += "• Advanced technical indicators (MACD, Stoch, BB)\n"
    startup_message += "• Confidence-based signal scoring\n"
    startup_message += "• Volume spike detection\n"
    startup_message += "• Breakout pattern recognition\n"
    startup_message += "• Enhanced risk management\n"
    startup_message += "• 3-minute monitoring intervals\n"
    startup_message += "• Comprehensive performance tracking"
    
    send_telegram_message(startup_message, "HIGH")
    
    loop_count = 0
    
    while True:
        try:
            current_time = datetime.now()
            loop_count += 1
            
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
            
            print(f"\n[{current_time.strftime('%H:%M:%S')}] Enhanced Analysis Cycle {loop_count}...")
            
            # Analyze all stocks with enhanced logic
            for ticker in TICKERS:
                analyze_stock_enhanced(ticker)
                time.sleep(0.5)  # Small delay between stocks
            
            # Print enhanced status every 5 cycles (15 minutes) or during alive check
            if loop_count % 5 == 0 or is_alive_check_time():
                print_enhanced_status_table()
                
                # Print performance summary every 10 cycles (30 minutes)
                if loop_count % 10 == 0:
                    print_performance_summary()
            
            print(f"[{current_time.strftime('%H:%M:%S')}] Enhanced analysis complete. Next cycle in {CHECK_INTERVAL//60} minutes...")
            
        except KeyboardInterrupt:
            print("\n🛑 Enhanced Bot stopped by user")
            
            final_message = "🛑 *ENHANCED BOT STOPPED*\n"
            final_message += "📊 Final performance summary being calculated..."
            send_telegram_message(final_message, "HIGH")
            
            print_performance_summary()
            break
            
        except Exception as e:
            print(f"Error in enhanced main loop: {e}")
            error_message = f"❌ *ENHANCED BOT ERROR*\n"
            error_message += f"Error: {str(e)[:100]}\n"
            error_message += f"Bot continuing with enhanced recovery..."
            send_telegram_message(error_message, "HIGH")
            import traceback
            traceback.print_exc()
        
        time.sleep(CHECK_INTERVAL)

# ============================
# ENHANCED ENTRY POINT
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
    
    # Start the enhanced trading bot
    main_enhanced_trading_loop()