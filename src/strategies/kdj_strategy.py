"""
KDJ随机指标策略
基于K、D、J的交叉与极值信号
"""

from typing import Dict, Any, List
from datetime import datetime
from loguru import logger
import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType, MarketData


class KDJStrategy(BaseStrategy):
    """KDJ随机指标策略"""

    def __init__(self, parameters: Dict[str, Any] = None):
        """
        初始化策略

        参数:
            period: RSV计算周期（默认：9）
            k_smooth: K平滑系数（默认：3）
            d_smooth: D平滑系数（默认：3）
            oversold: 超卖阈值（默认：20）
            overbought: 超买阈值（默认：80）
            min_confidence: 最小置信度（默认：0.6）
            stop_loss: 止损比例（默认：0.02）
            take_profit: 止盈比例（默认：0.04）
        """
        default_params = {
            "period": 9,
            "k_smooth": 3,
            "d_smooth": 3,
            "oversold": 20,
            "overbought": 80,
            "min_confidence": 0.6,
            "stop_loss": 0.02,
            "take_profit": 0.04,
        }

        if parameters:
            default_params.update(parameters)

        super().__init__("KDJ", default_params)
        self.close_history: List[float] = []
        self.high_history: List[float] = []
        self.low_history: List[float] = []
        self.max_history_size = 300

        # K/D初始值（常用为50）
        self.prev_k = 50.0
        self.prev_d = 50.0

        self.last_k = 50.0
        self.last_d = 50.0
        self.last_j = 50.0

    def validate_parameters(self) -> bool:
        try:
            period = self.parameters["period"]
            if period <= 0:
                logger.error("KDJ周期必须大于0")
                return False
            if not (0 < self.parameters["oversold"] < self.parameters["overbought"] <= 100):
                logger.error("KDJ阈值设置错误")
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

    def _update_history(self, md: MarketData):
        self.close_history.append(md.close)
        self.high_history.append(md.high)
        self.low_history.append(md.low)
        if len(self.close_history) > self.max_history_size:
            self.close_history.pop(0)
            self.high_history.pop(0)
            self.low_history.pop(0)

    def _compute_kdj(self) -> Dict[str, float]:
        period = self.parameters["period"]
        if len(self.close_history) < period:
            return {"k": self.prev_k, "d": self.prev_d, "j": 3 * self.prev_k - 2 * self.prev_d}

        closes = pd.Series(self.close_history)
        highs = pd.Series(self.high_history)
        lows = pd.Series(self.low_history)

        ll = lows.iloc[-period:].min()
        hh = highs.iloc[-period:].max()
        rsv = 0.0 if hh == ll else (closes.iloc[-1] - ll) / (hh - ll) * 100.0

        # 平滑(SMA)方式: K_t = (2/3)*K_{t-1} + (1/3)*RSV; D_t = (2/3)*D_{t-1} + (1/3)*K_t
        k = (2.0 / 3) * self.prev_k + (1.0 / 3) * rsv
        d = (2.0 / 3) * self.prev_d + (1.0 / 3) * k
        j = 3 * k - 2 * d

        return {"k": k, "d": d, "j": j, "rsv": rsv}

    def analyze(self, market_data: MarketData) -> Signal:
        if not self.is_active:
            return Signal(market_data.symbol, SignalType.HOLD, market_data.close, 0.0, datetime.now())

        # 更新历史
        self._update_history(market_data)

        # 计算KDJ
        vals = self._compute_kdj()
        k, d, j = vals["k"], vals["d"], vals["j"]

        # 生成信号
        signal_type = SignalType.HOLD
        confidence = 0.0
        metadata = {"k": k, "d": d, "j": j, "rsv": vals.get("rsv", 0.0), "price": market_data.close}

        # 交叉信号：K上穿D买入，K下穿D卖出；结合超买超卖过滤
        if self.last_k <= self.last_d and k > d and k < self.parameters["overbought"]:
            signal_type = SignalType.BUY
            confidence = self._calc_confidence(k, d, j, "BUY")
        elif self.last_k >= self.last_d and k < d and k > self.parameters["oversold"]:
            signal_type = SignalType.SELL
            confidence = self._calc_confidence(k, d, j, "SELL")

        # 极值辅助：J过度上行/下行作风险提示
        # 持仓止损止盈
        if self.position != 0:
            stop_signal = self._check_stop_loss_take_profit(market_data.close)
            if stop_signal != SignalType.HOLD:
                signal_type = stop_signal
                confidence = 1.0
                metadata["stop_trigger"] = True

        # 更新最近值
        self.prev_k = k
        self.prev_d = d
        self.last_k = k
        self.last_d = d
        self.last_j = j

        return Signal(
            symbol=market_data.symbol,
            signal_type=signal_type,
            price=market_data.close,
            confidence=confidence,
            timestamp=datetime.now(),
            metadata=metadata,
        )

    def _calc_confidence(self, k: float, d: float, j: float, side: str) -> float:
        base = self.parameters["min_confidence"]
        # K-D差距越大，置信度越高；J接近极值降低置信度
        kd_gap = abs(k - d) / 100.0
        j_penalty = max(0.0, (abs(j - 50.0) / 50.0) * 0.3)
        confidence = base * (1 + kd_gap) * (1 - j_penalty)
        return min(max(confidence, 0.0), 1.0)

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update({
            "last_k": self.last_k,
            "last_d": self.last_d,
            "last_j": self.last_j,
            "history_len": len(self.close_history),
        })
        return status