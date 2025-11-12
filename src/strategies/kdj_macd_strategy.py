"""
KDJ+MACD 合并策略
在同一K线收盘时，只有当 KDJ 与 MACD 信号同向（BUY/SELL）时才发出交易信号。
"""

from typing import Dict, Any, List
from datetime import datetime
from loguru import logger
import pandas as pd
import numpy as np

from .base_strategy import BaseStrategy, Signal, SignalType, MarketData, calculate_macd
try:
    import talib
except Exception:
    talib = None


class KDJMACDStrategy(BaseStrategy):
    """
    KDJ 与 MACD 的联合策略

    参数结构：
      {
        "kdj": {"period": 9, "k_smooth": 3, "d_smooth": 3, "oversold": 20, "overbought": 80},
        "macd": {"fast": 5, "slow": 13, "signal": 4},
        "min_confidence": 0.55,
        "stop_loss": 0.02,
        "take_profit": 0.04
      }
    """

    def __init__(self, parameters: Dict[str, Any] = None):
        default_params = {
            "kdj": {
                "period": 9,
                "k_smooth": 3,
                "d_smooth": 3,
                "oversold": 20,
                "overbought": 80,
            },
            "macd": {
                "fast": 5,
                "slow": 13,
                "signal": 4,
            },
            "min_confidence": 0.55,
            "stop_loss": 0.02,
            "take_profit": 0.04,
        }
        if parameters:
            # 浅合并：允许外部传入覆盖子参数
            for k, v in parameters.items():
                if isinstance(v, dict) and k in default_params:
                    default_params[k].update(v)
                else:
                    default_params[k] = v

        super().__init__("KDJ_MACD", default_params)

        # 历史数据缓存
        self.close_history: List[float] = []
        self.high_history: List[float] = []
        self.low_history: List[float] = []
        self.max_history_size = 500

        # KDJ 最近值
        self.prev_k = 50.0
        self.prev_d = 50.0
        self.last_k = 50.0
        self.last_d = 50.0
        self.last_j = 50.0

        # MACD 最近值
        self.last_macd = 0.0
        self.last_signal_line = 0.0
        self.last_hist = 0.0

    def validate_parameters(self) -> bool:
        try:
            kdj = self.parameters.get("kdj", {})
            macd = self.parameters.get("macd", {})
            period = int(kdj.get("period", 9))
            if period <= 0:
                logger.error("KDJ周期必须大于0")
                return False
            oversold = float(kdj.get("oversold", 20))
            overbought = float(kdj.get("overbought", 80))
            if not (0 < oversold < overbought <= 100):
                logger.error("KDJ阈值设置错误")
                return False

            fast = int(macd.get("fast", 5))
            slow = int(macd.get("slow", 13))
            signal = int(macd.get("signal", 4))
            if not (fast > 0 and slow > 0 and signal > 0):
                logger.error("MACD周期必须大于0")
                return False
            if fast >= slow:
                logger.error("MACD快线周期必须小于慢线周期")
                return False

            if not 0 < float(self.parameters.get("stop_loss", 0.02)) < 1:
                logger.error("止损比例必须在0到1之间")
                return False
            if not 0 < float(self.parameters.get("take_profit", 0.04)) < 1:
                logger.error("止盈比例必须在0到1之间")
                return False

            return True
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
        kdj = self.parameters.get("kdj", {})
        period = int(kdj.get("period", 9))
        if len(self.close_history) < period:
            return {"k": self.prev_k, "d": self.prev_d, "j": 3 * self.prev_k - 2 * self.prev_d}

        closes = pd.Series(self.close_history)
        highs = pd.Series(self.high_history)
        lows = pd.Series(self.low_history)

        ll = lows.iloc[-period:].min()
        hh = highs.iloc[-period:].max()
        rsv = 0.0 if hh == ll else (closes.iloc[-1] - ll) / (hh - ll) * 100.0

        k_smooth = int(kdj.get("k_smooth", 3))
        d_smooth = int(kdj.get("d_smooth", 3))
        if talib is not None and len(closes) >= period + max(k_smooth, d_smooth):
            slowk, slowd = talib.STOCH(
                highs.values.astype(float),
                lows.values.astype(float),
                closes.values.astype(float),
                fastk_period=period,
                slowk_period=k_smooth,
                slowk_matype=0,
                slowd_period=d_smooth,
                slowd_matype=0,
            )
            k = float(slowk[-1]) if not np.isnan(slowk[-1]) else self.prev_k
            d = float(slowd[-1]) if not np.isnan(slowd[-1]) else self.prev_d
            j = 3 * k - 2 * d
            return {"k": k, "d": d, "j": j, "rsv": rsv}

        k = (2.0 / 3) * self.prev_k + (1.0 / 3) * rsv
        d = (2.0 / 3) * self.prev_d + (1.0 / 3) * k
        j = 3 * k - 2 * d
        return {"k": k, "d": d, "j": j, "rsv": rsv}

    def _kdj_signal(self, k: float, d: float, j: float) -> (SignalType, float):
        kdj_params = self.parameters.get("kdj", {})
        overbought = float(kdj_params.get("overbought", 80))
        oversold = float(kdj_params.get("oversold", 20))
        base = float(self.parameters.get("min_confidence", 0.55))

        st = SignalType.HOLD
        conf = 0.0
        if self.last_k <= self.last_d and k > d and k < overbought:
            st = SignalType.BUY
            conf = self._kdj_confidence(k, d, j, base)
        elif self.last_k >= self.last_d and k < d and k > oversold:
            st = SignalType.SELL
            conf = self._kdj_confidence(k, d, j, base)
        return st, conf

    def _kdj_confidence(self, k: float, d: float, j: float, base: float) -> float:
        kd_gap = abs(k - d) / 100.0
        j_penalty = max(0.0, (abs(j - 50.0) / 50.0) * 0.3)
        confidence = base * (1 + kd_gap) * (1 - j_penalty)
        return min(max(confidence, 0.0), 1.0)

    def _macd_signal(self, macd_line: float, signal_line: float, hist: float) -> (SignalType, float):
        base = float(self.parameters.get("min_confidence", 0.55))
        st = SignalType.HOLD
        conf = 0.0
        if self.last_macd <= self.last_signal_line and macd_line > signal_line:
            st = SignalType.BUY
            conf = self._macd_confidence(macd_line, signal_line, hist, base)
        elif self.last_macd >= self.last_signal_line and macd_line < signal_line:
            st = SignalType.SELL
            conf = self._macd_confidence(macd_line, signal_line, hist, base)
        return st, conf

    def _macd_confidence(self, macd: float, signal: float, hist: float, base: float) -> float:
        cross_strength = abs(macd - signal)
        hist_factor = min(abs(hist), 1.0)
        confidence = base * (1 + min(cross_strength, 1.0)) * (1 + 0.3 * hist_factor)
        return min(confidence, 1.0)

    def analyze(self, market_data: MarketData) -> Signal:
        if not self.is_active:
            return Signal(market_data.symbol, SignalType.HOLD, market_data.close, 0.0, datetime.now())

        # 更新历史
        self._update_history(market_data)

        # 计算KDJ
        kdj_vals = self._compute_kdj()
        k, d, j = kdj_vals["k"], kdj_vals["d"], kdj_vals["j"]

        # 计算MACD
        macd_params = self.parameters.get("macd", {})
        min_len = max(int(macd_params.get("slow", 13)), int(macd_params.get("signal", 4))) + 3
        if len(self.close_history) < min_len:
            return Signal(market_data.symbol, SignalType.HOLD, market_data.close, 0.0, datetime.now())
        prices = pd.Series(self.close_history)
        macd_vals = calculate_macd(prices, int(macd_params.get("fast", 5)), int(macd_params.get("slow", 13)), int(macd_params.get("signal", 4)))
        macd_line = float(macd_vals["macd"].iloc[-1])
        signal_line = float(macd_vals["signal"].iloc[-1])
        hist = float(macd_vals["histogram"].iloc[-1])

        # 各自信号
        kdj_st, kdj_conf = self._kdj_signal(k, d, j)
        macd_st, macd_conf = self._macd_signal(macd_line, signal_line, hist)

        # 止损止盈优先
        stop_signal = self._check_stop_loss_take_profit(market_data.close)
        if stop_signal != SignalType.HOLD:
            metadata = {
                "stop_trigger": True,
                "price": market_data.close,
                "kdj": {"k": k, "d": d, "j": j, "rsv": kdj_vals.get("rsv", 0.0)},
                "macd": {"macd": macd_line, "signal": signal_line, "hist": hist},
            }
            return Signal(
                symbol=market_data.symbol,
                signal_type=stop_signal,
                price=market_data.close,
                confidence=1.0,
                timestamp=datetime.now(),
                metadata=metadata,
            )

        # 联合判定：同向才触发
        if kdj_st != SignalType.HOLD and kdj_st == macd_st:
            conf = min(kdj_conf, macd_conf)
            metadata = {
                "kdj": {"k": k, "d": d, "j": j, "rsv": kdj_vals.get("rsv", 0.0)},
                "macd": {"macd": macd_line, "signal": signal_line, "hist": hist},
                "price": market_data.close,
            }
            # 更新最近值缓存
            self.prev_k = k
            self.prev_d = d
            self.last_k = k
            self.last_d = d
            self.last_j = j
            self.last_macd = macd_line
            self.last_signal_line = signal_line
            self.last_hist = hist

            return Signal(
                symbol=market_data.symbol,
                signal_type=kdj_st,
                price=market_data.close,
                confidence=conf,
                timestamp=datetime.now(),
                metadata=metadata,
            )

        # 更新最近值缓存并返回HOLD
        self.prev_k = k
        self.prev_d = d
        self.last_k = k
        self.last_d = d
        self.last_j = j
        self.last_macd = macd_line
        self.last_signal_line = signal_line
        self.last_hist = hist

        return Signal(market_data.symbol, SignalType.HOLD, market_data.close, 0.0, datetime.now())

    def _check_stop_loss_take_profit(self, current_price: float) -> SignalType:
        """检查止损止盈（参考RSI/MA策略实现）"""
        if self.position == 0 or self.entry_price == 0:
            return SignalType.HOLD

        if self.position > 0:  # 多头
            pnl_ratio = (current_price - self.entry_price) / self.entry_price
            if pnl_ratio <= -self.parameters["stop_loss"]:
                logger.info(f"多头止损触发: 盈亏比例 {pnl_ratio:.4f}")
                return SignalType.SELL
            if pnl_ratio >= self.parameters["take_profit"]:
                logger.info(f"多头止盈触发: 盈亏比例 {pnl_ratio:.4f}")
                return SignalType.SELL
        else:  # 空头
            pnl_ratio = (self.entry_price - current_price) / self.entry_price
            if pnl_ratio <= -self.parameters["stop_loss"]:
                logger.info(f"空头止损触发: 盈亏比例 {pnl_ratio:.4f}")
                return SignalType.BUY
            if pnl_ratio >= self.parameters["take_profit"]:
                logger.info(f"空头止盈触发: 盈亏比例 {pnl_ratio:.4f}")
                return SignalType.BUY

        return SignalType.HOLD

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update({
            "last_k": self.last_k,
            "last_d": self.last_d,
            "last_j": self.last_j,
            "last_macd": self.last_macd,
            "last_signal": self.last_signal_line,
            "last_hist": self.last_hist,
            "history_len": len(self.close_history),
        })
        return status
