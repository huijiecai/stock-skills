# 典型失败案例

记录 Module Bench 典型失败案例，供后续诊断参考。

---

## 案例 1：Job 183927171 - ModuleEvents Protobuf 并发访问

### 基本信息
- **Job ID**: 183927171
- **失败 Stage**: `Stage.THREAD_SANITIZER`
- **问题类型**: Data Race (28 个) + Heap-use-after-free (1 个)
- **影响模块**: platform/church + common/module_event

### 问题摘要

```
┌──────────────────────────┬──────────┐
│ THREAD SANITIZER SUMMARY │   COUNT  │
├──────────────────────────┼──────────┤
│ Data Races               │       28 │
├──────────────────────────┼──────────┤
│ Deadlocks                │        0 │
├──────────────────────────┼──────────┤
│ Other Issues             │        1 │  (heap-use-after-free)
└──────────────────────────┴──────────┘
```

### 详细分析

#### 核心问题：`dr::common::ModuleEvents` Protobuf 对象并发读写

**竞争对象**: `dr::common::ModuleEvents` 及其内部的 `RepeatedPtrField<dr::common::EventInfo>`

**读线程 (Thread T8)**:
- 调用链: `InnerProc()` → `ModuleEvents::ByteSizeLong()` → 遍历 `event_infos`
- 文件: `external/platform/church/task/component_task_ddl.cc:224`
- 操作: 读取 RepeatedPtrField 的 size、begin、迭代器等

**写线程 (Thread T97)**:
- 调用链: `IntraReader::CallbackRoutine()` → `Node::CallTopicObserver()` → `ModuleEvents::CopyFrom()`
- 文件: `external/platform/church/task/component_task_ddl.cc:154`
- 操作: Clear + MergeFrom (修改 RepeatedPtrField 内容)

#### 涉及的 Data Race 位置

| 读操作 | 写操作 | 说明 |
|--------|--------|------|
| `RepeatedPtrField::size()` | `RepeatedPtrFieldBase::ExchangeCurrentSize()` | 读取 size 同时被 Clear 修改 |
| `RepeatedPtrField::begin()` | `RepeatedPtrFieldBase::InternalExtend()` | 读取迭代器同时内部数组被扩展 |
| `RepeatedPtrIterator::operator*()` | `operator new()` (扩展数组) | 迭代访问同时数组重新分配 |
| `EventInfo::ByteSizeLong()` | `EventInfo::MergeImpl()` | 读取字段大小同时字段被修改 |
| `EventInfo::_internal_module()` | `EventInfo::MergeImpl()` | 读取 module 字段同时被写入 |
| `EventInfo::_internal_event()` | `EventInfo::MergeImpl()` | 读取 event 字段同时被写入 |
| `EventInfo::_internal_timestamp()` | `EventInfo::MergeImpl()` | 读取 timestamp 同时被写入 |

#### Heap-use-after-free

```
SUMMARY: ThreadSanitizer: heap-use-after-free /usr/include/x86_64-linux-gnu/bits/string_fortified.h:34 in memcpy
```

这是 data race 的严重后果：当一个线程在读取/复制 protobuf 字段时，另一个线程 Clear 了对象，导致内存被释放后又被访问。

### 根因分析

1. **共享 Protobuf 对象无锁保护**：`ModuleEvents` 对象在多个线程间共享
2. **读写时机冲突**：
   - Thread T8 在 `InnerProc()` 中读取 `ModuleEvents` 计算序列化大小
   - Thread T97 在回调中执行 `CopyFrom()` 修改同一对象
3. **CopyFrom 的破坏性**：`CopyFrom` = `Clear()` + `MergeFrom()`，Clear 会释放内存

### 修复建议

#### 方案 1：加锁保护 (推荐)

```cpp
// 在 component_task_ddl.cc 中
std::mutex module_events_mutex_;
dr::common::ModuleEvents module_events_;

// 写操作
void OnModuleEventsReceived(const dr::common::ModuleEvents& msg) {
    std::lock_guard<std::mutex> lock(module_events_mutex_);
    module_events_.CopyFrom(msg);
}

// 读操作
size_t GetModuleEventsSize() {
    std::lock_guard<std::mutex> lock(module_events_mutex_);
    return module_events_.ByteSizeLong();
}
```

#### 方案 2：使用原子交换 (Copy-on-Write)

```cpp
std::shared_ptr<const dr::common::ModuleEvents> module_events_;
std::mutex mutex_;

void OnModuleEventsReceived(const dr::common::ModuleEvents& msg) {
    auto new_msg = std::make_shared<dr::common::ModuleEvents>(msg);
    std::lock_guard<std::mutex> lock(mutex_);
    module_events_ = new_msg;
}

std::shared_ptr<const dr::common::ModuleEvents> GetModuleEvents() {
    std::lock_guard<std::mutex> lock(mutex_);
    return module_events_;  // 返回 shared_ptr，读者持有引用
}
```

#### 方案 3：使用读写锁 (适合读多写少)

```cpp
std::shared_mutex rw_mutex_;
dr::common::ModuleEvents module_events_;

void OnModuleEventsReceived(const dr::common::ModuleEvents& msg) {
    std::unique_lock<std::shared_mutex> lock(rw_mutex_);
    module_events_.CopyFrom(msg);
}

dr::common::ModuleEvents GetModuleEventsCopy() {
    std::shared_lock<std::shared_mutex> lock(rw_mutex_);
    return module_events_;  // 返回拷贝
}
```

### 关键代码位置

| 文件 | 行号 | 说明 |
|------|------|------|
| `external/platform/church/task/component_task_ddl.cc` | 224 | 读操作 `InnerProc` |
| `external/platform/church/task/component_task_ddl.cc` | 154 | 写操作 `CopyFrom` |
| `external/platform/church/node/node.h` | 233 | 订阅回调 |
| `external/platform/church/node/intra_reader.cc` | 32, 44 | IntraReader 回调 |

### 标签

`#protobuf` `#data-race` `#concurrency` `#church-platform` `#high-severity`

---

## 案例 2：Job 190236626 - Performance 回归

### 基本信息
- **Job ID**: 190236626
- **失败 Stage**: `Stage.PERFORMANCE`
- **失败元素数**: 7

### 失败元素

| Plug | Group | 元素 | 数量 |
|------|-------|------|------|
| DRIVING | Calculator | occupancy_filter | 2 |
| DRIVING | Calculator | RasMapCpuPostProcess | 1 |
| DRIVING | Process | lidar_process | 1 |
| ... | ... | ... | ... |

### 可能原因

1. **代码变更导致性能回归** - 验证：检查相关模块的最近 commit
2. **测试环境波动** - 验证：重跑确认是否复现
3. **Baseline 版本差异** - 验证：对比 baseline 版本

### 标签

`#performance` `#regression`
