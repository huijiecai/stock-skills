# Stage 类型详解

Module Bench 包含多种测试 Stage，每种 Stage 有不同的测试目标和失败原因。

## Stage 列表

### Stage.PERFORMANCE

**测试目标**：性能对比测试，对比 testline 和 baseline 的性能指标

**测试内容**：
- Calculator 执行时间
- Process 处理时间
- NN-Internal-Priority 异步任务时间

**常见失败原因**：
1. 代码变更导致性能回归
2. 新增计算逻辑增加耗时
3. 资源竞争导致性能波动

**分析方法**：
- 查看 `Performance Report` 中的 `Failed Elements`
- 对比具体失败元素的耗时变化

---

### Stage.MEMGATE_GPU

**测试目标**：GPU 显存使用门限测试

**测试内容**：
- PEAK：峰值显存使用
- PROCESS：进程显存使用

**常见失败原因**：
1. 新增模型或网络层
2. Batch size 增大
3. 显存泄漏

**分析方法**：
- 查看 `GPU Memory Gate` 对比报告
- 对比 Test Value 和 Base Value 的差异
- 检查差异是否超过 Threshold

---

### Stage.MEMGATE_CPU

**测试目标**：CPU 内存使用门限测试

**测试内容**：
- 峰值内存使用
- 平均内存使用

**常见失败原因**：
1. 内存泄漏
2. 缓存策略变更
3. 数据结构膨胀

**分析方法**：
- 查看 `CPU Memory Gate` 对比报告
- 多次运行观察内存增长趋势

---

### Stage.EVALUATION

**测试目标**：算法精度评估

**测试内容**：
- Precision（精确率）
- Recall（召回率）
- Error（误差）

**常见失败原因**：
1. 算法逻辑变更
2. 模型权重变化
3. 预处理/后处理变更

**分析方法**：
- 查看具体的评估指标变化
- 对比 baseline 和 testline 的结果文件

---

### Stage.CPU_MONITOR

**测试目标**：CPU 使用率监控

**测试内容**：
- 各线程 CPU 占用
- 整体 CPU 使用率

**常见失败原因**：
1. 计算密集型代码增加
2. 线程竞争加剧
3. 死循环或忙等待

---

### Stage.NSYS_PROFILE

**测试目标**：NVIDIA Nsight Systems 性能分析

**测试内容**：
- CUDA kernel 执行时间
- GPU 利用率
- 内存带宽使用

**常见失败原因**：
1. CUDA 代码效率下降
2. Kernel 启动开销增加

---

### Stage.MEMCHECK_CPU

**测试目标**：内存检查（如 Valgrind）

**测试内容**：
- 内存泄漏检测
- 未初始化内存使用
- 内存越界访问

**常见失败原因**：
1. 内存泄漏
2. 野指针
3. 数组越界

---

### Stage.THREAD_SANITIZER

**测试目标**：线程安全检查（ThreadSanitizer）

**测试内容**：
- Data Race（数据竞争）：多线程同时访问共享内存，至少一个是写操作
- Lock Order Inversion（锁顺序反转）：可能导致死锁
- Thread Leak（线程泄漏）：未正确回收线程资源
- Other Issues：其他线程安全问题

**失败报告格式**：
```
┌──────────────────────────┬──────────┐
│ THREAD SANITIZER SUMMARY │   COUNT  │
├──────────────────────────┼──────────┤
│ Data Races               │       28 │
├──────────────────────────┼──────────┤
│ Deadlocks                │        0 │
├──────────────────────────┼──────────┤
│ Other Issues             │        1 │
└──────────────────────────┴──────────┘
```

**常见失败原因**：
1. Protobuf 对象并发读写（最常见）
2. 成员变量未加锁保护
3. 容器（vector/map）并发修改
4. 回调函数中访问共享数据

**分析方法**：
1. 使用 `--tsan` 模式获取完整日志：
   ```bash
   python3 scripts/fetch_gitlab_log.py <job_url> --tsan
   ```

2. 从 SUMMARY 行定位问题文件和函数：
   ```
   SUMMARY: ThreadSanitizer: data race /path/file.cc:123 in ClassName::Method()
   ```

3. 分析详细堆栈，找到读写操作的调用链

4. 确定竞争的变量/资源类型

**详细分析指南**：参见 `knowledge/tsan-analysis.md`

---

### Stage.CALCULATOR_PROFILE

**测试目标**：Calculator 性能分析

**测试内容**：
- 各 Calculator 执行时间
- 调用频率
- 资源消耗

---

### Stage.PERF_ANALYSIS

**测试目标**：综合性能分析

**测试内容**：
- 整体性能指标汇总
- 性能趋势分析

---

## DrivingMode 说明

| Mode | 说明 |
|------|------|
| DrivingMode.DRIVING | 正常驾驶模式 |
| DrivingMode.LOW_SPEED | 低速模式 |
| DrivingMode.PARKING | 泊车模式 |
| QueryTracker.DrivingMode.DRIVING | QueryTracker 驾驶模式 |
| Single_Thread | 单线程模式 |

## Plug 与 Group 说明

### Plug（插件/模式）
- 对应不同的驾驶场景
- 影响测试数据集选择

### Group（性能分组）
- **Calculator**：计算器执行时间
- **Process**：进程处理时间
- **NN-Internal-Priority**：神经网络内部优先级任务

