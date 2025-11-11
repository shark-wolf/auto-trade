"""
OKX自动交易机器人主程序
"""

import asyncio
import signal
import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger
import json
import argparse
from pathlib import Path

# 添加src目录到Python路径
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
sys.path.insert(0, str(src_dir))

from api import OKXClient, OKXWebSocketClient, MarketDataHandler, OKXConfig
from strategies import StrategyManager, MovingAverageCrossStrategy, RSIStrategy, GridTradingStrategy, MarketData
from risk import RiskManager, PortfolioManager
from execution import OrderManager
from monitoring import MonitoringService


class TradingBot:
    """主交易机器人"""
    
    def __init__(self, config_path: str = ".env"):
        """
        初始化交易机器人
        
        参数:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = self._load_config()
        
        # 初始化组件
        self.api_client = None
        self.ws_client = None
        self.market_data_handler = None
        self.strategy_manager = None
        self.risk_manager = None
        self.portfolio_manager = None
        self.order_manager = None
        
        # 运行状态
        self.is_running = False
        self.tasks = []
        
        # 设置日志
        self._setup_logging()
        
        logger.info("交易机器人初始化完成")
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        from dotenv import load_dotenv
        
        # 加载环境变量
        load_dotenv(self.config_path)
        
        config = {
            # API配置
            "api_key": os.getenv("OKX_API_KEY", ""),
            "api_secret": os.getenv("OKX_SECRET_KEY", ""),
            "passphrase": os.getenv("OKX_PASSPHRASE", ""),
            "testnet": os.getenv("OKX_TESTNET", "true").lower() == "true",
            
            # 交易配置
            "trading_mode": os.getenv("TRADING_MODE", "demo"),
            "symbol": os.getenv("TRADING_SYMBOL", "BTC-USDT-SWAP"),
            "position_size": float(os.getenv("POSITION_SIZE", "0.01")),
            "max_positions": int(os.getenv("MAX_POSITIONS", "5")),
            
            # 风险管理
            "max_daily_loss": float(os.getenv("MAX_DAILY_LOSS", "100")),
            "max_position_ratio": float(os.getenv("MAX_POSITION_RATIO", "0.3")),
            "stop_loss_pct": float(os.getenv("STOP_LOSS_PCT", "0.02")),
            "take_profit_pct": float(os.getenv("TAKE_PROFIT_PCT", "0.05")),
            
            # 策略配置
            "strategies": os.getenv("ENABLED_STRATEGIES", "kdj,macd").split(","),
            "ma_short_period": int(os.getenv("MA_SHORT_PERIOD", "10")),
            "ma_long_period": int(os.getenv("MA_LONG_PERIOD", "30")),
            "rsi_period": int(os.getenv("RSI_PERIOD", "14")),
            "rsi_overbought": int(os.getenv("RSI_OVERBOUGHT", "70")),
            "rsi_oversold": int(os.getenv("RSI_OVERSOLD", "30")),
            "grid_levels": int(os.getenv("GRID_LEVELS", "10")),
            "grid_spacing": float(os.getenv("GRID_SPACING", "0.01")),
            
            # 日志配置
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "log_file": os.getenv("LOG_FILE", "logs/trading_bot.log"),
            
            # 监控配置
            "enable_monitoring": os.getenv("ENABLE_MONITORING", "true").lower() == "true",
            "monitoring_interval": int(os.getenv("MONITORING_INTERVAL", "60")),
            
            # 数据库配置
            "database_url": os.getenv("DATABASE_URL", "")
        }
        
        # 验证必要配置
        required_keys = ["api_key", "api_secret", "passphrase"]
        missing_keys = [key for key in required_keys if not config.get(key) or config.get(key) == f"your_{key}_here"]
        
        if missing_keys:
            logger.warning(f"缺少必要配置: {', '.join(missing_keys)}，使用演示模式")
            config["trading_mode"] = "demo"
            config["api_key"] = "demo_key"
            config["api_secret"] = "demo_secret" 
            config["passphrase"] = "demo_passphrase"
        
        return config
    
    def _setup_logging(self):
        """设置日志"""
        log_level = self.config["log_level"]
        log_file = self.config["log_file"]
        
        # 移除默认日志处理器
        logger.remove()
        
        # 控制台日志
        logger.add(
            sys.stdout,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
        
        # 文件日志
        if log_file:
            log_dir = Path(log_file).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            
            logger.add(
                log_file,
                level=log_level,
                rotation="10 MB",
                retention="30 days",
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
            )
    
    async def initialize(self):
        """初始化所有组件"""
        try:
            logger.info("开始初始化交易机器人组件...")
            
            # 初始化API客户端
            okx_config = OKXConfig(
                api_key=self.config["api_key"],
                secret_key=self.config["api_secret"],
                passphrase=self.config["passphrase"],
                testnet=self.config["testnet"]
            )
            self.api_client = OKXClient(okx_config)
            
            # 测试API连接
            await self._test_api_connection()
            
            # 初始化WebSocket客户端
            auth_data = self.api_client.get_ws_auth()
            self.ws_client = OKXWebSocketClient(auth_data)
            
            # 初始化市场数据处理
            self.market_data_handler = MarketDataHandler()
            
            # 初始化投资组合管理器
            self.portfolio_manager = PortfolioManager(
                initial_cash=10000.0,  # 初始资金
                max_risk_per_trade=0.02  # 单笔交易最大风险比例
            )
            
            # 初始化风险管理器
            risk_config = {
                "max_risk_per_trade": 0.02,
                "max_total_risk": 0.06,
                "max_drawdown": 0.10,
                "max_position_size": 0.5,
                "stop_loss_multiplier": 2.0,
                "take_profit_multiplier": 3.0
            }
            self.risk_manager = RiskManager(risk_config)
            
            # 初始化订单管理器
            self.order_manager = OrderManager(
                api_client=self.api_client,
                risk_manager=self.risk_manager,
                portfolio_manager=self.portfolio_manager
            )
            
            # 初始化策略管理器
            self.strategy_manager = StrategyManager()
            
            # 注册策略
            await self._register_strategies()
            
            # 初始化监控服务
            self.monitoring_service = MonitoringService(self.config)
            
            logger.info("交易机器人组件初始化完成")
            
        except Exception as e:
            logger.error(f"初始化失败: {str(e)}")
            raise
    
    async def _test_api_connection(self):
        """测试API连接"""
        logger.info("测试API连接...")
        
        # 如果是演示模式，跳过API连接测试
        if self.config.get("trading_mode") == "demo":
            logger.info("演示模式：跳过API连接测试")
            return
            
        # 获取账户余额
        result = await self.api_client.get_account_balance()
        if result["success"]:
            logger.info("API连接成功")
            logger.info(f"账户余额: {result['data']}")
        else:
            raise ConnectionError(f"API连接失败: {result.get('error', '未知错误')}")
    
    async def _register_strategies(self):
        """注册交易策略"""
        enabled_strategies = self.config["strategies"]
        
        if "ma_cross" in enabled_strategies:
            ma_config = {
                "fast_period": self.config.get("ma_short_period", 20),
                "slow_period": self.config.get("ma_long_period", 50),
                "ma_type": "EMA",
                "stop_loss": 0.02,
                "take_profit": 0.04,
                "min_confidence": 0.6
            }
            ma_strategy = MovingAverageCrossStrategy(ma_config)
            self.strategy_manager.register_strategy(ma_strategy)
            logger.info("已注册均线交叉策略")
        
        if "rsi" in enabled_strategies:
            rsi_config = {
                "period": self.config.get("rsi_period", 14),
                "overbought": self.config.get("rsi_overbought", 70),
                "oversold": self.config.get("rsi_oversold", 30),
                "stop_loss": 0.02,
                "take_profit": 0.04,
                "min_confidence": 0.6
            }
            rsi_strategy = RSIStrategy(rsi_config)
            self.strategy_manager.register_strategy(rsi_strategy)
            logger.info("已注册RSI策略")
        
        if "grid" in enabled_strategies:
            grid_config = {
                "grid_count": self.config.get("grid_levels", 10),
                "price_range": self.config.get("grid_spacing", 0.05),
                "base_price": None,
                "grid_size": 0.01,
                "max_position": 1.0,
                "min_confidence": 0.7
            }
            grid_strategy = GridTradingStrategy(grid_config)
            self.strategy_manager.register_strategy(grid_strategy)
            logger.info("已注册网格交易策略")

        # 新增：根据配置启用KDJ与MACD策略
        if "kdj" in enabled_strategies:
            from strategies.kdj_strategy import KDJStrategy
            kdj_config = {
                "period": self.config.get("kdj_period", 9),
                "oversold": 20,
                "overbought": 80,
                "stop_loss": 0.02,
                "take_profit": 0.04,
                "min_confidence": 0.6,
            }
            kdj_strategy = KDJStrategy(kdj_config)
            self.strategy_manager.register_strategy(kdj_strategy)
            logger.info("已注册KDJ策略")

        if "macd" in enabled_strategies:
            from strategies.macd_strategy import MACDStrategy
            macd_config = {
                "fast": 12,
                "slow": 26,
                "signal": 9,
                "stop_loss": 0.02,
                "take_profit": 0.04,
                "min_confidence": 0.6,
            }
            macd_strategy = MACDStrategy(macd_config)
            self.strategy_manager.register_strategy(macd_strategy)
            logger.info("已注册MACD策略")
    
    async def start(self):
        """启动交易机器人"""
        if self.is_running:
            logger.warning("交易机器人已在运行中")
            return
        
        try:
            logger.info("启动交易机器人...")
            self.is_running = True
            
            # 启动订单管理器
            await self.order_manager.start()
            
            # 启动WebSocket连接
            await self.ws_client.connect(testnet=self.config.get("testnet", True))
            
            # 订阅市场数据
            symbol = self.config["symbol"]
            await self.ws_client.subscribe_ticker(symbol, self.market_data_handler.handle_ticker)
            await self.ws_client.subscribe_orderbook(symbol, self.market_data_handler.handle_orderbook)
            # 订阅1分钟K线并解析为OHLC
            await self.ws_client.subscribe_candles(symbol, "1m", lambda d: asyncio.create_task(self.market_data_handler.handle_candles_ws(symbol, d)))
            
            # 启动策略管理器
            await self.strategy_manager.start()
            # 激活已注册的策略
            for strategy_name in list(self.strategy_manager.strategies.keys()):
                self.strategy_manager.activate_strategy(strategy_name)
            
            # 启动监控服务
            if self.config.get("enable_monitoring", True):
                await self.monitoring_service.start()
            
            # 启动监控任务
            if self.config["enable_monitoring"]:
                monitor_task = asyncio.create_task(self._monitoring_loop())
                self.tasks.append(monitor_task)
            
            # 启动交易循环
            trading_task = asyncio.create_task(self._trading_loop())
            self.tasks.append(trading_task)
            
            logger.info("交易机器人启动完成")
            
        except Exception as e:
            logger.error(f"启动失败: {str(e)}")
            await self.stop()
            raise
    
    async def stop(self):
        """停止交易机器人"""
        if not self.is_running:
            return
        
        logger.info("停止交易机器人...")
        self.is_running = False
        
        try:
            # 停止策略管理器
            await self.strategy_manager.stop()
            
            # 停止订单管理器
            await self.order_manager.stop()
            
            # 停止监控服务
            if hasattr(self, 'monitoring_service'):
                await self.monitoring_service.stop()
            
            # 关闭WebSocket连接
            await self.ws_client.disconnect()
            
            # 取消所有任务
            for task in self.tasks:
                task.cancel()
            
            # 等待任务完成
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            
            logger.info("交易机器人已停止")
            
        except Exception as e:
            logger.error(f"停止过程中出错: {str(e)}")
    
    async def _handle_market_data(self, message: Dict[str, Any]):
        """处理市场数据"""
        try:
            # 更新市场数据处理
            await self.market_data_handler.handle_message(message)
            
            # 更新策略数据
            symbol = message.get("arg", {}).get("instId", "")
            if symbol == self.config["symbol"]:
                await self.strategy_manager.update_market_data(message)
                
        except Exception as e:
            logger.error(f"处理市场数据失败: {str(e)}")
    
    async def _trading_loop(self):
        """主交易循环"""
        logger.info("启动交易循环...")
        
        while self.is_running:
            try:
                # 使用最新的1分钟K线驱动策略分析
                candle = self.market_data_handler.get_latest_candle(self.config["symbol"])
                if candle:
                    last_price = self.market_data_handler.get_latest_price(self.config["symbol"]) or candle.get("close", 0.0)
                    market_data = MarketData(
                        symbol=self.config["symbol"],
                        timestamp=datetime.now(),
                        open=candle.get("open", 0.0),
                        high=candle.get("high", 0.0),
                        low=candle.get("low", 0.0),
                        close=candle.get("close", 0.0),
                        volume=candle.get("volume", 0.0),
                        bid=last_price,
                        ask=last_price
                    )

                    signals = await self.strategy_manager.analyze(market_data)
                    await self._process_signals(signals)
                
                # 等待下一个循环
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"交易循环出错: {str(e)}")
                await asyncio.sleep(60)  # 出错后等待1分钟
    
    async def _process_signals(self, signals: list):
        """处理交易信号"""
        for signal in signals:
            try:
                symbol = signal.symbol
                signal_type = signal.signal_type
                confidence = signal.confidence
                
                logger.info(f"收到交易信号: {symbol} {signal_type.value} 置信度: {confidence}")
                
                # 风险检查
                risk_check = self.risk_manager.check_trade_signal(signal)
                if not risk_check["allowed"]:
                    logger.warning(f"信号被风险管理器拒绝: {risk_check['reason']}")
                    continue
                
                # 创建订单
                order_id = await self._create_order_from_signal(signal)
                if order_id:
                    logger.info(f"成功创建订单: {order_id}")
                    
            except Exception as e:
                logger.error(f"处理交易信号失败: {str(e)}")
    
    async def _create_order_from_signal(self, signal) -> Optional[str]:
        """根据信号创建订单"""
        try:
            symbol = signal.symbol
            signal_type = signal.signal_type
            
            # 确定交易方向
            if signal_type.value == "buy":
                side = "buy"
            elif signal_type.value == "sell":
                side = "sell"
            else:
                return None
            
            # 确定订单类型和价格
            current_price = signal.metadata.get("current_price", 0)
            if current_price <= 0:
                logger.error("无法获取当前价格")
                return None
            
            # 计算订单数量
            position_size = self.config["position_size"]
            order_size = position_size / current_price
            
            # 创建订单
            order_id = self.order_manager.create_order(
                symbol=symbol,
                side=side,
                order_type="market",  # 使用市价单
                size=order_size,
                price=None,
                metadata={
                    "signal_id": signal.signal_id,
                    "strategy_name": signal.strategy_name,
                    "confidence": signal.confidence
                }
            )
            
            # 提交订单
            result = await self.order_manager.submit_order(order_id)
            if result.success:
                return order_id
            else:
                logger.error(f"订单提交失败: {result.error_message}")
                return None
                
        except Exception as e:
            logger.error(f"创建订单失败: {str(e)}")
            return None
    
    async def _monitoring_loop(self):
        """监控循环"""
        logger.info("启动监控循环...")
        
        while self.is_running:
            try:
                # 获取当前状态
                status = await self.get_status()
                
                # 记录状态信息
                logger.info(f"机器人状态: {json.dumps(status, indent=2, ensure_ascii=False)}")
                
                # 检查风险指标
                try:
                    if hasattr(self.risk_manager, 'is_daily_limit_reached') and self.risk_manager.is_daily_limit_reached():
                        logger.warning("已达到日亏损限制，暂停交易")
                        # 可以在这里添加暂停交易的逻辑
                except AttributeError:
                    # RiskManager没有is_daily_limit_reached方法，跳过检查
                    pass
                
                # 等待下次检查
                await asyncio.sleep(self.config["monitoring_interval"])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环出错: {str(e)}")
                await asyncio.sleep(60)
    
    async def get_status(self) -> Dict[str, Any]:
        """获取机器人状态"""
        status = {
            "timestamp": datetime.now().isoformat(),
            "is_running": self.is_running,
            "config": {
                "symbol": self.config["symbol"],
                "trading_mode": self.config["trading_mode"],
                "enabled_strategies": self.config["strategies"]
            }
        }
        
        # 获取投资组合状态
        if hasattr(self, 'portfolio_manager') and self.portfolio_manager:
            try:
                status["portfolio"] = self.portfolio_manager.get_status()
            except AttributeError:
                status["portfolio"] = {"error": "PortfolioManager未实现get_status方法"}
        
        # 获取订单状态
        if self.order_manager:
            status["orders"] = self.order_manager.get_order_summary()
        
        # 获取策略状态
        if self.strategy_manager:
            status["strategies"] = {
                "active_strategies": self.strategy_manager.get_active_strategies(),
                "recent_signals": len(self.strategy_manager.get_recent_signals(5))
            }
        
        return status
    
    def signal_handler(self, signum, frame):
        """信号处理"""
        logger.info(f"收到信号 {signum}，准备停止机器人...")
        asyncio.create_task(self.stop())


async def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="OKX自动交易机器人")
    parser.add_argument("--config", "-c", default=".env", help="配置文件路径")
    parser.add_argument("--symbol", "-s", help="交易对")
    parser.add_argument("--mode", "-m", choices=["demo", "live"], help="交易模式")
    parser.add_argument("--log-level", "-l", default="INFO", help="日志级别")
    
    args = parser.parse_args()
    
    # 创建交易机器人
    bot = TradingBot(config_path=args.config)
    
    # 设置信号处理
    signal.signal(signal.SIGINT, bot.signal_handler)
    signal.signal(signal.SIGTERM, bot.signal_handler)
    
    try:
        # 初始化
        await bot.initialize()
        
        # 启动
        await bot.start()
        
        # 保持运行
        while bot.is_running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("用户中断，正在停止...")
    except Exception as e:
        logger.error(f"运行错误: {str(e)}")
    finally:
        await bot.stop()


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())