import os
import pandas as pd
import numpy as np
import time
from binance.client import Client
from dotenv import load_dotenv
import requests
from datetime import datetime
from utils import get_secret
# ==============================
# CONFIGURATION
# ==============================
load_dotenv()

secret = get_secret()
BINANCE_API_KEY =secret.get("BINANCE_API_KEY")
BINANCE_API_SECRET = secret.get("BINANCE_API_SECRET")
TELEGRAM_BOT_TOKEN = secret.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = secret.get("TELEGRAM_CHANNEL_ID")

PAIRS = [
    # Major Cryptos
    "BTCUSDT",  # Bitcoin
    "ETHUSDT",  # Ethereum
    "BNBUSDT",  # Binance Coin
    "XRPUSDT",  # Ripple
    "ADAUSDT",  # Cardano
    "SOLUSDT",  # Solana
    "DOGEUSDT", # Dogecoin
    "MATICUSDT",# Polygon

    # Tokenized Gold
    "PAXGUSDT", # Gold token
    # Popular Altcoins
    "LTCUSDT",  # Litecoin
    "DOTUSDT",  # Polkadot
    "LINKUSDT", # Chainlink

]
INTERVAL = "1m"  # 1 minute candles
LIMIT = 500

client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# ==============================
# TELEGRAM FUNCTION
# ==============================
def send_telegram_signal(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

# ==============================
# GET HISTORICAL DATA
# ==============================
def get_data(symbol):
    print(f"Fetching data {symbol}")
    klines = client.get_klines(symbol=symbol, interval=INTERVAL, limit=LIMIT)
    df = pd.DataFrame(klines, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_asset_volume","number_of_trades",
        "taker_buy_base","taker_buy_quote","ignore"
    ])
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)
    df['time'] = pd.to_datetime(df['open_time'], unit='ms')
    return df

# ==============================
# ADD INDICATORS
# ==============================
def add_indicators(df):
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
    df['vol_mean'] = df['volume'].rolling(20).mean()
    df['vol_spike'] = df['volume'] > 1.8 * df['vol_mean']

    return df


def get_spread(symbol):
    book = client.get_order_book(symbol=symbol, limit=5)
    bid = float(book['bids'][0][0])
    ask = float(book['asks'][0][0])
    spread = ask - bid
    spread_pct = spread / bid * 100
    return spread, spread_pct

def market_is_tradable(df, symbol):
    row = df.iloc[-1]

    # ===== Spread filter =====
    spread, spread_pct = get_spread(symbol)
    if spread_pct > 0.15:   # 0.15% max for scalping
        return False

    # ===== Volatility filter (avoid news spikes) =====
    atr_ratio = row['atr'] / row['atr_mean']
    if atr_ratio > 3:   # insane volatility
        return False

    # ===== Volume filter (avoid dead markets) =====
    if row['volume'] < row['vol_mean']:
        return False

    # ===== Huge candle filter (stop hunts) =====
    candle_size = row['high'] - row['low']
    if candle_size > 3 * row['atr']:
        return False

    return True

def market_regime(row):
    trend_strength = abs(row['ema9'] - row['ema50']) / row['close']
    
    if trend_strength > 0.002:  # strong trend
        return "trend"
    else:
        return "range"
    

def get_structure_levels(df):
    recent_low = df['low'].rolling(20).min().iloc[-1]
    recent_high = df['high'].rolling(20).max().iloc[-1]
    return recent_low, recent_high

def calculate_sl_tp(df, signal_type, sl_mult=1.5, rr=2):
    row = df.iloc[-1]
    atr = row['atr']
    entry = row['close']

    recent_low, recent_high = get_structure_levels(df)
    regime = market_regime(row)

    # ===== LONG =====
    if signal_type == "BUY":
        atr_sl = entry - atr * sl_mult
        structure_sl = recent_low - atr * 0.2
        sl = min(atr_sl, structure_sl)

        # TP based on regime
        if regime == "trend":
            tp = entry + atr * rr * 1.5
        else:
            tp = entry + atr * rr

    # ===== SHORT =====
    else:
        atr_sl = entry + atr * sl_mult
        structure_sl = recent_high + atr * 0.2
        sl = max(atr_sl, structure_sl)

        if regime == "trend":
            tp = entry - atr * rr * 1.5
        else:
            tp = entry - atr * rr

    return round(sl, 4), round(tp, 4)

# ==============================
# GENERATE SIGNALS
# ==============================
def generate_signal_current_candle(df, symbol,sl_multiplier=1.5, tp_multiplier=2):
    """
    Generates a trading signal only for the latest candle.
    """
    if df.empty or len(df) < 52:
        return None  # Not enough data

    row = df.iloc[-1]
    prev = df.iloc[-2]

    # ✅ FILTER BAD MARKET CONDITIONS
    if not market_is_tradable(df, symbol):
        return None
    
    atr = row['atr']

    # ----- LONG SIGNAL -----
    # EMA veloce sopra EMA media sopra EMA lenta
    trend_long = row['ema9'] > row['ema20'] > row['ema50']
    # il prezzo è tornato indietro fino alla EMA20
    pullback_long = row['low'] <= row['ema20']
    # ENGULFING LONG: candela bullish che ingloba la precedente (segnale di inversione/momentum)
    # 1) candela verde
    # 2) apre sotto la chiusura precedente
    # 3) chiude sopra l apertura precedente
    
    engulf_long = (row['close'] > row['open']) and (row['open'] < prev['close']) and (row['close'] > prev['open'])
    atr_expand = row['atr'] > 1.3 * row['atr_mean']

    if trend_long and pullback_long and engulf_long and row['vol_spike'] and atr_expand:
        entry_price = row['close']
        sl, tp = calculate_sl_tp(df, "BUY")
        return {
            "time": row['time'],
            "type": "BUY",
            "price": round(entry_price, 4),
            "sl": round(sl, 4),
            "tp": round(tp, 4)
        }

    # ----- SHORT SIGNAL -----
    # EMA veloce sotto EMA media sotto EMA lenta
    trend_short = row['ema9'] < row['ema20'] < row['ema50']
    # il prezzo è risalito fino alla EMA20
    pullback_short = row['high'] >= row['ema20']
    # ENGULFING SHORT: candela bearish che ingloba la precedente (segnale di inversione/momentum)
    # 1) candela rossa
    # 2) apre sopra la chiusura precedente
    # 3) chiude sotto l’apertura precedente
    engulf_short = (row['close'] < row['open']) and (row['open'] > prev['close']) and (row['close'] < prev['open'])

    if trend_short and pullback_short and engulf_short and row['vol_spike'] and atr_expand:
        entry_price = row['close']
        sl, tp = calculate_sl_tp(df, "SELL")
        return {
            "time": row['time'],
            "type": "SELL",
            "price": round(entry_price, 4),
            "sl": round(sl, 4),
            "tp": round(tp, 4)
        }

    return None  # No signal on this candle
# ==============================
# SCAN MULTIPLE PAIRS
# ==============================
def scan_pairs_current_candle(pairs):
    results = []

    for symbol in pairs:
        df = get_data(symbol)
        df = add_indicators(df)
        signal = generate_signal_current_candle(df,symbol)

        if signal:
            results.append({
                "symbol": symbol,
                "time": signal['time'],
                "type": signal['type'],
                "price": signal['price'],
                "sl": signal['sl'],
                "tp": signal['tp']
            })

            message = f"""
🚨 *TRADING SIGNAL*

📊 Symbol: *{symbol}*
🕒 Time: `{signal['time']}`
📌 Type: *{signal['type']}*
💰 Entry: `{signal['price']}`
🛑 SL: `{signal['sl']}`
🎯 TP: `{signal['tp']}`
"""
            send_telegram_signal(message)

    return pd.DataFrame(results)
# ==============================
# LOOP FOR LIVE SCANNING
# ==============================
def main():
    while True:
        try:
            signals_df = scan_pairs_current_candle(PAIRS)
            if not signals_df.empty:
                print(f"{datetime.now()} - Active Signals:")
                print(signals_df)
            else:
                print(f"{datetime.now()} - No signals on current candles.")
        except Exception as e:
            print("Error:", e)

        time.sleep(60)  # Check every minute for M1
        
        
main()