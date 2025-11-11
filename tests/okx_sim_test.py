import os
import sys
import asyncio
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# 保证可以找到项目内的 src 包
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import OKXClient, OKXConfig


def main():
    cfg = OKXConfig(
        api_key=os.getenv("OKX_API_KEY"),
        secret_key=os.getenv("OKX_SECRET_KEY"),
        passphrase=os.getenv("OKX_PASSPHRASE"),
        testnet=os.getenv("OKX_TESTNET", "false").lower() == "true",
    )
    client = OKXClient(cfg)

    symbol = os.getenv("TRADING_SYMBOL", "BTC-USDT-SWAP")
    print("TESTNET", cfg.testnet, "SYMBOL", symbol)

    # 1) 余额查询（同步）
    try:
        bal = client.get_account_balance()
        print("BALANCE_CODE", bal.get("code"))
        print("BALANCE_MSG", bal.get("msg"))
        print("BALANCE_DATA_LEN", len(bal.get("data", [])))
    except Exception as e:
        print("BALANCE_ERROR", e)

    # 2) 行情查询
    try:
        tk = client.get_ticker(symbol)
        data = tk.get("data", [])
        last = None
        if isinstance(data, list) and data:
            last = data[0].get("last")
        elif isinstance(data, dict):
            last = data.get("last")
        print("TICKER_LAST", last)
    except Exception as e:
        print("TICKER_ERROR", e)

    # 3) 下发市价测试单，随后查询/撤单
    async def test_order():
        try:
            res = await client.place_order(
                symbol=symbol,
                side="buy",
                order_type="market",
                size=1,
            )
            print("PLACE_ORDER_RES", json.dumps(res))
            ord_id = res.get("data", {}).get("ordId")
            if not ord_id:
                print("NO_ORD_ID")
                return
            oo = await client.get_open_orders(symbol)
            print("OPEN_ORDERS_LEN", len(oo.get("data", [])))
            c = await client.cancel_order(symbol, ord_id)
            print("CANCEL_RES", json.dumps(c))
        except Exception as e:
            print("ORDER_ERROR", e)

    asyncio.run(test_order())


if __name__ == "__main__":
    main()