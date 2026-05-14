"""
jstock 量化数据中心 - 配置
"""
import os

# PostgreSQL 连接 (使用 Docker 容器，与 backend 共用)
DB_CONFIG = {
    "host": os.getenv("JSTOCK_DB_HOST", "localhost"),
    "port": int(os.getenv("JSTOCK_DB_PORT", "5432")),
    "dbname": os.getenv("JSTOCK_DB_NAME", "jstock"),
    "user": os.getenv("JSTOCK_DB_USER", "postgres"),
    "password": os.getenv("JSTOCK_DB_PASS", "password"),
}

# 数据保留天数
RETENTION_DAYS = 30

# 主要指数
INDICES = [
    ("000001", "上证指数"),
    ("399001", "深证成指"),
    ("399006", "创业板指"),
    ("000688", "科创50"),
]
