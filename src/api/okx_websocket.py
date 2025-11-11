"""
OKX WebSocket客户端
提供实时市场数据和订单推送
"""

import asyncio
import json
import websockets
from typing import Dict, List, Callable, Optional
from loguru import logger
from datetime import datetime


class OKXWebSocketClient:
    """OKX WebSocket客户端"""
    
    def __init__(self, auth_data: Dict):
        self.auth_data = auth_data
        self.ws = None
        self.is_connected = False
        self.subscriptions = set()
        self.callbacks = {}
        self.reconnect_interval = 5  # 重连间隔（秒）
        
    async def connect(self, testnet: bool = True):
        """连接到WebSocket服务器"""
        url = "wss://wspap.okx.com:8443/ws/v5/public" if testnet else "wss://ws.okx.com:8443/ws/v5/public"
        
        # 在模拟交易模式下，部分环境需要在WebSocket握手时附带 x-simulated-trading 标头
        extra_headers = {"x-simulated-trading": "1"} if testnet else None
        
        try:
            # websockets.connect 支持 extra_headers 传递额外HTTP头
            if extra_headers:
                self.ws = await websockets.connect(url, extra_headers=extra_headers)
            else:
                self.ws = await websockets.connect(url)
            self.is_connected = True
            logger.info("WebSocket连接成功")
            
            # 启动消息监听任务
            asyncio.create_task(self._listen())
            
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            await self._reconnect()
    
    async def disconnect(self):
        """断开WebSocket连接"""
        self.is_connected = False
        if self.ws:
            await self.ws.close()
            logger.info("WebSocket连接已断开")
    
    async def _listen(self):
        """监听WebSocket消息"""
        try:
            async for message in self.ws:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket连接已关闭")
            await self._reconnect()
        except Exception as e:
            logger.error(f"WebSocket监听错误: {e}")
            await self._reconnect()
    
    async def _reconnect(self):
        """重连机制"""
        if not self.is_connected:
            return
            
        logger.info(f"{self.reconnect_interval}秒后重连...")
        await asyncio.sleep(self.reconnect_interval)
        
        try:
            await self.connect()
            # 重新订阅之前的频道
            for channel in self.subscriptions:
                await self.subscribe(channel)
        except Exception as e:
            logger.error(f"重连失败: {e}")
            await self._reconnect()
    
    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            
            # 处理心跳
            if data.get("event") == "subscribe":
                logger.info(f"订阅成功: {data.get('arg', {})}")
                return
            
            if data.get("event") == "error":
                logger.error(f"WebSocket错误: {data.get('msg', '未知错误')}")
                return
            
            # 处理数据推送
            if "arg" in data and "data" in data:
                channel = data["arg"].get("channel")
                inst_id = data["arg"].get("instId")
                key = f"{channel}:{inst_id}" if channel and inst_id else channel
                callback = self.callbacks.get(key) or self.callbacks.get(channel)
                if callback:
                    await callback(data["data"])
                    
        except json.JSONDecodeError:
            logger.error(f"解析消息失败: {message}")
        except Exception as e:
            logger.error(f"处理消息错误: {e}")
    
    async def subscribe(self, channel: str, inst_id: str, callback: Callable):
        """订阅频道"""
        subscription = {
            "op": "subscribe",
            "args": [{
                "channel": channel,
                "instId": inst_id
            }]
        }
        
        try:
            await self.ws.send(json.dumps(subscription))
            self.subscriptions.add(f"{channel}:{inst_id}")
            self.callbacks[f"{channel}:{inst_id}"] = callback
            logger.info(f"已订阅: {channel} - {inst_id}")
        except Exception as e:
            logger.error(f"订阅失败: {e}")
    
    async def unsubscribe(self, channel: str, inst_id: str):
        """取消订阅"""
        unsubscription = {
            "op": "unsubscribe",
            "args": [{
                "channel": channel,
                "instId": inst_id
            }]
        }
        
        try:
            await self.ws.send(json.dumps(unsubscription))
            self.subscriptions.discard(f"{channel}:{inst_id}")
            self.callbacks.pop(f"{channel}:{inst_id}", None)
            logger.info(f"已取消订阅: {channel} - {inst_id}")
        except Exception as e:
            logger.error(f"取消订阅失败: {e}")
    
    # 常用订阅方法
    async def subscribe_ticker(self, inst_id: str, callback: Callable):
        """订阅行情数据"""
        await self.subscribe("tickers", inst_id, callback)
    
    async def subscribe_orderbook(self, inst_id: str, callback: Callable):
        """订阅订单簿"""
        await self.subscribe("books", inst_id, callback)
    
    async def subscribe_candles(self, inst_id: str, bar: str, callback: Callable):
        """订阅K线数据"""
        await self.subscribe(f"candle{bar}", inst_id, callback)
    
    async def subscribe_trades(self, inst_id: str, callback: Callable):
        """订阅成交数据"""
        await self.subscribe("trades", inst_id, callback)
    
    async def subscribe_account(self, callback: Callable):
        """订阅账户数据（需要认证）"""
        if not self.auth_data:
            logger.error("订阅账户数据需要认证信息")
            return
        
        # 发送认证信息
        auth_msg = {
            "op": "login",
            "args": [self.auth_data]
        }
        
        try:
            await self.ws.send(json.dumps(auth_msg))
            await self.subscribe("account", "default", callback)
        except Exception as e:
            logger.error(f"账户订阅失败: {e}")


class MarketDataHandler:
    """市场数据处理类"""
    
    def __init__(self):
        self.price_cache = {}
        self.orderbook_cache = {}
        self.candle_cache = {}
    
    async def handle_ticker(self, data: List[Dict]):
        """处理行情数据"""
        for ticker in data:
            inst_id = ticker.get("instId")
            if inst_id:
                self.price_cache[inst_id] = {
                    "last": float(ticker.get("last", 0)),
                    "bid": float(ticker.get("bidPx", 0)),
                    "ask": float(ticker.get("askPx", 0)),
                    "vol": float(ticker.get("vol24h", 0)),
                    "timestamp": datetime.now()
                }
                logger.debug(f"行情更新: {inst_id} - 价格: {ticker.get('last')}")
    
    async def handle_orderbook(self, data: List[Dict]):
        """处理订单簿数据"""
        for book in data:
            inst_id = book.get("instId")
            if inst_id:
                self.orderbook_cache[inst_id] = {
                    "bids": [[float(price), float(size)] for price, size in book.get("bids", [])],
                    "asks": [[float(price), float(size)] for price, size in book.get("asks", [])],
                    "timestamp": datetime.now()
                }
    
    async def handle_candles_ws(self, inst_id: str, data: List):
        """处理来自OKX WebSocket的K线数据
        OKX公共频道 candle{bar} 推送的数据为数组形式，例如：
        [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        这里我们仅使用 o/h/l/c/vol。
        """
        try:
            if not data:
                return
            # 取最后一根（最新）K线
            last = data[-1]
            if isinstance(last, list) and len(last) >= 6:
                # 解析时间戳与收盘确认标记
                ts_val = None
                confirm_val = False
                try:
                    ts_val = int(last[0])
                except Exception:
                    ts_val = None
                try:
                    raw_confirm = last[8] if len(last) >= 9 else 0
                    # OKX文档：confirm布尔，部分实现可能为'1'/'0'或'true'/'false'
                    confirm_val = str(raw_confirm).lower() in ("true", "1")
                except Exception:
                    confirm_val = False
                # 解析数组索引
                open_px = float(last[1])
                high_px = float(last[2])
                low_px = float(last[3])
                close_px = float(last[4])
                volume = float(last[5])
                self.candle_cache[inst_id] = {
                    "open": open_px,
                    "high": high_px,
                    "low": low_px,
                    "close": close_px,
                    "volume": volume,
                    "timestamp": datetime.now(),
                    "ts": ts_val,
                    "confirm": confirm_val
                }
                logger.debug(f"K线更新: {inst_id} - close: {close_px}")
            elif isinstance(last, dict):
                # 兼容字典格式（如REST归一化后）
                self.candle_cache[inst_id] = {
                    "open": float(last.get("o", 0)),
                    "high": float(last.get("h", 0)),
                    "low": float(last.get("l", 0)),
                    "close": float(last.get("c", 0)),
                    "volume": float(last.get("vol", 0)),
                    "timestamp": datetime.now(),
                    "ts": int(last.get("ts", 0)) if last.get("ts") else None,
                    "confirm": bool(last.get("confirm", False))
                }
            else:
                logger.warning(f"未识别的K线数据格式: {type(last)}")
        except Exception as e:
            logger.error(f"处理K线数据错误: {e}")
    
    def get_latest_price(self, inst_id: str) -> Optional[float]:
        """获取最新价格"""
        ticker = self.price_cache.get(inst_id)
        return ticker["last"] if ticker else None
    
    def get_orderbook(self, inst_id: str) -> Optional[Dict]:
        """获取订单簿"""
        return self.orderbook_cache.get(inst_id)
    
    def get_latest_candle(self, inst_id: str) -> Optional[Dict]:
        """获取最新K线"""
        return self.candle_cache.get(inst_id)