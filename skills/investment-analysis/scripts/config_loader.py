#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置加载器 - 简化版
用于 investment-analysis skill 的配置管理
"""

import os
from pathlib import Path


class ConfigLoader:
    """配置加载器（简化版）"""
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_tushare_token(self) -> str:
        """
        获取Tushare token
        优先级：环境变量 > ~/.tushare_token 文件
        """
        # 1. 尝试从环境变量读取
        token = os.getenv('TUSHARE_TOKEN')
        if token:
            return token
        
        # 2. 尝试从用户目录读取
        token_file = Path.home() / '.tushare_token'
        if token_file.exists():
            with open(token_file, 'r') as f:
                return f.read().strip()
        
        # 3. 尝试从dragon-stock-trading的config.yaml读取
        try:
            import yaml
            config_file = Path(__file__).parent.parent.parent / 'dragon-stock-trading' / 'config.yaml'
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    token = config.get('tushare', {}).get('token', '')
                    if token and not token.startswith('${'):  # 排除环境变量占位符
                        return token
        except:
            pass
        
        return ''
    
    def get_tushare_base_url(self) -> str:
        """获取Tushare基础URL（高积分用户专用）"""
        return 'http://tushare.xyz'


# 全局配置实例
config = ConfigLoader()


def main():
    """测试配置加载"""
    print("=" * 60)
    print("Tushare配置测试")
    print("=" * 60)
    
    token = config.get_tushare_token()
    if token:
        print(f"✅ Tushare Token: {token[:20]}...")
        print(f"✅ Base URL: {config.get_tushare_base_url()}")
    else:
        print("❌ 未找到Tushare Token")
        print("\n请设置token:")
        print("  方法1: export TUSHARE_TOKEN='your_token'")
        print("  方法2: echo 'your_token' > ~/.tushare_token")


if __name__ == "__main__":
    main()
