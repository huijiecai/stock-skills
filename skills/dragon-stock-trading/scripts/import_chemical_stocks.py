#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导入化工股票到数据库
"""

import sys
from pathlib import Path

# 添加 scripts 目录到路径
script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(script_dir))

from stock_concept_manager import StockConceptManager


def main():
    """批量导入化工股票-概念关系"""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    db_path = project_root / "data" / "dragon_stock.db"
    
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        return
    
    manager = StockConceptManager(str(db_path))
    
    print("=" * 60)
    print("批量导入化工股票-概念关系")
    print("=" * 60)
    
    # 1. 玻纤类
    print("\n【玻纤】")
    boqian_stocks = [
        ('600176', '玻纤', True, '化工/玻纤'),   # 中国巨石 - 龙头
        ('605006', '玻纤', False, '化工/玻纤'),  # 山东玻纤
        ('301526', '玻纤', False, '化工/玻纤'),  # 国际复材
    ]
    manager.batch_add_stocks(boqian_stocks)
    
    # 2. 磷化工
    print("\n【磷化工】")
    lin_stocks = [
        ('600096', '磷化工', True, '化工/磷化工'),   # 云天化 - 龙头
        ('000422', '磷化工', True, '化工/磷化工'),   # 湖北宜化
    ]
    manager.batch_add_stocks(lin_stocks)
    
    # 3. 氟化工
    print("\n【氟化工】")
    fu_stocks = [
        ('600722', '氟化工', False, '化工/氟化工'),  # 金牛化工
    ]
    manager.batch_add_stocks(fu_stocks)
    
    # 4. 染料化工
    print("\n【染料化工】")
    ranliao_stocks = [
        ('002440', '染料化工', True, '化工/染料化工'),   # 闰土股份 - 龙头
        ('002455', '染料化工', False, '化工/染料化工'),  # 百川股份
        ('002054', '染料化工', False, '化工/染料化工'),  # 德美化工
        ('002809', '染料化工', False, '化工/染料化工'),  # 红墙股份
    ]
    manager.batch_add_stocks(ranliao_stocks)
    
    # 5. 聚氨酯
    print("\n【聚氨酯】")
    juanzhi_stocks = [
        ('600309', '聚氨酯', True, '化工/聚氨酯'),   # 万华化学 - 龙头
        ('600230', '聚氨酯', False, '化工/聚氨酯'),  # 沧州大化
        ('002165', '聚氨酯', False, '化工/聚氨酯'),  # 红宝丽
    ]
    manager.batch_add_stocks(juanzhi_stocks)
    
    print("\n" + "=" * 60)
    print("✅ 化工股票导入完成！")
    print("=" * 60)
    
    # 查看所有化工概念的股票
    print("\n【查看各概念下的股票】")
    for concept in ['玻纤', '磷化工', '氟化工', '染料化工', '聚氨酯']:
        stocks = manager.list_concept_stocks(concept)
        print(f"\n{concept} ({len(stocks)}只):")
        for stock in stocks:
            core_label = "核心" if stock['is_core'] else "相关"
            print(f"  - {stock['stock_code']} ({core_label})")


if __name__ == "__main__":
    main()
