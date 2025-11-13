"""
日志记录和监控模块
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import sqlite3
from loguru import logger
import psutil
import websockets
import aiohttp
from collections import defaultdict, deque
import statistics


@dataclass
class PerformanceMetric:
    """性能指标"""
    timestamp: datetime
    metric_name: str
    value: float
    tags: Dict[str, str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class TradingEvent:
    """交易事件"""
    event_id: str
    timestamp: datetime
    event_type: str  # order, signal, error, system
    level: str  # info, warning, error, critical
    message: str
    data: Dict[str, Any] = None
    tags: Dict[str, str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class MetricsCollector:
    """性能指标收集器"""
    
    def __init__(self, max_history: int = 1000):
        """
        初始化性能指标收集器
        
        参数:
            max_history: 最大历史记录数
        """
        self.max_history = max_history
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.aggregated_metrics: Dict[str, Dict[str, Any]] = {}
        
        # 预定义的性能指标
        self.predefined_metrics = {
            "api_latency": {"unit": "ms", "type": "gauge"},
            "api_requests_per_minute": {"unit": "count/min", "type": "counter"},
            "order_execution_time": {"unit": "ms", "type": "gauge"},
            "signal_generation_time": {"unit": "ms", "type": "gauge"},
            "websocket_reconnects": {"unit": "count", "type": "counter"},
            "daily_pnl": {"unit": "USDT", "type": "gauge"},
            "win_rate": {"unit": "percent", "type": "gauge"},
            "sharpe_ratio": {"unit": "ratio", "type": "gauge"},
            "max_drawdown": {"unit": "percent", "type": "gauge"},
            "active_positions": {"unit": "count", "type": "gauge"},
            "total_trades": {"unit": "count", "type": "counter"},
            "system_memory_usage": {"unit": "percent", "type": "gauge"},
            "system_cpu_usage": {"unit": "percent", "type": "gauge"}
        }
    
    def record_metric(self, metric_name: str, value: float, tags: Dict[str, str] = None):
        """记录性能指标"""
        metric = PerformanceMetric(
            timestamp=datetime.now(),
            metric_name=metric_name,
            value=value,
            tags=tags or {}
        )
        
        # 存储原始数据
        self.metrics[metric_name].append(metric)
        
        # 更新聚合数据
        self._update_aggregated_metrics(metric_name, value)
        
        logger.debug(f"记录指标: {metric_name} = {value}")
    
    def _update_aggregated_metrics(self, metric_name: str, value: float):
        """更新聚合指标"""
        if metric_name not in self.aggregated_metrics:
            self.aggregated_metrics[metric_name] = {
                "count": 0,
                "sum": 0,
                "min": float('inf'),
                "max": float('-inf'),
                "values": []
            }
        
        agg = self.aggregated_metrics[metric_name]
        agg["count"] += 1
        agg["sum"] += value
        agg["min"] = min(agg["min"], value)
        agg["max"] = max(agg["max"], value)
        agg["values"].append(value)
        
        # 保持最近100个值用于计算统计
        if len(agg["values"]) > 100:
            agg["values"].pop(0)
    
    def get_metric_stats(self, metric_name: str, window_minutes: int = 60) -> Dict[str, Any]:
        """获取指标统计信息"""
        if metric_name not in self.metrics:
            return {}
        
        # 获取时间窗口内的数据
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        recent_metrics = [m for m in self.metrics[metric_name] if m.timestamp >= cutoff_time]
        
        if not recent_metrics:
            return {}
        
        values = [m.value for m in recent_metrics]
        
        stats = {
            "metric_name": metric_name,
            "count": len(values),
            "avg": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0,
            "p50": statistics.median(values),
            "p95": self._percentile(values, 95),
            "p99": self._percentile(values, 99)
        }
        
        return stats
    
    def _percentile(self, values: List[float], percentile: int) -> float:
        """计算百分位数"""
        if not values:
            return 0
        
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def get_all_metrics_summary(self) -> Dict[str, Any]:
        """获取所有指标摘要"""
        summary = {}
        
        for metric_name in self.predefined_metrics:
            if metric_name in self.aggregated_metrics:
                agg = self.aggregated_metrics[metric_name]
                summary[metric_name] = {
                    "count": agg["count"],
                    "avg": agg["sum"] / agg["count"] if agg["count"] > 0 else 0,
                    "min": agg["min"] if agg["min"] != float('inf') else 0,
                    "max": agg["max"] if agg["max"] != float('-inf') else 0
                }
        
        return summary


class EventLogger:
    """事件日志记录器"""
    
    def __init__(self, max_events: int = 10000):
        """
        初始化事件日志记录器
        
        参数:
            max_events: 最大事件数
        """
        self.max_events = max_events
        self.events: List[TradingEvent] = []
        self.event_counts: Dict[str, int] = defaultdict(int)
        
        # 事件类型映射
        self.event_type_mapping = {
            "order": {"level": "info", "category": "trading"},
            "signal": {"level": "info", "category": "strategy"},
            "error": {"level": "error", "category": "system"},
            "warning": {"level": "warning", "category": "system"},
            "info": {"level": "info", "category": "system"},
            "system": {"level": "info", "category": "system"}
        }
    
    def log_event(self, event_type: str, level: str, message: str, 
                  data: Dict[str, Any] = None, tags: Dict[str, str] = None,
                  event_id: str = None):
        """记录事件"""
        if event_id is None:
            event_id = f"{event_type}_{int(time.time() * 1000)}"
        
        event = TradingEvent(
            event_id=event_id,
            timestamp=datetime.now(),
            event_type=event_type,
            level=level,
            message=message,
            data=data or {},
            tags=tags or {}
        )
        
        # 添加到事件列表
        self.events.append(event)
        
        # 更新事件计数
        self.event_counts[event_type] += 1
        
        # 限制事件数量
        if len(self.events) > self.max_events:
            removed_event = self.events.pop(0)
            self.event_counts[removed_event.event_type] -= 1
        
        # 记录到loguru
        log_method = getattr(logger, level.lower(), logger.info)
        log_method(f"[{event_type.upper()}] {message}")
        
        if data:
            logger.debug(f"事件数据: {json.dumps(data, ensure_ascii=False)}")
    
    def get_recent_events(self, event_type: str = None, level: str = None, 
                         limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近事件"""
        filtered_events = self.events
        
        if event_type:
            filtered_events = [e for e in filtered_events if e.event_type == event_type]
        
        if level:
            filtered_events = [e for e in filtered_events if e.level == level]
        
        # 按时间倒序排列
        filtered_events.sort(key=lambda x: x.timestamp, reverse=True)
        
        # 限制数量
        filtered_events = filtered_events[:limit]
        
        return [event.to_dict() for event in filtered_events]
    
    def get_event_summary(self, hours: int = 24) -> Dict[str, Any]:
        """获取事件摘要"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_events = [e for e in self.events if e.timestamp >= cutoff_time]
        
        summary = {
            "total_events": len(recent_events),
            "event_counts": defaultdict(int),
            "level_counts": defaultdict(int),
            "error_rate": 0
        }
        
        for event in recent_events:
            summary["event_counts"][event.event_type] += 1
            summary["level_counts"][event.level] += 1
        
        # 计算错误率
        total_events = len(recent_events)
        error_count = summary["level_counts"]["error"]
        summary["error_rate"] = (error_count / total_events * 100) if total_events > 0 else 0
        
        return dict(summary)


class MonitoringDashboard:
    """监控仪表板"""
    
    def __init__(self, metrics_collector: MetricsCollector, event_logger: EventLogger):
        """
        初始化监控仪表板
        
        参数:
            metrics_collector: 性能指标收集器
            event_logger: 事件日志记录器
        """
        self.metrics_collector = metrics_collector
        self.event_logger = event_logger
        self.dashboard_data = {}
        self.last_update = None
        
        # 初始化仪表板数据
        self._initialize_dashboard()
    
    def _initialize_dashboard(self):
        """初始化仪表板数据"""
        self.dashboard_data = {
            "system_status": {
                "status": "running",
                "uptime": 0,
                "last_heartbeat": datetime.now().isoformat(),
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "connections": 0
            },
            "performance_metrics": {},
            "trading_metrics": {},
            "risk_metrics": {},
            "recent_events": [],
            "alerts": []
        }
    
    def update_dashboard(self):
        """更新仪表板数据"""
        try:
            current_time = datetime.now()
            
            # 更新系统状态
            self.dashboard_data["system_status"]["last_heartbeat"] = current_time.isoformat()
            if self.last_update:
                self.dashboard_data["system_status"]["uptime"] = (
                    current_time - self.last_update
                ).total_seconds()
            # 采集系统资源
            try:
                self.dashboard_data["system_status"]["cpu_percent"] = psutil.cpu_percent(interval=None)
                self.dashboard_data["system_status"]["memory_percent"] = psutil.virtual_memory().percent
            except Exception:
                # 如果采集失败，保留默认值
                pass
            
            # 更新性能指标
            self.dashboard_data["performance_metrics"] = self.metrics_collector.get_all_metrics_summary()
            
            # 更新交易指标
            self.dashboard_data["trading_metrics"] = self._get_trading_metrics()
            
            # 更新风险指标
            self.dashboard_data["risk_metrics"] = self._get_risk_metrics()
            
            # 更新最近事件
            self.dashboard_data["recent_events"] = self.event_logger.get_recent_events(limit=10)
            
            # 检查警报
            self.dashboard_data["alerts"] = self._check_alerts()
            
            self.last_update = current_time
            
        except Exception as e:
            logger.error(f"更新仪表板失败: {str(e)}")
    
    def _get_trading_metrics(self) -> Dict[str, Any]:
        """获取交易指标（对齐前端期待的数值字段）"""
        agg = getattr(self.metrics_collector, "aggregated_metrics", {})

        def get_agg_sum(name: str) -> float:
            a = agg.get(name)
            return float(a.get("sum", 0)) if a else 0.0

        def get_agg_avg(name: str) -> float:
            a = agg.get(name)
            return float(a.get("sum", 0)) / float(a.get("count", 1)) if a and a.get("count", 0) > 0 else 0.0

        def get_agg_count(name: str) -> int:
            a = agg.get(name)
            return int(a.get("count", 0)) if a else 0

        # 历史PnL（最近50条）
        pnl_metrics = self.metrics_collector.metrics.get("daily_pnl", [])
        recent = list(pnl_metrics)[-50:] if pnl_metrics else []
        pnl_history = [m.value for m in recent]
        pnl_labels = [m.timestamp.strftime("%H:%M:%S") for m in recent]

        return {
            "total_trades": get_agg_count("total_trades"),
            "win_rate": get_agg_avg("win_rate"),
            "total_pnl": get_agg_sum("daily_pnl"),
            "sharpe_ratio": get_agg_avg("sharpe_ratio"),
            "pnl_history": pnl_history,
            "pnl_labels": pnl_labels,
            "winning_trades": get_agg_count("winning_trades"),
            "losing_trades": get_agg_count("losing_trades")
        }

    def _get_risk_metrics(self) -> Dict[str, Any]:
        """获取风险指标（对齐前端期待的数值字段）"""
        agg = getattr(self.metrics_collector, "aggregated_metrics", {})

        def get_agg_avg(name: str) -> float:
            a = agg.get(name)
            return float(a.get("sum", 0)) / float(a.get("count", 1)) if a and a.get("count", 0) > 0 else 0.0

        def get_agg_max(name: str) -> float:
            a = agg.get(name)
            val = a.get("max") if a else None
            return float(val) if val not in (None, float("-inf")) else 0.0

        return {
            "risk_exposure": get_agg_avg("active_positions"),
            "max_drawdown": get_agg_max("max_drawdown"),
            "risk_reward_ratio": get_agg_avg("risk_reward_ratio"),
            # daily_loss_limit 将在服务层注入（来自配置）
            "daily_loss_limit": 0.0
        }
    
    def _check_alerts(self) -> List[Dict[str, Any]]:
        """检查警报"""
        alerts = []
        
        # 检查API延迟
        api_latency = self.metrics_collector.get_metric_stats("api_latency", 60)
        if api_latency and api_latency.get("avg", 0) > 5000:  # 5秒
            alerts.append({
                "level": "warning",
                "type": "performance",
                "message": "API延迟过高",
                "value": api_latency["avg"],
                "threshold": 5000
            })
        
        # 检查错误率
        event_summary = self.event_logger.get_event_summary(1)
        if event_summary["error_rate"] > 10:  # 10%
            alerts.append({
                "level": "error",
                "type": "system",
                "message": "系统错误率过高",
                "value": event_summary["error_rate"],
                "threshold": 10
            })
        
        return alerts
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表板数据"""
        self.update_dashboard()
        return self.dashboard_data


class MonitoringService:
    """监控服务"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化监控服务
        
        参数:
            config: 配置字典
        """
        self.config = config or {}
        self.metrics_collector = MetricsCollector()
        self.event_logger = EventLogger()
        self.dashboard = MonitoringDashboard(self.metrics_collector, self.event_logger)
        # 外部状态（例如来自交易机器人）
        self.portfolio_status: Optional[Dict[str, Any]] = None
        # 外部策略状态（由交易机器人推送，用于显示策略与指标参数）
        self.strategy_status: Optional[Dict[str, Any]] = None
        
        # WebSocket服务器
        self.ws_server = None
        self.ws_clients = set()
        # 控制回调（由交易机器人注册，用于处理启停等指令）
        self.control_callback = None
        # 参数更新回调（由交易机器人注册，用于处理指标参数更新）
        self.params_callback = None
        self.timeframe_callback = None
        self.creds_callback = None
        
        # 数据库连接
        self.db_connection = None
        self.db_path = self.config.get("db_path") or self._derive_db_path(self.config)
        
        # 初始化数据库
        self._initialize_database()
        try:
            self._migrate_settings_from_legacy()
        except Exception as _:
            pass
        try:
            self._consolidate_labels_in_current_db()
        except Exception as _:
            pass
        try:
            self._seed_settings_from_config()
        except Exception as _:
            pass
        
        # 启动后台任务
        self.background_tasks = []
        self.is_running = False

    def update_portfolio_status(self, status: Dict[str, Any]):
        """更新外部传入的组合状态快照"""
        try:
            self.portfolio_status = status or {}
        except Exception:
            # 保底防护，避免异常导致整个监控失败
            self.portfolio_status = {}
        try:
            import asyncio
            asyncio.create_task(self._broadcast_dashboard())
        except Exception:
            pass

    def update_strategy_status(self, status: Dict[str, Any]):
        """更新外部传入的策略状态（包含活动策略与指标参数）"""
        try:
            self.strategy_status = status or {}
        except Exception:
            self.strategy_status = {}
        try:
            import asyncio
            asyncio.create_task(self._broadcast_dashboard())
        except Exception:
            pass
    
    def _initialize_database(self):
        """初始化数据库"""
        try:
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)
            
            self.db_connection = sqlite3.connect(self.db_path, check_same_thread=False)
            
            # 创建表
            cursor = self.db_connection.cursor()
            
            # 性能指标表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 事件表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON performance_metrics(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON performance_metrics(metric_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON trading_events(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON trading_events(event_type)")
            
            # 设置表：持久化配置（key-value）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    label TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # 兼容：若旧库无label列，补充添加
            try:
                cols = cursor.execute("PRAGMA table_info(settings)").fetchall()
                names = {c[1] for c in cols}
                if "label" not in names:
                    cursor.execute("ALTER TABLE settings ADD COLUMN label TEXT")
            except Exception:
                pass

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_params (
                    strategy TEXT PRIMARY KEY,
                    params TEXT NOT NULL,
                    win_rate REAL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS api_credentials (
                    backend TEXT,
                    exchange_type TEXT,
                    api_key TEXT,
                    api_secret TEXT,
                    passphrase TEXT,
                    testnet TEXT,
                    is_demo TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            try:
                cols = cursor.execute("PRAGMA table_info(api_credentials)").fetchall()
                names = {c[1] for c in cols}
                if "exchange_type" not in names:
                    cursor.execute("ALTER TABLE api_credentials ADD COLUMN exchange_type TEXT")
            except Exception:
                pass
            try:
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_api_credentials_exchange_type ON api_credentials(exchange_type)")
            except Exception:
                pass

            self.db_connection.commit()
            
        except Exception as e:
            logger.error(f"初始化数据库失败: {str(e)}")

    def _derive_db_path(self, cfg: Dict[str, Any]) -> str:
        try:
            url = (cfg or {}).get("database_url") or ""
            if url.startswith("sqlite:///"):
                return url.replace("sqlite:///", "")
            if url.endswith(".db"):
                return url
        except Exception:
            pass
        return "logs/monitoring.db"

    def _migrate_settings_from_legacy(self):
        try:
            legacy_path = "logs/monitoring.db"
            if not legacy_path or legacy_path == self.db_path:
                return
            legacy = Path(legacy_path)
            if not legacy.exists():
                return
            src = sqlite3.connect(legacy_path)
            try:
                cursor = src.cursor()
                rows = cursor.execute("SELECT key, value FROM settings").fetchall()
            except Exception:
                rows = []
            finally:
                try:
                    src.close()
                except Exception:
                    pass
            if not rows:
                return
            try:
                for k, v in rows:
                    try:
                        k = str(k)
                        if k.startswith("label:"):
                            actual = k[6:]
                            # 设置显示文字到label列
                            self.set_setting(actual, self.get_setting(actual) or "", label=str(v))
                        else:
                            self.set_setting(k, str(v))
                    except Exception:
                        pass
                logger.info(f"迁移完成: settings 从 {legacy_path} -> {self.db_path}")
            except Exception as e:
                logger.error(f"迁移settings失败: {str(e)}")
        except Exception:
            pass

    def _consolidate_labels_in_current_db(self):
        try:
            cursor = self.db_connection.cursor()
            rows = cursor.execute("SELECT key, value FROM settings WHERE key LIKE 'label:%'").fetchall()
            if not rows:
                return
            for lk, lbl in rows:
                try:
                    actual = str(lk)[6:]
                    exists = cursor.execute("SELECT key FROM settings WHERE key = ?", (actual,)).fetchone()
                    if exists:
                        cursor.execute("UPDATE settings SET label = ? WHERE key = ?", (str(lbl), actual))
                    else:
                        cursor.execute(
                            "INSERT INTO settings(key, value, label, updated_at) VALUES(?, ?, ?, CURRENT_TIMESTAMP)",
                            (actual, "", str(lbl))
                        )
                    cursor.execute("DELETE FROM settings WHERE key = ?", (lk,))
                except Exception:
                    pass
            self.db_connection.commit()
        except Exception:
            pass

    def _seed_settings_from_config(self):
        cfg = self.config or {}
        defaults = [
            ("api_backend", str(cfg.get("api_backend") or "ccxt"), "后端"),
            ("symbol", str(cfg.get("symbol") or "BTC-USDT-SWAP"), "交易对"),
            ("trading_timeframe", str(cfg.get("trading_timeframe") or "1m"), "周期"),
            ("ws_host", str(cfg.get("ws_host") or "127.0.0.1"), "WS主机"),
            ("ws_port", str(cfg.get("ws_port") or 8765), "WS端口"),
            ("enable_websocket", "true" if bool(cfg.get("enable_websocket", True)) else "false", "启用WS"),
            ("enable_monitoring", "true" if bool(cfg.get("enable_monitoring", True)) else "false", "启用监控"),
            ("enable_ccxt_polling", "true" if bool(cfg.get("enable_ccxt_polling", True)) else "false", "启用轮询"),
            ("database_url", str(cfg.get("database_url") or "sqlite:///data/trading.db"), "数据库URL"),
        ]
        # 默认卡片顺序初始化到 card_layouts 表（仅在不存在时）
        try:
            cursor = self.db_connection.cursor()
            row = cursor.execute("SELECT container FROM card_layouts WHERE container = 'main'").fetchone()
            if not row:
                default_main_order = ["card-strategy", "card-settings", "card-indicators", "card-system", "card-risk", "card-stats", "card-portfolio"]
                cursor.execute(
                    "INSERT INTO card_layouts(container, order_json, updated_at) VALUES(?, ?, CURRENT_TIMESTAMP)",
                    ('main', json.dumps(default_main_order, ensure_ascii=False))
                )
            row = cursor.execute("SELECT container FROM card_layouts WHERE container = 'settings'").fetchone()
            if not row:
                default_settings_order = ["card-settings"]
                cursor.execute(
                    "INSERT INTO card_layouts(container, order_json, updated_at) VALUES(?, ?, CURRENT_TIMESTAMP)",
                    ('settings', json.dumps(default_settings_order, ensure_ascii=False))
                )
            self.db_connection.commit()
        except Exception:
            pass

        try:
            cursor = self.db_connection.cursor()
            rows = cursor.execute("SELECT key, label FROM settings").fetchall()
            existing = {row[0] for row in rows}
            existing_labels = {row[0]: row[1] for row in rows}
        except Exception:
            existing = set()
            existing_labels = {}

        for k, v, lbl in defaults:
            try:
                if k not in existing:
                    self.set_setting(k, v, lbl)
                else:
                    cur_lbl = existing_labels.get(k)
                    if (cur_lbl is None or str(cur_lbl).strip() == "") and lbl:
                        try:
                            cursor.execute("UPDATE settings SET label = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?", (lbl, k))
                            self.db_connection.commit()
                        except Exception:
                            pass
            except Exception:
                pass

    def get_setting(self, key: str) -> Optional[str]:
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def set_setting(self, key: str, value: str, label: Optional[str] = None) -> bool:
        try:
            cursor = self.db_connection.cursor()
            cursor.execute(
                "INSERT INTO settings(key, value, label, updated_at) VALUES(?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value, label=COALESCE(excluded.label, settings.label), updated_at=excluded.updated_at",
                (key, value, label)
            )
            self.db_connection.commit()
            return True
        except Exception:
            return False

    def get_strategy_params(self, strategy: str) -> Optional[Dict[str, Any]]:
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("SELECT params FROM strategy_params WHERE strategy = ?", (strategy,))
            row = cursor.fetchone()
            if not row:
                return None
            return json.loads(row[0])
        except Exception:
            return None

    def set_strategy_params(self, strategy: str, params: Dict[str, Any], win_rate: float = 0.0) -> bool:
        try:
            cursor = self.db_connection.cursor()
            cursor.execute(
                "INSERT INTO strategy_params(strategy, params, win_rate, updated_at) VALUES(?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(strategy) DO UPDATE SET params=excluded.params, win_rate=excluded.win_rate, updated_at=excluded.updated_at",
                (strategy, json.dumps(params, ensure_ascii=False), float(win_rate))
            )
            self.db_connection.commit()
            return True
        except Exception:
            return False
    
    async def start(self):
        """启动监控服务"""
        if self.is_running:
            return
        
        logger.info("启动监控服务...")
        self.is_running = True
        
        # 启动数据持久化任务
        persist_task = asyncio.create_task(self._persist_data_loop())
        self.background_tasks.append(persist_task)
        
        # 启动WebSocket服务器
        if self.config.get("enable_websocket", True):
            ws_task = asyncio.create_task(self._start_websocket_server())
            self.background_tasks.append(ws_task)
        
        logger.info("监控服务启动完成")
    
    async def stop(self):
        """停止监控服务"""
        if not self.is_running:
            return
        
        logger.info("停止监控服务...")
        self.is_running = False
        
        # 取消后台任务
        for task in self.background_tasks:
            task.cancel()
        
        # 等待任务完成
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # 关闭数据库连接
        if self.db_connection:
            self.db_connection.close()
        
        # 关闭WebSocket服务器
        if self.ws_server:
            self.ws_server.close()
            await self.ws_server.wait_closed()
        
        logger.info("监控服务已停止")
    
    async def _persist_data_loop(self):
        """数据持久化循环"""
        while self.is_running:
            try:
                # 持久化性能指标
                await self._persist_metrics()
                
                # 持久化事件
                await self._persist_events()
                
                # 等待下次持久化
                await asyncio.sleep(300)  # 5分钟
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"数据持久化失败: {str(e)}")
                await asyncio.sleep(60)
    
    async def _persist_metrics(self):
        """持久化性能指标"""
        try:
            cursor = self.db_connection.cursor()
            
            # 获取需要持久化的指标
            for metric_name, metrics in self.metrics_collector.metrics.items():
                for metric in metrics:
                    cursor.execute("""
                        INSERT INTO performance_metrics (timestamp, metric_name, value, tags)
                        VALUES (?, ?, ?, ?)
                    """, (
                        metric.timestamp.isoformat(),
                        metric.metric_name,
                        metric.value,
                        json.dumps(metric.tags) if metric.tags else None
                    ))
            
            self.db_connection.commit()
            
        except Exception as e:
            logger.error(f"持久化性能指标失败: {str(e)}")
    
    async def _persist_events(self):
        """持久化事件"""
        try:
            cursor = self.db_connection.cursor()
            
            # 获取需要持久化的事件
            for event in self.event_logger.events:
                cursor.execute("""
                    INSERT INTO trading_events (event_id, timestamp, event_type, level, message, data, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id,
                    event.timestamp.isoformat(),
                    event.event_type,
                    event.level,
                    event.message,
                    json.dumps(event.data) if event.data else None,
                    json.dumps(event.tags) if event.tags else None
                ))
            
            self.db_connection.commit()
            
        except Exception as e:
            logger.error(f"持久化事件失败: {str(e)}")
    
    async def _start_websocket_server(self):
        """启动WebSocket服务器"""
        try:
            host = self.config.get("ws_host", "localhost")
            port = self.config.get("ws_port", 8765)
            
            self.ws_server = await websockets.serve(
                self._handle_websocket_client,
                host,
                port
            )
            
            logger.info(f"WebSocket监控服务器启动: ws://{host}:{port}")
            
        except Exception as e:
            logger.error(f"启动WebSocket服务器失败: {str(e)}")
    
    async def _handle_websocket_client(self, websocket):
        """处理WebSocket客户端连接并支持控制消息（websockets v12+ 单参数 handler）"""
        self.ws_clients.add(websocket)
        try:
            remote = getattr(websocket, 'remote_address', None)
            path = getattr(websocket, 'path', '/')
            logger.info(f"WebSocket客户端连接: {remote}, path: {path}")
        except Exception:
            logger.info("WebSocket客户端连接")

        # 启动发送循环任务
        sender_task = asyncio.create_task(self._ws_send_loop(websocket))
        try:
            # 接收控制消息
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                if isinstance(msg, dict) and msg.get("type") == "control":
                    action = str(msg.get("action", "")).lower()
                    if action in ("start", "stop"):
                        # 记录事件
                        try:
                            self.log_event(
                                event_type="system",
                                level="info",
                                message=f"收到控制指令: {action}",
                                data={"source": "dashboard", "action": action}
                            )
                        except Exception:
                            pass

                # 参数更新：允许前端修改策略指标参数
                elif isinstance(msg, dict) and str(msg.get("type", "")).lower() in ("params", "update_params"):
                    strategy = str(msg.get("strategy", "")).strip()
                    updates = msg.get("updates") or {}

                    try:
                        # 记录事件
                        try:
                            self.log_event(
                                event_type="system",
                                level="info",
                                message=f"收到参数更新: {strategy}",
                                data={"source": "dashboard", "strategy": strategy, "updates": updates}
                            )
                        except Exception:
                            pass

                        # 回调交易机器人应用参数
                        if callable(self.params_callback):
                            result = self.params_callback(strategy, updates)
                            if asyncio.iscoroutine(result):
                                await result

                        # 反馈客户端
                        try:
                            await websocket.send(json.dumps({
                                "type": "ack",
                                "action": "params",
                                "strategy": strategy,
                                "status": "ok"
                            }))
                        except Exception:
                            pass
                    except Exception as e:
                        logger.error(f"处理参数更新失败: {str(e)}")
                        try:
                            await websocket.send(json.dumps({
                                "type": "ack",
                                "action": "params",
                                "strategy": strategy,
                                "status": "error",
                                "error": str(e)
                            }))
                        except Exception:
                            pass

                elif isinstance(msg, dict) and str(msg.get("type", "")).lower() in ("timeframe", "set_timeframe"):
                    tf = str(msg.get("timeframe", "")).strip()
                    try:
                        try:
                            self.log_event(
                                event_type="system",
                                level="info",
                                message="收到周期更新",
                                data={"timeframe": tf}
                            )
                        except Exception:
                            pass

                        if callable(self.timeframe_callback):
                            result = self.timeframe_callback(tf)
                            if asyncio.iscoroutine(result):
                                await result

                        try:
                            await websocket.send(json.dumps({
                                "type": "ack",
                                "action": "timeframe",
                                "status": "ok",
                                "timeframe": tf
                            }))
                        except Exception:
                            pass

                    except Exception as e:
                        logger.error(f"处理周期更新失败: {str(e)}")
                        try:
                            await websocket.send(json.dumps({
                                "type": "ack",
                                "action": "timeframe",
                                "status": "error",
                                "error": str(e)
                            }))
                        except Exception:
                            pass

                elif isinstance(msg, dict) and str(msg.get("type", "")).lower() in ("config_get",):
                    try:
                        cursor = self.db_connection.cursor()
                        items = []
                        try:
                            for k, v, lbl in cursor.execute("SELECT key, value, label FROM settings"):
                                items.append({"key": k, "value": v, "label": lbl})
                        except Exception:
                            items = []
                        layouts = []
                        try:
                            for c, ojson in cursor.execute("SELECT container, order_json FROM card_layouts"):
                                try:
                                    order = json.loads(ojson)
                                except Exception:
                                    order = []
                                layouts.append({"container": c, "order": order})
                        except Exception:
                            layouts = []
                        creds = []
                        try:
                            for et, ak, sk, pp, tn, demo in cursor.execute("SELECT exchange_type, api_key, api_secret, passphrase, testnet, is_demo FROM api_credentials"):
                                creds.append({
                                    "exchange_type": et or "okx",
                                    "api_key": ak or "",
                                    "api_secret": sk or "",
                                    "passphrase": pp or "",
                                    "testnet": tn or "false",
                                    "is_demo": demo or "true",
                                })
                        except Exception:
                            creds = []
                        await websocket.send(json.dumps({"type": "config", "settings": items, "layouts": layouts, "creds": creds}))
                    except Exception as e:
                        try:
                            await websocket.send(json.dumps({"type": "ack", "action": "config_get", "status": "error", "error": str(e)}))
                        except Exception:
                            pass
                elif isinstance(msg, dict) and str(msg.get("type", "")).lower() in ("config_set",):
                    try:
                        k = msg.get("key")
                        v = msg.get("value")
                        lbl = msg.get("label")
                        ok = True
                        if k is not None:
                            ok = bool(self.set_setting(str(k), str(v), str(lbl) if lbl is not None else None))
                        await websocket.send(json.dumps({"type": "ack", "action": "config_set", "status": "ok" if ok else "error"}))
                    except Exception as e:
                        try:
                            await websocket.send(json.dumps({"type": "ack", "action": "config_set", "status": "error", "error": str(e)}))
                        except Exception:
                            pass
                elif isinstance(msg, dict) and str(msg.get("type", "")).lower() in ("layout_set",):
                    try:
                        container = str(msg.get("container", ""))
                        order = msg.get("order")
                        if not container or not isinstance(order, list):
                            await websocket.send(json.dumps({"type": "ack", "action": "layout_set", "status": "error", "error": "参数不合法"}))
                            return
                        ojson = json.dumps(order, ensure_ascii=False)
                        cursor = self.db_connection.cursor()
                        cursor.execute(
                            "INSERT INTO card_layouts(container, order_json, updated_at) VALUES(?, ?, CURRENT_TIMESTAMP) ON CONFLICT(container) DO UPDATE SET order_json=excluded.order_json, updated_at=excluded.updated_at",
                            (container, ojson)
                        )
                        self.db_connection.commit()
                        await websocket.send(json.dumps({"type": "ack", "action": "layout_set", "status": "ok"}))
                    except Exception as e:
                        try:
                            await websocket.send(json.dumps({"type": "ack", "action": "layout_set", "status": "error", "error": str(e)}))
                        except Exception:
                            pass
                elif isinstance(msg, dict) and str(msg.get("type", "")).lower() in ("creds_set",):
                    try:
                        exchange_type = str(msg.get("exchange_type", "okx")).strip().lower()
                        api_key = str(msg.get("api_key", ""))
                        api_secret = str(msg.get("api_secret", ""))
                        passphrase = str(msg.get("passphrase", ""))
                        testnet = "true" if str(msg.get("testnet", "false")).lower() == "true" else "false"
                        is_demo = "true" if str(msg.get("is_demo", "true")).lower() == "true" else "false"
                        if not exchange_type:
                            await websocket.send(json.dumps({"type": "ack", "action": "creds_set", "status": "error", "error": "交易所类型不能为空"}))
                            return
                        cursor = self.db_connection.cursor()
                        cursor.execute(
                            "INSERT INTO api_credentials(exchange_type, api_key, api_secret, passphrase, testnet, is_demo, updated_at) VALUES(?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(exchange_type) DO UPDATE SET api_key=excluded.api_key, api_secret=excluded.api_secret, passphrase=excluded.passphrase, testnet=excluded.testnet, is_demo=excluded.is_demo, updated_at=excluded.updated_at",
                            (exchange_type, api_key, api_secret, passphrase, testnet, is_demo)
                        )
                        self.db_connection.commit()
                        try:
                            if callable(self.creds_callback):
                                payload = {"exchange_type": exchange_type, "api_key": api_key, "api_secret": api_secret, "passphrase": passphrase, "testnet": testnet, "is_demo": is_demo}
                                r = self.creds_callback(payload)
                                if asyncio.iscoroutine(r):
                                    await r
                        except Exception:
                            pass
                        await websocket.send(json.dumps({"type": "ack", "action": "creds_set", "status": "ok"}))
                    except Exception as e:
                        try:
                            await websocket.send(json.dumps({"type": "ack", "action": "creds_set", "status": "error", "error": str(e)}))
                        except Exception:
                            pass
                elif isinstance(msg, dict) and str(msg.get("type", "")).lower() in ("creds_get",):
                    try:
                        cursor = self.db_connection.cursor()
                        rows = cursor.execute("SELECT exchange_type, api_key, api_secret, passphrase, testnet, is_demo FROM api_credentials").fetchall()
                        out = []
                        for et, ak, sk, pp, tn, demo in rows:
                            out.append({
                                "exchange_type": et or "okx",
                                "api_key": ak or "",
                                "api_secret": sk or "",
                                "passphrase": pp or "",
                                "testnet": tn or "false",
                                "is_demo": demo or "true",
                            })
                        await websocket.send(json.dumps({"type": "creds", "items": out}))
                    except Exception as e:
                        try:
                            await websocket.send(json.dumps({"type": "ack", "action": "creds_get", "status": "error", "error": str(e)}))
                        except Exception:
                            pass
                else:
                    action = str(msg.get("action", "")).lower()
                    try:
                        if callable(self.control_callback):
                            await self.control_callback(action)
                    except Exception as e:
                        logger.error(f"执行控制回调失败: {str(e)}")
                    # 反馈客户端
                    try:
                        await websocket.send(json.dumps({
                            "type": "ack",
                            "action": action,
                            "status": "ok"
                        }))
                    except Exception:
                        pass

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket客户端断开连接: {getattr(websocket, 'remote_address', '')}")
        except Exception as e:
            logger.error(f"WebSocket客户端错误: {str(e)}")
        finally:
            # 停止发送循环
            try:
                sender_task.cancel()
                await asyncio.gather(sender_task, return_exceptions=True)
            except Exception:
                pass
            self.ws_clients.discard(websocket)

    async def _ws_send_loop(self, websocket):
        """向指定客户端周期性推送仪表板数据"""
        try:
            # 首次发送
            await self._send_dashboard_once(websocket)
            # 周期推送
            while self.is_running:
                await asyncio.sleep(2)
                await self._send_dashboard_once(websocket)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WebSocket发送循环错误: {str(e)}")

    async def _broadcast_dashboard(self):
        try:
            clients = list(self.ws_clients)
            if not clients:
                return
            for ws in clients:
                try:
                    await self._send_dashboard_once(ws)
                except Exception:
                    pass
        except Exception:
            pass

    async def _send_dashboard_once(self, websocket):
        """构造并发送一次仪表板数据"""
        dashboard_data = self.dashboard.get_dashboard_data()
        # 注入连接数与每日亏损限额
        try:
            dashboard_data["system_status"]["connections"] = len(self.ws_clients)
        except Exception:
            pass
        try:
            if "risk_metrics" in dashboard_data:
                dashboard_data["risk_metrics"]["daily_loss_limit"] = float(self.config.get("max_daily_loss", 0.0))
        except Exception:
            pass
        # 注入资金与持仓
        try:
            if self.portfolio_status is not None:
                dashboard_data["portfolio_status"] = self.portfolio_status
        except Exception:
            pass
        # 注入策略状态（含指标参数）
        try:
            if self.strategy_status is not None:
                dashboard_data["strategy_status"] = self.strategy_status
            
        except Exception:
            pass
        await websocket.send(json.dumps(dashboard_data))
    
    # 公共API方法
    def record_metric(self, metric_name: str, value: float, tags: Dict[str, str] = None):
        """记录性能指标"""
        self.metrics_collector.record_metric(metric_name, value, tags)
    
    def log_event(self, event_type: str, level: str, message: str, 
                  data: Dict[str, Any] = None, tags: Dict[str, str] = None):
        """记录事件"""
        self.event_logger.log_event(event_type, level, message, data, tags)
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表板数据"""
        return self.dashboard.get_dashboard_data()
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        return self.metrics_collector.get_all_metrics_summary()
    
    def get_event_summary(self, hours: int = 24) -> Dict[str, Any]:
        """获取事件摘要"""
        return self.event_logger.get_event_summary(hours)

    # 控制回调注册
    def register_control_callback(self, callback):
        """注册控制回调，用于处理来自前端的启停指令"""
        self.control_callback = callback

    def register_params_callback(self, callback):
        """注册参数更新回调，用于处理来自前端的指标参数更新"""
        self.params_callback = callback

    def register_timeframe_callback(self, callback):
        self.timeframe_callback = callback

    def register_creds_callback(self, callback):
        self.creds_callback = callback


# 全局监控服务实例
_monitoring_service: Optional[MonitoringService] = None


def get_monitoring_service() -> MonitoringService:
    """获取全局监控服务实例"""
    global _monitoring_service
    if _monitoring_service is None:
        _monitoring_service = MonitoringService()
    return _monitoring_service


def record_metric(metric_name: str, value: float, tags: Dict[str, str] = None):
    """记录性能指标（便捷函数）"""
    service = get_monitoring_service()
    service.record_metric(metric_name, value, tags)


def log_event(event_type: str, level: str, message: str, 
              data: Dict[str, Any] = None, tags: Dict[str, str] = None):
    """记录事件（便捷函数）"""
    service = get_monitoring_service()
    service.log_event(event_type, level, message, data, tags)
