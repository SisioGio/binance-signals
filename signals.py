import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import os
from datetime import datetime
from telegram import send_telegram_signal
# ==============================
# CONFIGURATION
# ==============================
load_dotenv()

ACCOUNT = 727159
PASSWORD = os.getenv("MT5_PASSWORD")
SERVER = "BlackBullMarkets-Demo"

TIMEFRAME = mt5.TIMEFRAME_M1
BARS = 500
PAIRS = ["BTCUSD", "XRPUSD", "XAUUSD", "USDJPY"]

# ==============================
# CONNECT TO MT5
# ==============================
def connect():
    if not mt5.initialize():
        raise Exception("MT5 initialization failed")
    authorized = mt5.login(ACCOUNT, password=PASSWORD, server=SERVER)
    if not authorized:
        raise Exception("MT5 login failed")
    print("Connected to MT5")

# ==============================
# DATA FETCH
# ==============================
def get_data(symbol):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, BARS)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# ==============================
# INDICATORS
# ==============================
def add_indicators(df):

    # EMAs
    df['ema9'] = df['close'].ewm(span=9).mean()
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

    # ATR
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        )
    )
    df['atr'] = df['tr'].rolling(14).mean()
    df['atr_mean'] = df['atr'].rolling(50).mean()

    # Volume spike
    df['vol_mean'] = df['tick_volume'].rolling(20).mean()
    df['vol_spike'] = df['tick_volume'] > 1.8 * df['vol_mean']

    return df

# ==============================
# SIGNAL LOGIC
# ==============================
def generate_signals(df):

    signals = []

    for i in range(51, len(df)):

        row = df.iloc[i]
        prev = df.iloc[i-1]

        # ----- LONG CONDITIONS -----
        trend_long = row['ema9'] > row['ema20'] > row['ema50']
        pullback_long = row['low'] <= row['ema20']
        engulf_long = (
            (row['close'] > row['open']) and
            (row['open'] < prev['close']) and
            (row['close'] > prev['open'])
        )
        atr_expand = row['atr'] > 1.3 * row['atr_mean']

        if trend_long and pullback_long and engulf_long and row['vol_spike'] and atr_expand:
            signals.append({
                "time": row['time'],
                "type": "BUY",
                "price": row['close']
            })

        # ----- SHORT CONDITIONS -----
        trend_short = row['ema9'] < row['ema20'] < row['ema50']
        pullback_short = row['high'] >= row['ema20']
        engulf_short = (
            (row['close'] < row['open']) and
            (row['open'] > prev['close']) and
            (row['close'] < prev['open'])
        )

        if trend_short and pullback_short and engulf_short and row['vol_spike'] and atr_expand:
            signals.append({
                "time": row['time'],
                "type": "SELL",
                "price": row['close']
            })

    return pd.DataFrame(signals)
# ==============================
# SCAN MULTIPLE PAIRS
# ==============================
def scan_pairs(pairs):
    results = []

    for symbol in pairs:
        df = get_data(symbol)
        df = add_indicators(df)
        signals = generate_signals(df)

        if not signals.empty:
            latest_signal = signals.iloc[-1]
            results.append({
                "symbol": symbol,
                "time": latest_signal['time'],
                "type": latest_signal['type'],
                "price": latest_signal['price']
            })
            message = f"""
                🚨 *TRADING SIGNAL*

                📊 Symbol: *{symbol}*
                🕒 Time: `{latest_signal['time']}`
                📌 Type: *{latest_signal['type']}*
                💰 Price: `{latest_signal['price']}`
                """

            send_telegram_signal(message)

    return pd.DataFrame(results)


# ==============================
# SCORE SYMBOL
# ==============================
def score_symbol(symbol):

    info = mt5.symbol_info(symbol)
    if info is None or not info.visible:
        return None

    df = get_data(symbol)
    if df is None or len(df) < 100:
        return None

    # EMAs
    df['ema9'] = df['close'].ewm(span=9).mean()
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

    # ATR
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        )
    )
    df['atr'] = df['tr'].rolling(14).mean()
    df['atr_mean'] = df['atr'].rolling(50).mean()

    # Volume
    df['vol_mean'] = df['tick_volume'].rolling(20).mean()

    latest = df.iloc[-1]

    # Trend strength
    trend_score = abs(latest['ema9'] - latest['ema50'])

    # ATR expansion
    atr_score = latest['atr'] / latest['atr_mean'] if latest['atr_mean'] > 0 else 0

    # Volume expansion
    vol_score = latest['tick_volume'] / latest['vol_mean'] if latest['vol_mean'] > 0 else 0

    # Spread (important for scalping)
    spread = info.spread

    # Normalize spread (lower = better)
    spread_score = 1 / spread if spread > 0 else 0

    total_score = (
        trend_score * 2 +
        atr_score * 3 +
        vol_score * 2 +
        spread_score * 1
    )

    return {
        "symbol": symbol,
        "score": total_score,
        "spread": spread,
        "atr_ratio": atr_score,
        "vol_ratio": vol_score
    }

# ==============================
# SCAN ALL SYMBOLS
# ==============================
def scan_market():

    symbols = mt5.symbols_get()
    results = []

    for s in symbols:
        # Only forex majors/minors (adjust filter if needed)
        if len(s.name) == 6 and s.name.isalpha():
            data = score_symbol(s.name)
            if data:
                results.append(data)

    df = pd.DataFrame(results)
    df = df.sort_values("score", ascending=False)

    return df


# ==============================
# MAIN
# ==============================
if __name__ == "__main__":

    connect()

  
    pairs = ['BTCUSD', 'XRPUSD','ETHUSD']
    
    signals_df = scan_pairs(pairs)

    if signals_df.empty:
        print("No signals found.")
    else:
        print("\nActive Signals:")
        print(signals_df)

    mt5.shutdown()
