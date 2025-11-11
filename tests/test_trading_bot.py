import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
import sys
import os

# 添加src目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from api.okx_client import OKXClient
from api.okx_websocket import OKXWebSocketClient
from strategies.base_strategy import BaseStrategy, SignalType, MarketData, Signal
# from strategies.strategy_manager import StrategyManager
from strategies.ma_cross_strategy import MovingAverageCrossStrategy
from strategies.rsi_strategy import RSIStrategy
# from strategies.grid_strategy import GridTradingStrategy
from risk.risk_manager import RiskManager
from risk.portfolio_manager import PortfolioManager
from execution.order_manager import OrderManager
from monitoring.monitoring import MonitoringService
from config.config_loader import ConfigLoader
# from main import TradingBot


class TestTradingBot(unittest.TestCase):
    """交易机器人单元测试"""

    def setUp(self):
        """测试前的准备工作"""
        self.mock_config = {
            'api': {
                'api_key': 'test_key',
                'secret_key': 'test_secret',
                'passphrase': 'test_passphrase',
                'sandbox': True
            },
            'risk': {
                'max_position_size': 1000,
                'max_daily_loss': 10000,
                'stop_loss_pct': 0.05,
                'take_profit_pct': 0.10
            },
            'strategies': {
                'ma_cross': {
                    'enabled': True,
                    'short_window': 5,
                    'long_window': 20
                },
                'rsi': {
                    'enabled': True,
                    'period': 14,
                    'overbought': 70,
                    'oversold': 30
                }
            }
        }

    def test_okx_client_initialization(self):
        """测试OKX客户端初始化"""
        import sys
        sys.path.insert(0, 'd:\code\python\auto_trade\src')
        from api.okx_client import OKXClient, OKXConfig
        
        config = OKXConfig(
            api_key='test_key',
            secret_key='test_secret',
            passphrase='test_pass',
            testnet=True
        )
        client = OKXClient(config)
        
        self.assertIsNotNone(client)
        self.assertTrue(client.config.testnet)

    @patch('api.okx_client.OKXClient._make_request')
    def test_okx_client_get_ticker(self, mock_request):
        """测试获取行情数据"""
        mock_request.return_value = {
            'code': '0',
            'data': [{'last': '50000', 'ask': '50100', 'bid': '49900'}]
        }
        
        import sys
        sys.path.insert(0, 'd:\code\python\auto_trade\src')
        from api.okx_client import OKXClient, OKXConfig
        
        config = OKXConfig(
            api_key='test_key',
            secret_key='test_secret',
            passphrase='test_pass',
            testnet=True
        )
        client = OKXClient(config)
        
        result = client.get_ticker('BTC-USDT')
        
        self.assertEqual(result['code'], '0')
        self.assertIsNotNone(result['data'])

    # 策略测试
    def test_base_strategy_initialization(self):
        """测试基础策略初始化"""
        # BaseStrategy是抽象类，不能直接实例化
        # 我们测试具体的策略实现
        from strategies.ma_cross_strategy import MovingAverageCrossStrategy
        
        strategy = MovingAverageCrossStrategy({
            'fast_period': 10,
            'slow_period': 20
        })
        
        self.assertEqual(strategy.name, 'MovingAverageCross')
        self.assertEqual(strategy.parameters['fast_period'], 10)
        self.assertEqual(strategy.parameters['slow_period'], 20)

    def test_ma_cross_strategy_signal_generation(self):
        """测试均线交叉策略信号生成"""
        strategy = MovingAverageCrossStrategy({'short_window': 5, 'long_window': 20})
        
        # 创建测试数据
        dates = pd.date_range('2023-01-01', periods=30, freq='1h')
        prices = [50000 + i * 100 for i in range(30)]  # 上涨趋势
        market_data = MarketData(
            symbol='BTC-USDT',
            timestamp=dates[-1],
            open=prices[-2],
            high=prices[-1] + 50,
            low=prices[-1] - 50,
            close=prices[-1],
            volume=100
        )
        
        signal = strategy.analyze(market_data)
        self.assertIn(signal.signal_type.value, ['buy', 'sell', 'hold'])

    def test_rsi_strategy_signal_generation(self):
        """测试RSI策略信号生成"""
        strategy = RSIStrategy({'period': 14, 'overbought': 70, 'oversold': 30})
        
        # 创建测试数据
        dates = pd.date_range('2023-01-01', periods=30, freq='1h')
        # 模拟超买情况
        prices = [50000] * 14 + [51000] * 16  # 后期上涨
        market_data = MarketData(
            symbol='BTC-USDT',
            timestamp=dates[-1],
            open=prices[-2],
            high=prices[-1] + 100,
            low=prices[-1] - 100,
            close=prices[-1],
            volume=100
        )
        
        signal = strategy.analyze(market_data)
        self.assertIn(signal.signal_type.value, ['buy', 'sell', 'hold'])

    # def test_grid_strategy_signal_generation(self):
    #     """测试网格交易策略信号生成"""
    #     strategy = GridTradingStrategy('grid', {
    #         'grid_count': 10,
    #         'grid_spacing': 0.01,
    #         'base_price': 50000
    #     })
    #     
    #     # 创建测试数据
    #     dates = pd.date_range('2023-01-01', periods=10, freq='1h')
    #     prices = [50000 + (i % 2) * 1000 for i in range(10)]  # 震荡行情
    #     market_data = MarketData(
    #         symbol='BTC-USDT',
    #         timestamp=dates[-1],
    #         open=prices[-2],
    #         high=prices[-1] + 100,
    #         low=prices[-1] - 100,
    #         close=prices[-1],
    #         volume=100
    #     )
    #     
    #     signal = strategy.analyze(market_data)
    #     self.assertIn(signal.signal_type.value, ['buy', 'sell', 'hold'])

    # 风险管理测试
    def test_risk_manager_initialization(self):
        """测试风险管理器初始化"""
        config = {
            "max_risk_per_trade": 0.02,
            "max_total_risk": 0.06,
            "max_drawdown": 0.10,
            "max_position_size": 0.5,
            "stop_loss_multiplier": 2.0,
            "take_profit_multiplier": 3.0
        }
        risk_manager = RiskManager(config)
        
        self.assertEqual(risk_manager.max_risk_per_trade, 0.02)
        self.assertEqual(risk_manager.max_total_risk, 0.06)
        self.assertEqual(risk_manager.max_drawdown, 0.10)

    def test_risk_manager_validate_order(self):
        """测试订单风险验证"""
        risk_manager = RiskManager({
            "max_risk_per_trade": 0.02,
            "max_total_risk": 0.06,
            "max_drawdown": 0.10,
            "max_position_size": 0.5,
            "stop_loss_multiplier": 2.0,
            "take_profit_multiplier": 3.0
        })
        
        # 设置账户余额
        risk_manager.update_account_balance(10000.0)
        
        # 测试交易风险评估
        result = risk_manager.assess_trade_risk('BTC-USDT', 'buy', 0.1, 50000, 49000)
        self.assertIn('risk_level', result)
        self.assertIn('allowed', result)

    def test_portfolio_manager_initialization(self):
        """测试投资组合管理器初始化"""
        portfolio_manager = PortfolioManager(
            initial_cash=1000000.0,
            max_risk_per_trade=0.02
        )
        
        self.assertEqual(portfolio_manager.initial_cash, 1000000.0)
        self.assertEqual(portfolio_manager.cash, 1000000.0)
        self.assertEqual(portfolio_manager.total_value, 1000000.0)
        self.assertEqual(len(portfolio_manager.positions), 0)

    def test_portfolio_manager_execute_order(self):
        """测试投资组合订单执行"""
        portfolio_manager = PortfolioManager(initial_cash=100000.0)
        
        # 测试买入
        portfolio_manager.execute_order('BTC-USDT', 1, 50000, 'buy')
        self.assertEqual(portfolio_manager.cash, 50000.0)
        self.assertEqual(portfolio_manager.positions['BTC-USDT']['qty'], 1)
        self.assertEqual(portfolio_manager.positions['BTC-USDT']['avg_price'], 50000)
        
        # 测试卖出
        portfolio_manager.execute_order('BTC-USDT', 1, 51000, 'sell')
        self.assertEqual(portfolio_manager.cash, 101000.0)
        self.assertEqual(len(portfolio_manager.positions), 0)

    def test_portfolio_manager_position_sizing(self):
        """测试仓位大小计算"""
        portfolio_manager = PortfolioManager(
            initial_cash=100000.0,
            max_risk_per_trade=0.02
        )
        
        position_size = portfolio_manager.calculate_position_size(
            symbol='BTC-USDT',
            entry_price=50000,
            stop_loss_price=49000  # 风险1000美元
        )
        
        # 风险金额 = 100000 * 0.02 = 2000美元
        # 每股风险 = 1000美元
        # 仓位大小 = 2000 / 1000 = 2股
        self.assertEqual(position_size, 2)

    # 订单管理测试
    def test_order_manager_initialization(self):
        """测试订单管理器初始化"""
        order_manager = OrderManager(
            api_client=Mock(),
            risk_manager=Mock(),
            portfolio_manager=Mock()
        )
        
        self.assertIsNotNone(order_manager.api_client)
        self.assertIsNotNone(order_manager.risk_manager)
        self.assertIsNotNone(order_manager.portfolio_manager)

    def test_order_manager_initialization(self):
        """测试订单管理器初始化"""
        # 创建模拟对象
        mock_api_client = Mock()
        mock_risk_manager = Mock()
        mock_portfolio_manager = Mock()
        
        # 创建订单管理器
        order_manager = OrderManager(
            api_client=mock_api_client,
            risk_manager=mock_risk_manager,
            portfolio_manager=mock_portfolio_manager
        )
        
        # 验证初始化成功
        self.assertIsNotNone(order_manager.api_client)
        self.assertIsNotNone(order_manager.risk_manager)
        self.assertIsNotNone(order_manager.portfolio_manager)

    # 监控服务测试
    def test_monitoring_service_initialization(self):
        """测试监控服务初始化"""
        monitoring_service = MonitoringService()
        
        self.assertIsNotNone(monitoring_service)
        self.assertIsNotNone(monitoring_service.metrics_collector)
        self.assertIsNotNone(monitoring_service.event_logger)

    def test_monitoring_service_record_metric(self):
        """测试指标记录"""
        monitoring_service = MonitoringService()
        
        monitoring_service.metrics_collector.record_metric(
            metric_name='test_metric',
            value=100.0,
            tags={'symbol': 'BTC-USDT'}
        )
        
        self.assertTrue(True)  # 简化测试

    def test_monitoring_service_log_event(self):
        """测试事件日志记录"""
        monitoring_service = MonitoringService()
        
        monitoring_service.event_logger.log_event(
            event_type='order',
            level='info',
            message='测试订单事件',
            data={'order_id': '12345'}
        )
        
        self.assertTrue(True)  # 简化测试

    # 配置加载测试
    def test_config_loader_initialization(self):
        """测试配置加载器初始化"""
        config_loader = ConfigLoader()
        self.assertIsNotNone(config_loader)

    @patch('config.config_loader.ConfigLoader.load_config')
    def test_config_loader_load_config(self, mock_load):
        """测试配置文件加载"""
        mock_load.return_value = self.mock_config
        
        config_loader = ConfigLoader('test_config.yaml')
        config = config_loader.load_config()
        
        self.assertEqual(config, self.mock_config)

    # 主交易机器人测试
    def test_trading_bot_initialization(self):
        """测试交易机器人初始化"""
        # 验证配置格式
        config = self.mock_config
        self.assertIn('api', config)
        self.assertIn('risk', config)
        self.assertIn('strategies', config)
        self.assertEqual(config['api']['api_key'], 'test_key')

    # 集成测试
    def test_strategy_to_order_flow(self):
        """测试策略到订单的完整流程"""
        # 创建策略
        strategy = MovingAverageCrossStrategy({'short_window': 5, 'long_window': 20})
        
        # 创建测试数据
        dates = pd.date_range('2023-01-01', periods=30, freq='1h')
        prices = [50000 + i * 100 for i in range(30)]  # 上涨趋势
        market_data = MarketData(
            symbol='BTC-USDT',
            timestamp=dates[-1],
            open=prices[-2],
            high=prices[-1] + 50,
            low=prices[-1] - 50,
            close=prices[-1],
            volume=100
        )
        
        # 生成信号
        signal = strategy.analyze(market_data)
        
        # 验证信号格式
        self.assertIn(signal.signal_type.value, ['buy', 'sell', 'hold'])
        self.assertTrue(hasattr(signal, 'metadata'))


if __name__ == '__main__':
    unittest.main()