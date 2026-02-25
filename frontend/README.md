# 龙头战法Web平台 - 前端

React + Ant Design前端应用。

## 功能

- 市场总览：市场情绪、人气榜、概念龙头
- 股票池管理：添加/删除股票
- 概念管理：可视化编辑概念和股票关系
- 龙头分析：分析个股是否符合龙头战法

## 安装

```bash
cd frontend
npm install
```

## 运行

```bash
# 开发模式（需要后端运行在8000端口）
npm start

# 构建生产版本
npm run build
```

应用将运行在 http://localhost:3000

## 技术栈

- React 18
- Ant Design 5
- React Router 6
- Axios
- Day.js

## 目录结构

```
frontend/
├── src/
│   ├── pages/          # 页面组件
│   │   ├── Dashboard.js
│   │   ├── StockPool.js
│   │   ├── ConceptManage.js
│   │   └── Analysis.js
│   ├── services/       # API服务
│   │   └── api.js
│   ├── App.js
│   └── index.js
├── public/
└── package.json
```

## 注意事项

1. 确保后端服务已启动（端口8000）
2. API请求通过proxy转发到后端
3. 日期格式统一为 YYYY-MM-DD
