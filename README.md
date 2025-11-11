# Auto Trade (OKX 模拟盘 / 永续合约)

一个支持 OKX 模拟交易的自动化交易机器人，内置策略框架、风险管理与监控面板。已适配永续合约（`-SWAP`），提供异步下单接口与系统指标推送。

**主要特性**
- 支持 OKX 模拟交易（`OKX_TESTNET=true`），REST 与 WebSocket。
- 适配永续合约：当 `instId` 以 `-SWAP` 结尾时自动使用 `tdMode=cross`。
- 异步交易接口：下单、撤单、订单状态查询均提供 `await` 版本。
- 策略框架：`ma_cross`、`rsi`、`grid` 等示例策略，可按需启用。
- 风险与监控：系统资源、交易与风险指标通过 WebSocket 推送到监控面板。

**目录结构**
- `src/api/`：OKX 客户端（REST 与 WebSocket）。
- `src/strategies/`：策略实现与基类。
- `src/execution/order_manager.py`：订单管理与异步执行。
- `src/risk/`：风险与投资组合管理。
- `src/monitoring/`：监控服务与 `dashboard.html` 前端页面。
- `tests/`：连通性与基本功能测试脚本。

**环境准备**
- Python 3.11+，建议使用虚拟环境。
- 安装依赖：`pip install -r requirements.txt`
- 本项目已提供 `.gitignore`，会忽略本地缓存、日志、数据库与 `.env`。

**配置说明（.env）**
- 需在 `.env` 中配置模拟盘密钥：
  - `OKX_API_KEY=...`
  - `OKX_SECRET_KEY=...`
  - `OKX_PASSPHRASE=...`
  - `OKX_TESTNET=true`
- 交易标的：
  - `TRADING_SYMBOL=BTC-USDT-SWAP`（默认已切换为永续合约）
- 启用策略：
  - `ENABLED_STRATEGIES=ma_cross,rsi,grid`
- 风险参数（示例）：
  - `MAX_DAILY_LOSS=...`（在 `main.py` 中会读取并注入监控数据）

注意：`.env` 含敏感信息，不要提交到仓库。你可以参考 `.env.example`。

**OKX 模拟盘连通性测试**
- 运行脚本：`python tests/okx_sim_test.py`
- 脚本会执行：
  - 余额查询（私有接口）
  - 行情查询（公共接口）
  - 下发市价测试单（`symbol=BTC-USDT-SWAP`，`side=buy`，`ordType=market`）
  - 查询挂单并撤单
- 若出现 `401 Unauthorized`：检查 `API_KEY/SECRET/PASSPHRASE` 是否正确、是否为模拟环境密钥、权限是否包含交易与读取、是否存在 IP 白名单限制。

**运行机器人**
- 启动：`python run.py`（或 `python main.py`，视你的入口而定）
- 确保 `.env` 已配置且 `OKX_TESTNET=true`。
- 默认交易标的为 `BTC-USDT-SWAP`，策略启用列表来自 `.env`。

**监控面板**
- 启动本地服务：在 `src/monitoring` 目录运行 `python -m http.server 8000`
- 打开：`http://localhost:8000/dashboard.html`
- 后端会每 5 秒推送一次系统与交易指标，包括：
  - 系统状态：`cpu_percent`、`memory_percent`、`connections`
  - 交易指标：成交量、胜率、平均盈亏等（无交易时可能为 0）
  - 风险指标：`daily_loss_limit`（来自 `.env`）等

**策略说明**
- `ma_cross_strategy.py`：均线金叉/死叉示例。
- `rsi_strategy.py`：RSI 超买超卖示例。
- `grid_strategy.py`：网格交易示例（合约上使用请谨慎，关注持仓模式与 `reduceOnly` 需求）。
- 在 `.env` 中通过 `ENABLED_STRATEGIES` 控制启用列表。

**永续合约要点**
- 账户持仓模式：
  - 单向（Net）模式下无需 `posSide`。
  - 双向（Hedge）模式需指定 `posSide=long|short`。如需支持请在下单调用中补充，我们可快速添加。
- 平仓控制：如需显式平仓，建议使用 `reduceOnly=true`。目前接口未暴露该字段，如有需求请提出。

**常见问题**
- 私有接口 `401 Unauthorized`：优先检查密钥与权限；确保为模拟盘密钥；必要时关闭 IP 白名单测试。
- 监控数据为 0：在无交易或 demo 模式下部分指标为默认值，正常。
- `.env` 未生效：确认在运行目录存在 `.env`，或使用 `python-dotenv` 已加载。

**测试与开发**
- 运行基本测试：`pytest -q`（若你安装了 `pytest`）
- 连通性测试：`python tests/okx_sim_test.py`

**安全与合规**
- 不要将 `.env`、日志或本地数据库提交到仓库。
- 本项目的示例策略与风险参数仅用于演示，真实交易前请进行充分回测与风控评估。

**贡献**
- 欢迎提交 Issue/PR，或反馈你希望支持的交易参数（如 `posSide`、`reduceOnly`）、更多策略示例与监控指标。