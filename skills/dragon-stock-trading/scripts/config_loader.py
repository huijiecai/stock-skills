#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置加载器
统一读取和管理 config.yaml 配置
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any


class ConfigLoader:
    """配置加载器"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化配置"""
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        # 获取配置文件路径（尝试多个可能的位置）
        script_dir = Path(__file__).resolve().parent
        config_file = script_dir.parent / "config.yaml"
        
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_file}")
        
        # 读取 YAML
        with open(config_file, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
        
        # 处理环境变量替换
        self._process_env_vars(self._config)
    
    def get_tushare_token(self) -> str:
        """获取Tushare token"""
        return self._config.get('tushare', {}).get('token', '')
    
    def get_tushare_base_url(self) -> str:
        """获取Tushare基础URL"""
        return self._config.get('tushare', {}).get('base_url', 'http://api.tushare.pro')
    
    def get_tushare_timeout(self) -> int:
        """获取Tushare超时时间"""
        return self._config.get('tushare', {}).get('timeout', 30)
    
    # 兼容旧的iTock方法名（已废弃，建议使用Tushare方法）
    def get_itick_api_key(self) -> str:
        """获取iTock API密钥（已废弃，请使用get_tushare_token）"""
        return self.get_tushare_token()
    
    def get_itick_base_url(self) -> str:
        """获取iTock基础URL（已废弃，请使用get_tushare_base_url）"""
        return self.get_tushare_base_url()
    
    def get_itick_timeout(self) -> int:
        """获取iTock超时时间（已废弃，请使用get_tushare_timeout）"""
    def _process_env_vars(self, config: Dict):
        """递归处理环境变量"""
        for key, value in config.items():
            if isinstance(value, dict):
                self._process_env_vars(value)
            elif isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                # 提取环境变量名
                env_var = value[2:-1]
                # 替换为环境变量值
                env_value = os.getenv(env_var)
                if env_value:
                    config[key] = env_value
                else:
                    # 如果环境变量不存在，使用默认值（Tushare token）
                    if env_var == 'TUSHARE_TOKEN':
                        config[key] = '2fcac3d55f4d1844d0bd4e4b8d205003b947a625b596767c697d0e7b'
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key_path: 配置路径，用点分隔，如 'itick.api_key'
            default: 默认值
        
        Returns:
            配置值
        """
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_db_path(self) -> str:
        """获取数据库路径"""
        return self.get('data.db_path', './data/dragon_stock.db')
    
    def get_itick_api_key(self) -> str:
        """获取 itick API key"""
        return self.get('itick.api_key', '')
    
    def get_itick_base_url(self) -> str:
        """获取 itick API base URL"""
        return self.get('itick.base_url', 'https://api.itick.io')
    
    def get_itick_timeout(self) -> int:
        """获取 itick API 超时时间"""
        return self.get('itick.timeout', 10)
    
    def get_limit_up_threshold(self, board_type: str) -> float:
        """
        获取涨停阈值
        
        Args:
            board_type: 板块类型 ('main_board', 'growth_board', 'st_stock')
        
        Returns:
            涨停阈值
        """
        return self.get(f'limit_up.{board_type}', 0.099)
    
    def reload(self):
        """重新加载配置"""
        self._config = None
        self._load_config()


# 全局配置实例
config = ConfigLoader()


def main():
    """测试配置加载"""
    print("="*60)
    print("配置加载测试")
    print("="*60)
    
    print(f"\n数据库路径: {config.get_db_path()}")
    print(f"itick API Key: {config.get_itick_api_key()[:20]}...")
    print(f"itick Base URL: {config.get_itick_base_url()}")
    print(f"itick Timeout: {config.get_itick_timeout()}s")
    
    print(f"\n涨停阈值:")
    print(f"  主板: {config.get_limit_up_threshold('main_board')*100}%")
    print(f"  创业板: {config.get_limit_up_threshold('growth_board')*100}%")
    print(f"  ST股票: {config.get_limit_up_threshold('st_stock')*100}%")
    
    print("\n✅ 配置加载成功！")


if __name__ == "__main__":
    main()
