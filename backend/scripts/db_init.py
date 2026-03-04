#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化模块
创建 SQLite 数据库和表结构
"""

import sqlite3
import os
from pathlib import Path

class DatabaseInitializer:
    """数据库初始化器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    def init_database(self):
        """初始化数据库，创建所有表"""
        # 确保目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 1. 市场情绪日统计表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_sentiment (
            trade_date TEXT PRIMARY KEY,
            limit_up_count INTEGER,
            limit_down_count INTEGER,
            broken_board_count INTEGER,
            max_streak INTEGER,
            sh_index_change REAL,
            sz_index_change REAL,
            cy_index_change REAL,
            kc_index_change REAL,
            total_turnover REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 2. 个股日行情表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            market TEXT,
            open_price REAL,
            high_price REAL,
            low_price REAL,
            close_price REAL,
            pre_close REAL,
            change_amount REAL,
            change_percent REAL,
            volume INTEGER,
            turnover REAL,
            turnover_rate REAL,
            is_limit_up INTEGER DEFAULT 0,
            is_limit_down INTEGER DEFAULT 0,
            limit_up_time TEXT,
            streak_days INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, stock_code)
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_daily_date ON stock_daily(trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_daily_code ON stock_daily(stock_code)')
        
        # 3. 个股分时数据表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_intraday (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            trade_time TEXT NOT NULL,
            price REAL,
            change_percent REAL,
            volume INTEGER,
            turnover REAL,
            avg_price REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, stock_code, trade_time)
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_intraday_date_code ON stock_intraday(trade_date, stock_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_intraday_time ON stock_intraday(trade_time)')
        
        # 4. 股票基本信息表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_info (
            stock_code TEXT PRIMARY KEY,
            stock_name TEXT,
            market TEXT,
            board_type TEXT,
            industry TEXT,
            sub_industry TEXT,
            list_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 5. 概念题材配置表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_concept (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            concept_name TEXT NOT NULL,
            is_core INTEGER DEFAULT 0,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, concept_name)
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_concept_stock ON stock_concept(stock_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_concept_name ON stock_concept(concept_name)')
        
        # 6. 概念日统计表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS concept_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            concept_name TEXT NOT NULL,
            stock_count INTEGER,
            limit_up_count INTEGER,
            avg_change REAL,
            total_turnover REAL,
            leader_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, concept_name)
        )
        ''')
        
        # 7. 异动记录表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            event_date TEXT NOT NULL,
            event_type TEXT,
            event_desc TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_code ON stock_events(stock_code)')
        
        # 8. 股票池配置表（新增）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_pool (
            stock_code TEXT PRIMARY KEY,
            stock_name TEXT NOT NULL,
            market TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            added_date TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 9. 概念层级表（新增）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS concept_hierarchy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_name TEXT UNIQUE NOT NULL,
            parent_concept TEXT,
            description TEXT,
            position_in_chain TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_parent_concept ON concept_hierarchy(parent_concept)')
        
        # 10. 竞价数据表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_auction (
            trade_date TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            open_vol INTEGER,
            open_amount REAL,
            open_vwap REAL,
            close_vol INTEGER,
            close_amount REAL,
            close_vwap REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, stock_code)
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_auction_date ON stock_auction(trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_auction_code ON stock_auction(stock_code)')
        
        # 11. 同花顺概念列表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ths_concept (
            ts_code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            concept_type TEXT,
            component_count INTEGER,
            list_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 12. 同花顺概念成分股
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ths_concept_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_code TEXT NOT NULL,
            concept_name TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(concept_code, stock_code)
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_member_concept ON ths_concept_member(concept_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_member_stock ON ths_concept_member(stock_code)')
        
        # 13. 同花顺概念日行情
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ths_concept_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            concept_code TEXT NOT NULL,
            concept_name TEXT,
            pre_close REAL,
            open REAL,
            close REAL,
            high REAL,
            low REAL,
            pct_change REAL,
            vol REAL,
            turnover_rate REAL,
            total_mv REAL,
            float_mv REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, concept_code)
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_concept_daily_date ON ths_concept_daily(trade_date)')
        
        # 14. 同花顺个股热榜
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ths_hot_rank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            rank_time TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            ts_name TEXT,
            rank INTEGER,
            hot REAL,
            pct_change REAL,
            current_price REAL,
            concept TEXT,
            rank_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, rank_time, ts_code)
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_hot_rank_date ON ths_hot_rank(trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_hot_rank_stock ON ths_hot_rank(ts_code)')
        
        # 15. 同花顺涨跌停榜单（连板天梯）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ths_limit_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            ts_name TEXT,
            price REAL,
            pct_chg REAL,
            limit_type TEXT NOT NULL,
            tag TEXT,
            status TEXT,
            lu_desc TEXT,
            open_num INTEGER,
            first_lu_time TEXT,
            last_lu_time TEXT,
            limit_order REAL,
            limit_amount REAL,
            lu_limit_order REAL,
            turnover_rate REAL,
            turnover REAL,
            free_float REAL,
            sum_float REAL,
            limit_up_suc_rate REAL,
            market_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, ts_code, limit_type)
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_limit_date ON ths_limit_list(trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_limit_stock ON ths_limit_list(ts_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_limit_type ON ths_limit_list(limit_type)')
        
        conn.commit()
        conn.close()
        
        print(f"✅ 数据库初始化完成: {self.db_path}")
        
    def reset_database(self):
        """重置数据库（删除所有表并重新创建）"""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            print(f"🗑️  已删除旧数据库: {self.db_path}")
        self.init_database()


def main():
    """命令行入口"""
    import sys
    
    # 默认数据库路径
    script_dir = Path(__file__).parent
    # 计算项目根目录（需要往上3层）
    project_root = script_dir.parent.parent.parent
    db_path = project_root / "data" / "dragon_stock.db"
    
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        initializer = DatabaseInitializer(str(db_path))
        initializer.reset_database()
    else:
        initializer = DatabaseInitializer(str(db_path))
        initializer.init_database()


if __name__ == "__main__":
    main()
