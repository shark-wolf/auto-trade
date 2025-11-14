"""
主src模块初始化文件
"""

# API模块
from .api import (
    CCXTClient,
    MarketDataHandler
)

# 策略模块
from .strategies import (
    BaseStrategy,
    StrategyManager,
    Signal,
    SignalType,
    MarketData,
    KDJMACDStrategy
)

# 风险管理模块
from .risk import (
    RiskManager,
    PortfolioManager,
    Position,
    TradeRecord,
    PositionSide
)

# 执行模块
from .execution import (
    OrderManager,
    Order,
    OrderResult,
    OrderStatus,
    OrderType,
    OrderSide
)

# 监控模块
from .monitoring import (
    MonitoringService,
    MetricsCollector,
    EventLogger,
    MonitoringDashboard,
    PerformanceMetric,
    TradingEvent,
    get_monitoring_service,
    record_metric,
    log_event
)

# 配置模块
from .config import (
    StrategyType,
    StrategyConfig,
    STRATEGY_TEMPLATES,
    STRATEGY_COMBINATIONS,
    DEFAULT_CONFIG,
    get_strategy_template,
    get_strategy_combination,
    create_custom_strategy,
    validate_strategy_config,
    ConfigLoader,
    load_config,
    create_default_config
)

__all__ = [
    # API模块
    "CCXTClient",
    "MarketDataHandler",
    
    # 策略模块
    "BaseStrategy",
    "StrategyManager",
    "Signal",
    "SignalType",
    "MarketData",
    "KDJMACDStrategy",
    
    # 风险管理模块
    "RiskManager",
    "PortfolioManager",
    "Position",
    "TradeRecord",
    "PositionSide",
    
    # 执行模块
    "OrderManager",
    "Order",
    "OrderResult",
    "OrderStatus",
    "OrderType",
    "OrderSide",
    
    # 监控模块
    "MonitoringService",
    "MetricsCollector",
    "EventLogger",
    "MonitoringDashboard",
    "PerformanceMetric",
    "TradingEvent",
    "get_monitoring_service",
    "record_metric",
    "log_event",
    
    # 配置模块
    "StrategyType",
    "StrategyConfig",
    "STRATEGY_TEMPLATES",
    "STRATEGY_COMBINATIONS",
    "DEFAULT_CONFIG",
    "get_strategy_template",
    "get_strategy_combination",
    "create_custom_strategy",
    "validate_strategy_config",
    "ConfigLoader",
    "load_config",
    "create_default_config"
]
