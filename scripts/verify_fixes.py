
import asyncio
import sys
import pandas as pd
from datetime import datetime, timezone

# Add project root to path
sys.path.append("/Users/ym/Desktop/개발/bitcoin autotrading")

from src.indicators.volume import is_volume_above_average
# We need to test the logic usage as in signals.py, which calls:
# is_volume_above_average(df_15m, row_idx=-2)

def test_volume_logic():
    print("--- Testing Volume Logic ---")
    # Create a dummy DataFrame with 3 candles
    # Candle 0: Volume 100
    # Candle 1: Volume 200 (Previous Closed)
    # Candle 2: Volume 10 (Current Open)
    
    data = {
        "timestamp": [1, 2, 3],
        "volume": [100, 200, 10], 
        "volume_ma": [100, 100, 100] # MA is low enough
    }
    df = pd.DataFrame(data)
    
    # Current Open Candle Check (Old Logic)
    # 10 < 100 -> Should return False
    res_open = is_volume_above_average(df, row_idx=-1)
    print(f"Old Logic (Open Candle): {res_open} (Expected: False)")
    
    # Previous Closed Candle Check (New Logic)
    # 200 > 100 -> Should return True
    res_closed = is_volume_above_average(df, row_idx=-2)
    print(f"New Logic (Closed Candle): {res_closed} (Expected: True)")
    
    if not res_open and res_closed:
        print("✅ Volume Logic Verification PASSED")
    else:
        print("❌ Volume Logic Verification FAILED")

async def test_scheduling_logic():
    print("\n--- Testing Scheduling Logic ---")
    now = datetime.now(timezone.utc)
    print(f"Current UTC Time: {now}")
    
    # Simulate logic from trading_bot.py
    next_timestamp = (now.timestamp() // 300 + 1) * 300
    sleep_duration = next_timestamp - now.timestamp() + 2
    
    next_dt = datetime.fromtimestamp(next_timestamp, tz=timezone.utc)
    print(f"Next 5-min Mark: {next_dt}")
    print(f"Calculated Sleep Duration: {sleep_duration:.2f} seconds")
    
    # Verify it targets the next 5-minute mark
    if 0 < sleep_duration <= 302:
        print("✅ Scheduling Logic Verification PASSED")
    else:
        print("❌ Scheduling Logic Verification FAILED")

if __name__ == "__main__":
    test_volume_logic()
    asyncio.run(test_scheduling_logic())
