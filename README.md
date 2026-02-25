# 龙头战法Web平台 - 完整项目

基于龙头战法理论的股票分析系统，包含数据采集、Web可视化平台和AI分析Skill。

## 项目架构

```
stock/
├── skills/dragon-stock-trading/    # Skill（AI分析模块）
│   ├── scripts/                    # 数据采集和查询脚本
│   │   ├── db_init.py             # 数据库初始化
│   │   ├── market_fetcher.py      # 市场数据采集
│   │   ├── query_service.py       # 数据查询服务
│   │   ├── concept_manager.py     # 概念管理
│   │   └── skill_api_client.py    # Skill API客户端（新）
│   ├── data/                       # 数据存储
│   │   ├── dragon_stock.db        # SQLite数据库
│   │   ├── concepts.json          # 概念层级配置
│   │   └── stock_list.json        # 股票池
│   └── SKILL.md                    # Skill说明文档
│
├── backend/                        # FastAPI后端（新）
│   ├── app/
│   │   ├── api/                   # REST API路由
│   │   │   ├── market.py          # 市场数据API
│   │   │   ├── stocks.py          # 股票管理API
│   │   │   ├── concepts.py        # 概念管理API
│   │   │   └── analysis.py        # 龙头分析API
│   │   ├── services/              # 业务逻辑层
│   │   │   ├── data_service.py
│   │   │   └── analysis_service.py
│   │   ├── models/                # 数据模型
│   │   └── main.py                # FastAPI应用入口
│   ├── requirements.txt
│   └── README.md
│
└── frontend/                       # React前端（新）
    ├── src/
    │   ├── pages/                 # 页面组件
    │   │   ├── Dashboard.js       # 市场总览
    │   │   ├── StockPool.js       # 股票池管理
    │   │   ├── ConceptManage.js   # 概念管理
    │   │   └── Analysis.js        # 龙头分析
    │   ├── services/
    │   │   └── api.js             # API封装
    │   ├── App.js
    │   └── index.js
    ├── package.json
    └── README.md
```

## 系统组成

### 1. 数据层（skills/dragon-stock-trading）
- **SQLite数据库**：存储历史行情、涨停数据、概念关系
- **数据采集脚本**：通过itick API获取实时数据
- **查询服务**：提供数据访问接口

### 2. 后端层（backend/）
- **FastAPI框架**：提供REST API
- **复用脚本模块**：直接导入skills中的Python模块
- **业务逻辑**：龙头战法分析算法

### 3. 前端层（frontend/）
- **React 18**：现代化SPA应用
- **Ant Design 5**：UI组件库
- **可视化**：ECharts图表、数据表格

### 4. AI层（skills/dragon-stock-trading/SKILL.md）
- **LLM Skill**：通过API Client访问数据
- **智能分析**：基于龙头战法理论的决策支持

## 快速开始

### 1. 安装依赖

```bash
# 后端依赖
cd backend
pip install -r requirements.txt

# 前端依赖
cd frontend
npm install
```

### 2. 初始化数据

```bash
cd skills/dragon-stock-trading/scripts

# 初始化数据库
python db_init.py

# 采集市场数据（示例：2026-02-25）
python market_fetcher.py 2026-02-25
```

### 3. 启动服务

**终端1 - 启动后端**：
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**终端2 - 启动前端**：
```bash
cd frontend
npm start
```

**访问应用**：
- 前端Web界面：http://localhost:3000
- 后端API文档：http://localhost:8000/docs

### 4. LLM Skill使用

在Cursor中与AI对话时，AI会自动通过API获取数据：

```
用户：分析002342是否符合龙头战法
AI：（自动调用 skill_api_client.analyze_stock()）
```

## 核心功能

### Web平台功能
1. **市场总览** - 实时市场情绪、人气榜、概念龙头
2. **股票池管理** - 添加/删除关注股票
3. **概念管理** - 可视化编辑概念层级和股票关系
4. **龙头分析** - 一键分析个股是否符合龙头标准

### Skill功能（AI）
1. **市场情绪判断** - 冰点/主升/正常
2. **个股人气分析** - 成交额排名
3. **逻辑正宗性评估** - 概念归属、核心标的
4. **龙头候选筛选** - 综合多维度指标
5. **操作建议生成** - 买入/观望决策

## 数据流

```
itick API → 数据采集脚本 → SQLite数据库
                              ↓
        ← Web前端 ← FastAPI后端 ← 复用脚本模块
                              ↓
                    Skill API Client → LLM分析 → 用户决策
```

## API文档

### 后端API端点

**市场数据**：
- `GET /api/market/sentiment/{date}` - 市场情绪
- `GET /api/market/sentiment` - 今日市场情绪

**股票管理**：
- `GET /api/stocks` - 股票池
- `POST /api/stocks` - 添加股票
- `DELETE /api/stocks/{code}` - 删除股票
- `GET /api/stocks/{code}/detail` - 股票详情
- `GET /api/stocks/popularity/{date}` - 人气榜

**概念管理**：
- `GET /api/concepts` - 概念树
- `GET /api/concepts/{name}/stocks` - 概念下的股票
- `POST /api/concepts/{name}/stocks` - 添加股票到概念
- `DELETE /api/concepts/{name}/stocks/{code}` - 移除股票
- `GET /api/concepts/heatmap/{date}` - 概念热力图

**龙头分析**：
- `POST /api/analysis/stock` - 分析单只股票
- `POST /api/analysis/concept` - 分析概念
- `GET /api/analysis/leaders/{date}` - 获取龙头候选

### Skill API Client方法

```python
from scripts.skill_api_client import SkillAPIClient

client = SkillAPIClient()

# 市场数据
client.get_market_sentiment(date)

# 股票数据
client.get_stock_list()
client.get_stock_detail(code, date)
client.get_popularity_rank(date, limit)

# 概念数据
client.get_concepts()
client.get_concept_stocks(concept_name)
client.get_concept_heatmap(date)

# 分析功能
client.analyze_stock(code, date)
client.analyze_concept(concept_name, date)
client.get_leaders(date)
```

## 技术栈

### 后端
- FastAPI 0.109
- Python 3.8+
- SQLite 3
- Requests

### 前端
- React 18
- Ant Design 5
- Axios
- ECharts

### 数据
- itick API（行情数据源）
- SQLite（本地缓存）

## 配置说明

### 后端配置（config.yaml）
```yaml
api:
  base_url: http://itick.pytrade.cn
  key: <your_api_key>

limit_up:
  growth_board_threshold: 0.20
  main_board_threshold: 0.10
```

### 前端配置（.env）
```bash
REACT_APP_API_URL=http://localhost:8000/api
```

## 开发指南

### 添加新API端点
1. 在 `backend/app/api/` 创建新路由文件
2. 在 `backend/app/main.py` 注册路由
3. 在 `frontend/src/services/api.js` 添加API方法

### 添加新页面
1. 在 `frontend/src/pages/` 创建组件
2. 在 `frontend/src/App.js` 添加路由
3. 在菜单中添加导航链接

### 扩展Skill功能
1. 在 `scripts/skill_api_client.py` 添加新方法
2. 在 `SKILL.md` 更新文档
3. LLM即可使用新功能

## 注意事项

⚠️ **前置要求**：
- Python 3.8+
- Node.js 16+
- 有效的itick API Key

⚠️ **运行提示**：
- 后端必须先于前端启动
- 确保8000和3000端口未被占用
- 首次使用需初始化数据库

⚠️ **风险提示**：
- 本系统仅供学习研究使用
- 不构成任何投资建议
- 股市有风险，投资需谨慎

## 相关文档

- [龙头战法理论](skills/dragon-stock-trading/reference/龙头战法理论.md)
- [数据库设计](skills/dragon-stock-trading/reference/数据库设计.md)
- [概念配置指南](skills/dragon-stock-trading/reference/概念配置指南.md)
- [后端API文档](backend/README.md)
- [前端开发文档](frontend/README.md)

## 许可证

本项目仅供学习交流使用。
