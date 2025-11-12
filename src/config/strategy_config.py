"""
示例策略配置文件
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum


class StrategyType(Enum):
    """策略类型"""
    MA_CROSS = "ma_cross"
    RSI = "rsi"
    GRID = "grid"
    MACD = "macd"


@dataclass
class StrategyConfig:
    """策略配置"""
    strategy_type: StrategyType
    name: str
    enabled: bool = True
    symbol: str = "BTC-USDT"
    timeframe: str = "1h"
    
    # 通用参数
    position_size: float = 0.01  # 仓位大小
    max_positions: int = 1       # 最大仓位数
    stop_loss_pct: float = 0.02  # 止损百分比
    take_profit_pct: float = 0.05  # 止盈百分比
    
    # 策略特定参数
    parameters: Dict[str, Any] = None
    
    # 风险控制
    risk_per_trade: float = 0.01   # 每笔交易风险
    max_daily_loss: float = 100.0  # 最大日亏损
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


# 预定义的策略配置模板
STRATEGY_TEMPLATES = {
    StrategyType.MA_CROSS: StrategyConfig(
        strategy_type=StrategyType.MA_CROSS,
        name="均线交叉策略",
        parameters={
            "fast_period": 20,
            "slow_period": 50,
            "ma_type": "EMA",
            "min_confidence": 0.6,
            "stop_loss": 0.02,
            "take_profit": 0.04,
        }
    ),
    
    StrategyType.RSI: StrategyConfig(
        strategy_type=StrategyType.RSI,
        name="RSI策略",
        parameters={
            "rsi_period": 14,
            "overbought": 70,
            "oversold": 30,
            "min_confidence": 0.6,
            "stop_loss": 0.02,
            "take_profit": 0.04,
        }
    ),
    
    StrategyType.GRID: StrategyConfig(
        strategy_type=StrategyType.GRID,
        name="网格交易策略",
        parameters={
            "grid_levels": 10,       # 网格层数
            "grid_spacing": 0.01,    # 网格间距 (1%)
            "upper_price": None,     # 上限价格 (None表示动态计算)
            "lower_price": None,     # 下限价格 (None表示动态计算)
            "grid_size": 0.001,      # 每层网格大小
            "rebalance_threshold": 0.02  # 再平衡阈值
        }
    ),
    
    StrategyType.MACD: StrategyConfig(
        strategy_type=StrategyType.MACD,
        name="MACD策略",
        parameters={
            "fast": 12,
            "slow": 26,
            "signal": 9,
            "min_confidence": 0.6,
            "stop_loss": 0.02,
            "take_profit": 0.04,
        }
    ),
}


# 策略组合配置
STRATEGY_COMBINATIONS = {
    "conservative": [
        StrategyConfig(
            strategy_type=StrategyType.MA_CROSS,
            name="保守均线策略",
            position_size=0.005,
            stop_loss_pct=0.015,
            take_profit_pct=0.03,
            risk_per_trade=0.005,
            parameters={
                "short_period": 20,
                "long_period": 50,
                "ma_type": "ema",
                "confirmation_periods": 3
            }
        ),
        StrategyConfig(
            strategy_type=StrategyType.RSI,
            name="保守RSI策略",
            position_size=0.005,
            stop_loss_pct=0.015,
            take_profit_pct=0.03,
            parameters={
                "period": 21,
                "overbought": 75,
                "oversold": 25,
                "smoothing": 5
            }
        )
    ],
    
    "aggressive": [
        StrategyConfig(
            strategy_type=StrategyType.MA_CROSS,
            name="激进均线策略",
            position_size=0.02,
            stop_loss_pct=0.03,
            take_profit_pct=0.08,
            risk_per_trade=0.02,
            parameters={
                "fast_period": 10,
                "slow_period": 30,
                "ma_type": "EMA",
                "min_confidence": 0.6,
                "stop_loss": 0.03,
                "take_profit": 0.08,
            }
        ),
        StrategyConfig(
            strategy_type=StrategyType.MACD,
            name="激进MACD策略",
            position_size=0.02,
            stop_loss_pct=0.03,
            take_profit_pct=0.08,
            parameters={
                "fast": 8,
                "slow": 21,
                "signal": 5,
                "min_confidence": 0.6,
                "stop_loss": 0.03,
                "take_profit": 0.08,
            }
        )
    ],
    
    "diversified": [
        StrategyConfig(
            strategy_type=StrategyType.MA_CROSS,
            name="多样化均线策略",
            position_size=0.01,
            stop_loss_pct=0.02,
            take_profit_pct=0.05,
            parameters={
                "short_period": 10,
                "long_period": 30,
                "ma_type": "ema"
            }
        ),
        StrategyConfig(
            strategy_type=StrategyType.RSI,
            name="多样化RSI策略",
            position_size=0.01,
            stop_loss_pct=0.02,
            take_profit_pct=0.05,
            parameters={
                "period": 14,
                "overbought": 70,
                "oversold": 30
            }
        ),
        StrategyConfig(
            strategy_type=StrategyType.GRID,
            name="多样化网格策略",
            position_size=0.01,
            parameters={
                "grid_levels": 15,
                "grid_spacing": 0.008,
                "grid_size": 0.001
            }
        ),
    ]
}


# 默认配置
DEFAULT_CONFIG = {
    "global": {
        "symbol": "BTC-USDT",
        "timeframe": "1h",
        "max_positions": 3,
        "max_daily_loss": 100.0,
        "risk_per_trade": 0.01,
        "enable_monitoring": True,
        "enable_logging": True
    },
    
    "strategies": [
        StrategyConfig(
            strategy_type=StrategyType.MA_CROSS,
            name="主均线策略",
            enabled=True,
            position_size=0.01,
            stop_loss_pct=0.02,
            take_profit_pct=0.05,
            parameters={
                "fast_period": 20,
                "slow_period": 50,
                "ma_type": "EMA",
                "min_confidence": 0.6,
                "stop_loss": 0.02,
                "take_profit": 0.04,
            }
        ),
        StrategyConfig(
            strategy_type=StrategyType.RSI,
            name="主RSI策略",
            enabled=True,
            position_size=0.01,
            stop_loss_pct=0.02,
            take_profit_pct=0.05,
            parameters={
                "rsi_period": 14,
                "overbought": 70,
                "oversold": 30,
                "min_confidence": 0.6,
                "stop_loss": 0.02,
                "take_profit": 0.04,
            }
        )
    ]
}


def get_strategy_template(strategy_type: StrategyType) -> StrategyConfig:
    """获取策略模板"""
    return STRATEGY_TEMPLATES.get(strategy_type)


def get_strategy_combination(name: str) -> List[StrategyConfig]:
    """获取策略组合"""
    return STRATEGY_COMBINATIONS.get(name, [])


def create_custom_strategy(
    strategy_type: StrategyType,
    name: str,
    enabled: bool = True,
    **kwargs
) -> StrategyConfig:
    """创建自定义策略配置"""
    template = get_strategy_template(strategy_type)
    if template:
        config = StrategyConfig(
            strategy_type=strategy_type,
            name=name,
            enabled=enabled,
            **kwargs
        )
        return config
    else:
        raise ValueError(f"不支持的策略类型: {strategy_type}")


def validate_strategy_config(config: StrategyConfig) -> Dict[str, Any]:
    """验证策略配置"""
    errors = []
    warnings = []
    
    # 基础验证
    if config.position_size <= 0:
        errors.append("仓位大小必须大于0")
    
    if config.stop_loss_pct <= 0 or config.stop_loss_pct >= 1:
        errors.append("止损百分比必须在0和1之间")
    
    if config.take_profit_pct <= 0:
        errors.append("止盈百分比必须大于0")
    
    if config.risk_per_trade <= 0 or config.risk_per_trade >= 1:
        errors.append("每笔交易风险必须在0和1之间")
    
    # 策略特定验证
    if config.strategy_type == StrategyType.MA_CROSS:
        params = config.parameters
        if params.get("short_period", 0) >= params.get("long_period", 0):
            errors.append("短期均线周期必须小于长期均线周期")
        
        if params.get("short_period", 0) < 2:
            warnings.append("短期均线周期建议大于等于2")
    
    elif config.strategy_type == StrategyType.RSI:
        params = config.parameters
        if params.get("overbought", 0) <= params.get("oversold", 100):
            errors.append("超买阈值必须大于超卖阈值")
        
        if params.get("period", 0) < 5:
            warnings.append("RSI周期建议大于等于5")
    
    elif config.strategy_type == StrategyType.GRID:
        params = config.parameters
        if params.get("grid_levels", 0) < 2:
            errors.append("网格层数必须大于等于2")
        
        if params.get("grid_spacing", 0) <= 0:
            errors.append("网格间距必须大于0")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }
