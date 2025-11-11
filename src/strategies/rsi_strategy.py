"""
RSI相对强弱指标策略
基于RSI指标的超买超卖信号
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List
from datetime import datetime
from loguru import logger

from .base_strategy import BaseStrategy, Signal, SignalType, MarketData, calculate_rsi


class RSIStrategy(BaseStrategy):
    """RSI相对强弱指标策略"""
    
    def __init__(self, parameters: Dict[str, Any] = None):
        """
        初始化策略
        
        参数:
            rsi_period: RSI计算周期（默认：14）
            overbought: 超买阈值（默认：70）
            oversold: 超卖阈值（默认：30）
            min_confidence: 最小置信度（默认：0.6）
            stop_loss: 止损比例（默认：0.02）
            take_profit: 止盈比例（默认：0.04）
        """
        default_params = {
            "rsi_period": 14,
            "overbought": 70,
            "oversold": 30,
            "min_confidence": 0.6,
            "stop_loss": 0.02,
            "take_profit": 0.04
        }
        
        if parameters:
            default_params.update(parameters)
        
        super().__init__("RSI", default_params)
        self.price_history = []
        self.max_history_size = 200
        self.rsi_history = []
        self.last_rsi = 50.0  # 中性RSI值
        
    def validate_parameters(self) -> bool:
        """验证策略参数"""
        try:
            period = self.parameters["rsi_period"]
            overbought = self.parameters["overbought"]
            oversold = self.parameters["oversold"]
            
            if period <= 0:
                logger.error("RSI周期必须大于0")
                return False
            
            if not (0 < oversold < overbought < 100):
                logger.error("RSI阈值设置错误")
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
        if len(self.price_history) < self.parameters["rsi_period"] + 1:
            return Signal(
                symbol=market_data.symbol,
                signal_type=SignalType.HOLD,
                price=market_data.close,
                confidence=0.0,
                timestamp=datetime.now()
            )
        
        # 计算RSI
        prices = pd.Series(self.price_history)
        rsi_period = self.parameters["rsi_period"]
        current_rsi = calculate_rsi(prices, rsi_period).iloc[-1]
        
        # 更新RSI历史
        self.rsi_history.append(current_rsi)
        if len(self.rsi_history) > self.max_history_size:
            self.rsi_history.pop(0)
        
        # 生成信号
        signal_type = SignalType.HOLD
        confidence = 0.0
        metadata = {
            "rsi": current_rsi,
            "overbought": self.parameters["overbought"],
            "oversold": self.parameters["oversold"],
            "price": market_data.close
        }
        
        # 检查RSI信号
        if self.last_rsi > 0:
            # RSI从超卖区域上穿 - 买入信号
            if self.last_rsi <= self.parameters["oversold"] and current_rsi > self.parameters["oversold"]:
                signal_type = SignalType.BUY
                confidence = self._calculate_confidence(current_rsi, "BUY")
            
            # RSI从超买区域下穿 - 卖出信号
            elif self.last_rsi >= self.parameters["overbought"] and current_rsi < self.parameters["overbought"]:
                signal_type = SignalType.SELL
                confidence = self._calculate_confidence(current_rsi, "SELL")
        
        # 检查持仓的止损止盈
        if self.position != 0:
            stop_signal = self._check_stop_loss_take_profit(market_data.close)
            if stop_signal != SignalType.HOLD:
                signal_type = stop_signal
                confidence = 1.0
                metadata["stop_trigger"] = True
        
        # 更新上一次RSI值
        self.last_rsi = current_rsi
        
        return Signal(
            symbol=market_data.symbol,
            signal_type=signal_type,
            price=market_data.close,
            confidence=confidence,
            timestamp=datetime.now(),
            metadata=metadata
        )
    
    def _calculate_confidence(self, rsi: float, signal_type: str) -> float:
        """计算信号置信度"""
        min_confidence = self.parameters["min_confidence"]
        
        # 基础置信度
        base_confidence = min_confidence
        
        # RSI强度因子
        if signal_type == "BUY":
            # RSI越低，买入信号越强
            rsi_strength = (self.parameters["oversold"] - rsi) / self.parameters["oversold"]
        else:  # SELL
            # RSI越高，卖出信号越强
            rsi_strength = (rsi - self.parameters["overbought"]) / (100 - self.parameters["overbought"])
        
        # 确保强度因子在合理范围内
        rsi_strength = max(0, min(rsi_strength, 1))
        
        # 综合置信度
        confidence = base_confidence * (1 + rsi_strength * 0.3)
        
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
            "rsi_history_length": len(self.rsi_history),
            "last_rsi": self.last_rsi,
            "overbought_threshold": self.parameters["overbought"],
            "oversold_threshold": self.parameters["oversold"],
            "stop_loss_ratio": self.parameters["stop_loss"],
            "take_profit_ratio": self.parameters["take_profit"]
        })
        return status