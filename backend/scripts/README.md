# Backend Scripts

后端工具脚本集合 - 用于数据库管理和数据迁移

## 脚本列表

### 1. db_init.py

**功能**: 初始化SQLite数据库，创建所有表结构

**用法**:
```bash
# 初始化数据库（如果表已存在则跳过）
python backend/scripts/db_init.py

# 重置数据库（删除旧表并重建）
python backend/scripts/db_init.py --reset
```

**包含的表**:
- `market_sentiment` - 市场情绪数据
- `stock_daily` - 个股日行情
- `stock_info` - 股票基本信息
- `stock_concept` - 股票概念关系
- `concept_daily` - 概念日统计
- `stock_events` - 异动记录
- `stock_pool` - 股票池配置
- `concept_hierarchy` - 概念层级

### 2. migrate_json_to_db.py

**功能**: 将JSON配置文件迁移到SQLite数据库

**迁移内容**:
- `data/stock_list.json` → `stock_pool` 表
- `data/concepts.json` → `concept_hierarchy` 表

**用法**:
```bash
python backend/scripts/migrate_json_to_db.py
```

**输出示例**:
```
============================================================
数据迁移工具：JSON -> SQLite
============================================================

📥 开始迁移股票池数据...
  ✅ 成功迁移 149/149 只股票

📥 开始迁移概念层级数据...
  ✅ 成功迁移 9 个顶级概念
  ✅ 成功迁移 44 个子概念

✅ 数据迁移完成！
```

## 使用场景

### 场景1: 首次部署

```bash
cd /path/to/stock

# 1. 初始化数据库
python backend/scripts/db_init.py

# 2. 迁移JSON数据
python backend/scripts/migrate_json_to_db.py

# 3. 启动后端服务
cd backend
uvicorn app.main:app --reload
```

### 场景2: 数据库Schema更新

```bash
# 重置并重建数据库
python backend/scripts/db_init.py --reset

# 重新迁移数据
python backend/scripts/migrate_json_to_db.py
```

### 场景3: 数据恢复

如果数据库损坏：
```bash
# 删除旧数据库
rm data/dragon_stock.db

# 初始化
python backend/scripts/db_init.py

# 从JSON备份恢复
python backend/scripts/migrate_json_to_db.py
```

## 注意事项

1. **数据库位置**: 脚本操作 `data/dragon_stock.db`
2. **JSON备份**: JSON文件作为备份保留，数据库是主数据源
3. **权限要求**: 需要对 `data/` 目录有读写权限
4. **依赖关系**: `migrate_json_to_db.py` 依赖 `db_init.py`

## 架构原则

这些脚本遵循"API优先"架构原则：
- ✅ 位于 `backend/scripts/` - 属于后端职责
- ✅ 直接操作数据库 - 后端是唯一数据访问层
- ✅ 供系统管理员使用 - 不对外暴露API
