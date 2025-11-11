"""
订单管理系统
提供订单创建、管理、执行和监控功能
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from loguru import logger
import uuid


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"  # 待处理
    SUBMITTED = "submitted"  # 已提交
    PARTIALLY_FILLED = "partially_filled"  # 部分成交
    FILLED = "filled"  # 完全成交
    CANCELLED = "cancelled"  # 已取消
    REJECTED = "rejected"  # 被拒绝
    EXPIRED = "expired"  # 已过期


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"  # 市价单
    LIMIT = "limit"  # 限价单
    STOP = "stop"  # 止损单
    STOP_LIMIT = "stop_limit"  # 止损限价单
    TRAILING_STOP = "trailing_stop"  # 跟踪止损单


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """订单信息"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Optional[float]
    size: float
    status: OrderStatus
    filled_size: float = 0.0
    filled_price: float = 0.0
    fee: float = 0.0
    client_order_id: str = ""
    exchange_order_id: str = ""
    created_time: datetime = field(default_factory=datetime.now)
    updated_time: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderResult:
    """订单执行结果"""
    success: bool
    order_id: str
    exchange_order_id: str = ""
    filled_size: float = 0.0
    filled_price: float = 0.0
    fee: float = 0.0
    error_message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class OrderManager:
    """订单管理器"""
    
    def __init__(self, api_client, risk_manager, portfolio_manager):
        """
        初始化订单管理器
        
        参数:
            api_client: API客户端
            risk_manager: 风险管理器
            portfolio_manager: 投资组合管理器
        """
        self.api_client = api_client
        self.risk_manager = risk_manager
        self.portfolio_manager = portfolio_manager
        
        # 订单存储
        self.active_orders: Dict[str, Order] = {}  # 活跃订单
        self.order_history: List[Order] = []  # 订单历史
        self.order_callbacks: Dict[str, List[Callable]] = {}  # 订单回调函数
        
        # 配置参数
        self.config = {
            "max_retry_attempts": 3,  # 最大重试次数
            "retry_delay": 1.0,  # 重试延迟(秒)
            "order_timeout": 300,  # 订单超时时间(秒)
            "batch_size": 10,  # 批量处理大小
            "enable_auto_cancel": True,  # 启用自动取消
            "cancel_after_seconds": 3600  # 订单自动取消时间(秒)
        }
        
        # 统计信息
        self.stats = {
            "total_orders": 0,
            "successful_orders": 0,
            "failed_orders": 0,
            "cancelled_orders": 0,
            "total_fees": 0.0
        }
        
        # 运行状态
        self.is_running = False
        self.monitor_task = None
        
        logger.info("订单管理器初始化完成")
    
    async def start(self):
        """启动订单管理器"""
        if self.is_running:
            return
        
        self.is_running = True
        self.monitor_task = asyncio.create_task(self._monitor_orders())
        logger.info("订单管理器已启动")
    
    async def stop(self):
        """停止订单管理器"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("订单管理器已停止")
    
    def create_order(self, symbol: str, side: str, order_type: str, 
                    size: float, price: Optional[float] = None,
                    client_order_id: str = "", metadata: Dict[str, Any] = None) -> str:
        """
        创建订单
        
        参数:
            symbol: 交易对
            side: 交易方向 (buy/sell)
            order_type: 订单类型 (market/limit/stop)
            size: 交易数量
            price: 价格(市价单可不传)
            client_order_id: 客户端订单ID
            metadata: 元数据
        
        返回:
            订单ID
        """
        # 生成订单ID
        if not client_order_id:
            client_order_id = f"order_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        
        # 验证订单参数
        validation_result = self._validate_order(symbol, side, order_type, size, price)
        if not validation_result["valid"]:
            logger.error(f"订单验证失败: {validation_result['error']}")
            raise ValueError(f"订单验证失败: {validation_result['error']}")
        
        # 风险检查
        risk_check = self.risk_manager.check_order_risk(symbol, side, size, price)
        if not risk_check["allowed"]:
            logger.error(f"风险检查失败: {risk_check['reason']}")
            raise ValueError(f"风险检查失败: {risk_check['reason']}")
        
        # 资金检查
        portfolio_check = self.portfolio_manager.can_open_position(
            symbol, side, size, price or 0
        )
        if not portfolio_check[0]:
            logger.error(f"资金检查失败: {portfolio_check[1]}")
            raise ValueError(f"资金检查失败: {portfolio_check[1]}")
        
        # 创建订单对象
        order = Order(
            order_id=client_order_id,
            symbol=symbol,
            side=OrderSide(side),
            order_type=OrderType(order_type),
            price=price,
            size=size,
            status=OrderStatus.PENDING,
            client_order_id=client_order_id,
            metadata=metadata or {}
        )
        
        # 存储订单
        self.active_orders[client_order_id] = order
        self.stats["total_orders"] += 1
        
        logger.info(f"创建订单: {client_order_id} {symbol} {side} {order_type} {size} @ {price}")
        return client_order_id
    
    async def submit_order(self, order_id: str) -> OrderResult:
        """
        提交订单到交易所
        
        参数:
            order_id: 订单ID
        
        返回:
            订单执行结果
        """
        if order_id not in self.active_orders:
            return OrderResult(
                success=False,
                order_id=order_id,
                error_message="订单不存在"
            )
        
        order = self.active_orders[order_id]
        
        # 更新订单状态
        order.status = OrderStatus.SUBMITTED
        order.updated_time = datetime.now()
        
        try:
            # 调用API提交订单
            result = await self._submit_to_exchange(order)
            
            if result["success"]:
                # 更新订单信息
                order.exchange_order_id = result.get("exchange_order_id", "")
                order.status = OrderStatus.SUBMITTED
                order.updated_time = datetime.now()
                
                self.stats["successful_orders"] += 1
                logger.info(f"订单提交成功: {order_id}")
                
                # 触发回调函数
                await self._trigger_callbacks(order_id, "submitted", order)
                
                return OrderResult(
                    success=True,
                    order_id=order_id,
                    exchange_order_id=order.exchange_order_id,
                    timestamp=datetime.now()
                )
            else:
                # 订单提交失败
                order.status = OrderStatus.REJECTED
                order.updated_time = datetime.now()
                
                self.stats["failed_orders"] += 1
                logger.error(f"订单提交失败: {order_id} - {result.get('error', '未知错误')}")
                
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    error_message=result.get("error", "订单提交失败")
                )
                
        except Exception as e:
            logger.error(f"提交订单异常: {order_id} - {str(e)}")
            return OrderResult(
                success=False,
                order_id=order_id,
                error_message=str(e)
            )
    
    async def cancel_order(self, order_id: str) -> OrderResult:
        """
        取消订单
        
        参数:
            order_id: 订单ID
        
        返回:
            取消结果
        """
        if order_id not in self.active_orders:
            return OrderResult(
                success=False,
                order_id=order_id,
                error_message="订单不存在"
            )
        
        order = self.active_orders[order_id]
        
        # 检查订单状态
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
            return OrderResult(
                success=False,
                order_id=order_id,
                error_message=f"订单状态为{order.status.value}，无法取消"
            )
        
        try:
            # 调用API取消订单
            result = await self._cancel_from_exchange(order)
            
            if result["success"]:
                # 更新订单状态
                order.status = OrderStatus.CANCELLED
                order.updated_time = datetime.now()
                
                # 从活跃订单中移除
                del self.active_orders[order_id]
                self.order_history.append(order)
                
                self.stats["cancelled_orders"] += 1
                logger.info(f"订单取消成功: {order_id}")
                
                # 触发回调函数
                await self._trigger_callbacks(order_id, "cancelled", order)
                
                return OrderResult(
                    success=True,
                    order_id=order_id,
                    timestamp=datetime.now()
                )
            else:
                logger.error(f"订单取消失败: {order_id} - {result.get('error', '未知错误')}")
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    error_message=result.get("error", "订单取消失败")
                )
                
        except Exception as e:
            logger.error(f"取消订单异常: {order_id} - {str(e)}")
            return OrderResult(
                success=False,
                order_id=order_id,
                error_message=str(e)
            )
    
    async def batch_submit_orders(self, order_ids: List[str]) -> List[OrderResult]:
        """
        批量提交订单
        
        参数:
            order_ids: 订单ID列表
        
        返回:
            执行结果列表
        """
        tasks = []
        for order_id in order_ids:
            if order_id in self.active_orders:
                tasks.append(self.submit_order(order_id))
        
        if not tasks:
            return []
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(OrderResult(
                    success=False,
                    order_id=order_ids[i],
                    error_message=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def batch_cancel_orders(self, order_ids: List[str]) -> List[OrderResult]:
        """
        批量取消订单
        
        参数:
            order_ids: 订单ID列表
        
        返回:
            取消结果列表
        """
        tasks = []
        for order_id in order_ids:
            if order_id in self.active_orders:
                tasks.append(self.cancel_order(order_id))
        
        if not tasks:
            return []
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(OrderResult(
                    success=False,
                    order_id=order_ids[i],
                    error_message=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self.active_orders.get(order_id)
    
    def get_all_orders(self) -> List[Order]:
        """获取所有活跃订单"""
        return list(self.active_orders.values())
    
    def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        """获取指定交易对的订单"""
        return [order for order in self.active_orders.values() if order.symbol == symbol]
    
    def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        """获取指定状态的订单"""
        return [order for order in self.active_orders.values() if order.status == status]
    
    def register_callback(self, order_id: str, callback: Callable):
        """注册订单回调函数"""
        if order_id not in self.order_callbacks:
            self.order_callbacks[order_id] = []
        self.order_callbacks[order_id].append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "active_orders": len(self.active_orders),
            "order_history": len(self.order_history)
        }
    
    def _validate_order(self, symbol: str, side: str, order_type: str, 
                       size: float, price: Optional[float]) -> Dict[str, Any]:
        """验证订单参数"""
        # 基本参数验证
        if not symbol or not symbol.strip():
            return {"valid": False, "error": "交易对不能为空"}
        
        if side not in ["buy", "sell"]:
            return {"valid": False, "error": "交易方向必须是buy或sell"}
        
        if order_type not in ["market", "limit", "stop", "stop_limit"]:
            return {"valid": False, "error": "订单类型不支持"}
        
        if size <= 0:
            return {"valid": False, "error": "交易数量必须大于0"}
        
        if order_type in ["limit", "stop", "stop_limit"] and price is None:
            return {"valid": False, "error": "限价单必须指定价格"}
        
        if price is not None and price <= 0:
            return {"valid": False, "error": "价格必须大于0"}
        
        return {"valid": True, "error": ""}
    
    async def _submit_to_exchange(self, order: Order) -> Dict[str, Any]:
        """提交订单到交易所"""
        try:
            # 调用OKX API
            result = await self.api_client.place_order(
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                size=order.size,
                price=order.price
            )
            
            if result["success"]:
                return {
                    "success": True,
                    "exchange_order_id": result["data"]["ordId"]
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "订单提交失败")
                }
                
        except Exception as e:
            logger.error(f"提交订单到交易所失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _cancel_from_exchange(self, order: Order) -> Dict[str, Any]:
        """从交易所取消订单"""
        try:
            if not order.exchange_order_id:
                return {
                    "success": False,
                    "error": "交易所订单ID为空"
                }
            
            # 调用OKX API
            result = await self.api_client.cancel_order(
                symbol=order.symbol,
                order_id=order.exchange_order_id
            )
            
            if result["success"]:
                return {"success": True}
            else:
                return {
                    "success": False,
                    "error": result.get("error", "订单取消失败")
                }
                
        except Exception as e:
            logger.error(f"从交易所取消订单失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _monitor_orders(self):
        """监控订单状态"""
        while self.is_running:
            try:
                # 获取需要检查的订单
                orders_to_check = [
                    order for order in self.active_orders.values()
                    if order.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]
                ]
                
                if orders_to_check:
                    logger.debug(f"检查 {len(orders_to_check)} 个订单状态")
                    
                    # 批量查询订单状态
                    for order in orders_to_check:
                        await self._check_order_status(order)
                
                # 检查超时订单
                if self.config["enable_auto_cancel"]:
                    await self._check_timeout_orders()
                
                # 等待下次检查
                await asyncio.sleep(5)  # 每5秒检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控订单状态异常: {str(e)}")
                await asyncio.sleep(10)  # 异常时等待更长时间
    
    async def _check_order_status(self, order: Order):
        """检查单个订单状态"""
        try:
            if not order.exchange_order_id:
                return
            
            # 调用API查询订单状态
            result = await self.api_client.get_order(
                symbol=order.symbol,
                order_id=order.exchange_order_id
            )
            
            if result["success"]:
                order_data = result["data"]
                
                # 更新订单状态
                new_status = self._map_exchange_status(order_data["state"])
                if new_status != order.status:
                    old_status = order.status
                    order.status = new_status
                    order.updated_time = datetime.now()
                    
                    # 更新成交信息
                    if new_status in [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED]:
                        order.filled_size = float(order_data.get("fillSz", 0))
                        order.filled_price = float(order_data.get("avgPx", 0))
                        order.fee = float(order_data.get("fee", 0))
                        self.stats["total_fees"] += order.fee
                    
                    # 如果订单完成，移动到历史记录
                    if new_status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                        del self.active_orders[order.order_id]
                        self.order_history.append(order)
                        
                        # 更新投资组合
                        if new_status == OrderStatus.FILLED:
                            await self._update_portfolio(order)
                    
                    logger.info(f"订单状态更新: {order.order_id} {old_status.value} -> {new_status.value}")
                    
                    # 触发回调函数
                    await self._trigger_callbacks(order.order_id, "status_changed", order)
                    
        except Exception as e:
            logger.error(f"检查订单状态失败 {order.order_id}: {str(e)}")
    
    def _map_exchange_status(self, exchange_status: str) -> OrderStatus:
        """映射交易所状态到内部状态"""
        status_map = {
            "live": OrderStatus.SUBMITTED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.EXPIRED
        }
        return status_map.get(exchange_status, OrderStatus.SUBMITTED)
    
    async def _check_timeout_orders(self):
        """检查超时订单"""
        current_time = datetime.now()
        timeout_orders = []
        
        for order in self.active_orders.values():
            if order.status == OrderStatus.SUBMITTED:
                time_diff = (current_time - order.created_time).total_seconds()
                if time_diff > self.config["cancel_after_seconds"]:
                    timeout_orders.append(order.order_id)
        
        if timeout_orders:
            logger.info(f"发现 {len(timeout_orders)} 个超时订单，开始取消")
            await self.batch_cancel_orders(timeout_orders)
    
    async def _update_portfolio(self, order: Order):
        """更新投资组合"""
        try:
            if order.status == OrderStatus.FILLED:
                if order.side == OrderSide.BUY:
                    # 开仓或加仓
                    self.portfolio_manager.open_position(
                        symbol=order.symbol,
                        side="buy",
                        size=order.filled_size,
                        price=order.filled_price,
                        order_id=order.order_id,
                        metadata=order.metadata
                    )
                else:  # SELL
                    # 平仓或减仓
                    self.portfolio_manager.close_position(
                        symbol=order.symbol,
                        size=order.filled_size,
                        price=order.filled_price,
                        order_id=order.order_id,
                        metadata=order.metadata
                    )
                    
        except Exception as e:
            logger.error(f"更新投资组合失败: {str(e)}")
    
    async def _trigger_callbacks(self, order_id: str, event_type: str, order: Order):
        """触发回调函数"""
        if order_id in self.order_callbacks:
            callbacks = self.order_callbacks[order_id]
            for callback in callbacks:
                try:
                    # 异步调用回调函数
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event_type, order)
                    else:
                        callback(event_type, order)
                except Exception as e:
                    logger.error(f"回调函数执行失败: {str(e)}")
    
    def get_order_summary(self) -> Dict[str, Any]:
        """获取订单摘要"""
        status_counts = {}
        for order in self.active_orders.values():
            status = order.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_orders": self.stats["total_orders"],
            "active_orders": len(self.active_orders),
            "order_history": len(self.order_history),
            "status_distribution": status_counts,
            "success_rate": self.stats["successful_orders"] / max(self.stats["total_orders"], 1),
            "total_fees": self.stats["total_fees"]
        }