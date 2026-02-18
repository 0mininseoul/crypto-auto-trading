import asyncio
import sys
import os
from pprint import pprint

# Add project root to python path
sys.path.append(os.getcwd())

import ccxt.async_support as ccxt
from src.config.settings import get_settings
from src.config.trading_mode import is_demo_mode

async def main():
    print(f"Current Mode: {'DEMO' if is_demo_mode() else 'LIVE'}")
    
    settings = get_settings()
    
    # Test 1: Current Implementation (Header only)
    print("\n=== Test 1: Current Implementation (Header only) ===")
    config = {
        "apiKey": settings.bitget_api_key,
        "secret": settings.bitget_secret_key,
        "password": settings.bitget_passphrase,
        "options": {
            "defaultType": "swap",
            "defaultSubType": "linear",
            "headers": {"PAPTRADING": "1"}
        },
        "enableRateLimit": True,
    }
    
    exchange = ccxt.bitget(config)
    try:
        await exchange.load_markets()
        print("Connected.")
        
        # Check markets context
        print("First 5 symbols:", list(exchange.markets.keys())[:5])
        demo_markets = [m for m in exchange.markets.keys() if 'SBTC' in m or 'SUSDT' in m]
        print(f"Demo Markets Found: {demo_markets[:5]}")

        print("\n--- Futures (Swap) Balance ---")
        print("\n--- Futures (Swap) Balance Tests ---")
        product_types = ['USDT-FUTURES', 'SUSDT-FUTURES', 'umcbl', 'sumcbl']
        
        for pt in product_types:
            print(f"\nTesting productType: {pt}")
            try:
                # Note: ccxt might use specific keys for params like 'productType' or 'marginCoin'
                # For Bitget V2, it's often 'productType'
                balance = await exchange.fetch_balance({"type": "swap", "productType": pt})
                print(f"Keys: {list(balance.keys())}")
                if 'USDT' in balance: print(f"USDT: {balance['USDT']}")
                if 'SUSDT' in balance: print(f"SUSDT: {balance['SUSDT']}")
                if 'SBTC' in balance: print(f"SBTC: {balance['SBTC']}")
                
                if 'info' in balance and isinstance(balance['info'], list):
                     for item in balance['info']:
                        if float(item.get('available', 0)) > 0 or float(item.get('equity', 0)) > 0:
                            print(f"!!! FOUND FUNDS in {pt}: {item}")
            except Exception as e:
                print(f"Failed for {pt}: {e}")
            
        print("\n--- Spot Balance ---")
        try:
            balance_spot = await exchange.fetch_balance({"type": "spot"})
            print("Spot Balance keys:", list(balance_spot.keys()))
            if 'USDT' in balance_spot: print("Spot USDT:", balance_spot['USDT'])
            if 'SUSDT' in balance_spot: print("Spot SUSDT:", balance_spot['SUSDT'])
            
             # Check raw data for any SUSDT clue
            if 'info' in balance_spot:
                data = balance_spot['info']
                 # Bitget V2 balance structure
                if isinstance(data, list):
                    for item in data:
                        if float(item.get('available', 0)) > 0:
                            print(f"Non-zero asset (Spot): {item}")
        except Exception as e:
            print(f"Fetch spot balance failed: {e}")

    finally:
        await exchange.close()

    # Test 2: Using set_sandbox_mode(True)
    print("\n=== Test 2: Using set_sandbox_mode(True) ===")
    config2 = {
        "apiKey": settings.bitget_api_key,
        "secret": settings.bitget_secret_key,
        "password": settings.bitget_passphrase,
        "options": {
            "defaultType": "swap",
            "defaultSubType": "linear",
        },
        "enableRateLimit": True,
    }
    
    exchange = ccxt.bitget(config2)
    try:
        exchange.set_sandbox_mode(True)
        await exchange.load_markets()
        print("Connected with sandbox mode.")
        try:
            balance = await exchange.fetch_balance({"type": "swap"})
            print("Balance keys:", list(balance.keys()))
            if 'USDT' in balance: print("USDT:", balance['USDT'])
            if 'SUSDT' in balance: print("SUSDT:", balance['SUSDT'])
            if 'SBTC' in balance: print("SBTC:", balance['SBTC'])
        except Exception as e:
            print(f"Fetch balance failed: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
