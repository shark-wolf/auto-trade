"""
风险管理模块
提供风险评估、头寸管理、止损止盈等功能
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
from enum import Enum


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskMetrics:
    """风险指标"""
    max_drawdown: float
    volatility: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    risk_level: RiskLevel
    timestamp: datetime


@dataclass
class PositionRisk:
    """头寸风险"""
    symbol: str
    position_size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    risk_amount: float
    risk_percentage: float
    liquidation_price: Optional[float]
    risk_level: RiskLevel


class RiskManager:
    """风险管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化风险管理器
        
        参数:
            max_risk_per_trade: 每笔交易最大风险（默认：0.02，即2%）
            max_total_risk: 总风险上限（默认：0.06，即6%）
            max_drawdown: 最大回撤限制（默认：0.10，即10%）
            max_position_size: 最大头寸规模（默认：0.5，即50%账户资金）
            stop_loss_multiplier: 止损倍数（默认：2.0）
            take_profit_multiplier: 止盈倍数（默认：3.0）
        """
        self.config = config
        self.max_risk_per_trade = config.get("max_risk_per_trade", 0.02)
        self.max_total_risk = config.get("max_total_risk", 0.06)
        self.max_drawdown = config.get("max_drawdown", 0.10)
        self.max_position_size = config.get("max_position_size", 0.5)
        self.stop_loss_multiplier = config.get("stop_loss_multiplier", 2.0)
        self.take_profit_multiplier = config.get("take_profit_multiplier", 3.0)
        
        self.account_balance = 0.0
        self.total_risk = 0.0
        self.positions = {}
        self.trade_history = []
        self.daily_pnl = []
        self.max_balance = 0.0
        self.current_drawdown = 0.0
        
    def update_account_balance(self, balance: float):
        """更新账户余额"""
        self.account_balance = balance
        if balance > self.max_balance:
            self.max_balance = balance
        
        # 计算当前回撤
        if self.max_balance > 0:
            self.current_drawdown = (self.max_balance - balance) / self.max_balance
    
    def calculate_position_size(self, entry_price: float, stop_loss_price: float, 
                               confidence: float = 1.0) -> Tuple[float, float]:
        """
        计算头寸规模
        
        参数:
            entry_price: 入场价格
            stop_loss_price: 止损价格
            confidence: 置信度（0-1）
        
        返回:
            (position_size, risk_amount)
        """
        # 计算每笔交易的风险金额
        risk_per_trade = self.account_balance * self.max_risk_per_trade * confidence
        
        # 计算价格风险（止损距离）
        price_risk = abs(entry_price - stop_loss_price)
        
        if price_risk == 0:
            logger.warning("止损价格与入场价格相同，无法计算头寸规模")
            return 0.0, 0.0
        
        # 计算头寸规模
        position_size = risk_per_trade / price_risk
        
        # 检查总风险限制
        if self.total_risk + risk_per_trade > self.account_balance * self.max_total_risk:
            logger.warning("总风险超过限制，调整头寸规模")
            available_risk = self.account_balance * self.max_total_risk - self.total_risk
            if available_risk > 0:
                position_size = available_risk / price_risk
                risk_per_trade = available_risk
            else:
                position_size = 0.0
                risk_per_trade = 0.0
        
        # 检查最大头寸限制
        max_position_value = self.account_balance * self.max_position_size
        if position_size * entry_price > max_position_value:
            position_size = max_position_value / entry_price
            risk_per_trade = position_size * price_risk
        
        return position_size, risk_per_trade
    
    def assess_trade_risk(self, symbol: str, side: str, size: float, 
                         entry_price: float, stop_loss: float) -> Dict[str, Any]:
        """
        评估交易风险
        
        参数:
            symbol: 交易对
            side: 交易方向（buy/sell）
            size: 交易规模
            entry_price: 入场价格
            stop_loss: 止损价格
        
        返回:
            风险评估结果
        """
        # 计算风险金额
        price_risk = abs(entry_price - stop_loss)
        risk_amount = size * price_risk
        risk_percentage = risk_amount / self.account_balance
        
        # 评估风险等级
        if risk_percentage > self.max_risk_per_trade * 1.5:
            risk_level = RiskLevel.CRITICAL
        elif risk_percentage > self.max_risk_per_trade:
            risk_level = RiskLevel.HIGH
        elif risk_percentage > self.max_risk_per_trade * 0.5:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        # 检查回撤限制
        if self.current_drawdown > self.max_drawdown:
            risk_level = RiskLevel.CRITICAL
            logger.warning(f"当前回撤 {self.current_drawdown:.4f} 超过限制 {self.max_drawdown}")
        
        return {
            "risk_amount": risk_amount,
            "risk_percentage": risk_percentage,
            "risk_level": risk_level,
            "allowed": risk_level != RiskLevel.CRITICAL,
            "reason": self._get_risk_reason(risk_level, risk_percentage)
        }
    
    def add_position(self, symbol: str, side: str, size: float, 
                    entry_price: float, stop_loss: float, 
                    take_profit: float, liquidation_price: Optional[float] = None):
        """添加持仓"""
        # 计算风险
        price_risk = abs(entry_price - stop_loss)
        risk_amount = size * price_risk
        
        # 更新总风险
        self.total_risk += risk_amount
        
        # 保存持仓信息
        self.positions[symbol] = PositionRisk(
            symbol=symbol,
            position_size=size if side == "buy" else -size,
            entry_price=entry_price,
            current_price=entry_price,
            unrealized_pnl=0.0,
            risk_amount=risk_amount,
            risk_percentage=risk_amount / self.account_balance,
            liquidation_price=liquidation_price,
            risk_level=RiskLevel.MEDIUM
        )
        
        logger.info(f"添加持仓: {symbol} {side} {size} @ {entry_price}, 风险: {risk_amount:.4f}")
    
    def update_position(self, symbol: str, current_price: float):
        """更新持仓信息"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        position.current_price = current_price
        
        # 计算未实现盈亏
        if position.position_size > 0:  # 多头
            position.unrealized_pnl = (current_price - position.entry_price) * position.position_size
        else:  # 空头
            position.unrealized_pnl = (position.entry_price - current_price) * abs(position.position_size)
        
        # 更新风险等级
        risk_percentage = abs(position.risk_percentage)
        if risk_percentage > self.max_risk_per_trade * 1.5:
            position.risk_level = RiskLevel.CRITICAL
        elif risk_percentage > self.max_risk_per_trade:
            position.risk_level = RiskLevel.HIGH
        elif risk_percentage > self.max_risk_per_trade * 0.5:
            position.risk_level = RiskLevel.MEDIUM
        else:
            position.risk_level = RiskLevel.LOW
    
    def remove_position(self, symbol: str, exit_price: float, realized_pnl: float):
        """移除持仓"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        # 更新总风险
        self.total_risk -= position.risk_amount
        
        # 添加到交易历史
        self.trade_history.append({
            "symbol": symbol,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "position_size": position.position_size,
            "realized_pnl": realized_pnl,
            "timestamp": datetime.now()
        })
        
        # 更新每日盈亏
        self._update_daily_pnl(realized_pnl)
        
        # 删除持仓
        del self.positions[symbol]
        
        logger.info(f"移除持仓: {symbol}, 实现盈亏: {realized_pnl:.4f}")
    
    def _update_daily_pnl(self, pnl: float):
        """更新每日盈亏"""
        today = datetime.now().date()
        
        if not self.daily_pnl or self.daily_pnl[-1]["date"] != today:
            self.daily_pnl.append({
                "date": today,
                "pnl": pnl,
                "trades": 1
            })
        else:
            self.daily_pnl[-1]["pnl"] += pnl
            self.daily_pnl[-1]["trades"] += 1
    
    def calculate_risk_metrics(self) -> RiskMetrics:
        """计算风险指标"""
        if not self.daily_pnl:
            return RiskMetrics(
                max_drawdown=0.0,
                volatility=0.0,
                sharpe_ratio=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                risk_level=RiskLevel.LOW,
                timestamp=datetime.now()
            )
        
        # 计算最大回撤
        pnl_values = [day["pnl"] for day in self.daily_pnl]
        cumulative_pnl = np.cumsum(pnl_values)
        running_max = np.maximum.accumulate(cumulative_pnl)
        drawdown = (running_max - cumulative_pnl) / self.account_balance
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0.0
        
        # 计算波动率
        volatility = np.std(pnl_values) / self.account_balance if len(pnl_values) > 1 else 0.0
        
        # 计算夏普比率（假设无风险利率为0）
        avg_pnl = np.mean(pnl_values) if pnl_values else 0.0
        sharpe_ratio = avg_pnl / volatility if volatility > 0 else 0.0
        
        # 计算胜率
        winning_trades = sum(1 for pnl in pnl_values if pnl > 0)
        total_trades = len(pnl_values)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        
        # 计算盈亏比
        gross_profit = sum(pnl for pnl in pnl_values if pnl > 0)
        gross_loss = abs(sum(pnl for pnl in pnl_values if pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # 评估整体风险等级
        if max_drawdown > self.max_drawdown or volatility > 0.05:
            risk_level = RiskLevel.HIGH
        elif max_drawdown > self.max_drawdown * 0.5 or volatility > 0.02:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        return RiskMetrics(
            max_drawdown=max_drawdown,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            risk_level=risk_level,
            timestamp=datetime.now()
        )
    
    def get_position_risk(self, symbol: str) -> Optional[PositionRisk]:
        """获取持仓风险"""
        return self.positions.get(symbol)
    
    def get_all_positions_risk(self) -> List[PositionRisk]:
        """获取所有持仓风险"""
        return list(self.positions.values())
    
    def get_total_risk(self) -> float:
        """获取总风险"""
        return self.total_risk
    
    def get_risk_percentage(self) -> float:
        """获取风险百分比"""
        return self.total_risk / self.account_balance if self.account_balance > 0 else 0.0
    
    def should_stop_trading(self) -> Tuple[bool, str]:
        """判断是否应该停止交易"""
        # 检查回撤限制
        if self.current_drawdown > self.max_drawdown:
            return True, f"回撤超过限制: {self.current_drawdown:.4f} > {self.max_drawdown}"
        
        # 检查总风险限制
        if self.get_risk_percentage() > self.max_total_risk:
            return True, f"总风险超过限制: {self.get_risk_percentage():.4f} > {self.max_total_risk}"
        
        # 检查账户余额
        if self.account_balance <= 0:
            return True, "账户余额不足"
        
        return False, ""
    
    def _get_risk_reason(self, risk_level: RiskLevel, risk_percentage: float) -> str:
        """获取风险原因"""
        if risk_level == RiskLevel.CRITICAL:
            return f"风险过高: {risk_percentage:.4f}"
        elif risk_level == RiskLevel.HIGH:
            return f"风险较高: {risk_percentage:.4f}"
        elif risk_level == RiskLevel.MEDIUM:
            return f"风险适中: {risk_percentage:.4f}"
        else:
            return f"风险较低: {risk_percentage:.4f}"
    
    def get_status(self) -> Dict[str, Any]:
        """获取风险管理器状态"""
        risk_metrics = self.calculate_risk_metrics()
        should_stop, reason = self.should_stop_trading()
        
        return {
            "account_balance": self.account_balance,
            "total_risk": self.total_risk,
            "risk_percentage": self.get_risk_percentage(),
            "current_drawdown": self.current_drawdown,
            "max_drawdown": self.max_drawdown,
            "position_count": len(self.positions),
            "risk_metrics": {
                "max_drawdown": risk_metrics.max_drawdown,
                "volatility": risk_metrics.volatility,
                "sharpe_ratio": risk_metrics.sharpe_ratio,
                "win_rate": risk_metrics.win_rate,
                "profit_factor": risk_metrics.profit_factor,
                "risk_level": risk_metrics.risk_level.value
            },
            "should_stop_trading": should_stop,
            "stop_reason": reason,
            "trade_count": len(self.trade_history),
            "daily_trades": len(self.daily_pnl)
        }