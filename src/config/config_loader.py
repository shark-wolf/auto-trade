"""
策略配置加载器
"""

import yaml
import json
from pathlib import Path
from typing import Dict, Any, List
from .strategy_config import StrategyConfig, StrategyType, validate_strategy_config


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化配置加载器
        
        参数:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config_data = {}
        
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if not self.config_path.exists():
                raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as file:
                self.config_data = yaml.safe_load(file)
            
            # 验证配置
            self._validate_config()
            
            return self.config_data
            
        except Exception as e:
            raise RuntimeError(f"加载配置文件失败: {str(e)}")
    
    def _validate_config(self):
        """验证配置"""
        required_sections = ["global", "strategies"]
        
        for section in required_sections:
            if section not in self.config_data:
                raise ValueError(f"配置缺少必要部分: {section}")
        
        # 验证策略配置
        strategies = self.config_data.get("strategies", [])
        if not strategies:
            raise ValueError("至少需要配置一个策略")
        
        for strategy_config in strategies:
            # 转换为StrategyConfig对象
            strategy_obj = self._create_strategy_config(strategy_config)
            
            # 验证策略配置
            validation_result = validate_strategy_config(strategy_obj)
            if not validation_result["valid"]:
                raise ValueError(f"策略配置验证失败: {validation_result['errors']}")
    
    def _create_strategy_config(self, config_data: Dict[str, Any]) -> StrategyConfig:
        """创建策略配置对象"""
        try:
            strategy_type = StrategyType(config_data["strategy_type"])
            
            return StrategyConfig(
                strategy_type=strategy_type,
                name=config_data["name"],
                enabled=config_data.get("enabled", True),
                symbol=config_data.get("symbol", "BTC-USDT"),
                timeframe=config_data.get("timeframe", "1h"),
                position_size=config_data.get("position_size", 0.01),
                max_positions=config_data.get("max_positions", 1),
                stop_loss_pct=config_data.get("stop_loss_pct", 0.02),
                take_profit_pct=config_data.get("take_profit_pct", 0.05),
                risk_per_trade=config_data.get("risk_per_trade", 0.01),
                parameters=config_data.get("parameters", {})
            )
            
        except Exception as e:
            raise ValueError(f"创建策略配置对象失败: {str(e)}")
    
    def get_global_config(self) -> Dict[str, Any]:
        """获取全局配置"""
        return self.config_data.get("global", {})
    
    def get_strategies_config(self) -> List[StrategyConfig]:
        """获取策略配置列表"""
        strategies = []
        
        for strategy_config in self.config_data.get("strategies", []):
            strategy_obj = self._create_strategy_config(strategy_config)
            strategies.append(strategy_obj)
        
        return strategies
    
    def get_risk_management_config(self) -> Dict[str, Any]:
        """获取风险管理配置"""
        return self.config_data.get("risk_management", {})
    
    def get_multi_symbol_config(self) -> Dict[str, Any]:
        """获取多币种配置"""
        return self.config_data.get("multi_symbol", {})
    
    def get_advanced_config(self) -> Dict[str, Any]:
        """获取高级配置"""
        return self.config_data.get("advanced", {})
    
    def save_config(self, config_data: Dict[str, Any] = None):
        """保存配置"""
        if config_data:
            self.config_data = config_data
        
        try:
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存配置
            with open(self.config_path, 'w', encoding='utf-8') as file:
                yaml.dump(self.config_data, file, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"配置已保存到: {self.config_path}")
            
        except Exception as e:
            raise RuntimeError(f"保存配置文件失败: {str(e)}")
    
    def export_config(self, export_path: str, format: str = "yaml"):
        """导出配置"""
        export_path = Path(export_path)
        
        try:
            if format.lower() == "yaml":
                with open(export_path, 'w', encoding='utf-8') as file:
                    yaml.dump(self.config_data, file, default_flow_style=False, allow_unicode=True)
            
            elif format.lower() == "json":
                with open(export_path, 'w', encoding='utf-8') as file:
                    json.dump(self.config_data, file, indent=2, ensure_ascii=False)
            
            else:
                raise ValueError(f"不支持的导出格式: {format}")
            
            logger.info(f"配置已导出到: {export_path}")
            
        except Exception as e:
            raise RuntimeError(f"导出配置文件失败: {str(e)}")
    
    def create_default_config(self):
        """创建默认配置"""
        from .strategy_config import DEFAULT_CONFIG
        
        self.config_data = DEFAULT_CONFIG.copy()
        self.save_config()
        
        logger.info(f"默认配置已创建: {self.config_path}")
        return self.config_data
    
    def update_strategy_config(self, strategy_name: str, updates: Dict[str, Any]):
        """更新策略配置"""
        strategies = self.config_data.get("strategies", [])
        
        for i, strategy in enumerate(strategies):
            if strategy.get("name") == strategy_name:
                # 更新配置
                strategies[i].update(updates)
                
                # 验证更新后的配置
                strategy_obj = self._create_strategy_config(strategies[i])
                validation_result = validate_strategy_config(strategy_obj)
                
                if not validation_result["valid"]:
                    raise ValueError(f"策略配置更新验证失败: {validation_result['errors']}")
                
                # 保存配置
                self.save_config()
                
                logger.info(f"策略配置已更新: {strategy_name}")
                return True
        
        raise ValueError(f"未找到策略: {strategy_name}")
    
    def enable_strategy(self, strategy_name: str, enabled: bool = True):
        """启用/禁用策略"""
        return self.update_strategy_config(strategy_name, {"enabled": enabled})
    
    def add_strategy(self, strategy_config: Dict[str, Any]):
        """添加新策略"""
        # 验证策略配置
        strategy_obj = self._create_strategy_config(strategy_config)
        validation_result = validate_strategy_config(strategy_obj)
        
        if not validation_result["valid"]:
            raise ValueError(f"新策略配置验证失败: {validation_result['errors']}")
        
        # 添加到配置
        if "strategies" not in self.config_data:
            self.config_data["strategies"] = []
        
        self.config_data["strategies"].append(strategy_config)
        
        # 保存配置
        self.save_config()
        
        logger.info(f"新策略已添加: {strategy_config.get('name', 'Unknown')}")
    
    def remove_strategy(self, strategy_name: str):
        """移除策略"""
        strategies = self.config_data.get("strategies", [])
        
        for i, strategy in enumerate(strategies):
            if strategy.get("name") == strategy_name:
                del strategies[i]
                
                # 保存配置
                self.save_config()
                
                logger.info(f"策略已移除: {strategy_name}")
                return True
        
        raise ValueError(f"未找到策略: {strategy_name}")
    
    def get_strategy_names(self) -> List[str]:
        """获取策略名称列表"""
        strategies = self.config_data.get("strategies", [])
        return [strategy.get("name", f"strategy_{i}") for i, strategy in enumerate(strategies)]
    
    def get_enabled_strategies(self) -> List[StrategyConfig]:
        """获取启用的策略列表"""
        all_strategies = self.get_strategies_config()
        return [strategy for strategy in all_strategies if strategy.enabled]
    
    def validate_all_strategies(self) -> Dict[str, Any]:
        """验证所有策略配置"""
        results = {}
        strategies = self.get_strategies_config()
        
        for strategy in strategies:
            validation_result = validate_strategy_config(strategy)
            results[strategy.name] = validation_result
        
        return results


def load_config(config_path: str = "config.yaml") -> ConfigLoader:
    """加载配置文件"""
    loader = ConfigLoader(config_path)
    loader.load_config()
    return loader


def create_default_config(config_path: str = "config.yaml"):
    """创建默认配置文件"""
    loader = ConfigLoader(config_path)
    loader.create_default_config()
    return loader