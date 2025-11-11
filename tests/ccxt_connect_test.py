import asyncio
import os

async def main():
    import ccxt.async_support as ccxt
    ex = ccxt.okx({'enableRateLimit': True})
    ex.setSandboxMode(True)
    t = await ex.fetch_ticker('BTC/USDT:USDT')
    print('CCXT_OKX_TICKER', 'last' in t, int(t.get('timestamp', 0)) > 0)
    await ex.close()

if __name__ == '__main__':
    asyncio.run(main())