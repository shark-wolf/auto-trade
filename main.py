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
from dotenv import load_dotenv
from utils.settings_store import SettingsStore

# 添加src目录到Python路径
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
sys.path.insert(0, str(src_dir))

from api import MarketDataHandler, CCXTClient
from strategies import StrategyManager, MarketData, Signal, SignalType
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
        self.ccxt_poll_task = None
        # 分钟边界对齐：记录最近已处理的K线时间戳（毫秒）
        self.last_processed_candle_ts = None
        
        # 设置日志
        self._setup_logging()
        
        logger.info("交易机器人初始化完成")
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        
        # 加载 .env 环境变量（优先使用项目根目录下的 .env）
        try:
            env_path = Path(".env")
            if env_path.exists():
                load_dotenv(env_path)
            else:
                load_dotenv()
        except Exception:
            load_dotenv()
        
        config = {
            # API配置（从数据库读取为主，默认空/演示）
            "api_key": "",
            "api_secret": "",
            "passphrase": "",
            "testnet": True,
            
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
            "strategies": os.getenv("ENABLED_STRATEGIES", "kdj_macd").split(","),
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
            # 监控WebSocket服务配置（用于前端仪表板连接）
            "ws_host": os.getenv("WS_HOST", "127.0.0.1"),
            "ws_port": int(os.getenv("WS_PORT", "8765")),
            "enable_websocket": os.getenv("ENABLE_WEBSOCKET", "true").lower() == "true",
            # 行情轮询（CCXT）
            "enable_ccxt_polling": os.getenv("ENABLE_CCXT_POLLING", "true").lower() == "true",
            "enable_backtest": os.getenv("ENABLE_BACKTEST", "true").lower() == "true",
            "backtest_bars": int(os.getenv("BACKTEST_BARS", "500")),
            
            # 数据库配置
            "database_url": os.getenv("DATABASE_URL", "")
        }

        try:
            db_url = config.get("database_url") or "sqlite:///data/trading.db"
            db_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else db_url
            store = SettingsStore(db_path)
            # 通用设置
            v = store.get("api_backend")
            if v: config["api_backend"] = v.lower()
            v = store.get("symbol")
            if v: config["symbol"] = v
            v = store.get("trading_timeframe")
            if v: config["trading_timeframe"] = v
            # 凭据（按后端读取）
            creds = store.get_credentials(config.get("exchange_type", None))
            if creds:
                config["api_key"] = creds.get("api_key", "")
                config["api_secret"] = creds.get("api_secret", "")
                config["passphrase"] = creds.get("passphrase", "")
                config["testnet"] = str(creds.get("testnet", "false")).lower() == "true"
                et = creds.get("exchange_type", "okx")
                if et:
                    config["exchange_type"] = et
                is_demo = str(creds.get("is_demo", "true")).lower() == "true"
                if is_demo:
                    config["trading_mode"] = "demo"
        except Exception:
            pass

        # 后端选择与调试开关
        config["api_backend"] = "ccxt"
        config["trading_timeframe"] = config.get("trading_timeframe") or "1m"
        config["api_debug"] = os.getenv("API_DEBUG", "false").lower() == "true"
        
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
            
            # 初始化API客户端（统一使用 CCXT）
            logger.info("使用 CCXT 作为交易后端")
            self.api_client = CCXTClient(
                api_key=self.config["api_key"],
                secret=self.config["api_secret"],
                passphrase=self.config["passphrase"],
                testnet=self.config["testnet"],
                exchange_type=self.config.get("exchange_type", "okx")
            )
            
            # 测试API连接
            await self._test_api_connection()
            
            # 初始化WebSocket客户端（监控页交互，交易不使用WS）
            self.ws_client = None
            
            # 初始化市场数据处理
            self.market_data_handler = MarketDataHandler()

            # 初始化 CCXT 公共客户端（用于行情轮询）
            try:
                self.ccxt_public = CCXTClient(
                    api_key=self.config["api_key"],
                    secret=self.config["api_secret"],
                    passphrase=self.config["passphrase"],
                    testnet=self.config["testnet"],
                    exchange_type=self.config.get("exchange_type", "okx")
                )
            except Exception:
                self.ccxt_public = None
            
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
            # 注册监控面板控制回调
            try:
                self.monitoring_service.register_control_callback(self._on_monitoring_control)
            except Exception:
                pass
            # 注册监控面板参数更新回调
            try:
                self.monitoring_service.register_params_callback(self._on_monitoring_params_update)
            except Exception:
                pass
            try:
                self.monitoring_service.register_timeframe_callback(self._on_monitoring_timeframe_update)
            except Exception:
                pass
            try:
                self.monitoring_service.register_creds_callback(self._on_monitoring_creds_update)
            except Exception:
                pass
            
            logger.info("交易机器人组件初始化完成")
            
        except Exception as e:
            logger.error(f"初始化失败: {str(e)}")
            raise

        try:
            tf_saved = self.monitoring_service.get_setting('trading_timeframe') if self.monitoring_service else None
            if tf_saved:
                self.config['trading_timeframe'] = tf_saved
        except Exception:
            pass

        try:
            cm = None
            if self.strategy_manager:
                cm = self.strategy_manager.get_strategy('KDJ_MACD')
            if cm and self.monitoring_service:
                sp = self.monitoring_service.get_strategy_params('KDJ_MACD')
                if sp:
                    cm.update_parameters(sp)
        except Exception:
            pass
    
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

        # 新增：根据配置启用合并策略或单独策略
        if "kdj_macd" in enabled_strategies:
            # 优先注册合并策略
            from strategies.kdj_macd_strategy import KDJMACDStrategy
            composite_config = {
                "kdj": {
                    "period": self.config.get("kdj_period", 9),
                    "oversold": 20,
                    "overbought": 80,
                },
                "macd": {
                    "fast": 5,
                    "slow": 13,
                    "signal": 4,
                },
                "stop_loss": 0.02,
                "take_profit": 0.04,
                "min_confidence": 0.55,
            }
            cm_strategy = KDJMACDStrategy(composite_config)
            self.strategy_manager.register_strategy(cm_strategy)
            logger.info("已注册KDJ+MACD合并策略")
        else:
            # 兼容旧配置：分别注册KDJ与MACD
            if "kdj" in enabled_strategies:
                from strategies.kdj_strategy import KDJStrategy
                kdj_config = {
                    "period": self.config.get("kdj_period", 9),
                    "oversold": 20,
                    "overbought": 80,
                    "stop_loss": 0.02,
                    "take_profit": 0.04,
                    "min_confidence": 0.55,
                }
                kdj_strategy = KDJStrategy(kdj_config)
                self.strategy_manager.register_strategy(kdj_strategy)
                logger.info("已注册KDJ策略")

            if "macd" in enabled_strategies:
                from strategies.macd_strategy import MACDStrategy
                macd_config = {
                    "fast": 5,
                    "slow": 13,
                    "signal": 4,
                    "stop_loss": 0.02,
                    "take_profit": 0.04,
                    "min_confidence": 0.55,
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
            if self.ws_client:
                await self.ws_client.connect(testnet=self.config.get("testnet", True))
            
            # 订阅市场数据
            symbol = self.config["symbol"]
            # 行情订阅：更新缓存并同步到投资组合现价
            if self.ws_client:
                await self.ws_client.subscribe_ticker(symbol, self._on_ticker)
                await self.ws_client.subscribe_orderbook(symbol, self.market_data_handler.handle_orderbook)
                await self.ws_client.subscribe_candles(symbol, "1m", self._on_candles)

            # 启动 CCXT 轮询（作为实时/回退数据源）
            if self.config.get("enable_ccxt_polling", True) and getattr(self, "ccxt_public", None):
                try:
                    self.ccxt_poll_task = asyncio.create_task(self._ccxt_polling_loop())
                    self.tasks.append(self.ccxt_poll_task)
                    logger.info("已启动CCXT行情轮询")
                except Exception as e:
                    logger.error(f"启动CCXT轮询失败: {str(e)}")

            if self.config.get("enable_backtest", True):
                try:
                    bt_task = asyncio.create_task(self._backtest_kdj_macd_okx())
                    self.tasks.append(bt_task)
                    logger.info("已启动OKX模拟数据回测任务")
                except Exception as e:
                    logger.error(f"启动回测失败: {str(e)}")
            
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
            # 推送开启事件到监控
            try:
                if self.monitoring_service:
                    self.monitoring_service.log_event(
                        event_type="system",
                        level="success",
                        message="自动交易已开启",
                        data={"source": "bot", "symbol": self.config.get("symbol")}
                    )
                    try:
                        tf_opts = None
                        if getattr(self, 'ccxt_public', None):
                            tf_opts = self.ccxt_public.available_timeframes()
                        self.monitoring_service.update_strategy_status({
                            'active_strategies': self.strategy_manager.get_active_strategies(),
                            'recent_signals': len(self.strategy_manager.get_recent_signals(24)),
                            'executed_orders': self.order_manager.get_order_summary().get('total_orders', 0) if self.order_manager else 0,
                            'open_positions': 0,
                            'indicator_params': {},
                            'indicator_values': {},
                            'timeframe': self.config.get('trading_timeframe', '1m'),
                            'timeframe_options': tf_opts or ['1m','5m','15m','1h','4h']
                        })
                    except Exception:
                        pass
            except Exception:
                pass
            
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
            
            # 保持监控服务运行，以便从仪表板重新开启交易
            # if hasattr(self, 'monitoring_service'):
            #     await self.monitoring_service.stop()
            
            # 关闭WebSocket连接
            await self.ws_client.disconnect()
            
            # 取消所有任务
            for task in self.tasks:
                task.cancel()
            
            # 等待任务完成
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            
            logger.info("交易机器人已停止")
            # 推送关闭事件到监控
            try:
                if self.monitoring_service:
                    self.monitoring_service.log_event(
                        event_type="system",
                        level="warning",
                        message="自动交易已关闭",
                        data={"source": "bot", "symbol": self.config.get("symbol")}
                    )
            except Exception:
                pass
            
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

    async def _on_ticker(self, data: list):
        """行情回调：更新缓存并同步 PortfolioManager 现价"""
        try:
            # 更新行情缓存
            await self.market_data_handler.handle_ticker(data)
            # 同步现价到投资组合
            for t in data:
                inst_id = t.get("instId")
                last = t.get("last")
                try:
                    price = float(last) if last is not None else None
                except Exception:
                    price = None
                if inst_id and price is not None and price > 0:
                    # 仅同步当前交易对，避免无关数据污染
                    if inst_id == self.config.get("symbol") and hasattr(self, 'portfolio_manager') and self.portfolio_manager:
                        try:
                            self.portfolio_manager.update_price(inst_id, price)
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"处理行情回调失败: {str(e)}")

    async def _on_candles(self, data: list):
        """K线回调：在K线收盘确认时触发分析"""
        try:
            symbol = self.config.get("symbol")
            # 更新K线缓存
            await self.market_data_handler.handle_candles_ws(symbol, data)
            # 读取最新K线
            candle = self.market_data_handler.get_latest_candle(symbol)
            if not candle:
                return

            ts = candle.get("ts")
            confirm = candle.get("confirm", False)
            if ts is None or not confirm:
                return
            # 去重：只在新的收盘K线触发
            if self.last_processed_candle_ts == ts:
                return
            self.last_processed_candle_ts = ts

            last_price = self.market_data_handler.get_latest_price(symbol) or candle.get("close", 0.0)
            market_data = MarketData(
                symbol=symbol,
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
            logger.info(f"分钟收盘分析完成: ts={ts}, 信号数={len(signals)}")
        except Exception as e:
            logger.error(f"处理K线回调失败: {str(e)}")
    
    async def _trading_loop(self):
        """主交易循环"""
        logger.info("启动交易循环...")
        
        while self.is_running:
            try:
                # 使用最新的1分钟K线驱动策略分析
                candle_getter = getattr(self.market_data_handler, "get_latest_candle", None)
                if callable(candle_getter):
                    candle = candle_getter(self.config["symbol"]) 
                else:
                    candle = getattr(self.market_data_handler, "candle_cache", {}).get(self.config["symbol"]) 
                if candle:
                    ts = candle.get("ts")
                    confirm = candle.get("confirm", False)
                    # 作为回退机制：仅在确认收盘且未处理过的K线时分析
                    if ts is None or not confirm or self.last_processed_candle_ts == ts:
                        await asyncio.sleep(5)
                        continue
                    self.last_processed_candle_ts = ts
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
                await asyncio.sleep(5)  # 更快的回退轮询，避免错过收盘触发
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"交易循环出错: {str(e)}")
                await asyncio.sleep(60)  # 出错后等待1分钟

    async def _ccxt_polling_loop(self):
        """使用CCXT轮询行情与K线，并填充到MarketDataHandler缓存，驱动策略计算更新"""
        symbol = self.config.get("symbol")
        while self.is_running:
            try:
                if not getattr(self, "ccxt_public", None):
                    await asyncio.sleep(5)
                    continue
                # 获取最近两根K线
                tf = self.config.get("trading_timeframe", "1m")
                ohlcv = await self.ccxt_public.fetch_ohlcv(symbol, timeframe=tf, limit=2)
                if ohlcv and len(ohlcv) >= 2:
                    prev = ohlcv[-2]
                    ts, o, h, l, c, v = prev[0], float(prev[1]), float(prev[2]), float(prev[3]), float(prev[4]), float(prev[5])
                    # 写入最新确认K线
                    try:
                        self.market_data_handler.candle_cache[symbol] = {
                            "open": o,
                            "high": h,
                            "low": l,
                            "close": c,
                            "volume": v,
                            "timestamp": datetime.now(),
                            "ts": int(ts),
                            "confirm": True,
                        }
                    except Exception:
                        pass
                # 更新最新价格
                last_price = await self.ccxt_public.fetch_ticker_price(symbol)
                if last_price and last_price > 0:
                    try:
                        self.market_data_handler.price_cache[symbol] = {
                            "last": float(last_price),
                            "bid": float(last_price),
                            "ask": float(last_price),
                            "vol": 0.0,
                            "timestamp": datetime.now(),
                        }
                        # 同步到组合
                        if hasattr(self, 'portfolio_manager') and self.portfolio_manager:
                            self.portfolio_manager.update_price(symbol, float(last_price))
                    except Exception:
                        pass
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"CCXT轮询失败: {str(e)}")
                await asyncio.sleep(5)

    async def _backtest_kdj_macd_okx(self):
        symbol = self.config.get("symbol")
        timeframe = self.config.get("trading_timeframe", "1m")
        bars = int(self.config.get("backtest_bars", 500))
        import asyncio
        from strategies.kdj_macd_strategy import KDJMACDStrategy
        cm = self.strategy_manager.get_strategy("KDJ_MACD")
        params = cm.parameters if cm else {
            "kdj": {"period": 9, "k_smooth": 3, "d_smooth": 3, "oversold": 20, "overbought": 80},
            "macd": {"fast": 5, "slow": 13, "signal": 4},
            "min_confidence": 0.55, "stop_loss": 0.02, "take_profit": 0.04,
        }
        s = KDJMACDStrategy(params)
        s.start()
        ohlcv = await self.ccxt_public.fetch_ohlcv(symbol, timeframe=timeframe, limit=bars) if getattr(self, 'ccxt_public', None) else None
        candles = list(ohlcv or [])
        wins = 0
        losses = 0
        total = 0
        position = 0.0
        entry_price = 0.0
        for c in candles:
            try:
                o = float(c[1]); h = float(c[2]); l = float(c[3]); cl = float(c[4]); v = float(c[5])
            except Exception:
                continue
            md = MarketData(symbol=symbol, timestamp=datetime.now(), open=o, high=h, low=l, close=cl, volume=v, bid=cl, ask=cl)
            sig = s.analyze(md)
            if sig.signal_type == SignalType.BUY and position == 0:
                position = 1.0
                entry_price = cl
            elif sig.signal_type == SignalType.SELL and position > 0:
                pnl = cl - entry_price
                total += 1
                if pnl > 0:
                    wins += 1
                    if self.monitoring_service:
                        self.monitoring_service.record_metric("winning_trades", 1)
                else:
                    losses += 1
                    if self.monitoring_service:
                        self.monitoring_service.record_metric("losing_trades", 1)
                if self.monitoring_service:
                    self.monitoring_service.record_metric("total_trades", 1)
                position = 0.0
                entry_price = 0.0
        win_rate = (wins / total * 100.0) if total > 0 else 0.0
        try:
            if self.monitoring_service:
                self.monitoring_service.record_metric("win_rate", win_rate)
                self.monitoring_service.log_event(
                    event_type="system", level="info",
                    message="回测完成: OKX模拟数据胜率",
                    data={"symbol": symbol, "timeframe": timeframe, "bars": bars, "wins": wins, "losses": losses, "total": total, "win_rate": win_rate}
                )
        except Exception:
            pass
        if win_rate < 75.0:
            try:
                await self._auto_tune_kdj_macd(timeframe, bars)
            except Exception:
                pass

    async def _evaluate_kdj_macd(self, params: Dict[str, Any], timeframe: str, bars: int) -> float:
        symbol = self.config.get("symbol")
        from strategies.kdj_macd_strategy import KDJMACDStrategy
        s = KDJMACDStrategy(params)
        s.start()
        ohlcv = await self.ccxt_public.fetch_ohlcv(symbol, timeframe=timeframe, limit=bars) if getattr(self, 'ccxt_public', None) else None
        candles = list(ohlcv or [])
        wins = 0
        total = 0
        position = 0.0
        entry_price = 0.0
        for c in candles:
            try:
                o = float(c[1]); h = float(c[2]); l = float(c[3]); cl = float(c[4]); v = float(c[5])
            except Exception:
                continue
            md = MarketData(symbol=symbol, timestamp=datetime.now(), open=o, high=h, low=l, close=cl, volume=v, bid=cl, ask=cl)
            sig = s.analyze(md)
            if sig.signal_type == SignalType.BUY and position == 0:
                position = 1.0
                entry_price = cl
            elif sig.signal_type == SignalType.SELL and position > 0:
                pnl = cl - entry_price
                total += 1
                if pnl > 0:
                    wins += 1
                position = 0.0
                entry_price = 0.0
        return (wins / total * 100.0) if total > 0 else 0.0

    async def _auto_tune_kdj_macd(self, timeframe: str, bars: int):
        cm = self.strategy_manager.get_strategy("KDJ_MACD")
        base = cm.parameters if cm else {
            "kdj": {"period": 9, "k_smooth": 3, "d_smooth": 3, "oversold": 20, "overbought": 80},
            "macd": {"fast": 5, "slow": 13, "signal": 4},
            "min_confidence": 0.55, "stop_loss": 0.02, "take_profit": 0.04,
        }
        periods = [7, 9, 11]
        fasts = [5, 8, 12]
        slows = [13, 21, 26]
        signals = [4, 5, 9]
        best_params = base
        best_wr = await self._evaluate_kdj_macd(base, timeframe, bars)
        for p in periods:
            for f in fasts:
                for sl in slows:
                    if f >= sl:
                        continue
                    for sg in signals:
                        cand = {
                            "kdj": {**(base.get("kdj") or {}), "period": p},
                            "macd": {**(base.get("macd") or {}), "fast": f, "slow": sl, "signal": sg},
                            "min_confidence": base.get("min_confidence", 0.55),
                            "stop_loss": base.get("stop_loss", 0.02),
                            "take_profit": base.get("take_profit", 0.04),
                        }
                        wr = await self._evaluate_kdj_macd(cand, timeframe, bars)
                        if wr > best_wr:
                            best_wr = wr
                            best_params = cand
                        if best_wr >= 75.0:
                            break
                    if best_wr >= 75.0:
                        break
                if best_wr >= 75.0:
                    break
            if best_wr >= 75.0:
                break
        if cm:
            cm.update_parameters(best_params)
        try:
            if self.monitoring_service:
                self.monitoring_service.set_strategy_params('KDJ_MACD', best_params, best_wr)
                self.monitoring_service.log_event(
                    event_type="system", level="info",
                    message="参数自动调优完成",
                    data={"win_rate": best_wr}
                )
        except Exception:
            pass
    
    async def _process_signals(self, signals: list):
        """处理交易信号：仅在KDJ与MACD共振时执行下单；止损/止盈触发不受共振限制"""
        try:
            if not signals:
                return

            # 止损/止盈触发优先处理（不要求共振）
            stop_signals = [s for s in signals if s.metadata.get("stop_trigger")]
            for s in stop_signals:
                try:
                    logger.info(f"处理止损/止盈信号: {s.symbol} {s.signal_type.value} 置信度: {s.confidence}")
                    risk_check = self.risk_manager.check_trade_signal(s)
                    if not risk_check["allowed"]:
                        logger.warning(f"止损/止盈信号被风险管理器拒绝: {risk_check['reason']}")
                        continue
                    order_id = await self._create_order_from_signal(s)
                    if order_id:
                        logger.info(f"止损/止盈订单创建成功: {order_id}")
                except Exception as e:
                    logger.error(f"处理止损/止盈信号失败: {str(e)}")

            # 若存在合并策略（KDJ_MACD），其信号可直接用于下单
            def _strategy_name(s):
                return (s.metadata or {}).get("strategy_name", "")

            composite_signals = [s for s in signals if _strategy_name(s) in ("KDJ_MACD", "KDJ+MACD") and s.signal_type != SignalType.HOLD]
            for s in composite_signals:
                try:
                    risk_check = self.risk_manager.check_trade_signal(s)
                    if not risk_check["allowed"]:
                        logger.warning(f"合并策略信号被风险管理器拒绝: {risk_check['reason']}")
                        continue
                    order_id = await self._create_order_from_signal(s)
                    if order_id:
                        logger.info(f"合并策略订单创建成功: {order_id}")
                except Exception as e:
                    logger.error(f"处理合并策略信号失败: {str(e)}")

            # 共振逻辑：当分别启用KDJ与MACD时，需同向才下单
            kdj_signals = [s for s in signals if _strategy_name(s) == "KDJ" and s.signal_type != SignalType.HOLD]
            macd_signals = [s for s in signals if _strategy_name(s) == "MACD" and s.signal_type != SignalType.HOLD]

            if not kdj_signals or not macd_signals:
                # 当合并策略已处理或缺少分策略信号时，直接返回
                return

            # 取最新各一个信号进行共振判断
            kdj = kdj_signals[-1]
            macd = macd_signals[-1]

            if kdj.signal_type == macd.signal_type and kdj.signal_type != SignalType.HOLD:
                side = kdj.signal_type.value
                symbol = kdj.symbol
                combined_conf = min(kdj.confidence, macd.confidence)

                logger.info(f"检测到KDJ+MACD共振: {symbol} {side} 置信度(取最小): {combined_conf}")

                # 以KDJ的价格为主，若缺失则用MACD价格
                price = kdj.price or macd.price
                metadata = {
                    "strategy_name": "KDJ+MACD",
                    "signal_id": f"KDJ+MACD-{int(datetime.now().timestamp())}",
                    "current_price": price,
                    "kdj": kdj.metadata,
                    "macd": macd.metadata,
                    "confidence": combined_conf,
                }

                consensus_signal = Signal(
                    symbol=symbol,
                    signal_type=kdj.signal_type,
                    price=price,
                    confidence=combined_conf,
                    timestamp=datetime.now(),
                    metadata=metadata,
                )

                # 风险检查
                risk_check = self.risk_manager.check_trade_signal(consensus_signal)
                if not risk_check["allowed"]:
                    logger.warning(f"共振信号被风险管理器拒绝: {risk_check['reason']}")
                    return

                # 创建订单
                order_id = await self._create_order_from_signal(consensus_signal)
                if order_id:
                    logger.info(f"共振订单创建成功: {order_id}")
            else:
                # 无需日志噪音，保持安静
                pass
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
            # 兼容策略输出的price以及管理器注入的current_price
            current_price = 0
            try:
                current_price = float(signal.metadata.get("current_price", 0))
            except Exception:
                current_price = 0
            if not current_price or current_price <= 0:
                try:
                    current_price = float(getattr(signal, "price", 0) or signal.metadata.get("price", 0))
                except Exception:
                    current_price = 0
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
                    "signal_id": signal.metadata.get("signal_id"),
                    "strategy_name": signal.metadata.get("strategy_name"),
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

                # 推送资金与持仓到监控服务
                try:
                    if self.monitoring_service and 'portfolio' in status:
                        self.monitoring_service.update_portfolio_status(status['portfolio'])
                except Exception as _:
                    # 监控服务更新失败不影响主流程
                    pass

                # 推送策略状态与指标参数到监控服务
                try:
                    if self.monitoring_service and self.strategy_manager:
                        active = self.strategy_manager.get_active_strategies()
                        recent_signals = len(self.strategy_manager.get_recent_signals(24))
                        order_summary = self.order_manager.get_order_summary() if self.order_manager else {}
                        executed_orders = int(order_summary.get('total_orders', 0))
                        pf = status.get('portfolio') or {}
                        open_positions = int(pf.get('position_count', len(pf.get('positions', []) or [])))
                        try:
                            if self.monitoring_service:
                                self.monitoring_service.record_metric("daily_pnl", float(pf.get("pnl", 0.0)))
                        except Exception:
                            pass

                        kdj = self.strategy_manager.get_strategy('KDJ')
                        macd = self.strategy_manager.get_strategy('MACD')
                        cm = self.strategy_manager.get_strategy('KDJ_MACD')
                        indicator_params = {}
                        indicator_values = {}
                        try:
                            if kdj:
                                indicator_params['KDJ'] = dict(kdj.parameters)
                            if macd:
                                indicator_params['MACD'] = dict(macd.parameters)
                            if cm:
                                # 从合并策略拆分子参数，保持前端展示一致
                                k_params = (cm.parameters.get('kdj') or {}).copy()
                                m_params = (cm.parameters.get('macd') or {}).copy()
                                # 合并通用风险参数与置信度
                                shared = {
                                    'stop_loss': cm.parameters.get('stop_loss'),
                                    'take_profit': cm.parameters.get('take_profit'),
                                    'min_confidence': cm.parameters.get('min_confidence'),
                                }
                                indicator_params['KDJ'] = {**k_params, **shared}
                                indicator_params['MACD'] = {**m_params, **shared}
                                # 指标实时值（来自策略状态）
                                try:
                                    st = cm.get_status()
                                    indicator_values['KDJ'] = {
                                        'k': float(st.get('last_k', 0.0)),
                                        'd': float(st.get('last_d', 0.0)),
                                        'j': float(st.get('last_j', 0.0)),
                                    }
                                    indicator_values['MACD'] = {
                                        'macd': float(st.get('last_macd', 0.0)),
                                        'signal': float(st.get('last_signal', 0.0)),
                                        'hist': float(st.get('last_hist', 0.0)),
                                    }
                                except Exception:
                                    pass
                        except Exception:
                            # 保底：避免参数对象不可序列化导致失败
                            pass

                        self.monitoring_service.update_strategy_status({
                            'active_strategies': active,
                            'recent_signals': recent_signals,
                            'executed_orders': executed_orders,
                            'open_positions': open_positions,
                            'indicator_params': indicator_params,
                            'indicator_values': indicator_values,
                            'timeframe': self.config.get("trading_timeframe", "1m"),
                            'current_price': float(self.market_data_handler.get_latest_price(self.config.get("symbol")) or 0.0),
                            'timeframe_options': (self.ccxt_public.available_timeframes() if getattr(self, 'ccxt_public', None) else None) or ['1m','5m','15m','1h','4h'],
                            'is_running': bool(self.is_running)
                        })
                except Exception:
                    # 推送失败不影响主流程
                    pass

                # 同步风险管理账户余额（用于回撤等指标）
                try:
                    pf = status.get('portfolio') or {}
                    total_value = float(pf.get('total_value', 0.0))
                    if total_value > 0 and hasattr(self.risk_manager, 'update_account_balance'):
                        self.risk_manager.update_account_balance(total_value)
                except Exception:
                    pass
                
                # 检查风险指标（包括25%总额止损）
                try:
                    if hasattr(self.risk_manager, 'is_daily_limit_reached') and self.risk_manager.is_daily_limit_reached():
                        logger.warning("已达到日亏损限制，暂停交易")
                        # 可以在这里添加暂停交易的逻辑
                except AttributeError:
                    # RiskManager没有is_daily_limit_reached方法，跳过检查
                    pass

                # 25%总额止损：当净值较初始资金回撤达到25%时自动停止
                try:
                    pf = status.get('portfolio') or {}
                    pnl_ratio = float(pf.get('pnl_ratio', 0.0))
                    if pnl_ratio <= -0.25 and self.is_running:
                        logger.warning("触发25%总额止损，自动停止交易")
                        # 记录事件
                        try:
                            if self.monitoring_service:
                                self.monitoring_service.log_event(
                                    event_type="risk",
                                    level="critical",
                                    message="触发25%总额止损，自动停止交易",
                                    data={
                                        "source": "bot",
                                        "pnl_ratio": pnl_ratio,
                                        "total_value": pf.get('total_value'),
                                        "initial_cash": pf.get('initial_cash')
                                    }
                                )
                        except Exception:
                            pass
                        await self.stop()
                        # 停止后跳出循环防止重复处理
                        break
                except Exception:
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
            # 同时附加当前KDJ/MACD的参数，便于诊断与前端兼容读取
            try:
                kdj = self.strategy_manager.get_strategy('KDJ')
                macd = self.strategy_manager.get_strategy('MACD')
                cm = self.strategy_manager.get_strategy('KDJ_MACD')
                if cm:
                    k_params = (cm.parameters.get('kdj') or {})
                    m_params = (cm.parameters.get('macd') or {})
                    shared = {
                        'stop_loss': cm.parameters.get('stop_loss'),
                        'take_profit': cm.parameters.get('take_profit'),
                        'min_confidence': cm.parameters.get('min_confidence'),
                    }
                    status["strategies"]["indicator_params"] = {
                        "KDJ": {**k_params, **shared},
                        "MACD": {**m_params, **shared},
                    }
                else:
                    status["strategies"]["indicator_params"] = {
                        "KDJ": (kdj.parameters if kdj else {}),
                        "MACD": (macd.parameters if macd else {}),
                    }
            except Exception:
                pass
        
        return status

    async def _on_monitoring_control(self, action: str):
        """处理来自监控面板的启停控制指令"""
        try:
            if action == 'start':
                if not self.is_running:
                    await self.start()
            elif action == 'stop':
                if self.is_running:
                    await self.stop()
        except Exception as e:
            logger.error(f"处理监控控制指令失败: {str(e)}")

    async def _on_monitoring_params_update(self, strategy: str, updates: Dict[str, Any]):
        """处理来自监控面板的策略参数更新"""
        try:
            if not self.strategy_manager:
                raise RuntimeError("策略管理器未初始化")

            # 获取目标策略
            target = self.strategy_manager.get_strategy(strategy)
            if not target:
                # 兼容大小写与别名
                alias = strategy.upper()
                if alias in ("KDJ", "MACD", "KDJ_MACD"):
                    target = self.strategy_manager.get_strategy(alias)
            if not target:
                raise ValueError(f"未找到指定策略: {strategy}")

            # 组合参数更新（支持深度合并）
            new_params = dict(target.parameters or {})
            for key, val in (updates or {}).items():
                if key in ("kdj", "macd") and isinstance(val, dict):
                    inner = dict(new_params.get(key, {}))
                    inner.update(val)
                    new_params[key] = inner
                else:
                    new_params[key] = val

            # 应用并校验
            target.update_parameters(new_params)

            # 记录日志与状态快照
            logger.info(f"策略参数更新成功: {strategy} -> {new_params}")
            try:
                self.monitoring_service.log_event(
                    event_type="system",
                    level="info",
                    message=f"参数已更新: {strategy}",
                    data={"params": new_params}
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"处理参数更新失败: {str(e)}")
            # 将错误抛出以便监控服务发送ACK
            raise

    async def _on_monitoring_timeframe_update(self, timeframe: str):
        try:
            tf = str(timeframe or "").strip()
            if not tf:
                return
            # 校验周期合法性（交易所支持）
            try:
                if getattr(self, 'ccxt_public', None):
                    opts = self.ccxt_public.available_timeframes() or []
                    if opts and tf not in opts:
                        raise ValueError(f"不支持的周期: {tf}")
            except Exception:
                pass

            self.config["trading_timeframe"] = tf
            # 持久化到SQLite
            try:
                if self.monitoring_service:
                    self.monitoring_service.set_setting('trading_timeframe', tf)
            except Exception:
                pass
            try:
                if self.monitoring_service and self.strategy_manager:
                    active = self.strategy_manager.get_active_strategies()
                    self.monitoring_service.update_strategy_status({
                        'active_strategies': active,
                        'recent_signals': len(self.strategy_manager.get_recent_signals(24)),
                        'executed_orders': self.order_manager.get_order_summary().get('total_orders', 0) if self.order_manager else 0,
                        'open_positions': 0,
                        'indicator_params': {},
                        'indicator_values': {},
                        'timeframe': tf,
                        'current_price': float(self.market_data_handler.get_latest_price(self.config.get("symbol")) or 0.0),
                        'timeframe_options': (self.ccxt_public.available_timeframes() if getattr(self, 'ccxt_public', None) else None) or ['1m','5m','15m','1h','4h']
                    })
            except Exception:
                pass
        except Exception:
            pass

    async def _on_monitoring_creds_update(self, payload: Dict[str, Any]):
        try:
            backend = str(payload.get("backend", "ccxt")).lower()
            exchange_type = str(payload.get("exchange_type", "okx")).lower()
            api_key = str(payload.get("api_key", ""))
            api_secret = str(payload.get("api_secret", ""))
            passphrase = str(payload.get("passphrase", ""))
            testnet = str(payload.get("testnet", "false")).lower() == "true"
            is_demo = str(payload.get("is_demo", "true")).lower() == "true"
            self.config["api_backend"] = backend
            self.config["exchange_type"] = exchange_type
            self.config["api_key"] = api_key
            self.config["api_secret"] = api_secret
            self.config["passphrase"] = passphrase
            self.config["testnet"] = testnet
            if is_demo:
                self.config["trading_mode"] = "demo"
            try:
                if getattr(self, "api_client", None):
                    await self.api_client.close()
            except Exception:
                pass
            try:
                if getattr(self, "ccxt_public", None):
                    await self.ccxt_public.close()
            except Exception:
                pass
            try:
                self.api_client = CCXTClient(
                    api_key=self.config["api_key"],
                    secret=self.config["api_secret"],
                    passphrase=self.config["passphrase"],
                    testnet=self.config["testnet"],
                    exchange_type=self.config.get("exchange_type", "okx")
                )
                self.ccxt_public = CCXTClient(
                    api_key=self.config["api_key"],
                    secret=self.config["api_secret"],
                    passphrase=self.config["passphrase"],
                    testnet=self.config["testnet"],
                    exchange_type=self.config.get("exchange_type", "okx")
                )
            except Exception:
                return
            try:
                if getattr(self, "order_manager", None):
                    self.order_manager.api_client = self.api_client
            except Exception:
                pass
            try:
                if self.ccxt_poll_task:
                    self.ccxt_poll_task.cancel()
                    await asyncio.gather(self.ccxt_poll_task, return_exceptions=True)
                if self.config.get("enable_ccxt_polling", True) and getattr(self, "ccxt_public", None):
                    self.ccxt_poll_task = asyncio.create_task(self._ccxt_polling_loop())
                    self.tasks.append(self.ccxt_poll_task)
            except Exception:
                pass
            try:
                if self.monitoring_service and self.strategy_manager:
                    active = self.strategy_manager.get_active_strategies()
                    self.monitoring_service.update_strategy_status({
                        'active_strategies': active,
                        'recent_signals': len(self.strategy_manager.get_recent_signals(24)),
                        'executed_orders': self.order_manager.get_order_summary().get('total_orders', 0) if self.order_manager else 0,
                        'open_positions': 0,
                        'indicator_params': {},
                        'indicator_values': {},
                        'timeframe': self.config.get('trading_timeframe', '1m'),
                        'current_price': float(self.market_data_handler.get_latest_price(self.config.get("symbol")) or 0.0),
                        'timeframe_options': (self.ccxt_public.available_timeframes() if getattr(self, 'ccxt_public', None) else None) or ['1m','5m','15m','1h','4h']
                    })
            except Exception:
                pass
        except Exception:
            pass
    
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
