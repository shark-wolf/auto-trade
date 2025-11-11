class PortfolioManager:
    """
    投资组合风险管理器
    负责仓位控制、风险度量和动态调仓
    """

    def __init__(self, initial_cash: float = 1_000_000.0, max_risk_per_trade: float = 0.02):
        """
        初始化投资组合管理器

        :param initial_cash: 初始资金
        :param max_risk_per_trade: 单笔交易最大风险（占净值比例）
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions = {}  # 持仓字典: {symbol: {'qty': 数量, 'avg_price': 均价}}
        self.max_risk_per_trade = max_risk_per_trade
        self.total_value = initial_cash

    def update_price(self, symbol: str, current_price: float):
        """
        更新某只标的的最新价格，用于计算总市值

        :param symbol: 标的代码
        :param current_price: 当前价格
        """
        if symbol in self.positions:
            self.positions[symbol]['last_price'] = current_price
        self._recalculate_total_value()

    def _recalculate_total_value(self):
        """重新计算组合总市值"""
        holdings_value = 0.0
        for sym, info in self.positions.items():
            qty = info['qty']
            price = info.get('last_price', info['avg_price'])
            holdings_value += qty * price
        self.total_value = self.cash + holdings_value

    def calculate_position_size(self, symbol: str, entry_price: float, stop_loss_price: float) -> int:
        """
        根据凯利公式或固定风险比例计算开仓数量

        :param symbol: 标的代码
        :param entry_price: 入场价格
        :param stop_loss_price: 止损价格
        :return: 可开仓数量（股）
        """
        risk_per_share = abs(entry_price - stop_loss_price)
        if risk_per_share <= 0:
            return 0
        risk_amount = self.total_value * self.max_risk_per_trade
        size = int(risk_amount / risk_per_share)
        # 不超过可用资金
        max_size = int(self.cash / entry_price)
        return min(size, max_size)

    def execute_order(self, symbol: str, qty: int, price: float, side: str):
        """
        执行买卖订单并更新持仓和现金

        :param symbol: 标的代码
        :param qty: 数量
        :param price: 成交价格
        :param side: 'buy' 或 'sell'
        """
        if side == 'buy':
            cost = qty * price
            if cost > self.cash:
                raise ValueError("现金不足，无法买入")
            self.cash -= cost
            if symbol in self.positions:
                old_qty = self.positions[symbol]['qty']
                old_avg = self.positions[symbol]['avg_price']
                new_qty = old_qty + qty
                new_avg = (old_qty * old_avg + qty * price) / new_qty
                self.positions[symbol] = {'qty': new_qty, 'avg_price': new_avg}
            else:
                self.positions[symbol] = {'qty': qty, 'avg_price': price}
        elif side == 'sell':
            if symbol not in self.positions or self.positions[symbol]['qty'] < qty:
                raise ValueError("持仓不足，无法卖出")
            self.positions[symbol]['qty'] -= qty
            self.cash += qty * price
            if self.positions[symbol]['qty'] == 0:
                del self.positions[symbol]
        else:
            raise ValueError("side 只能是 'buy' 或 'sell'")
        self._recalculate_total_value()

    def get_portfolio_risk(self) -> dict:
        """
        返回当前组合风险指标

        :return: 包含多个风险指标的字典
        """
        if self.total_value <= 0:
            return {'exposure': 0, 'cash_ratio': 1.0, 'position_count': 0}
        holdings_value = self.total_value - self.cash
        exposure = holdings_value / self.total_value
        cash_ratio = self.cash / self.total_value
        return {
            'exposure': exposure,
            'cash_ratio': cash_ratio,
            'position_count': len(self.positions),
            'total_value': self.total_value,
            'initial_cash': self.initial_cash,
            'pnl': self.total_value - self.initial_cash,
            'pnl_ratio': (self.total_value - self.initial_cash) / self.initial_cash
        }

    def rebalance(self, target_weights: dict, current_prices: dict):
        """
        根据目标权重进行再平衡

        :param target_weights: 目标权重字典 {symbol: 权重}
        :param current_prices: 当前价格字典 {symbol: 价格}
        """
        # 计算目标市值
        target_values = {sym: self.total_value * w for sym, w in target_weights.items()}
        orders = []
        for sym, tgt_val in target_values.items():
            price = current_prices.get(sym, 0)
            if price <= 0:
                continue
            tgt_qty = int(tgt_val / price)
            if sym in self.positions:
                current_qty = self.positions[sym]['qty']
            else:
                current_qty = 0
            delta = tgt_qty - current_qty
            if delta > 0:
                orders.append({'symbol': sym, 'qty': delta, 'side': 'buy', 'price': price})
            elif delta < 0:
                orders.append({'symbol': sym, 'qty': -delta, 'side': 'sell', 'price': price})
        # 执行订单
        for o in orders:
            self.execute_order(o['symbol'], o['qty'], o['price'], o['side'])

    def get_status(self) -> dict:
        """
        返回资金与持仓的快照，用于监控展示

        :return: 包含现金、总资产、风险敞口和详细持仓的字典
        """
        # 确保总市值为最新
        self._recalculate_total_value()

        holdings_value = self.total_value - self.cash
        risk = self.get_portfolio_risk()

        positions_list = []
        for sym, info in self.positions.items():
            qty = int(info.get('qty', 0))
            avg_price = float(info.get('avg_price', 0.0))
            last_price = float(info.get('last_price', avg_price))
            value = qty * last_price
            unrealized_pnl = (last_price - avg_price) * qty
            unrealized_pnl_ratio = (last_price - avg_price) / avg_price if avg_price > 0 else 0.0

            positions_list.append({
                'symbol': sym,
                'qty': qty,
                'avg_price': avg_price,
                'last_price': last_price,
                'value': value,
                'unrealized_pnl': unrealized_pnl,
                'unrealized_pnl_ratio': unrealized_pnl_ratio
            })

        return {
            'cash': float(self.cash),
            'holdings_value': float(holdings_value),
            'total_value': float(self.total_value),
            'initial_cash': float(self.initial_cash),
            'pnl': float(self.total_value - self.initial_cash),
            'pnl_ratio': float((self.total_value - self.initial_cash) / self.initial_cash) if self.initial_cash > 0 else 0.0,
            'exposure': float(risk.get('exposure', 0.0)),
            'cash_ratio': float(risk.get('cash_ratio', 0.0)),
            'position_count': int(risk.get('position_count', 0)),
            'positions': positions_list
        }
