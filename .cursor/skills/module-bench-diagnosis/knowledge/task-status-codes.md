# Task 状态码和返回码详解

Module Bench 任务执行过程中会产生各种状态码，本文档详细说明各状态码的含义、分析方法和处理方式。

---

## TaskStatus 状态码

### TaskStatus.SUCCESS

任务成功完成，无需处理。

---

### TaskStatus.FAILED

**含义**：测试流程本身出现了问题，而非被测代码的性能/内存问题。

**常见原因**：
- 测试框架执行异常
- 数据集加载失败
- 测试环境配置问题
- 测试脚本 bug

**处理方式**：
- 需要通知 **@yufanpu@jiuhongmin** 进行分析
- 不要将此类失败归因于被测代码

---

### TaskStatus.BAG_SELECT_INVALID

**含义**：Bag 选择无效，需要进一步检查 task 执行日志来判断根因。

**分析步骤**：

1. 在日志中搜索该 TASK_ID 的执行日志
2. 查找 `"node_ret_codes"` 字段，格式如：
   ```json
   "node_ret_codes":{"ddl_v2":111,"perception":11}
   ```
3. 检查各模块的返回码

**情况 A：模块返回码 ≠ 0**

- **结论**：模块 crash 了
- **归属**：模块 crash 问题
- **处理**：需要模块 owner 排查 crash 原因，参考 [node_ret_codes 返回码](#node_ret_codes-返回码)

**情况 B：模块返回码 = 0**

- **结论**：bag 或代码版本有问题，模块一帧也没运行
- **归属**：测试数据/版本问题
- **常见原因**：
  - bag 文件损坏或不兼容
  - 代码版本与 bag 版本不匹配
  - bag 中缺少必要的 topic/数据
- **处理**：需要通知 **@yufanpu@jiuhongmin** 检查 bag 和版本配置

---

### TaskStatus.MODULE_CRASH

**含义**：某个模块在运行过程中崩溃了。

**分析步骤**：

1. 在日志中搜索该 TASK_ID 的执行日志
2. 查找 `"node_ret_codes"` 字段
3. 找出返回码非 0 的模块，即为 crash 的模块
4. 根据返回码判断 crash 类型，参考 [node_ret_codes 返回码](#node_ret_codes-返回码)

**输出格式示例**：
```
### Module Crash 分析

| 模块 | 返回码 | 信号 | 诊断 |
|------|--------|------|------|
| perception | 11 | SIGSEGV | 段错误，内存访问异常 |
| ddl_v2 | 111 | 自定义 | 框架自定义错误 |

**Crash 模块**: perception
**可能原因**: 空指针、野指针、数组越界
**建议**: 检查 perception 模块最近的代码变更，特别关注指针操作
```

---

### TaskStatus.UNKNOW_DDL_CRASH

**含义**：DDL 调度框架层面出现了未知的崩溃，需要进一步分析根因。

**分析步骤**：

1. 在日志中搜索该 TASK_ID 的执行日志
2. 查找 `"node_ret_codes"` 字段
3. 检查各模块的返回码

**情况 A：模块返回码 ≠ 0**

- **结论**：实际是模块 crash 导致的
- **归属**：模块 crash 问题
- **处理**：参考 `TaskStatus.MODULE_CRASH` 的分析流程

**情况 B：模块返回码 = 0**

- **结论**：DDL 调度框架本身的问题
- **归属**：DDL 框架问题
- **处理**：需要通知 **@lezhilian@ziqizhang** 进行排查

---

### TaskStatus.CATCH_THREAD_ISSUE

**含义**：任务执行成功，但 ThreadSanitizer 检测到线程安全问题（如 data race）。

**特点**：
- ✅ 任务本身运行成功完成
- ⚠️ 但检测工具发现了代码问题
- 🚫 不会有 `node_ret_codes` 错误返回码（模块都正常退出）

**常见检出问题**：
- Data Race（数据竞争）
- Deadlock（死锁）
- Thread Leak（线程泄漏）
- Lock Order Inversion（锁顺序反转）

**处理方式**：
- 需要分析 ThreadSanitizer 的详细报告
- 使用 `--tsan` 模式获取完整的 TSan 日志
- 根据报告定位竞争代码并修复
- 详见 `knowledge/tsan-analysis.md`

**输出格式示例**：
```
### Thread Issue 分析

任务 000201 执行成功，但 TSan 检测到线程问题：

| 问题类型 | 数量 |
|---------|------|
| Data Race | 28 |
| Other Issues | 1 |

需要获取完整 TSan 报告进行深入分析。
```

---

### TaskStatus.CATCH_MEM_ERROR

**含义**：任务执行成功，但内存检测工具发现了内存问题。

**特点**：
- ✅ 任务本身运行成功完成
- ⚠️ 但检测工具发现了代码问题
- 🚫 不会有 `node_ret_codes` 错误返回码（模块都正常退出）

**常见检出问题**：
- Memory Leak（内存泄漏）
- Use-After-Free（释放后使用）
- Buffer Overflow（缓冲区溢出）
- Uninitialized Memory Read（读取未初始化内存）
- Double Free（重复释放）

**处理方式**：
- 需要分析内存检测工具的详细报告
- 根据报告定位问题代码并修复
- 通知相关模块 owner 处理

**输出格式示例**：
```
### Memory Error 分析

任务 XXXXXX 执行成功，但内存检测发现问题：

| 问题类型 | 数量 |
|---------|------|
| Memory Leak | 5 |
| Use-After-Free | 1 |

需要获取完整内存检测报告进行深入分析。
```

---

## node_ret_codes 返回码

任务执行日志中的 `"node_ret_codes"` 字段记录了各模块的退出码，格式如：

```json
"node_ret_codes":{"ddl_v2":111,"perception":11,"prediction":0}
```

### 标准错误码对照表

| 返回码 | 信号 | 含义 | 常见原因 |
|--------|------|------|---------|
| 0 | - | 正常退出 | 模块正常运行完成 |
| 1 | - | 一般错误 | 程序逻辑错误、异常退出 |
| 2 | - | 误用 | 命令行参数错误 |
| 6 | SIGABRT | 异常终止 | `abort()` 调用、断言失败、`std::terminate()` |
| 8 | SIGFPE | 浮点异常 | 除零错误、浮点溢出 |
| 9 | SIGKILL | 强制杀死 | OOM Killer、手动 kill -9 |
| 11 | SIGSEGV | 段错误 | 空指针、野指针、数组越界、栈溢出 |
| 15 | SIGTERM | 终止信号 | 正常终止请求、超时被杀 |
| 111 | - | 自定义 | 通常为框架/业务自定义错误码 |
| 128+N | 信号 N | 被信号终止 | 进程被信号 N 杀死 |

### 常见返回码速查

| 返回码 | 诊断结论 | 排查方向 |
|--------|---------|---------|
| 0 | 正常 | 无需排查 |
| 6 | 断言失败或异常 | 查看日志中的 `FATAL`、`CHECK failed`、`ASSERT` |
| 9 | 被系统杀死 | 检查是否 OOM，查看 `dmesg` 或系统日志 |
| 11 | 内存访问错误 | 空指针解引用、use-after-free、buffer overflow |
| 111 | 框架自定义错误 | 查看框架相关日志 |
| 134 (128+6) | SIGABRT | 同返回码 6 |
| 139 (128+11) | 段错误 | 同返回码 11 |
| 137 (128+9) | 被 SIGKILL | 同返回码 9 |

### 信号码对照表

| 信号 | 编号 | 128+N | 含义 |
|------|------|-------|------|
| SIGHUP | 1 | 129 | 挂起 |
| SIGINT | 2 | 130 | 中断 (Ctrl+C) |
| SIGQUIT | 3 | 131 | 退出 |
| SIGILL | 4 | 132 | 非法指令 |
| SIGTRAP | 5 | 133 | 跟踪/断点陷阱 |
| SIGABRT | 6 | 134 | 异常终止 |
| SIGBUS | 7 | 135 | 总线错误 |
| SIGFPE | 8 | 136 | 浮点异常 |
| SIGKILL | 9 | 137 | 强制杀死 |
| SIGSEGV | 11 | 139 | 段错误 |
| SIGPIPE | 13 | 141 | 管道破裂 |
| SIGTERM | 15 | 143 | 终止信号 |

---

## 日志搜索模式

### 查找返回码
```bash
grep "node_ret_codes" <log_file>
```

### 查找 crash 相关日志
```bash
grep -E "FATAL|Segmentation fault|SIGSEGV|SIGABRT|core dumped" <log_file>
```

### 查找 OOM 相关
```bash
grep -E "Out of memory|OOM|oom-killer" <log_file>
dmesg | grep -i oom
```

---

## 状态码快速对照表

### 执行失败类（需查 node_ret_codes）

| TaskStatus | 含义 | 处理人 |
|------------|------|--------|
| FAILED | 测试流程问题 | @yufanpu@jiuhongmin |
| BAG_SELECT_INVALID (返回码≠0) | 模块 crash | 模块 owner |
| BAG_SELECT_INVALID (返回码=0) | bag/版本问题 | @yufanpu@jiuhongmin |
| MODULE_CRASH | 模块崩溃 | 模块 owner |
| UNKNOW_DDL_CRASH (返回码≠0) | 模块 crash | 模块 owner |
| UNKNOW_DDL_CRASH (返回码=0) | DDL 框架问题 | @lezhilian@ziqizhang |

### 执行成功但检出问题类（无 node_ret_codes）

| TaskStatus | 含义 | 处理人 |
|------------|------|--------|
| SUCCESS | 成功 | - |
| CATCH_THREAD_ISSUE | 检测到线程问题 | 模块 owner（分析 TSan 报告）|
| CATCH_MEM_ERROR | 检测到内存问题 | 模块 owner（分析内存检测报告）|

> **注意**：`CATCH_THREAD_ISSUE` 和 `CATCH_MEM_ERROR` 表示任务执行成功完成，但检测工具发现了代码问题。这类状态码不会产生 `node_ret_codes` 错误返回码。

