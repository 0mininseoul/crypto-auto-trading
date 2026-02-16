import asyncio
import sys
import os
from pprint import pprint

# Add project root to python path
sys.path.append(os.getcwd())

from src.exchange.bitget_client import get_bitget_client
from src.config.trading_mode import is_demo_mode

async def main():
    print(f"Current Mode: {'DEMO' if is_demo_mode() else 'LIVE'}")
    
    client = get_bitget_client()
    try:
        # Force connection
        await client._get_exchange()
        print("Connected via BitgetClient.")
        
        print("\n--- Testing get_balance() ---")
        try:
            balance = await client.get_balance()
            print("Balance Result:")
            pprint(balance)
            
            if balance['total'] > 0:
                print("\n✅ SUCCESS: Balance found!")
            else:
                print("\n❌ FAILED: Balance is still 0.")
                
        except Exception as e:
            print(f"Error calling get_balance(): {e}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
