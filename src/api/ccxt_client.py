"""
CCXT API 客户端适配
提供与现有 OrderManager 兼容的异步接口：place_order/cancel_order/get_order
"""

import os
from typing import Dict, Any, Optional
from loguru import logger


class CCXTClient:
    def __init__(self, api_key: str, secret: str, passphrase: str, testnet: bool = True, exchange_type: str = "okx"):
        import ccxt.async_support as ccxt
        self.ccxt = ccxt
        self.exchange_type = (exchange_type or "okx").lower()
        if self.exchange_type == "okx":
            self.exchange = ccxt.okx({
                'apiKey': api_key,
                'secret': secret,
                'password': passphrase,
                'enableRateLimit': True,
                'options': { 'defaultType': 'swap' }
            })
        elif self.exchange_type == "binance":
            self.exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': { 'defaultType': 'future' }
            })
        elif self.exchange_type == "bybit":
            self.exchange = ccxt.bybit({
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': { 'defaultType': 'swap' }
            })
        else:
            self.exchange = ccxt.okx({
                'apiKey': api_key,
                'secret': secret,
                'password': passphrase,
                'enableRateLimit': True,
                'options': { 'defaultType': 'swap' }
            })
        if testnet:
            try:
                self.exchange.setSandboxMode(True)
            except Exception:
                pass

        # 开发调试：输出接口参数
        self.api_debug = str(os.getenv("API_DEBUG", "false")).lower() == "true"

    def _convert_symbol(self, symbol: str) -> str:
        try:
            s = symbol.upper()
            if s.endswith('-SWAP'):
                base, quote, _ = s.split('-')
                if self.exchange_type in ("okx", "bybit"):
                    return f"{base}/{quote}:{quote}"
                return f"{base}/{quote}"
            if '-' in s:
                base, quote = s.split('-')
                return f"{base}/{quote}"
            return symbol
        except Exception:
            return symbol

    async def fetch_ticker_price(self, symbol: str) -> Optional[float]:
        try:
            market = self._convert_symbol(symbol)
            t = await self.exchange.fetch_ticker(market)
            last = t.get('last') if isinstance(t, dict) else None
            return float(last) if last is not None else None
        except Exception:
            return None

    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 2) -> Optional[list]:
        try:
            market = self._convert_symbol(symbol)
            data = await self.exchange.fetch_ohlcv(market, timeframe=timeframe, limit=limit)
            return data
        except Exception:
            return None

    def available_timeframes(self) -> Optional[list]:
        try:
            tf = getattr(self.exchange, 'timeframes', None)
            if isinstance(tf, dict):
                return list(tf.keys())
            return None
        except Exception:
            return None

    async def place_order(self, symbol: str, side: str, order_type: str, size: float,
                          price: Optional[float] = None, pos_side: Optional[str] = None) -> Dict[str, Any]:
        market = self._convert_symbol(symbol)
        if self.api_debug:
            logger.debug(f"CCXT PLACE_ORDER market={market} side={side} type={order_type} size={size} price={price}")
        try:
            params = {}
            # OKX 的 ccxt 可能需要 tdMode/posSide，保持最简参数
            order = await self.exchange.create_order(market, order_type, side, size, price, params)
            # 统一返回结构，与 OKXClient 对齐
            data = {
                'ordId': str(order.get('id') or order.get('order', {}).get('id', ''))
            }
            return {'success': True, 'data': data}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        market = self._convert_symbol(symbol)
        if self.api_debug:
            logger.debug(f"CCXT CANCEL_ORDER market={market} ordId={order_id}")
        try:
            await self.exchange.cancel_order(order_id, market)
            return {'success': True, 'data': {}}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def get_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        market = self._convert_symbol(symbol)
        if self.api_debug:
            logger.debug(f"CCXT GET_ORDER market={market} ordId={order_id}")
        try:
            o = await self.exchange.fetch_order(order_id, market)
            # 映射状态到内部字段
            status = str(o.get('status', ''))
            state_map = {
                'open': 'live',
                'closed': 'filled',
                'canceled': 'cancelled',
                'expired': 'expired',
                'rejected': 'rejected',
                'partially_filled': 'partially_filled'
            }
            item = {
                'ordId': str(o.get('id', '')),
                'state': state_map.get(status, 'live'),
                'fillSz': float(o.get('filled', 0) or 0),
                'avgPx': float(o.get('average', 0) or 0),
                'fee': float(o.get('fee', 0) or 0)
            }
            return {'success': True, 'data': item}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass
