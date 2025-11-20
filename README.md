# 自动交易平台（OKX/CCXT，含监控面板）

一个基于 CCXT 异步接口与合并策略（KDJ+MACD）的自动交易机器人，内置本地监控面板与 WebSocket 推送，支持交易对管理（添加/激活/删除）、风险与组合管理、订单执行与状态追踪。已适配开发模式完整 WS 数据输出，便于调试。

## 特性
- CCXT 异步行情/下单，支持 OKX（默认）与多交易所
- 合并策略 KDJ+MACD：同向共振才买入/卖出；止损/止盈优先
- 交易对管理：弹窗滚动列表添加、灰星点击激活、红星显示已激活、删除交易对；系统使用激活的交易对进行交易
- 监控面板：本地 HTML 仪表板，分卡片增量刷新，不整页刷新
- 开发模式：后端控制台格式化打印所有 WS 下发数据
- 关闭资源：在停止时显式关闭 CCXT/OKX 连接（`await exchange.close()`）

## 目录结构
- `main.py` 入口与主流程（启动/停止/交易循环/监控循环/CCXT轮询）
- `src/api/ccxt_client.py` CCXT 异步客户端适配（行情、下单、撤单、查单、关闭）
- `src/strategies/kdj_macd_strategy.py` 合并策略实现（KDJ+MACD 共振）
- `src/execution/order_manager.py` 订单创建、提交、取消、监控
- `src/risk/portfolio_manager.py` 组合管理（资金、持仓、再平衡）
- `src/risk/risk_manager.py` 风险指标与约束（单笔/总风险、回撤等）
- `src/monitoring/monitoring.py` 监控后端（SQLite、WS 服务、消息路由、开发日志）
- `src/monitoring/dashboard.html` 监控面板（交易对管理、指标卡片、策略状态等）


## 快速开始（Windows）
- 安装依赖
  - `python -m venv .venv`
  - `.\.venv\Scripts\pip install -r requirements.txt`
- 配置环境变量
  - 复制 `.env.example` 为 `.env`，根据需要修改（如 `DEV_MODE=true`）
- 启动
  - `.\.venv\Scripts\python .\run.py`
- 访问监控面板
  - 仪表板：`http://localhost:8000/dashboard.html`
  - WebSocket：`ws://127.0.0.1:8765`

## 运行与控制
- 开始/停止
  - 仪表板顶部按钮：开始自动交易、停止自动交易
  - 停止为“暂停交易”：不退出系统；取消未成交订单并尝试平掉持仓；不再发起新订单
- 周期选择
  - 顶部控制区下拉选择；成功后会更新 `当前周期` 显示
- 交易对管理
  - 顶部“⚑ 设置交易对”：弹出框内滚动列表展示交易对
  - 输入框与“添加”同一行；添加后持久化并刷新列表
  - 灰色星星点击激活，红色星星为当前激活；仅允许单一激活；激活项置顶显示
  - 删除按钮（“-”）移除该交易对
  - 顶部显示“当前交易对”，与卡片最左边对齐
- 凭据管理
  - “编辑凭据”弹出框：读取/编辑当前交易所凭据；激活交易所仅一个

## 策略逻辑（KDJ+MACD）
- KDJ 与 MACD 在同一确认收盘时同向（BUY/SELL）才发出交易信号
- 止损/止盈优先于共振逻辑（触发即平仓）
- 下单方向：BUY → 市价买入；SELL → 市价卖出
- 订单数量：`position_size / current_price`（从配置读取 `position_size`）

## 开发模式（建议本地启用）
- `.env` 设置 `DEV_MODE=true`
- 后端 `monitoring.py` 在所有下发 WS 数据时打印格式化 JSON（含客户端地址），便于联调与排错

## 资源释放
- 在停止时显式关闭 CCXT 异步客户端，确保 OKX 等连接正确释放
- 在 `main.py` 的停止流程中调用：`await self.api_client.close()` / `await self.ccxt_public.close()`

## 注意事项
- 请不要在生产环境中启用 `DEV_MODE=true`，以避免日志输出包含敏感数据
- 使用 OKX 需要正确的 `apiKey/secret/passphrase`，并根据需要配置 `options.defaultType='swap'` 或其他类型
- 仅合约交易对（如 `BTC-USDT-SWAP`）会用于交易；确保已激活的交易对与账户类型匹配

## 常见问题
- 面板显示“未连接监控服务”
  - 检查 WS 端口与主机（默认 `ws://127.0.0.1:8765`）
- 无法下单或报“无法获取当前价格”
  - 检查 CCXT 轮询是否正常、交易对是否激活、行情是否有最新价
- 停止后资源未释放
  - 确认 `CCXTClient.close()` 已调用；日志应显示“交易机器人已停止”

## 许可证
- 本项目仅用于学习与研究目的，风险自负。