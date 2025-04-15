# binance_super_bot.py
import os
import time
import requests
from datetime import datetime
from binance.client import Client
from binance.enums import HistoricalKlinesType
import numpy as np
import ta
import pytz

# === CONFIG ===
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

client = Client(API_KEY, API_SECRET)
timezone = pytz.timezone("UTC")

FUTURES = True  # True for Futures, False for Spot
SPOT_BASE = 'USDC'
FUTURES_BASE = 'USDT'

INTERVAL = Client.KLINE_INTERVAL_15MINUTE
LOOKBACK = 200

# === INDICATORS ===
def calculate_indicators(df):
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], 14).rsi()
    df['ema'] = ta.trend.EMAIndicator(df['close'], 20).ema_indicator()
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], 14).average_true_range()
    return df

# === STRATEGY ===
def check_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Spadający nóż – 3 duże czerwone świece
    red_candles = ((df['close'] < df['open'])[-3:]).sum()
    big_body = abs(last['close'] - last['open']) > (df['atr'].iloc[-1] * 0.8)
    no_wick = (last['low'] >= min(df['low'][-3:]))

    if red_candles >= 3 and big_body and no_wick:
        return None

    if last['rsi'] < 25 and last['close'] > last['ema']:
        return 'LONG'
    if last['rsi'] > 75 and last['close'] < last['ema']:
        return 'SHORT'
    return None

# === TRADE SETUP ===
def generate_trade_signal(symbol, df, direction):
    entry = df['close'].iloc[-1]
    atr = df['atr'].iloc[-1]
    sl = entry - 1.2 * atr if direction == 'LONG' else entry + 1.2 * atr
    tps = [entry + atr * m for m in range(1, 6)] if direction == 'LONG' else [entry - atr * m for m in range(1, 6)]
    leverage = 125 if FUTURES else 1

    signal = f"""
📣 Nowy sygnał ({'FUTURES' if FUTURES else 'SPOT'})
🪙 Para: {symbol}
{'🐂 LONG' if direction == 'LONG' else '🐻 SHORT'}
🎯 Entry: {entry:.2f}
📉 SL: {sl:.2f}
🎯 TP1: {tps[0]:.2f}
🎯 TP2: {tps[1]:.2f}
🎯 TP3: {tps[2]:.2f}
🎯 TP4: {tps[3]:.2f}
🎯 TP5: {tps[4]:.2f}
🧨 Lewar: {leverage}x
📊 Potwierdzenie: RSI i EMA ✅
"""
    return signal

# === TELEGRAM ===
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    requests.post(url, data=payload)

# === MAIN ===
def fetch_klines(symbol):
    try:
        klines = client.get_klines(symbol=symbol, interval=INTERVAL, limit=LOOKBACK)
        df = {
            'open': np.array([float(k[1]) for k in klines]),
            'high': np.array([float(k[2]) for k in klines]),
            'low': np.array([float(k[3]) for k in klines]),
            'close': np.array([float(k[4]) for k in klines])
        }
        df = {k: list(v) for k, v in df.items()}
        import pandas as pd
        df = pd.DataFrame(df)
        df = calculate_indicators(df)
        return df
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

def scan():
    base = FUTURES_BASE if FUTURES else SPOT_BASE
    market = client.get_ticker_price()
    pairs = [m['symbol'] for m in market if m['symbol'].endswith(base)]

    for symbol in pairs:
        df = fetch_klines(symbol)
        if df is None or df.isna().any().any():
            continue
        signal = check_signal(df)
        if signal:
            msg = generate_trade_signal(symbol, df, signal)
            send_telegram(msg)

if __name__ == '__main__':
    while True:
        scan()
        time.sleep(900)  # co 15 minut
