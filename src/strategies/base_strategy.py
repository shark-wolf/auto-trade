"""
基础策略类
定义所有策略的基类
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import pandas as pd
import numpy as np
from loguru import logger


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    """交易信号"""
    symbol: str
    signal_type: SignalType
    price: float
    confidence: float
    timestamp: datetime
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class MarketData:
    """市场数据"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: float = 0.0
    ask: float = 0.0
    
    @property
    def spread(self) -> float:
        return self.ask - self.bid if self.ask > 0 and self.bid > 0 else 0.0


class BaseStrategy(ABC):
    """基础策略类"""
    
    def __init__(self, name: str, parameters: Dict[str, Any] = None):
        self.name = name
        self.parameters = parameters or {}
        self.is_active = False
        self.position = 0
        self.entry_price = 0.0
        self.last_signal = None
        self.performance_metrics = {}
        
    @abstractmethod
    def analyze(self, market_data: MarketData) -> Signal:
        """分析市场数据并生成信号"""
        pass
    
    @abstractmethod
    def validate_parameters(self) -> bool:
        """验证策略参数"""
        pass
    
    def on_position_open(self, symbol: str, price: float, size: float):
        """开仓时的回调"""
        self.position = size
        self.entry_price = price
        logger.info(f"策略 {self.name} 开仓: {symbol} @ {price}, 数量: {size}")
    
    def on_position_close(self, symbol: str, price: float, size: float, pnl: float):
        """平仓时的回调"""
        self.position = 0
        self.entry_price = 0.0
        logger.info(f"策略 {self.name} 平仓: {symbol} @ {price}, 数量: {size}, 盈亏: {pnl}")
    
    def update_parameters(self, parameters: Dict[str, Any]):
        """更新策略参数"""
        self.parameters.update(parameters)
        if self.validate_parameters():
            logger.info(f"策略 {self.name} 参数已更新")
        else:
            logger.error(f"策略 {self.name} 参数验证失败")
    
    def get_status(self) -> Dict[str, Any]:
        """获取策略状态"""
        return {
            "name": self.name,
            "is_active": self.is_active,
            "position": self.position,
            "entry_price": self.entry_price,
            "parameters": self.parameters,
            "last_signal": self.last_signal.__dict__ if self.last_signal else None
        }
    
    def start(self):
        """启动策略"""
        if self.validate_parameters():
            self.is_active = True
            logger.info(f"策略 {self.name} 已启动")
        else:
            logger.error(f"策略 {self.name} 启动失败：参数验证失败")
    
    def stop(self):
        """停止策略"""
        self.is_active = False
        logger.info(f"策略 {self.name} 已停止")


class StrategyManager:
    """策略管理器"""
    
    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {}
        self.active_strategies: Dict[str, BaseStrategy] = {}
        self.signal_history: List[Signal] = []
        self.max_history_size = 1000
    
    def register_strategy(self, strategy: BaseStrategy):
        """注册策略"""
        self.strategies[strategy.name] = strategy
        logger.info(f"策略 {strategy.name} 已注册")
    
    def activate_strategy(self, strategy_name: str):
        """激活策略"""
        if strategy_name in self.strategies:
            strategy = self.strategies[strategy_name]
            strategy.start()
            self.active_strategies[strategy_name] = strategy
            logger.info(f"策略 {strategy_name} 已激活")
        else:
            logger.error(f"策略 {strategy_name} 不存在")
    
    def deactivate_strategy(self, strategy_name: str):
        """停用策略"""
        if strategy_name in self.active_strategies:
            strategy = self.active_strategies[strategy_name]
            strategy.stop()
            del self.active_strategies[strategy_name]
            logger.info(f"策略 {strategy_name} 已停用")
    
    def analyze_all(self, market_data: MarketData) -> List[Signal]:
        """运行所有激活的策略分析"""
        signals = []
        
        for strategy in self.active_strategies.values():
            try:
                signal = strategy.analyze(market_data)
                if signal.signal_type != SignalType.HOLD:
                    signals.append(signal)
                    self.signal_history.append(signal)
                    strategy.last_signal = signal
                    
                    # 限制历史记录大小
                    if len(self.signal_history) > self.max_history_size:
                        self.signal_history.pop(0)
                        
            except Exception as e:
                logger.error(f"策略 {strategy.name} 分析失败: {e}")
        
        return signals
    
    def get_strategy(self, name: str) -> Optional[BaseStrategy]:
        """获取策略实例"""
        return self.strategies.get(name)
    
    def get_active_strategies(self) -> List[str]:
        """获取激活的策略列表"""
        return list(self.active_strategies.keys())
    
    def get_strategy_status(self, name: str) -> Optional[Dict]:
        """获取策略状态"""
        strategy = self.strategies.get(name)
        return strategy.get_status() if strategy else None
    
    def get_recent_signals(self, count: int = 10) -> List[Signal]:
        """获取最近的信号"""
        return self.signal_history[-count:] if self.signal_history else []
    
    def clear_history(self):
        """清空信号历史"""
        self.signal_history.clear()
        logger.info("信号历史已清空")
    
    async def start(self):
        """启动策略管理器"""
        logger.info("策略管理器已启动")
    
    async def stop(self):
        """停止策略管理器"""
        # 停止所有激活的策略
        for strategy_name in list(self.active_strategies.keys()):
            self.deactivate_strategy(strategy_name)
        logger.info("策略管理器已停止")
    
    async def update_market_data(self, message: Dict[str, Any]):
        """更新市场数据"""
        # 这里可以添加市场数据更新的逻辑
        pass
    
    async def analyze(self, market_data: MarketData) -> List[Signal]:
        """分析市场数据"""
        return self.analyze_all(market_data)


# 工具函数
def calculate_returns(prices: pd.Series) -> pd.Series:
    """计算收益率"""
    return prices.pct_change()


def calculate_volatility(prices: pd.Series, window: int = 20) -> float:
    """计算波动率"""
    returns = calculate_returns(prices)
    return returns.rolling(window=window).std().iloc[-1]


def calculate_sma(prices: pd.Series, window: int) -> pd.Series:
    """计算简单移动平均"""
    return prices.rolling(window=window).mean()


def calculate_ema(prices: pd.Series, window: int) -> pd.Series:
    """计算指数移动平均"""
    return prices.ewm(span=window).mean()


def calculate_rsi(prices: pd.Series, window: int = 14) -> pd.Series:
    """计算RSI"""
    returns = calculate_returns(prices)
    gain = returns.where(returns > 0, 0)
    loss = -returns.where(returns < 0, 0)
    
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
    """计算MACD"""
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram
    }