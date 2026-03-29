# 数据存储目录

## 文件结构

```
data/
├── postgres/              # PostgreSQL 数据库文件（Docker 挂载）
├── exports/               # 导出数据
│   ├── concepts.json     # 概念配置
│   └── stock_pool.json   # 股票池配置
└── README.md
```

## 数据库说明

项目已升级为 PostgreSQL 数据库：

- 数据存储在 `data/postgres/` 目录下
- 由 Docker 容器管理
- 即使容器重启，数据依然保留

## 数据初始化

```bash
# 1. 启动 PostgreSQL 容器
cd backend
docker-compose up -d

# 2. 初始化数据库表结构
python scripts/pg_init.py
```

## 数据采集

```bash
# 触发全量采集
curl -X POST http://localhost:8000/api/collector/trigger/all
```

## 数据备份

```bash
# 导出数据库
docker exec stock_postgres pg_dump -U postgres stock > data/backup.sql

# 导入数据库
docker exec -i stock_postgres psql -U postgres stock < data/backup.sql
```

---
*PostgreSQL 版本 15 | 数据持久化存储