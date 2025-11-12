## 目标
- 在仪表板周期选择器中动态展示后端提供的可用时间框架（如 1m/5m/15m/1h/4h等）。
- 周期选择与后端的策略配置中`timeframe`联动：后端作为唯一“当前使用周期”的来源。
- 用户修改周期后，立即生效并持久化到SQLite数据库，重启后仍保持该周期。

## 后端改造
### 1. 持久化层（SQLite）
- 在监控数据库`logs/monitoring.db`新增`settings`表：`key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP`。
- 读写接口：
  - `get_setting(key) -> Optional[str]`
  - `set_setting(key, value)`（更新`updated_at`为当前时间）。
- 关键键：`trading_timeframe`，值为字符串如`"1m"`、`"5m"`等。

### 2. 周期源统一
- 启动时后端加载周期优先级：`settings['trading_timeframe']` > 环境变量`TRADING_TIMEFRAME` > 策略配置默认`StrategyConfig.timeframe` > 最后回退`"1m"`。
- 主流程使用统一的`config["trading_timeframe"]`作为轮询与回测周期，避免重复来源冲突。

### 3. CCXT可用周期动态提供
- 在`CCXTClient`新增方法`available_timeframes()`：返回`exchange.timeframes`的键列表（如OKX的`['1m','5m','15m','1h',...]`）。
- 在交易机器人初始化完成后，将`timeframe_options`与当前周期一起放入`strategy_status`，供仪表板初始渲染。

### 4. WebSocket消息协议（监控服务）
- 增加消息类型：`{"type":"timeframe","timeframe":"5m"}`
- 处理流程：
  - 校验时间框架是否在`available_timeframes()`之中；不合法则返回`ack: error`。
  - 更新`config['trading_timeframe']`。
  - 写入SQLite：`settings['trading_timeframe']=...`。
  - 立即广播一次最新`strategy_status`（包含`timeframe`与`timeframe_options`）。

### 5. 与策略配置联动
- 若后续接入`ConfigLoader`：当`trading_timeframe`更新时，同步更新策略配置中的`timeframe`字段（仅用于显示/回溯），但主数据源仍为`config['trading_timeframe']`。

## 前端改造（dashboard.html）
### 1. 动态选项
- 初始连接后，读取`strategy_status.timeframe`与`strategy_status.timeframe_options`：
  - 使用`timeframe_options`填充下拉框选项。
  - 选中当前`timeframe`。

### 2. 交互与立即生效
- 下拉选择变化时，发送`{"type":"timeframe","timeframe": selected}`到后端。
- 收到`ack`成功后：
  - 更新顶部“当前周期”展示；
  - 下一轮数据推送将按新周期更新（价格/确认收盘K线/指标）。
- 若`ack: error`：弹出提示并恢复下拉到原值。

## 验证与回退
- 启动后检查：仪表板展示的选项与当前周期与你的交易所（CCXT-OKX）的`timeframes`一致。
- 切换多次周期，确保：
  - SQLite被更新（查询`settings`表）。
  - 轮询下一轮按新周期获取OHLCV（可从日志观察）。
  - 仪表板“当前周期”与趋势图标签随之刷新。
- 若监控数据库不可写：后端提示警告但仍临时更新周期（不持久化），下次启动回退到环境/配置默认。

## 兼容与边界
- 仅当`available_timeframes()`存在且包含目标周期时允许修改；否则拒绝并提示。
- 当切换到更长周期（如1h）时，趋势图的点位刷新力度变慢属正常。
- 在纯演示模式下（无密钥），周期切换仍对轮询与指标有效。

## 交付清单
- 后端：SQLite`settings`表及读写方法；CCXT可用周期收集；WebSocket`timeframe`消息处理；周期广播与主流程统一。
- 前端：周期选择器动态填充与`ack`处理；当前周期显示与乐观更新；错误提示。

请确认该方案，我将据此实施并验证。