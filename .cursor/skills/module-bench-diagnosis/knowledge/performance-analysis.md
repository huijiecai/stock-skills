# Performance 分析指南

性能测试用于检测模块执行时间是否超过基线阈值。

---

## Perception 性能数据分析方法

> **适用范围**：Perception 模块的 Performance Stage 分析，包含 Single Thread Eval、Multi Thread Eval、Query Tracker Eval 等场景。

### 核心概念

#### 1. 日志数据结构

Performance 日志中，每个 Scene 包含三部分：
- **Testline**：当前测试版本的原始数据（含每个 node 的统计信息：mean, min, p50, p75, p95, p99, max, stdev, count）
- **Baseline**：基准版本的原始数据（同上结构）
- **Contrast**：Testline 与 Baseline 的对比结果（含 difference、percentage、threshold、Pass/NotPass 状态）

每部分按 Mode（如 DRIVING、LOW_SPEED、PARKING）分割，每个 Mode 下包含多种 time analysis：
- **Pipeline time analysis**：整体 Pipeline 耗时
- **Process time analysis**：各处理阶段耗时
- **Calculator time analysis**：各 Calculator 节点的 Process 耗时（顶层汇总）
- **NN-Internal time analysis**：GPU 推理模型（如 mighty、aroundview_det、uni_model_fusion_l2）的耗时
- **Calculator Frame time analysis**：每个 Calculator 节点的详细帧级 Start/Process/End 时间（关键！）
- 其他：NN-Internal-Camera、NN-Internal-BarrierGate、Init、Output、Prediction 等

#### 2. Scene 关系

| Scene | 说明 |
|-------|------|
| **Single Thread Eval** | 单线程模式，所有 node 串行执行，排除了多线程资源竞争的影响 |
| **Multi Thread Eval** | 多线程模式，node 可并行执行，是实际运行环境 |
| **Query Tracker Eval** | 追踪器评估，独立场景 |

**关键关系**：Single Thread Eval 是 Multi Thread Eval 的单线程版本。单线程下的性能数据更能反映代码/模型本身的真实性能变化，不受并发竞争干扰。

#### 3. Contrast 的重要限制

> **🔴 Contrast 只对比 Testline 和 Baseline 都存在的 node 耗时！**

- 如果 Testline 中**新增了 node**（Baseline 中不存在），该 node **不会出现在 Contrast 中**
- 如果 Baseline 中**删除了 node**（Testline 中不存在），该 node **也不会出现在 Contrast 中**
- 因此，仅看 Contrast 数据是**不完整**的，必须额外对比 Testline 和 Baseline 的原始数据以发现新增/删除 node

---

### 性能回退判定方法（三步法）

#### Step A: 先看单线程（Single Thread Eval）是否有回退

**核心原则：以 Single Thread Eval 为判定基准。**

1. 在 Single Thread Eval 的 Contrast 中查找所有 `NotPass` 项
2. 单线程中 NotPass 的 node → **真正的性能回退**（代码/模型本身变慢了）
3. 单线程中 Pass 的 node → 即使多线程 NotPass，也**不是真正的性能回退**

```bash
# 确定 Single Thread Eval Contrast 的行范围
grep -n "xxxxxxxx.*Single Thread Eval\|======.*Contrast\|xxxxxxxx.*Eval" /tmp/performance.txt | head -10

# 搜索 Single Thread Contrast 的 NotPass 项
sed -n '<ST_Contrast_start>,<ST_Contrast_end>p' /tmp/performance.txt | grep "NotPass"
```

#### Step B: 对于"仅多线程回退"的 node，分析资源竞争

如果某个 node 在 Single Thread 中 Pass，但在 Multi Thread 中 NotPass，需要通过 **Calculator Frame time 的 Start/End 时间** 判断是否存在资源竞争：

1. 从 Multi Thread Contrast 的 **Calculator Frame time analysis** 获取该 node 的 `Start` 和 `End` 时间（testline）
2. 查找所有与该 node 时间窗口 `[Start, End]` 存在**重叠**的其他 node（判断条件：`other.Start < node.End && other.End > node.Start`）
3. 在重叠的 node 中，检查哪些 node 的 **Process 时间有显著增加**（如 Δ > 0.5ms）
4. 如果有其他 node Process 增加且时间重叠 → **资源竞争导致**，非真正回退
5. 如果没有其他 node Process 增加 → 检查 GPU NN 模型的行为变化（如 mighty 等重量级模型的执行模式变化）

```bash
# 提取 Multi Thread Contrast Calculator Frame time 中目标 node 的 Start/End
sed -n '<MT_Contrast_FrameTime_start>,<MT_Contrast_FrameTime_end>p' /tmp/performance.txt | grep "<target_node>" -A 5
```

**时间重叠示意**：
```
node_A:  |---Start----Process----End---|
node_B:       |---Start---Process---End---|
              ↑ 重叠区间 ↑
如果 node_B 的 Process 增加了，可能占用了 CPU/GPU 资源，
导致 node_A 被抢占而变慢 → 这是资源竞争，不是 node_A 自身退化
```

#### Step C: 检查新增/删除 Node（Contrast 盲区）

由于 Contrast 只对比双方都存在的 node，必须额外从 Testline 和 Baseline 原始数据中提取完整 node 列表，找出差异：

1. 分别从 Testline 和 Baseline 的 **Calculator Frame time analysis** 提取所有 node 名称
2. 求差集：`仅Testline有` = 新增 node，`仅Baseline有` = 删除 node
3. 对新增 node 检查其 Start/End 时间，判断是否与回退 node 的时间窗口重叠
4. 新增 node 如果与回退 node 重叠且自身 Process 较大 → 可能是资源竞争的来源

```python
# 伪代码：提取并对比 node 集合
testline_nodes = extract_calculator_frame_nodes(testline_section)
baseline_nodes = extract_calculator_frame_nodes(baseline_section)

new_nodes = testline_nodes - baseline_nodes      # 新增 node（Contrast 不可见）
deleted_nodes = baseline_nodes - testline_nodes   # 删除 node（Contrast 不可见）

# 检查新增 node 是否与回退 node 时间重叠
for node in new_nodes:
    if node.start < target.end and node.end > target.start:
        print(f"⚠️ 新增 node {node.name} 与回退 node 时间重叠，可能导致资源竞争")
```

---

### 判定结果分类

根据以上三步分析，将每个 NotPass node 分类为：

| 分类 | 判定条件 | 含义 | 建议 |
|------|----------|------|------|
| **真正回退** | 单线程 NotPass | 代码/模型本身性能退化 | 需要排查代码变更 |
| **资源竞争** | 单线程 Pass + 多线程有重叠 node Process 增加 | 其他 node 耗时增加导致资源抢占 | 排查导致竞争的 node |
| **GPU 调度变化** | 单线程 Pass + 多线程无重叠 node Process 增加 + GPU 模型行为变化 | GPU 模型执行模式改变引起 | 调整 GPU 调度策略 |
| **新增 Node 影响** | 单线程 Pass + 新增 node 与回退 node 时间重叠 | 新增的 node 占用了共享资源 | 评估新增 node 的资源影响 |

---

### 分析示例

**场景**：aroundview_det 在 Multi Thread NotPass (+223%) 但 Single Thread Pass (+2.23%)

1. **Step A**：单线程 aroundview_det +2.23% → Pass → 不是真正回退
2. **Step B**：Multi Thread Frame time 分析
   - aroundview_det 运行区间 [4.81ms, 12.11ms]
   - 重叠节点中，mighty [5.01ms, 78.77ms] 完全覆盖，但 mighty 的 Process 反而**减少了** 16.67ms
   - 无其他重叠节点 Process 显著增加
3. **Step C**：检查新增 node
   - 新增 6 个 node（如 AroundViewPreprocessCalculator），但均不在 [4.81, 12.11] 重叠区间内
4. **结论**：mighty GPU 模型执行模式从"高方差长耗时 (p50=93ms)" 变为 "低方差短耗时 (p50=74ms)"，GPU 资源占用节奏改变导致 aroundview_det 受影响。属于 **GPU 调度变化**，非真正回退。

---

### 常见模式

| 模式 | 特征 | 说明 |
|------|------|------|
| **新增固定耗时** | Baseline≈0ms, Testline=固定值(如1ms) | 新增了 sleep、锁等待或新计算逻辑 |
| **渐进式退化** | 单线程一致 +3~10% | CPU 处理逻辑变重 |
| **仅多线程退化** | 单线程 Pass, 多线程大幅 NotPass | 资源竞争或调度问题 |
| **模型行为变化** | 重叠的 GPU 模型 stdev/分布巨变 | 模型优化改变了 GPU 占用模式 |
