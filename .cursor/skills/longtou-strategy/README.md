# 龙头战法选股助手

A股龙头超短战法智能选股SKILL，基于"预期管理"理论自动筛选股票。

## 🚀 快速开始

### 1. 安装依赖

```bash
# 激活虚拟环境
source /Users/huijiecai/Project/stock/.venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 使用SKILL

在Cursor中调用：

```
/longtou-strategy 筛选今日自选股
```

### 3. 测试

```bash
cd /Users/huijiecai/Project/stock/.cursor/skills/longtou-strategy
python test.py
```

## 📁 项目结构

```
longtou-strategy/
├── SKILL.md                      # SKILL主文件（LLM入口）
├── README.md                     # 用户文档（本文件）
├── logic_library/                # 逻辑库（核心配置）
│   └── current_logics.yaml       # 当前热点逻辑
├── modules/                      # 核心功能模块
│   ├── data_fetcher.py           # 数据获取
│   ├── logic_matcher.py          # 逻辑匹配
│   └── screener.py               # 筛选器
└── test.py                       # 测试脚本
```

## 📚 逻辑库管理

**逻辑库是什么？**
- 你当前关注的热点题材清单
- 告诉系统哪些是核心受益方、逻辑强度、持续性等

**如何维护？**
- 配置文件：`logic_library/current_logics.yaml`
- 更新频率：每周复盘或重大题材出现时
- 通过SKILL更新：`/longtou-strategy 更新逻辑库`

## 🎯 核心功能

1. **早盘筛选**：自动筛选符合战法的股票
2. **个股分析**：分析特定股票是否符合战法
3. **逻辑库管理**：查看和更新当前热点逻辑

## ⚠️ 重要提示

- 仅供参考，不构成投资建议
- 不是自动交易系统，需要人工判断
- 逻辑库质量直接影响筛选效果
- 股市有风险，投资需谨慎

## 📖 详细文档

- SKILL使用：参考 `SKILL.md`
- 战法思路：`/Users/huijiecai/Project/stock/龙头战法/思路.md`
