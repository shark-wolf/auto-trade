"""
统一入口：使用 .env 环境变量启动交易机器人

说明：从现在起建议通过 run.py 启动项目，配置项统一从 .env 读取。
"""

import asyncio
import sys
import os
import threading
from functools import partial
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlsplit
from loguru import logger

# 添加src目录到Python路径
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
sys.path.insert(0, str(src_dir))

from main import TradingBot


async def main():
    """主函数"""
    print("🚀 自动交易平台")
    print("=" * 50)

    # 创建交易机器人（从 .env 读取配置）
    print("🤖 初始化交易机器人...")
    bot = TradingBot(config_path=".env")

    try:
        # 初始化机器人
        print("⚙️  初始化组件...")
        await bot.initialize()

        # 启动内置静态页面服务（仪表板）
        http_host = os.environ.get("HTTP_HOST", "127.0.0.1")
        try:
            http_port = int(os.environ.get("HTTP_PORT", "8000"))
        except ValueError:
            http_port = 8000

        serve_dir = Path(__file__).parent  # 项目根目录

        class DashboardHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault("directory", str(serve_dir))
                super().__init__(*args, **kwargs)

            def do_GET(self):
                parsed = urlsplit(self.path)
                if parsed.path in ("/dashboard", "/dashboard.html"):
                    file_path = serve_dir / "src" / "monitoring" / "dashboard.html"
                    if file_path.exists():
                        try:
                            with open(file_path, "rb") as f:
                                content = f.read()
                            self.send_response(200)
                            self.send_header("Content-Type", "text/html; charset=utf-8")
                            self.send_header("Content-Length", str(len(content)))
                            self.send_header("Cache-Control", "no-store")
                            self.end_headers()
                            self.wfile.write(content)
                            return
                        except Exception as e:
                            self.send_error(500, f"Failed to serve dashboard: {e}")
                            return
                    else:
                        self.send_error(404, "Dashboard not found")
                        return
                return super().do_GET()

        handler = DashboardHandler
        http_server = ThreadingHTTPServer((http_host, http_port), handler)
        http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        http_thread.start()
        print(f"🌐 已启动静态页面服务: http://{http_host}:{http_port}/")

        # 启动机器人
        print("🚀 启动交易机器人...")
        await bot.start()

        # 仪表板地址基于配置动态输出
        ws_host = bot.config.get("ws_host", "127.0.0.1")
        ws_port = bot.config.get("ws_port", 8765)
        print("\n✅ 交易机器人已成功启动！")
        print(f"📊 监控WebSocket: ws://{ws_host}:{ws_port}")
        print("🔎 仪表板预览: http://localhost:8000/dashboard.html")
        print("📝 查看日志文件: logs/trading_bot.log")
        print("\n按 Ctrl+C 停止程序")

        # 保持运行
        while bot.is_running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("用户中断，正在停止...")
    except Exception as e:
        logger.error(f"运行错误: {str(e)}")
    finally:
        await bot.stop()
        # 优雅关闭静态页面服务
        try:
            http_server.shutdown()
            http_server.server_close()
        except Exception:
            pass
        try:
            http_thread.join(timeout=2)
        except Exception:
            pass
        print("👋 程序已停止")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())