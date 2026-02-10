# ThreadSanitizer 分析指南

## 概述

ThreadSanitizer (TSan) 是一个动态分析工具，用于检测 C++ 程序中的数据竞争和其他线程安全问题。

在 Module Bench 测试中，`Stage.THREAD_SANITIZER` 失败表示检测到线程安全问题。

## TSan 报告结构

### Summary 行

每个 TSan issue 都有一个 SUMMARY 行，格式如下：

```
SUMMARY: ThreadSanitizer: data race /path/to/file.cc:123 in ClassName::FunctionName()
```

关键信息：
- **问题类型**：`data race`, `lock-order-inversion`, `thread leak` 等
- **文件路径**：发生问题的源文件
- **行号**：问题发生的行
- **函数名**：涉及的函数

### 详细报告

```
WARNING: ThreadSanitizer: data race (pid=12345)
  Read of size 8 at 0x7f1234567890 by thread T1:
    #0 ClassName::ReadMethod() /path/to/file.cc:100 (module.so+0x123456)
    #1 Caller::Function() /path/to/caller.cc:50 (module.so+0x789abc)
    
  Previous write of size 8 at 0x7f1234567890 by thread T2:
    #0 ClassName::WriteMethod() /path/to/file.cc:200 (module.so+0xdef012)
    #1 OtherCaller::Function() /path/to/other.cc:30 (module.so+0x345678)
    
  Location is global 'some_variable' of size 8 at 0x7f1234567890 (module.so+0xabc)
  
  Thread T1 (tid=111, running) created by main thread at:
    ...
    
  Thread T2 (tid=222, running) created by main thread at:
    ...
```

### 关键分析点

1. **操作类型**：`Read of size X` vs `Write of size X`
2. **内存地址**：竞争发生的内存位置
3. **线程信息**：哪些线程参与竞争
4. **调用堆栈**：读写操作的完整调用链
5. **变量信息**：`Location is global/heap/stack 'variable_name'`

## 常见 Data Race 模式

### 1. Protobuf 并发读写

**特征**：堆栈中包含 `protobuf` 或 `.pb.` 相关类

```
Read of size 8 at 0x... by thread T1:
    #0 google::protobuf::...
    #1 MyClass::GetProtoField()
    
Previous write of size 8 at 0x... by thread T2:
    #0 google::protobuf::...
    #1 MyClass::SetProtoField()
```

**原因**：Protobuf 对象在多线程间共享，读写未加锁

**修复方案**：
```cpp
// 方案1：加锁保护
std::mutex mtx_;
void SetField(const Value& v) {
    std::lock_guard<std::mutex> lock(mtx_);
    proto_.set_field(v);
}
Value GetField() const {
    std::lock_guard<std::mutex> lock(mtx_);
    return proto_.field();
}

// 方案2：使用 copy
MyProto GetProtoCopy() const {
    std::lock_guard<std::mutex> lock(mtx_);
    return proto_;  // 返回拷贝
}
```

### 2. 成员变量并发访问

**特征**：读写发生在同一个类的不同方法

```
Read of size 1 at 0x... by thread T1:
    #0 MyClass::IsReady() /src/my_class.cc:50
    
Previous write of size 1 at 0x... by thread T2:
    #0 MyClass::SetReady() /src/my_class.cc:100
```

**修复方案**：
```cpp
// 对于简单类型，使用 std::atomic
std::atomic<bool> ready_{false};

// 对于复杂类型，使用 mutex
std::mutex mtx_;
State state_;
```

### 3. 容器并发修改

**特征**：涉及 `std::vector`, `std::map` 等容器操作

```
Write of size 8 at 0x... by thread T1:
    #0 std::vector<...>::push_back()
    #1 MyClass::AddItem()
    
Previous read of size 8 at 0x... by thread T2:
    #0 std::vector<...>::operator[]()
    #1 MyClass::GetItem()
```

**修复方案**：
```cpp
// 使用 mutex 保护容器
std::mutex items_mtx_;
std::vector<Item> items_;

void AddItem(const Item& item) {
    std::lock_guard<std::mutex> lock(items_mtx_);
    items_.push_back(item);
}

// 或使用 concurrent 容器
tbb::concurrent_vector<Item> items_;
```

### 4. 回调函数中的竞争

**特征**：读写发生在回调链中

```
Read of size 8 at 0x... by thread T1 (callback thread):
    #0 Callback::OnEvent()
    #1 EventLoop::Dispatch()
    
Previous write of size 8 at 0x... by main thread:
    #0 Manager::UpdateConfig()
```

**修复方案**：
- 在回调中对共享数据加锁
- 使用消息队列解耦
- Copy-on-read 模式

## 分析流程

### Step 1: 搜索 TSan 详细报告

**推荐方式**：搜索 Thread Sanitizer Summary（包含完整 data race 详情）

```bash
# 搜索完整的 TSan 报告（data race 日志可能很长，根据实际数量调整行数）
grep "Thread Sanitizer Summary" <log_file> -A 500

# 或使用脚本
python3 scripts/fetch_gitlab_log.py <job_url> --tsan
```

**备选方式**：直接搜索 data race 警告

```bash
# 搜索 data race 警告（每个 race 约 40-80 行）
grep -E "WARNING: ThreadSanitizer: data race" <log_file> -A 80

# 搜索写操作堆栈
grep -E "Previous write|Previous read" <log_file> -A 40

# 搜索单行摘要
grep "SUMMARY: ThreadSanitizer" <log_file>
```

### Step 2: 统计问题类型

从 Thread Sanitizer Report 表格中获取统计：

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

问题类型：
- `data race`: 数据竞争（最常见）
- `lock-order-inversion`: 锁顺序问题（可能死锁）
- `thread leak`: 线程泄漏

### Step 3: 分类分析

对每个 data race：
1. 识别涉及的类/模块
2. 分析读写操作的调用链
3. 确定竞争的变量/资源
4. 判断问题模式（protobuf/容器/成员变量等）

### Step 4: 输出诊断表格

**必须输出读写操作分析表格**：

```markdown
| 操作 | 线程 | 函数 | 代码位置 |
|------|------|------|---------|
| 读 | T45 | std::_Hashtable::count() | nn_internal_impl_cuda.cc:203 |
| 写 | T49 | std::_Hashtable 构造 | nn_internal_impl_cuda.cc:203 |
```

**调用链分析**：

```markdown
**读线程 T45**:
TrafficSignClsCalculator::Open() → NnInternal::Create() → InitNn() → count()

**写线程 T49**:
TrafficLightShapeCalculator::Open() → NnInternal::Create() → InitNn() → 构造
```

### Step 5: 输出诊断报告

```markdown
## Data Race 诊断报告

### 问题统计
| 问题类型 | 数量 |
|---------|------|
| data race | 28 |
| other issues | 1 |

### 按模块分类
| 模块 | 问题数 | 主要问题 |
|------|--------|---------|
| sensor_fusion | 10 | Protobuf 并发读写 |
| tracking | 8 | 容器并发修改 |
| prediction | 5 | 成员变量无锁 |

### 典型问题示例

#### Issue #1: sensor_fusion 模块 Protobuf 竞争
- **文件**: sensor_fusion.cc:123
- **读线程**: callback thread (OnSensorData)
- **写线程**: main thread (UpdateConfig)
- **竞争对象**: config_ (protobuf)
- **建议**: 使用 mutex 保护 config_ 读写

...
```

## 常见误报

### Arena 相关

Protobuf Arena 的某些操作可能触发 TSan 警告，但实际是安全的。

### Lazy 初始化

使用 `call_once` 或 `static` 局部变量的 lazy 初始化可能触发警告。

## 修复优先级

1. **高**：影响数据正确性的竞争（状态变量、配置对象）
2. **中**：可能导致崩溃的竞争（容器操作）
3. **低**：统计/日志相关的竞争（counter++）

## 参考资料

- [ThreadSanitizer Documentation](https://clang.llvm.org/docs/ThreadSanitizer.html)
- [Data Race Patterns](https://github.com/google/sanitizers/wiki/ThreadSanitizerPopularDataRaces)

