
import asyncio
import os
import sys

# Add project root to path
sys.path.append("/Users/ym/Desktop/개발/bitcoin autotrading")

from src.exchange.bitget_client import BitgetClient
from datetime import datetime, timezone

async def test_fetch_candles():
    client = BitgetClient()
    # Fetch 15m candles
    # Using 'BTC/USDT:USDT' as standard
    print("Fetching 15m candles...")
    candles = await client.get_ohlcv("BTC/USDT:USDT", "15m", limit=5)
    
    if candles:
        last_candle = candles[-1]
        timestamp = last_candle[0]
        dt = datetime.fromtimestamp(timestamp/1000, tz=timezone.utc)
        print(f"Last candle timestamp: {dt}")
        print(f"Last candle volume: {last_candle[5]}")
        
        # Check if it's the current open candle
        now = datetime.now(timezone.utc)
        print(f"Current UTC time: {now}")
        
        diff = (now - dt).total_seconds() / 60
        print(f"Minutes since candle start: {diff:.1f}")
        
        if diff < 15:
            print("RESULT: Last candle is the CURRENT OPEN candle.")
        else:
            print("RESULT: Last candle is the PREVIOUS CLOSED candle.")
            
    await client.close()

if __name__ == "__main__":
    asyncio.run(test_fetch_candles())
