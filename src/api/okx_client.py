"""
OKX API客户端模块
提供与OKX交易所的API连接功能
"""

import os
import time
import hmac
import hashlib
import base64
import requests
import json
from typing import Dict, List, Optional, Any
from loguru import logger
from dataclasses import dataclass


@dataclass
class OKXConfig:
    """OKX API配置"""
    api_key: str
    secret_key: str
    passphrase: str
    testnet: bool = True
    base_url: str = "https://www.okx.com"
    
    def __post_init__(self):
        if self.testnet:
            self.base_url = "https://www.okx.com"


class OKXClient:
    """OKX API客户端"""
    
    def __init__(self, config: OKXConfig):
        self.config = config
        self.session = requests.Session()
        # 交易模式默认：现货为 cash，永续合约为 cross
        self.default_swap_tdmode = "cross"
        
    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """生成API签名"""
        message = timestamp + method.upper() + request_path + body
        mac = hmac.new(
            bytes(self.config.secret_key, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )
        d = mac.digest()
        return base64.b64encode(d).decode()
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict:
        """发送API请求"""
        timestamp = str(time.time())
        request_path = f"/api/v5{endpoint}"
        url = f"{self.config.base_url}{request_path}"
        
        # 准备请求头
        headers = {
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": self.config.api_key,
            "OK-ACCESS-PASSPHRASE": self.config.passphrase,
            "OK-ACCESS-TIMESTAMP": timestamp,
        }

        # 在模拟交易模式下添加OKX要求的标头
        # 参考OKX文档：在REST请求中设置 x-simulated-trading: 1 表示使用模拟环境
        if getattr(self.config, "testnet", False):
            headers["x-simulated-trading"] = "1"
        
        # 生成签名
        body = json.dumps(data) if data else ""
        signature = self._generate_signature(timestamp, method, request_path, body)
        headers["OK-ACCESS-SIGN"] = signature
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = self.session.post(url, headers=headers, json=data)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
            
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != "0":
                logger.error(f"API错误: {result.get('msg', '未知错误')}")
                raise Exception(f"API错误: {result.get('msg', '未知错误')}")
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API请求失败: {e}")
            raise
    
    # 账户相关API
    def get_account_balance(self) -> Dict:
        """获取账户余额（同步）"""
        return self._make_request("GET", "/account/balance")
    
    def get_positions(self, inst_type: str = "SWAP") -> Dict:
        """获取持仓信息"""
        params = {"instType": inst_type}
        return self._make_request("GET", "/account/positions", params=params)
    
    # 市场数据API
    def get_ticker(self, inst_id: str) -> Dict:
        """获取行情数据"""
        params = {"instId": inst_id}
        return self._make_request("GET", "/market/ticker", params=params)
    
    def get_candles(self, inst_id: str, bar: str = "1m", limit: int = 100) -> Dict:
        """获取K线数据"""
        params = {
            "instId": inst_id,
            "bar": bar,
            "limit": str(limit)
        }
        return self._make_request("GET", "/market/candles", params=params)
    
    def get_orderbook(self, inst_id: str, depth: int = 20) -> Dict:
        """获取订单簿"""
        params = {
            "instId": inst_id,
            "sz": str(depth)
        }
        return self._make_request("GET", "/market/books", params=params)
    
    # 交易相关API
    def place_order_sync(self, inst_id: str, side: str, ord_type: str, sz: str, 
                   px: Optional[str] = None, pos_side: Optional[str] = None) -> Dict:
        """下单（同步）"""
        # 根据交易品种自动选择交易模式
        td_mode = "cash"
        try:
            if inst_id and inst_id.upper().endswith("-SWAP"):
                td_mode = self.default_swap_tdmode
        except Exception:
            pass

        data = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz
        }
        
        if px:
            data["px"] = px
        if pos_side:
            data["posSide"] = pos_side
            
        return self._make_request("POST", "/trade/order", data=data)

    # --------------------
    # 异步包装，适配上层 await 调用
    # --------------------
    async def get_account_balance_async(self) -> Dict[str, Any]:
        import asyncio
        def _call():
            return self._make_request("GET", "/account/balance")
        result = await asyncio.to_thread(_call)
        return {"success": True, "data": result.get("data", [])}

    async def place_order(self, symbol: str, side: str, order_type: str, size: float,
                          price: Optional[float] = None, pos_side: Optional[str] = None) -> Dict[str, Any]:
        """兼容订单管理器的异步下单接口"""
        import asyncio
        inst_id = symbol
        ord_type = order_type
        sz = str(size)
        px = str(price) if price is not None else None
        def _call():
            return self.place_order_sync(inst_id=inst_id, side=side, ord_type=ord_type, sz=sz, px=px, pos_side=pos_side)
        try:
            raw = await asyncio.to_thread(_call)
            return {"success": True, "data": raw.get("data", {})}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """异步撤单接口"""
        import asyncio
        def _call():
            return self._make_request("POST", "/trade/cancel-order", data={"instId": symbol, "ordId": order_id})
        try:
            raw = await asyncio.to_thread(_call)
            return {"success": True, "data": raw.get("data", {})}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_open_orders(self, symbol: str) -> Dict[str, Any]:
        """异步查询挂单"""
        import asyncio
        def _call():
            return self._make_request("GET", "/trade/orders-pending", params={"instId": symbol})
        try:
            raw = await asyncio.to_thread(_call)
            return {"success": True, "data": raw.get("data", [])}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """异步查询单个订单状态（通过订单历史匹配）"""
        import asyncio
        def _call():
            # 使用订单历史进行匹配（OKX未提供直接查询单个订单的公共接口）
            resp = self._make_request("GET", "/trade/orders-history", params={"instId": symbol, "limit": "100"})
            arr = resp.get("data", [])
            for item in arr:
                if item.get("ordId") == order_id:
                    return item
            return None
        try:
            item = await asyncio.to_thread(_call)
            if item:
                return {"success": True, "data": item}
            else:
                return {"success": False, "error": "未找到订单"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def cancel_order_sync(self, inst_id: str, ord_id: str) -> Dict:
        """撤单（同步）"""
        data = {
            "instId": inst_id,
            "ordId": ord_id
        }
        return self._make_request("POST", "/trade/cancel-order", data=data)
    
    def get_order_history(self, inst_id: str, limit: int = 100) -> Dict:
        """获取订单历史"""
        params = {
            "instId": inst_id,
            "limit": str(limit)
        }
        return self._make_request("GET", "/trade/orders-history", params=params)
    
    def get_open_orders_sync(self, inst_id: str) -> Dict:
        """获取当前挂单（同步）"""
        params = {"instId": inst_id}
        return self._make_request("GET", "/trade/orders-pending", params=params)
    
    # WebSocket相关
    def get_ws_auth(self) -> Dict:
        """获取WebSocket认证信息"""
        timestamp = str(time.time())
        method = "GET"
        request_path = "/users/self/verify"
        
        message = timestamp + method.upper() + request_path
        mac = hmac.new(
            bytes(self.config.secret_key, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )
        signature = base64.b64encode(mac.digest()).decode()
        
        return {
            "apiKey": self.config.api_key,
            "passphrase": self.config.passphrase,
            "timestamp": timestamp,
            "sign": signature
        }