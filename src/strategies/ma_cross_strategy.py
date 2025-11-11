"""
移动平均线交叉策略
基于短期和长期移动平均线的交叉信号
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List
from datetime import datetime
from loguru import logger

from .base_strategy import BaseStrategy, Signal, SignalType, MarketData, calculate_sma, calculate_ema


class MovingAverageCrossStrategy(BaseStrategy):
    """移动平均线交叉策略"""
    
    def __init__(self, parameters: Dict[str, Any] = None):
        """
        初始化策略
        
        参数:
            fast_period: 短期均线周期（默认：20）
            slow_period: 长期均线周期（默认：50）
            ma_type: 均线类型（SMA或EMA，默认：EMA）
            stop_loss: 止损比例（默认：0.02）
            take_profit: 止盈比例（默认：0.04）
            min_confidence: 最小置信度（默认：0.6）
        """
        default_params = {
            "fast_period": 20,
            "slow_period": 50,
            "ma_type": "EMA",
            "stop_loss": 0.02,
            "take_profit": 0.04,
            "min_confidence": 0.6
        }
        
        if parameters:
            default_params.update(parameters)
        
        super().__init__("MovingAverageCross", default_params)
        self.price_history = []
        self.max_history_size = 200
        self.last_fast_ma = 0.0
        self.last_slow_ma = 0.0
        
    def validate_parameters(self) -> bool:
        """验证策略参数"""
        try:
            fast = self.parameters["fast_period"]
            slow = self.parameters["slow_period"]
            
            if fast >= slow:
                logger.error("短期均线周期必须小于长期均线周期")
                return False
            
            if fast <= 0 or slow <= 0:
                logger.error("均线周期必须大于0")
                return False
            
            if self.parameters["ma_type"] not in ["SMA", "EMA"]:
                logger.error("均线类型必须是SMA或EMA")
                return False
            
            if not 0 < self.parameters["stop_loss"] < 1:
                logger.error("止损比例必须在0到1之间")
                return False
            
            if not 0 < self.parameters["take_profit"] < 1:
                logger.error("止盈比例必须在0到1之间")
                return False
            
            return True
            
        except KeyError as e:
            logger.error(f"缺少必要参数: {e}")
            return False
        except Exception as e:
            logger.error(f"参数验证失败: {e}")
            return False
    
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
        
        # 更新价格历史
        self.price_history.append(market_data.close)
        if len(self.price_history) > self.max_history_size:
            self.price_history.pop(0)
        
        # 确保有足够的历史数据
        if len(self.price_history) < self.parameters["slow_period"]:
            return Signal(
                symbol=market_data.symbol,
                signal_type=SignalType.HOLD,
                price=market_data.close,
                confidence=0.0,
                timestamp=datetime.now()
            )
        
        # 计算移动平均线
        prices = pd.Series(self.price_history)
        fast_period = self.parameters["fast_period"]
        slow_period = self.parameters["slow_period"]
        ma_type = self.parameters["ma_type"]
        
        if ma_type == "SMA":
            fast_ma = calculate_sma(prices, fast_period).iloc[-1]
            slow_ma = calculate_sma(prices, slow_period).iloc[-1]
        else:  # EMA
            fast_ma = calculate_ema(prices, fast_period).iloc[-1]
            slow_ma = calculate_ema(prices, slow_period).iloc[-1]
        
        # 生成信号
        signal_type = SignalType.HOLD
        confidence = 0.0
        metadata = {
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
            "price": market_data.close
        }
        
        # 检查均线交叉
        if self.last_fast_ma > 0 and self.last_slow_ma > 0:
            # 金叉（短期均线上穿长期均线）
            if self.last_fast_ma <= self.last_slow_ma and fast_ma > slow_ma:
                signal_type = SignalType.BUY
                confidence = self._calculate_confidence(market_data, fast_ma, slow_ma, "BUY")
            
            # 死叉（短期均线下穿长期均线）
            elif self.last_fast_ma >= self.last_slow_ma and fast_ma < slow_ma:
                signal_type = SignalType.SELL
                confidence = self._calculate_confidence(market_data, fast_ma, slow_ma, "SELL")
        
        # 检查持仓的止损止盈
        if self.position != 0:
            stop_signal = self._check_stop_loss_take_profit(market_data.close)
            if stop_signal != SignalType.HOLD:
                signal_type = stop_signal
                confidence = 1.0
                metadata["stop_trigger"] = True
        
        # 更新上一次均线值
        self.last_fast_ma = fast_ma
        self.last_slow_ma = slow_ma
        
        return Signal(
            symbol=market_data.symbol,
            signal_type=signal_type,
            price=market_data.close,
            confidence=confidence,
            timestamp=datetime.now(),
            metadata=metadata
        )
    
    def _calculate_confidence(self, market_data: MarketData, fast_ma: float, slow_ma: float, signal_type: str) -> float:
        """计算信号置信度"""
        min_confidence = self.parameters["min_confidence"]
        
        # 基础置信度
        base_confidence = min_confidence
        
        # 价格与均线的距离
        price = market_data.close
        ma_distance = abs(price - slow_ma) / slow_ma
        
        # 成交量因子
        volume_factor = min(market_data.volume / 1000000, 1.0)  # 归一化成交量
        
        # 波动率因子（简单计算）
        if len(self.price_history) >= 20:
            recent_prices = self.price_history[-20:]
            volatility = np.std(recent_prices) / np.mean(recent_prices)
            volatility_factor = max(0.5, 1.0 - volatility)  # 波动率越低，置信度越高
        else:
            volatility_factor = 1.0
        
        # 综合置信度
        confidence = base_confidence * (1 + ma_distance * 0.2) * volume_factor * volatility_factor
        
        # 限制置信度范围
        return min(confidence, 1.0)
    
    def _check_stop_loss_take_profit(self, current_price: float) -> SignalType:
        """检查止损止盈"""
        if self.position == 0 or self.entry_price == 0:
            return SignalType.HOLD
        
        # 计算盈亏比例
        if self.position > 0:  # 多头仓位
            pnl_ratio = (current_price - self.entry_price) / self.entry_price
            
            # 止损
            if pnl_ratio <= -self.parameters["stop_loss"]:
                logger.info(f"多头止损触发: 盈亏比例 {pnl_ratio:.4f}")
                return SignalType.SELL
            
            # 止盈
            if pnl_ratio >= self.parameters["take_profit"]:
                logger.info(f"多头止盈触发: 盈亏比例 {pnl_ratio:.4f}")
                return SignalType.SELL
                
        else:  # 空头仓位
            pnl_ratio = (self.entry_price - current_price) / self.entry_price
            
            # 止损
            if pnl_ratio <= -self.parameters["stop_loss"]:
                logger.info(f"空头止损触发: 盈亏比例 {pnl_ratio:.4f}")
                return SignalType.BUY
            
            # 止盈
            if pnl_ratio >= self.parameters["take_profit"]:
                logger.info(f"空头止盈触发: 盈亏比例 {pnl_ratio:.4f}")
                return SignalType.BUY
        
        return SignalType.HOLD
    
    def get_status(self) -> Dict[str, Any]:
        """获取策略状态"""
        status = super().get_status()
        status.update({
            "price_history_length": len(self.price_history),
            "last_fast_ma": self.last_fast_ma,
            "last_slow_ma": self.last_slow_ma,
            "ma_type": self.parameters["ma_type"],
            "stop_loss_ratio": self.parameters["stop_loss"],
            "take_profit_ratio": self.parameters["take_profit"]
        })
        return status