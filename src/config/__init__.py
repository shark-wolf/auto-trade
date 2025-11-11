"""
配置模块初始化文件
"""

from .strategy_config import (
    StrategyType,
    StrategyConfig,
    STRATEGY_TEMPLATES,
    STRATEGY_COMBINATIONS,
    DEFAULT_CONFIG,
    get_strategy_template,
    get_strategy_combination,
    create_custom_strategy,
    validate_strategy_config
)

from .config_loader import (
    ConfigLoader,
    load_config,
    create_default_config
)

__all__ = [
    # 策略配置
    "StrategyType",
    "StrategyConfig", 
    "STRATEGY_TEMPLATES",
    "STRATEGY_COMBINATIONS",
    "DEFAULT_CONFIG",
    "get_strategy_template",
    "get_strategy_combination",
    "create_custom_strategy",
    "validate_strategy_config",
    
    # 配置加载器
    "ConfigLoader",
    "load_config",
    "create_default_config"
]