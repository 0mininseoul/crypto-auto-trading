
import ccxt
import pandas as pd

import time
from datetime import datetime, timedelta
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.indicators.signals import check_long_entry, check_short_entry, prepare_dataframe, SignalType
from src.config.constants import (
    TIMEFRAMES, EMA_PERIODS, RSI_PERIOD, 
    MAX_STOP_LOSS_PERCENT, TAKE_PROFIT_LEVELS
)

def fetch_data(symbol='BTC/USDT', timeframe='15m', limit=1000, days=30):
    """Fetch historical data using CCXT"""
    exchange = ccxt.bitget()
    
    # Calculate start time
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    
    all_candles = []
    while since < exchange.milliseconds():
        candles = exchange.fetch_ohlcv(symbol, timeframe, since, limit=limit)
        if not candles:
            break
        all_candles.extend(candles)
        since = candles[-1][0] + 1
        time.sleep(0.1) # Rate limit
        
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # Remove duplicates
    df = df[~df.index.duplicated(keep='last')]
    
    return df

def run_backtest():
    print("🚀 Starting Backtest for 15m Day Trading Strategy...")
    
    # 1. Fetch Data
    print("📥 Fetching historical data (Last 30 days)...")
    df_15m = fetch_data(timeframe='15m', days=30)
    df_1h = fetch_data(timeframe='1h', days=30)
    df_5m = fetch_data(timeframe='5m', days=30)
    
    print(f"✅ Data fetched: 15m({len(df_15m)}), 1h({len(df_1h)}), 5m({len(df_5m)})")
    
    # 2. Calculate Indicators
    print("Calculaing indicators...")
    df_15m = prepare_dataframe(df_15m)
    df_1h = prepare_dataframe(df_1h)
    df_5m = prepare_dataframe(df_5m)
    
    # 3. Simulate Logic
    trades = []
    active_position = None
    balance = 10000  # Initial Balance
    initial_balance = balance
    
    print("🔄 Running simulation loop...")
    
    # Iterate through 15m candles (skip first 200 for indicators warmup)
    for i in range(200, len(df_15m)):
        curr_time = df_15m.index[i]
        
        # Get data slices up to current time
        slice_15m = df_15m.iloc[:i+1]
        
        # Get corresponding 1h and 5m data
        # Find the latest 1h candle before or at current time
        slice_1h = df_1h[df_1h.index <= curr_time]
        slice_5m = df_5m[df_5m.index <= curr_time]
        
        if len(slice_1h) < 50 or len(slice_5m) < 50:
            continue
            
        current_price = slice_15m['close'].iloc[-1]
        
        # --- Check Exit ---
        if active_position:
            pos = active_position
            
            # 1. Stop Loss
            if (pos['type'] == 'long' and current_price <= pos['sl']) or \
               (pos['type'] == 'short' and current_price >= pos['sl']):
                pnl_pct = (pos['sl'] - pos['entry']) / pos['entry'] if pos['type'] == 'long' else (pos['entry'] - pos['sl']) / pos['entry']
                pnl = pnl_pct * balance # Simple compound
                balance += pnl
                trades.append({
                    'type': 'SL', 'entry_time': pos['time'], 'exit_time': curr_time,
                    'pnl': pnl_pct * 100, 'balance': balance
                })
                active_position = None
                continue
                
            # 2. Take Profit 1
            if (pos['type'] == 'long' and current_price >= pos['tp1']) or \
               (pos['type'] == 'short' and current_price <= pos['tp1']):
                pnl_pct = (pos['tp1'] - pos['entry']) / pos['entry'] if pos['type'] == 'long' else (pos['entry'] - pos['tp1']) / pos['entry']
                pnl = pnl_pct * balance
                balance += pnl
                trades.append({
                    'type': 'TP1', 'entry_time': pos['time'], 'exit_time': curr_time,
                    'pnl': pnl_pct * 100, 'balance': balance
                })
                active_position = None
                continue

        # --- Check Entry ---
        if not active_position:
            long_signal = check_long_entry(slice_15m, slice_1h, slice_5m)
            short_signal = check_short_entry(slice_15m, slice_1h, slice_5m)
            
            if long_signal.signal_type == SignalType.LONG:
                active_position = {
                    'type': 'long', 'entry': long_signal.entry_price,
                    'sl': long_signal.stop_loss, 'tp1': long_signal.take_profit_1,
                    'time': curr_time
                }
            elif short_signal.signal_type == SignalType.SHORT:
                active_position = {
                    'type': 'short', 'entry': short_signal.entry_price,
                    'sl': short_signal.stop_loss, 'tp1': short_signal.take_profit_1,
                    'time': curr_time
                }
                
    # 4. Results
    print("\n" + "="*50)
    print("📊 BACKTEST RESULTS (Last 30 Days)")
    print("="*50)
    print(f"Total Trades: {len(trades)}")
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    total_pnl = (balance - initial_balance) / initial_balance * 100
    
    print(f"Win Rate: {win_rate:.2f}% ({len(wins)}W / {len(losses)}L)")
    print(f"Total PnL: {total_pnl:.2f}%")
    print(f"Final Balance: ${balance:.2f}")
    
    print("\nRecent Trades:")
    for t in trades[-5:]:
        print(f"{t['exit_time']} | {t['type']} | PnL: {t['pnl']:.2f}%")

if __name__ == "__main__":
    run_backtest()
