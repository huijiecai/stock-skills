# 数据库管理指南

## 📁 文件结构

```
data/
├── dragon_stock.db          # SQLite数据库文件（已加入.gitignore）
├── exports/                 # 可版本控制的导出数据
│   ├── stock_pool.json     # 股票池配置
│   └── concepts.json       # 概念配置
└── config.yaml             # 系统配置
```

## 🚫 为什么数据库文件不提交到Git？

1. **文件体积大** - `.db`文件通常几十MB到几百MB
2. **频繁变更** - 每次数据更新都会改变整个二进制文件
3. **无法diff** - Git无法有效比较二进制文件的差异
4. **合并冲突** - 多人同时修改会产生不可解决的冲突
5. **传输效率低** - 每次小改动都需要上传整个文件

## ✅ 替代方案

### 1. 数据库结构版本控制
数据库表结构通过 [`db_init.py`](../backend/scripts/db_init.py) 脚本管理：
```bash
# 初始化/重建数据库结构
python backend/scripts/db_init.py
```

### 2. 配置数据版本控制
重要的配置数据导出为JSON格式，可以提交到Git：

```bash
# 导出数据（供版本控制）
python backend/scripts/export_data.py export

# 导入数据（新环境初始化）
python backend/scripts/export_data.py import
```

### 3. 团队协作流程

**首次设置新环境：**
```bash
# 1. 克隆代码
git clone <repository>
cd stock

# 2. 初始化数据库结构
python backend/scripts/db_init.py

# 3. 导入配置数据
python backend/scripts/export_data.py import

# 4. 采集实时数据（可选）
python skills/dragon-stock-trading/scripts/collect_market_data.py
```

**更新配置数据：**
```bash
# 1. 修改配置后导出
python backend/scripts/export_data.py export

# 2. 提交JSON文件
git add data/exports/
git commit -m "update: 配置数据更新"
git push
```

## 📊 导出的数据内容

### `stock_pool.json`
- 股票代码、名称、市场、板块类型
- 用于初始化股票池

### `concepts.json`  
- 概念层级结构
- 股票与概念的关联关系
- 核心股票标记

## 🔧 开发规范

1. **永远不要手动修改`.db`文件**
2. **配置变更应通过JSON文件进行**
3. **新功能需要时更新`db_init.py`**
4. **定期导出重要配置数据**

## 🔄 数据同步

对于生产环境数据同步，建议：
1. 使用专业的数据库备份工具
2. 定期快照备份
3. 增量数据同步方案
4. 主从复制架构

---
*此方案平衡了开发便利性和版本控制需求*