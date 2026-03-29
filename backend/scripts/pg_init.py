#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL 数据库初始化脚本

创建所有表结构、索引、插入基础数据

使用方法:
    python scripts/pg_init.py
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.core.database import engine, Base
from app.core.logger import setup_logging, get_logger

logger = get_logger(__name__)


# SQL 建表语句
CREATE_TABLES_SQL = """
-- 1. 股票基本信息
CREATE TABLE IF NOT EXISTS stock_info (
    stock_code VARCHAR(10) PRIMARY KEY,
    stock_name VARCHAR(20) NOT NULL,
    industry VARCHAR(20),
    list_date DATE,
    market VARCHAR(10),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 股票日线行情
CREATE TABLE IF NOT EXISTS stock_daily (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    open_price DECIMAL(10,2),
    close_price DECIMAL(10,2),
    high_price DECIMAL(10,2),
    low_price DECIMAL(10,2),
    change_pct DECIMAL(8,4),
    volume BIGINT,
    amount DECIMAL(20,2),
    turnover_rate DECIMAL(8,4),
    turnover_rate_f DECIMAL(8,4),
    UNIQUE(trade_date, stock_code)
);

-- 3. 股票分时行情
CREATE TABLE IF NOT EXISTS stock_intraday (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    trade_time TIME NOT NULL,
    price DECIMAL(10,2),
    change_pct DECIMAL(8,4),
    volume BIGINT,
    amount DECIMAL(20,2),
    avg_price DECIMAL(10,2),
    UNIQUE(trade_date, stock_code, trade_time)
);

-- 4. 指数日线
CREATE TABLE IF NOT EXISTS index_daily (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    index_code VARCHAR(10) NOT NULL,
    index_name VARCHAR(20),
    open_price DECIMAL(10,2),
    close_price DECIMAL(10,2),
    high_price DECIMAL(10,2),
    low_price DECIMAL(10,2),
    change_pct DECIMAL(8,4),
    volume BIGINT,
    amount DECIMAL(20,2),
    UNIQUE(trade_date, index_code)
);

-- 5. 指数分时
CREATE TABLE IF NOT EXISTS index_intraday (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    index_code VARCHAR(10) NOT NULL,
    trade_time TIME NOT NULL,
    price DECIMAL(10,2),
    change_pct DECIMAL(8,4),
    volume BIGINT,
    amount DECIMAL(20,2),
    UNIQUE(trade_date, index_code, trade_time)
);

-- 6. 东方财富概念板块信息
CREATE TABLE IF NOT EXISTS concept_info_east (
    concept_code VARCHAR(20) PRIMARY KEY,
    concept_name VARCHAR(50) NOT NULL,
    component_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. 同花顺概念板块信息（预留）
CREATE TABLE IF NOT EXISTS concept_info_ths (
    concept_code VARCHAR(20) PRIMARY KEY,
    concept_name VARCHAR(50) NOT NULL,
    index_code VARCHAR(10),
    component_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. 东方财富概念板块日线
CREATE TABLE IF NOT EXISTS concept_daily_east (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    concept_code VARCHAR(20) NOT NULL,
    open_price DECIMAL(10,2),
    close_price DECIMAL(10,2),
    high_price DECIMAL(10,2),
    low_price DECIMAL(10,2),
    change_pct DECIMAL(8,4),
    volume BIGINT,
    amount DECIMAL(20,2),
    UNIQUE(trade_date, concept_code)
);

-- 9. 东方财富概念板块分时
CREATE TABLE IF NOT EXISTS concept_intraday_east (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    concept_code VARCHAR(20) NOT NULL,
    trade_time TIME NOT NULL,
    price DECIMAL(10,2),
    change_pct DECIMAL(8,4),
    volume BIGINT,
    amount DECIMAL(20,2),
    UNIQUE(trade_date, concept_code, trade_time)
);

-- 10. 东方财富个股概念映射
CREATE TABLE IF NOT EXISTS stock_concept_mapping_east (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    concept_code VARCHAR(20) NOT NULL,
    is_core BOOLEAN DEFAULT FALSE,
    reason TEXT,
    UNIQUE(stock_code, concept_code)
);

-- 11. 同花顺个股概念映射（预留）
CREATE TABLE IF NOT EXISTS stock_concept_mapping_ths (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    concept_code VARCHAR(20) NOT NULL,
    is_core BOOLEAN DEFAULT FALSE,
    reason TEXT,
    UNIQUE(stock_code, concept_code)
);

-- 12. 资金流向
CREATE TABLE IF NOT EXISTS capital_flow (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    main_net_inflow DECIMAL(20,2),
    main_net_inflow_pct DECIMAL(8,4),
    retail_net_inflow DECIMAL(20,2),
    retail_net_inflow_pct DECIMAL(8,4),
    super_net_inflow DECIMAL(20,2),
    big_net_inflow DECIMAL(20,2),
    mid_net_inflow DECIMAL(20,2),
    small_net_inflow DECIMAL(20,2),
    UNIQUE(trade_date, stock_code)
);

-- 13. 涨跌停数据
CREATE TABLE IF NOT EXISTS limit_list (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(20),
    limit_type CHAR(1) NOT NULL,
    close_price DECIMAL(10,2),
    change_pct DECIMAL(8,4),
    first_time TIME,
    last_time TIME,
    open_times INTEGER DEFAULT 0,
    limit_times INTEGER DEFAULT 0,
    limit_amount DECIMAL(20,2),
    is_broken BOOLEAN DEFAULT FALSE,
    broken_time TIME,
    reseal_time TIME,
    UNIQUE(trade_date, stock_code, limit_type)
);

-- 14. 账户信息
CREATE TABLE IF NOT EXISTS account_info (
    id SERIAL PRIMARY KEY,
    account_name VARCHAR(50) NOT NULL,
    initial_capital DECIMAL(20,2),
    available_cash DECIMAL(20,2),
    market_value DECIMAL(20,2),
    total_asset DECIMAL(20,2),
    total_profit DECIMAL(20,2),
    total_profit_pct DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. 持仓记录
CREATE TABLE IF NOT EXISTS position (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(20),
    quantity INTEGER DEFAULT 0,
    available INTEGER DEFAULT 0,
    cost_price DECIMAL(10,2),
    current_price DECIMAL(10,2),
    market_value DECIMAL(20,2),
    profit DECIMAL(20,2),
    profit_pct DECIMAL(8,4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 16. 交易记录
CREATE TABLE IF NOT EXISTS trade_record (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(30) NOT NULL,
    account_id INTEGER NOT NULL,
    trade_time TIMESTAMP NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(20),
    action VARCHAR(10) NOT NULL,
    price DECIMAL(10,2),
    quantity INTEGER,
    amount DECIMAL(20,2),
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 17. 账户每日快照
CREATE TABLE IF NOT EXISTS account_snapshot (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    total_asset DECIMAL(20,2),
    available_cash DECIMAL(20,2),
    market_value DECIMAL(20,2),
    daily_profit DECIMAL(20,2),
    daily_profit_pct DECIMAL(8,4),
    positions JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, snapshot_date)
);
"""

# 创建索引
CREATE_INDEXES_SQL = """
-- stock_daily 索引
CREATE INDEX IF NOT EXISTS idx_stock_daily_date ON stock_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_stock_daily_code ON stock_daily(stock_code);

-- stock_intraday 索引
CREATE INDEX IF NOT EXISTS idx_stock_intraday ON stock_intraday(trade_date, stock_code);

-- index_daily 索引
CREATE INDEX IF NOT EXISTS idx_index_daily_date ON index_daily(trade_date);

-- index_intraday 索引
CREATE INDEX IF NOT EXISTS idx_index_intraday ON index_intraday(trade_date, index_code);

-- concept_daily_east 索引
CREATE INDEX IF NOT EXISTS idx_concept_daily_east_date ON concept_daily_east(trade_date);
CREATE INDEX IF NOT EXISTS idx_concept_daily_east_code ON concept_daily_east(concept_code);

-- concept_intraday_east 索引
CREATE INDEX IF NOT EXISTS idx_concept_intraday_east ON concept_intraday_east(trade_date, concept_code);

-- stock_concept_mapping_east 索引
CREATE INDEX IF NOT EXISTS idx_stock_concept_east_stock ON stock_concept_mapping_east(stock_code);
CREATE INDEX IF NOT EXISTS idx_stock_concept_east_concept ON stock_concept_mapping_east(concept_code);

-- stock_concept_mapping_ths 索引
CREATE INDEX IF NOT EXISTS idx_stock_concept_ths_stock ON stock_concept_mapping_ths(stock_code);
CREATE INDEX IF NOT EXISTS idx_stock_concept_ths_concept ON stock_concept_mapping_ths(concept_code);

-- capital_flow 索引
CREATE INDEX IF NOT EXISTS idx_capital_flow_date ON capital_flow(trade_date);
CREATE INDEX IF NOT EXISTS idx_capital_flow_code ON capital_flow(stock_code);

-- limit_list 索引
CREATE INDEX IF NOT EXISTS idx_limit_list_date ON limit_list(trade_date);
CREATE INDEX IF NOT EXISTS idx_limit_list_type ON limit_list(limit_type);
CREATE INDEX IF NOT EXISTS idx_limit_list_times ON limit_list(limit_times);

-- position 索引
CREATE INDEX IF NOT EXISTS idx_position_account ON position(account_id);
CREATE INDEX IF NOT EXISTS idx_position_stock ON position(stock_code);

-- trade_record 索引
CREATE INDEX IF NOT EXISTS idx_trade_record_account ON trade_record(account_id);
CREATE INDEX IF NOT EXISTS idx_trade_record_time ON trade_record(trade_time);

-- account_snapshot 索引
CREATE INDEX IF NOT EXISTS idx_account_snapshot_account ON account_snapshot(account_id);
CREATE INDEX IF NOT EXISTS idx_account_snapshot_date ON account_snapshot(snapshot_date);
"""


def init_database():
    """初始化数据库"""
    logger.info("开始初始化数据库...")
    
    try:
        with engine.connect() as conn:
            # 创建表
            logger.info("创建表结构...")
            conn.execute(text(CREATE_TABLES_SQL))
            conn.commit()
            logger.info("✅ 表结构创建完成")
            
            # 创建索引
            logger.info("创建索引...")
            conn.execute(text(CREATE_INDEXES_SQL))
            conn.commit()
            logger.info("✅ 索引创建完成")
            
        logger.info("🎉 数据库初始化完成！")
        return True
        
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        return False


if __name__ == "__main__":
    setup_logging()
    success = init_database()
    sys.exit(0 if success else 1)
