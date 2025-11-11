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
    BOLLINGER_BANDS = "bollinger_bands"
    MOMENTUM = "momentum"


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
            "short_period": 10,      # 短期均线周期
            "long_period": 30,       # 长期均线周期
            "ma_type": "sma",        # 均线类型: sma, ema
            "confirmation_periods": 2  # 确认周期数
        }
    ),
    
    StrategyType.RSI: StrategyConfig(
        strategy_type=StrategyType.RSI,
        name="RSI策略",
        parameters={
            "period": 14,            # RSI周期
            "overbought": 70,        # 超买阈值
            "oversold": 30,          # 超卖阈值
            "smoothing": 3,          # 平滑因子
            "divergence_enabled": True  # 是否启用背离检测
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
            "fast_period": 12,       # 快速EMA周期
            "slow_period": 26,       # 慢速EMA周期
            "signal_period": 9,      # 信号线周期
            "histogram_threshold": 0.1  # 柱状图阈值
        }
    ),
    
    StrategyType.BOLLINGER_BANDS: StrategyConfig(
        strategy_type=StrategyType.BOLLINGER_BANDS,
        name="布林带策略",
        parameters={
            "period": 20,            # 布林带周期
            "std_dev": 2,            # 标准差倍数
            "band_width_threshold": 0.02  # 带宽阈值
        }
    ),
    
    StrategyType.MOMENTUM: StrategyConfig(
        strategy_type=StrategyType.MOMENTUM,
        name="动量策略",
        parameters={
            "period": 10,            # 动量周期
            "momentum_threshold": 0.5,  # 动量阈值
            "volume_confirmation": True,  # 是否确认成交量
            "volume_ratio": 1.2      # 成交量比率阈值
        }
    )
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
                "short_period": 5,
                "long_period": 15,
                "ma_type": "sma",
                "confirmation_periods": 1
            }
        ),
        StrategyConfig(
            strategy_type=StrategyType.MACD,
            name="激进MACD策略",
            position_size=0.02,
            stop_loss_pct=0.03,
            take_profit_pct=0.08,
            parameters={
                "fast_period": 8,
                "slow_period": 21,
                "signal_period": 5,
                "histogram_threshold": 0.05
            }
        ),
        StrategyConfig(
            strategy_type=StrategyType.MOMENTUM,
            name="激进动量策略",
            position_size=0.02,
            stop_loss_pct=0.03,
            take_profit_pct=0.08,
            parameters={
                "period": 5,
                "momentum_threshold": 0.3,
                "volume_confirmation": True,
                "volume_ratio": 1.5
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
        StrategyConfig(
            strategy_type=StrategyType.BOLLINGER_BANDS,
            name="多样化布林带策略",
            position_size=0.01,
            stop_loss_pct=0.02,
            take_profit_pct=0.05,
            parameters={
                "period": 20,
                "std_dev": 2.5
            }
        )
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
                "short_period": 10,
                "long_period": 30,
                "ma_type": "ema",
                "confirmation_periods": 2
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
                "period": 14,
                "overbought": 70,
                "oversold": 30,
                "smoothing": 3
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