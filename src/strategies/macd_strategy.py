"""
MACD策略
基于DIF/DEA(信号线)的交叉与柱体变化
"""

from typing import Dict, Any, List
from datetime import datetime
from loguru import logger
import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType, MarketData, calculate_macd


class MACDStrategy(BaseStrategy):
    """MACD策略"""

    def __init__(self, parameters: Dict[str, Any] = None):
        """
        参数:
            fast: 快线EMA周期（默认12）
            slow: 慢线EMA周期（默认26）
            signal: 信号线周期（默认9）
            min_confidence: 最小置信度（默认0.6）
            stop_loss: 止损比例（默认：0.02）
            take_profit: 止盈比例（默认：0.04）
        """
        default_params = {
            "fast": 12,
            "slow": 26,
            "signal": 9,
            "min_confidence": 0.6,
            "stop_loss": 0.02,
            "take_profit": 0.04,
        }
        if parameters:
            default_params.update(parameters)

        super().__init__("MACD", default_params)
        self.close_history: List[float] = []
        self.max_history_size = 500
        self.last_macd = 0.0
        self.last_signal = 0.0
        self.last_hist = 0.0

    def validate_parameters(self) -> bool:
        try:
            fast = self.parameters["fast"]
            slow = self.parameters["slow"]
            signal = self.parameters["signal"]
            if not (fast > 0 and slow > 0 and signal > 0):
                logger.error("MACD周期必须大于0")
                return False
            if fast >= slow:
                logger.error("MACD快线周期必须小于慢线周期")
                return False
            return True
        except KeyError as e:
            logger.error(f"缺少必要参数: {e}")
            return False
        except Exception as e:
            logger.error(f"参数验证失败: {e}")
            return False

    def analyze(self, market_data: MarketData) -> Signal:
        if not self.is_active:
            return Signal(market_data.symbol, SignalType.HOLD, market_data.close, 0.0, datetime.now())

        # 更新历史
        self.close_history.append(market_data.close)
        if len(self.close_history) > self.max_history_size:
            self.close_history.pop(0)

        # 确保有足够的数据
        min_len = max(self.parameters["slow"], self.parameters["signal"]) + 3
        if len(self.close_history) < min_len:
            return Signal(market_data.symbol, SignalType.HOLD, market_data.close, 0.0, datetime.now())

        # 计算MACD
        prices = pd.Series(self.close_history)
        macd_vals = calculate_macd(prices, self.parameters["fast"], self.parameters["slow"], self.parameters["signal"])
        macd_line = float(macd_vals["macd"].iloc[-1])
        signal_line = float(macd_vals["signal"].iloc[-1])
        hist = float(macd_vals["histogram"].iloc[-1])

        # 生成信号：DIF上穿DEA买入，下穿卖出；柱体由负转正/由正转负辅助
        signal_type = SignalType.HOLD
        confidence = 0.0
        metadata = {
            "macd": macd_line,
            "signal": signal_line,
            "hist": hist,
            "price": market_data.close,
        }

        if self.last_macd <= self.last_signal and macd_line > signal_line:
            signal_type = SignalType.BUY
            confidence = self._calc_confidence(macd_line, signal_line, hist, "BUY")
        elif self.last_macd >= self.last_signal and macd_line < signal_line:
            signal_type = SignalType.SELL
            confidence = self._calc_confidence(macd_line, signal_line, hist, "SELL")

        # 止损止盈
        if self.position != 0:
            stop_signal = self._check_stop_loss_take_profit(market_data.close)
            if stop_signal != SignalType.HOLD:
                signal_type = stop_signal
                confidence = 1.0
                metadata["stop_trigger"] = True

        # 更新缓存
        self.last_macd = macd_line
        self.last_signal = signal_line
        self.last_hist = hist

        return Signal(
            symbol=market_data.symbol,
            signal_type=signal_type,
            price=market_data.close,
            confidence=confidence,
            timestamp=datetime.now(),
            metadata=metadata,
        )

    def _calc_confidence(self, macd: float, signal: float, hist: float, side: str) -> float:
        base = self.parameters["min_confidence"]
        cross_strength = abs(macd - signal)
        hist_factor = min(abs(hist), 1.0)
        confidence = base * (1 + min(cross_strength, 1.0)) * (1 + 0.3 * hist_factor)
        return min(confidence, 1.0)

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update({
            "last_macd": self.last_macd,
            "last_signal": self.last_signal,
            "last_hist": self.last_hist,
            "history_len": len(self.close_history),
        })
        return status