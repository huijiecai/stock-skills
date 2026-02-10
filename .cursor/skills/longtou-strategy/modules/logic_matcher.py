"""
逻辑匹配模块
负责读取逻辑库，匹配股票逻辑
"""

import yaml
import os
from typing import Dict, List, Optional, Tuple


class LogicMatcher:
    """逻辑匹配器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化逻辑匹配器
        
        Args:
            config_path: 逻辑库配置文件路径
        """
        if config_path is None:
            # 默认路径：skill根目录的 logics.yaml
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(
                current_dir, 
                "..", 
                "logics.yaml"
            )
        
        self.config_path = config_path
        self.logics = self._load_logic_library()
    
    def _load_logic_library(self) -> List[Dict]:
        """
        加载逻辑库
        
        Returns:
            List[Dict]: 逻辑列表
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logics = config.get('逻辑库', [])
                print(f"✅ 逻辑库加载成功：{len(logics)} 个逻辑")
                return logics
        except FileNotFoundError:
            print(f"❌ 逻辑库文件不存在：{self.config_path}")
            return []
        except Exception as e:
            print(f"❌ 逻辑库加载失败：{e}")
            return []
    
    def match_logic(self, stock_concepts: List[str]) -> Optional[Dict]:
        """
        匹配股票逻辑
        
        Args:
            stock_concepts: 股票概念列表
            
        Returns:
            Dict: 匹配到的逻辑信息，如果没有匹配返回None
        """
        if not stock_concepts:
            return None
        
        # 遍历逻辑库
        for logic in self.logics:
            logic_concepts = logic.get('相关概念', [])
            
            # 检查是否有概念匹配
            matched_concepts = set(stock_concepts) & set(logic_concepts)
            
            if matched_concepts:
                # 返回匹配结果
                return {
                    '名称': logic.get('名称'),
                    '英文名': logic.get('英文名'),
                    '龙头股票': logic.get('龙头股票'),
                    '龙头代码': logic.get('龙头代码'),
                    '炒作原因': logic.get('炒作原因'),
                    '催化剂': logic.get('催化剂'),
                    '逻辑强度': logic.get('逻辑强度'),
                    '持续性': logic.get('持续性'),
                    '驱动类型': logic.get('驱动类型'),
                    '推荐模式': logic.get('推荐模式', []),
                    '风险提示': logic.get('风险提示'),
                    '匹配概念': list(matched_concepts),
                    '受益股票': logic.get('受益股票', {})
                }
        
        return None
    
    def is_core_beneficiary(self, stock_name: str, logic_name: str) -> Tuple[bool, str]:
        """
        判断股票是否是逻辑的核心受益方
        
        Args:
            stock_name: 股票名称
            logic_name: 逻辑名称
            
        Returns:
            Tuple[bool, str]: (是否核心受益方, 受益等级：核心/次核心/蹭热点/未知)
        """
        # 查找对应逻辑
        for logic in self.logics:
            if logic.get('名称') == logic_name:
                beneficiaries = logic.get('受益股票', {})
                
                # 检查核心受益
                core = beneficiaries.get('核心', {})
                if stock_name in core:
                    return True, "核心"
                
                # 检查次核心受益
                secondary = beneficiaries.get('次核心', {})
                if stock_name in secondary:
                    return True, "次核心"
                
                # 检查蹭热点
                fake = beneficiaries.get('蹭热点', [])
                if stock_name in fake:
                    return False, "蹭热点"
        
        return False, "未知"
    
    def get_logic_by_name(self, logic_name: str) -> Optional[Dict]:
        """
        根据逻辑名称获取逻辑详情
        
        Args:
            logic_name: 逻辑名称
            
        Returns:
            Dict: 逻辑详情
        """
        for logic in self.logics:
            if logic.get('名称') == logic_name:
                return logic
        return None
    
    def get_all_logics(self) -> List[Dict]:
        """
        获取所有逻辑
        
        Returns:
            List[Dict]: 逻辑列表
        """
        return self.logics
    
    def format_logic_strength(self, strength: int) -> str:
        """
        格式化逻辑强度显示
        
        Args:
            strength: 逻辑强度（1-5）
            
        Returns:
            str: 星级显示
        """
        return "⭐" * strength


if __name__ == "__main__":
    # 测试代码
    matcher = LogicMatcher()
    
    print("\n=== 测试1: 匹配稳定币逻辑 ===")
    concepts1 = ["数字货币", "区块链", "金融IC卡"]
    result1 = matcher.match_logic(concepts1)
    if result1:
        print(f"匹配逻辑：{result1['名称']}")
        print(f"逻辑强度：{matcher.format_logic_strength(result1['逻辑强度'])}")
        print(f"匹配概念：{result1['匹配概念']}")
    
    print("\n=== 测试2: 匹配液冷散热逻辑 ===")
    concepts2 = ["液冷", "数据中心"]
    result2 = matcher.match_logic(concepts2)
    if result2:
        print(f"匹配逻辑：{result2['名称']}")
        print(f"逻辑强度：{matcher.format_logic_strength(result2['逻辑强度'])}")
    
    print("\n=== 测试3: 判断受益方 ===")
    is_core, level = matcher.is_core_beneficiary("恒宝股份", "稳定币")
    print(f"恒宝股份是否核心受益方：{is_core}，等级：{level}")
    
    print("\n=== 测试4: 获取所有逻辑 ===")
    all_logics = matcher.get_all_logics()
    print(f"当前逻辑库共 {len(all_logics)} 个逻辑：")
    for logic in all_logics:
        print(f"  - {logic['名称']} ({matcher.format_logic_strength(logic['逻辑强度'])})")
