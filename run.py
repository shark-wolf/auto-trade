"""
基于OKX的自动交易平台

一个功能完整的加密货币自动交易系统，支持多种交易策略、风险管理和实时监控。
"""

import asyncio
import sys
from pathlib import Path
from loguru import logger

# 添加src目录到Python路径
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
sys.path.insert(0, str(src_dir))

from main import TradingBot
from src import create_default_config, get_monitoring_service
from src.monitoring import log_event


async def main():
    """主函数"""
    print("🚀 OKX自动交易平台")
    print("=" * 50)
    
    # 检查配置文件
    config_file = Path("config.yaml")
    if not config_file.exists():
        print("📄 创建默认配置文件...")
        create_default_config("config.yaml")
        print("✅ 默认配置文件已创建: config.yaml")
        print("请根据需要修改配置文件后重新运行程序")
        return
    
    # 创建交易机器人
    print("🤖 初始化交易机器人...")
    bot = TradingBot(config_path="config.yaml")
    
    # 获取监控服务（用于记录事件），监控服务的启动交由 TradingBot 管理，避免重复启动占用端口
    monitoring_service = None
    try:
        monitoring_service = get_monitoring_service()
        # 记录系统启动事件
        log_event("system", "info", "OKX自动交易平台启动")
        
        # 初始化机器人
        print("⚙️  初始化组件...")
        await bot.initialize()
        
        # 启动机器人
        print("🚀 启动交易机器人...")
        await bot.start()
        
        print("\n✅ 交易机器人已成功启动！")
        print("📊 监控仪表板: http://localhost:8765")
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
        if 'bot' in locals():
            await bot.stop()
        if monitoring_service:
            await monitoring_service.stop()
        print("👋 程序已停止")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())