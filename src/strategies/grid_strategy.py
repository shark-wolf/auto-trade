"""
网格交易策略
在价格区间内设置多个买卖网格
"""

import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime
from loguru import logger

from .base_strategy import BaseStrategy, Signal, SignalType, MarketData


class GridTradingStrategy(BaseStrategy):
    """网格交易策略"""
    
    def __init__(self, parameters: Dict[str, Any] = None):
        """
        初始化策略
        
        参数:
            grid_count: 网格数量（默认：10）
            price_range: 价格区间百分比（默认：0.05，即5%）
            base_price: 基准价格（默认：None，使用当前价格）
            grid_size: 每个网格的大小（默认：0.01）
            max_position: 最大持仓量（默认：1.0）
            min_confidence: 最小置信度（默认：0.7）
        """
        default_params = {
            "grid_count": 10,
            "price_range": 0.05,  # 5%
            "base_price": None,
            "grid_size": 0.01,
            "max_position": 1.0,
            "min_confidence": 0.7
        }
        
        if parameters:
            default_params.update(parameters)
        
        super().__init__("GridTrading", default_params)
        self.grids = []  # [(price, size, type), ...]
        self.base_price = None
        self.grid_levels = []
        self.position_sizes = {}  # 每个网格的持仓
        self.total_position = 0.0
        
    def validate_parameters(self) -> bool:
        """验证策略参数"""
        try:
            grid_count = self.parameters["grid_count"]
            price_range = self.parameters["price_range"]
            grid_size = self.parameters["grid_size"]
            max_position = self.parameters["max_position"]
            
            if grid_count <= 0:
                logger.error("网格数量必须大于0")
                return False
            
            if not 0 < price_range < 1:
                logger.error("价格区间必须在0到1之间")
                return False
            
            if grid_size <= 0:
                logger.error("网格大小必须大于0")
                return False
            
            if max_position <= 0:
                logger.error("最大持仓量必须大于0")
                return False
            
            return True
            
        except KeyError as e:
            logger.error(f"缺少必要参数: {e}")
            return False
        except Exception as e:
            logger.error(f"参数验证失败: {e}")
            return False
    
    def initialize_grids(self, current_price: float):
        """初始化网格"""
        if self.base_price is None:
            self.base_price = self.parameters["base_price"] or current_price
        
        price_range = self.parameters["price_range"]
        grid_count = self.parameters["grid_count"]
        
        # 计算价格区间
        upper_price = self.base_price * (1 + price_range / 2)
        lower_price = self.base_price * (1 - price_range / 2)
        
        # 生成网格价格
        self.grid_levels = np.linspace(lower_price, upper_price, grid_count)
        
        # 初始化每个网格的持仓
        for i, price in enumerate(self.grid_levels):
            self.position_sizes[i] = 0.0
        
        logger.info(f"网格初始化完成: {grid_count}个网格，价格区间 {lower_price:.4f} - {upper_price:.4f}")
    
    def analyze(self, market_data: MarketData) -> Signal:
        """分析市场数据并生成信号"""
        if not self.is_active:
            return Signal(
                symbol=market_data.symbol,
                signal_type=SignalType.HOLD,
                price=market_data.close,
                confidence=0.0,
                timestamp=datetime.now()
            )
        
        # 初始化网格（如果需要）
        if not self.grid_levels:
            self.initialize_grids(market_data.close)
        
        current_price = market_data.close
        signal_type = SignalType.HOLD
        confidence = 0.0
        metadata = {
            "current_price": current_price,
            "base_price": self.base_price,
            "total_position": self.total_position,
            "grid_levels": len(self.grid_levels)
        }
        
        # 检查每个网格
        for i, grid_price in enumerate(self.grid_levels):
            # 计算到网格的距离
            distance = abs(current_price - grid_price) / grid_price
            
            # 如果价格接近网格
            if distance < 0.001:  # 0.1%的容差
                signal = self._check_grid_signal(i, current_price, grid_price)
                if signal != SignalType.HOLD:
                    signal_type = signal
                    confidence = self.parameters["min_confidence"]
                    metadata["triggered_grid"] = i
                    metadata["grid_price"] = grid_price
                    break
        
        return Signal(
            symbol=market_data.symbol,
            signal_type=signal_type,
            price=current_price,
            confidence=confidence,
            timestamp=datetime.now(),
            metadata=metadata
        )
    
    def _check_grid_signal(self, grid_index: int, current_price: float, grid_price: float) -> SignalType:
        """检查网格信号"""
        grid_size = self.parameters["grid_size"]
        max_position = self.parameters["max_position"]
        
        # 当前网格持仓
        current_size = self.position_sizes.get(grid_index, 0.0)
        
        # 在网格下方 - 买入信号
        if current_price < grid_price:
            # 检查是否还有买入空间
            if self.total_position < max_position and current_size < grid_size:
                # 执行买入
                self.position_sizes[grid_index] = current_size + grid_size
                self.total_position += grid_size
                logger.info(f"网格买入: 价格={current_price:.4f}, 网格={grid_index}, 数量={grid_size}")
                return SignalType.BUY
        
        # 在网格上方 - 卖出信号
        elif current_price > grid_price:
            # 检查是否有持仓可以卖出
            if current_size > 0:
                # 执行卖出
                self.position_sizes[grid_index] = 0.0
                self.total_position -= current_size
                logger.info(f"网格卖出: 价格={current_price:.4f}, 网格={grid_index}, 数量={current_size}")
                return SignalType.SELL
        
        return SignalType.HOLD
    
    def rebalance_grids(self, current_price: float):
        """重新平衡网格"""
        # 如果价格偏离基准价格太多，重新设置网格
        deviation = abs(current_price - self.base_price) / self.base_price
        
        if deviation > self.parameters["price_range"] * 1.5:
            logger.info(f"价格偏离过大 {deviation:.4f}，重新设置网格")
            self.base_price = current_price
            self.grid_levels = []
            self.position_sizes = {}
            self.total_position = 0.0
            self.initialize_grids(current_price)
    
    def get_status(self) -> Dict[str, Any]:
        """获取策略状态"""
        status = super().get_status()
        status.update({
            "base_price": self.base_price,
            "grid_levels_count": len(self.grid_levels),
            "total_position": self.total_position,
            "position_sizes": self.position_sizes.copy(),
            "price_range": self.parameters["price_range"],
            "grid_count": self.parameters["grid_count"],
            "grid_size": self.parameters["grid_size"],
            "max_position": self.parameters["max_position"]
        })
        return status