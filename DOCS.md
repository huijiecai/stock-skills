# 文档索引

## 核心文档（必读）

### 1. [README.md](README.md) - 项目总览
- 快速开始指南
- 项目结构说明
- 基本使用方法
- 故障排查

**适合**: 新用户、部署人员

### 2. [ARCHITECTURE.md](ARCHITECTURE.md) - 架构文档
- 系统架构图
- 核心架构原则
- 分层设计详解
- API 端点说明
- 技术选型

**适合**: 开发人员、架构师

### 3. [skills/dragon-stock-trading/SKILL.md](skills/dragon-stock-trading/SKILL.md) - Skill 使用文档
- Skill 功能说明
- API 调用示例
- 数据采集方法
- LLM 使用指南

**适合**: LLM 用户、Cursor 用户

## 子模块文档

### 后端
- [backend/README.md](backend/README.md) - 后端开发文档
- [backend/scripts/README.md](backend/scripts/README.md) - 数据库管理工具

### 前端
- [frontend/README.md](frontend/README.md) - 前端开发文档

### Skill 参考文档
- [skills/dragon-stock-trading/reference/](skills/dragon-stock-trading/reference/)
  - 龙头战法理论.md
  - 数据库设计.md (已移至 backend/)
  - 技术指标详解.md
  - 风险控制.md

## 文档层级

```
项目根目录/
├── README.md              ⭐ 项目总览（快速开始）
├── ARCHITECTURE.md        ⭐ 架构文档（系统设计）
│
├── backend/
│   ├── README.md          📘 后端开发文档
│   └── scripts/
│       └── README.md      📘 数据库管理工具
│
├── frontend/
│   └── README.md          📘 前端开发文档
│
└── skills/
    └── dragon-stock-trading/
        ├── SKILL.md       ⭐ Skill 使用文档（LLM）
        ├── README.md      📘 Skill 概述
        └── reference/     📂 参考文档（详细理论）
```

## 文档用途

| 文档 | 用户类型 | 主要内容 |
|------|---------|---------|
| README.md | 新用户、运维 | 快速开始、安装、使用 |
| ARCHITECTURE.md | 开发者 | 架构设计、技术选型 |
| SKILL.md | LLM 用户 | API 使用、数据分析 |
| backend/README.md | 后端开发 | API 开发、数据服务 |
| frontend/README.md | 前端开发 | 组件开发、UI 设计 |
| reference/* | 所有人 | 理论、详细说明 |

## 快速导航

**我想...**
- 🚀 快速部署项目 → [README.md](README.md)
- 🏗️ 了解系统架构 → [ARCHITECTURE.md](ARCHITECTURE.md)
- 🤖 使用 LLM Skill → [SKILL.md](skills/dragon-stock-trading/SKILL.md)
- 💬 使用 AI 聊天分析 → 访问 http://localhost:3000/chat（需配置 OPENAI_API_KEY）
- 💻 开发后端 API → [backend/README.md](backend/README.md)
- 🎨 开发前端页面 → [frontend/README.md](frontend/README.md)
- 📚 学习龙头战法 → [reference/龙头战法理论.md](skills/dragon-stock-trading/reference/龙头战法理论.md)

## AI 聊天功能说明

### 功能特性
- **自然语言对话**: 通过聊天方式分析股票和市场
- **实时流式响应**: SSE 推送，打字机效果
- **智能工具调用**: LLM 自动调用 7 个数据工具（市场情绪、人气榜、概念热度等）
- **按需查阅文档**: LLM 可主动调用 `read_reference` 查询 7 个 reference 文档
- **Skill 集成**: 共享 `skills/dragon-stock-trading/` 下的 SKILL.md 和 reference 文档

### 使用方法
1. **配置 API Key**: 编辑 `backend/.env`，填写 `OPENAI_API_KEY=sk-xxxxx`
2. **访问聊天页面**: http://localhost:3000/chat
3. **开始对话**: 尝试问"今天市场情绪怎么样？"或"帮我分析 002342"

### 技术实现
- **System Prompt**: 动态加载 SKILL.md 核心部分（~1.5KB），避免 context 过长
- **按需加载**: LLM 根据问题复杂度，主动决策是否查阅详细文档
- **单一数据源**: Web 平台和 Cursor IDE 共享同一套 Skill 文件

### 测试脚本
运行 `./test_integration.sh` 验证集成是否正常。

## 更新日志

### 2026-02-26 - AI 聊天功能集成
- ✅ 集成 LLM 聊天功能到 Web 平台（`/chat` 路由）
- ✅ 采用 Skill 集成方案（按需加载，避免 context 过长）
- ✅ 添加 `read_reference` 工具，LLM 可主动查阅 7 个 reference 文档
- ✅ 前端支持 SSE 流式响应和 Markdown 渲染
- ✅ 创建集成测试脚本 `test_integration.sh`

### 2026-02-26 - 文档整理
- ✅ 删除临时报告文件（BACKEND_ISOLATION_REPORT.md 等）
- ✅ 合并 DEPLOYMENT.md 和 QUICK_START.md 到 README.md
- ✅ 精简 ARCHITECTURE.md，保留核心内容
- ✅ 重写 README.md，更清晰的快速开始指南
- ✅ 创建文档索引

---

**文档总数**: 2 个核心文档 + 5 个子模块文档  
**总行数**: ~600 行（核心文档）  
**维护原则**: 保持简洁，避免重复
