"""
风险模型定义
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PositionSide(Enum):
    """持仓方向"""
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    def update_price(self, new_price: float):
        """更新当前价格"""
        self.current_price = new_price
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (new_price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - new_price) * self.size


@dataclass 
class TradeRecord:
    """交易记录"""
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    exit_price: float
    entry_time: str
    exit_time: str
    pnl: float
    commission: float = 0.0
    
    @property
    def net_pnl(self) -> float:
        """净收益"""
        return self.pnl - self.commission