# Module Bench 测试诊断

让 AI 帮你一键诊断 Module Bench 性能测试 Job 的失败原因。

仓库地址：https://code.deeproute.ai/deeproute-org/agi/agent-skills/module-bench-diagnosis


## 为什么需要这个工具？

### Module Bench 诊断的痛点

Module Bench 是自动驾驶模块级性能测试框架，一个 Job 通常包含数百个任务、多个 Stage，产生数万行日志。当 Job 失败时，工程师需要：

- **翻阅海量日志**：日志动辄 5 万+ 行，手动定位失败任务犹如大海捞针
- **理解多种 Stage**：Performance、TSan、Memcheck、CPU Monitor、GPU Memory Gate……每种 Stage 有不同的分析方法
- **掌握三步法**：Performance 回退需要区分"真正回退"和"资源竞争 / GPU 调度变化"，分析链路复杂
- **对比大量数据**：Testline vs Baseline 的多维度对比（时间、内存、精度），容易遗漏关键信息

这些工作重复、繁琐，且对经验要求高。

### 解决方案：一句话完成诊断

本工具通过 Cursor 的 AI Agent 能力，实现了：

> "帮我分析一下 https://code.deeproute.ai/xxx/-/jobs/12345"

AI 自动完成：获取日志 → 任务统计 → 失败定位 → Stage 分析 → 精度评估 → 输出诊断报告

从一个 Job URL，到一份结构化的诊断报告，一步到位。


## 诊断能力一览

| 能力 | 说明 |
|------|------|
| 🔍 自动获取日志 | 从 GitLab Job URL 自动拉取完整日志 |
| 📊 任务统计 | 统计成功/失败任务数，定位失败任务和状态码 |
| 🧪 Stage 全览 | 检查所有 Stage 状态，仅深入分析失败 Stage |
| ⚡ Performance 三步法 | 单线程/多线程对比 → 资源竞争分析 → 新增 Node 检查 |
| 🧵 TSan 分析 | 提取 Data Race 详情，定位竞争变量和调用链 |
| 🧠 Memcheck 分析 | 识别内存泄漏、未初始化读取、无效读写 |
| 📈 资源监控 | CPU 使用率、CPU/GPU 内存门限分析 |
| 🎯 精度评估 | Tracker / AVP 算法指标对比，识别回退项 |
| 📝 结构化报告 | 输出标准化诊断报告，包含结论和修复建议 |


## 安装（2 分钟）

### 1. 克隆本仓库

```bash
git clone https://code.deeproute.ai/deeproute-org/agi/agent-skills/module-bench-diagnosis.git ~/workspace/skill/module-bench-diagnosis
```

### 2. 安装 Skill

将本仓库作为 Cursor Workspace 打开，Cursor 会自动识别 `module-bench-diagnosis.md` 作为 Skill。

或者手动安装到全局 Skills 目录：

```bash
mkdir -p ~/.cursor/skills/module-bench-diagnosis
cp ~/workspace/skill/module-bench-diagnosis/module-bench-diagnosis.md ~/.cursor/skills/module-bench-diagnosis/SKILL.md
cp -r ~/workspace/skill/module-bench-diagnosis/knowledge ~/.cursor/skills/module-bench-diagnosis/
cp -r ~/workspace/skill/module-bench-diagnosis/scripts ~/.cursor/skills/module-bench-diagnosis/
```

### 3. 配置 GitLab Token

本工具需要 GitLab Personal Access Token 来获取 Job 日志：

1. 访问 https://code.deeproute.ai/-/user_settings/personal_access_tokens
2. 创建一个 Token，勾选 `read_api` 权限
3. 使用时将 Token 作为参数传给 AI 即可

> ⚠️ **安全提示**：Token 等同于你的身份凭证，请勿泄露给他人或提交到代码仓库。

### 4. 推荐模型设置

- 推荐使用 **Claude Opus** 系列模型，分析能力更强、更稳定
- 日志量大时建议开启 Max Mode 以获得更完整的分析


## 快速体验

### 基本用法

在 Cursor 对话中输入：

```
帮我分析一下 https://code.deeproute.ai/xxx/module-bench/-/jobs/12345 ，token 为 glpat-xxxxx
```

AI 会自动执行 6 步标准化诊断流程，输出结构化报告。

### 诊断报告示例

AI 会输出包含以下章节的完整报告：

```
🔴 Module Bench 诊断报告

1️⃣ 失败概览        — 任务总数 / 成功 / 失败
2️⃣ 失败任务分析    — 状态码、返回码、根因判定
3️⃣ Stage 状态      — 各 Stage 成功/失败一览
4️⃣ 失败 Stage 分析 — Performance 三步法 / TSan / Memcheck / 资源监控
5️⃣ EVALUATION 分析 — Tracker / AVP 精度指标对比
6️⃣ 建议操作        — 按优先级排列的修复建议
```


## 支持的 Stage 类型

| Stage | 分析能力 |
|-------|---------|
| PERFORMANCE | ✅ 三步法深度分析（真正回退 / 资源竞争 / GPU 调度变化 / 新增 Node 影响） |
| THREAD_SANITIZER | ✅ Data Race 提取、调用链分析、修复建议 |
| MEMCHECK_CPU | ✅ 内存泄漏、未初始化值、无效读写定位 |
| CPU_MONITOR | ✅ CPU 时间对比、阈值判定 |
| MEMGATE_GPU | ✅ GPU 显存峰值/进程内存对比 |
| MEMGATE_CPU | ✅ CPU 内存峰值/进程内存对比 |
| FUNCTION_TEST | ✅ 崩溃类型识别、返回码分析 |
| EVALUATION | ✅ Tracker / AVP 精度指标对比 |


## 项目结构

```
module-bench-diagnosis/
├── module-bench-diagnosis.md    # Skill 主文件（诊断流程定义）
├── knowledge/                   # 知识库
│   ├── task-status-codes.md     #   TaskStatus 状态码详解
│   ├── performance-analysis.md  #   Performance 三步法分析指南
│   ├── tsan-analysis.md         #   ThreadSanitizer 分析指南
│   ├── memcheck-analysis.md     #   Memcheck 内存分析指南
│   ├── resource-analysis.md     #   CPU/GPU 资源监控分析指南
│   ├── stage-types.md           #   Stage 类型详解
│   └── typical-cases.md         #   典型案例记录
├── scripts/
│   └── fetch_gitlab_log.py      # GitLab 日志获取脚本
└── README.md
```


## 常见问题

**Q: 提示认证失败？**
检查 GitLab Token 是否正确，是否具有 `read_api` 权限。

**Q: 日志获取超时？**
脚本内置了 3 次重试机制。如果网络不稳定，可以稍后重试。

**Q: Performance 分析结果如何解读？**
AI 会按三步法（Step A → B → C → D）逐步分析，最终输出判定汇总表。详见 `knowledge/performance-analysis.md`。

**Q: 可以只分析某个 Stage 吗？**
可以。告诉 AI "只帮我分析 Performance Stage" 即可。

**Q: 如何新增典型案例？**
在 `knowledge/typical-cases.md` 中补充即可，AI 会在后续诊断中参考。


## 参与贡献

欢迎一起完善这个工具！如果你有好的想法或发现了 Bug，欢迎提交 Issue 或 Merge Request。

期待你的参与！


## 许可证

MIT License
