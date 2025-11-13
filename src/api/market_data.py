from typing import Dict, Any, Optional
from datetime import datetime

class MarketDataHandler:
    def __init__(self):
        self.price_cache: Dict[str, Dict[str, Any]] = {}
        self.candle_cache: Dict[str, Dict[str, Any]] = {}

    async def handle_orderbook(self, symbol: str, book: Dict[str, Any]):
        bid = 0.0
        ask = 0.0
        try:
            bids = book.get("bids") or []
            asks = book.get("asks") or []
            bid = float(bids[0][0]) if bids else 0.0
            ask = float(asks[0][0]) if asks else 0.0
        except Exception:
            pass
        self.price_cache[symbol] = {
            "last": bid or ask,
            "bid": bid,
            "ask": ask,
            "vol": float(book.get("vol", 0.0)) if isinstance(book.get("vol", 0.0), (int, float)) else 0.0,
            "timestamp": datetime.now(),
        }

    def get_latest_price(self, symbol: str) -> Optional[float]:
        try:
            p = self.price_cache.get(symbol) or {}
            val = p.get("last")
            if val is None:
                val = p.get("bid") or p.get("ask")
            return float(val) if val is not None else None
        except Exception:
            return None

    def get_latest_candle(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            return self.candle_cache.get(symbol)
        except Exception:
            return None

    def set_latest_candle(self, symbol: str, o: float, h: float, l: float, c: float, v: float, ts: int, confirm: bool = True):
        try:
            self.candle_cache[symbol] = {
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
                "timestamp": datetime.now(),
                "ts": int(ts),
                "confirm": bool(confirm),
            }
        except Exception:
            pass

    def update_price(self, symbol: str, price: float):
        try:
            cur = self.price_cache.get(symbol) or {}
            cur.update({
                "last": float(price),
                "bid": float(price),
                "ask": float(price),
                "timestamp": datetime.now(),
            })
            self.price_cache[symbol] = cur
        except Exception:
            pass
