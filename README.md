# OKX自动交易平台

一个功能完整的加密货币自动交易系统，基于OKX交易所API开发。

## 🚀 功能特性

### 核心功能
- ✅ **OKX API集成** - 完整的REST API和WebSocket支持
- ✅ **多种交易策略** - 均线交叉、RSI、网格交易等
- ✅ **风险管理** - 资金管理和风险控制
- ✅ **订单管理** - 完整的订单生命周期管理
- ✅ **实时监控** - 性能指标和事件日志
- ✅ **配置管理** - 灵活的策略配置系统

### 交易策略
- **均线交叉策略** - 基于移动平均线交叉信号
- **RSI策略** - 相对强弱指标交易策略
- **网格交易策略** - 自动化网格交易
- **MACD策略** - 指数平滑异同移动平均线
- **布林带策略** - 基于布林带指标
- **动量策略** - 基于价格动量

### 风险管理
- 资金管理和仓位控制
- 止损和止盈机制
- 最大日亏损限制
- 风险敞口监控
- 投资组合跟踪

### 监控功能
- 实时性能指标收集
- 事件日志记录
- WebSocket监控仪表板
- 系统健康检查
- 警报和通知

## 📦 安装

### 系统要求
- Python 3.8+
- Windows/Linux/macOS

### 安装步骤

1. **克隆项目**
```bash
git clone <项目地址>
cd auto_trade
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的OKX API密钥
```

4. **创建配置文件**
```bash
cp config_example.yaml config.yaml
# 根据需要修改策略配置
```

## 🚀 快速开始

### 基本使用
```bash
# 使用简化启动器
python run.py

# 或使用主程序
python main.py

# 指定配置文件
python main.py --config my_config.yaml

# 指定交易对
python main.py --symbol ETH-USDT

# 指定交易模式
python main.py --mode demo
```

### 命令行参数
```bash
python main.py --help

选项:
  -c, --config PATH    配置文件路径 (默认: .env)
  -s, --symbol TEXT   交易对 (如: BTC-USDT)
  -m, --mode TEXT     交易模式 (demo/live)
  -l, --log-level TEXT 日志级别 (DEBUG/INFO/WARNING/ERROR)
```

## ⚙️ 配置说明

### 环境变量配置 (.env)
```env
# OKX API配置
OKX_API_KEY=your_api_key
OKX_SECRET_KEY=your_secret_key
OKX_PASSPHRASE=your_passphrase
OKX_TESTNET=true

# 交易配置
TRADING_MODE=demo
TRADING_SYMBOL=BTC-USDT
POSITION_SIZE=0.01
MAX_POSITIONS=5

# 风险管理
MAX_DAILY_LOSS=100
MAX_POSITION_RATIO=0.3
STOP_LOSS_PCT=0.02
TAKE_PROFIT_PCT=0.05

# 策略配置
ENABLED_STRATEGIES=ma_cross,rsi,grid
```

### 策略配置 (config.yaml)
```yaml
global:
  symbol: "BTC-USDT"
  timeframe: "1h"
  max_positions: 3
  max_daily_loss: 100.0
  risk_per_trade: 0.01

strategies:
  - name: "均线交叉策略"
    strategy_type: "ma_cross"
    enabled: true
    position_size: 0.01
    stop_loss_pct: 0.02
    take_profit_pct: 0.05
    parameters:
      short_period: 10
      long_period: 30
      ma_type: "ema"

  - name: "RSI策略"
    strategy_type: "rsi"
    enabled: true
    position_size: 0.01
    parameters:
      period: 14
      overbought: 70
      oversold: 30
```

## 📊 监控仪表板

系统提供WebSocket监控仪表板，可以实时查看：
- 系统状态和性能指标
- 交易信号和订单状态
- 风险指标和警报
- 事件日志和错误信息

访问地址: `http://localhost:8765`

## 🛡️ 安全提示

1. **API密钥安全**
   - 不要在代码中硬编码API密钥
   - 使用环境变量或配置文件
   - 定期更换API密钥

2. **资金安全**
   - 先在测试网进行充分测试
   - 设置合理的止损和仓位限制
   - 监控账户余额和风险敞口

3. **系统安全**
   - 保持系统和依赖更新
   - 使用强密码和2FA
   - 定期备份配置和日志

## 📁 项目结构

```
auto_trade/
├── src/                    # 源代码目录
│   ├── api/               # API客户端模块
│   ├── strategies/        # 交易策略模块
│   ├── risk/             # 风险管理模块
│   ├── execution/        # 订单执行模块
│   ├── monitoring/       # 监控模块
│   ├── config/           # 配置管理模块
│   └── __init__.py       # 主模块初始化
├── logs/                  # 日志文件目录
├── main.py               # 主程序入口
├── run.py                # 简化启动器
├── requirements.txt      # 依赖列表
├── .env.example         # 环境变量示例
├── config_example.yaml  # 配置文件示例
└── README.md            # 项目说明
```

## 🔧 开发指南

### 添加新策略
1. 在 `src/strategies/` 目录创建新策略类
2. 继承 `BaseStrategy` 基类
3. 实现 `analyze()` 和 `validate_parameters()` 方法
4. 在策略管理器中注册新策略

### 添加新指标
1. 在 `src/strategies/base_strategy.py` 中添加指标函数
2. 使用标准的技术指标计算
3. 确保指标函数的参数验证

### 扩展监控功能
1. 在 `src/monitoring/` 目录添加新的监控指标
2. 使用 `record_metric()` 函数记录指标
3. 在仪表板中显示新指标

## 🧪 测试

```bash
# 运行单元测试
python -m pytest tests/

# 运行集成测试
python -m pytest tests/integration/

# 运行特定测试
python -m pytest tests/test_strategies.py
```

## 📈 性能优化

### 内存优化
- 使用生成器处理大量数据
- 定期清理历史数据缓存
- 限制日志文件大小

### 速度优化
- 使用异步编程
- 缓存频繁访问的数据
- 优化算法复杂度

### 网络优化
- 使用WebSocket获取实时数据
- 批量处理API请求
- 实现请求重试机制

## 🔍 故障排除

### 常见问题

1. **API连接失败**
   - 检查API密钥和网络连接
   - 确认OKX服务状态
   - 检查防火墙设置

2. **策略不生成信号**
   - 检查策略参数配置
   - 验证市场数据获取
   - 查看策略日志

3. **订单执行失败**
   - 检查账户余额
   - 验证订单参数
   - 查看订单管理器日志

### 日志分析
```bash
# 查看实时日志
tail -f logs/trading_bot.log

# 搜索特定错误
grep "ERROR" logs/trading_bot.log

# 查看特定日期日志
ls logs/trading_bot_*.log
```

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## ⚠️ 免责声明

**重要风险提示：**

1. **交易风险** - 加密货币交易存在重大风险，可能导致资金损失
2. **技术风险** - 自动化系统可能出现故障或错误
3. **市场风险** - 市场条件可能快速变化，策略可能失效
4. **监管风险** - 监管政策可能影响交易活动

**使用本软件即表示您：**
- 理解并接受所有相关风险
- 具备足够的交易知识和经验
- 只使用可承受损失的资金进行交易
- 定期监控系统的运行状态
- 对交易决策承担全部责任

**开发者免责声明：**
本软件按"现状"提供，不提供任何明示或暗示的保证。开发者不对因使用本软件造成的任何损失承担责任。

## 📞 支持

如有问题或建议，请通过以下方式联系：
- 提交 Issue
- 发送邮件
- 加入社区讨论

---

**⚠️ 再次提醒：请谨慎使用，风险自担！**