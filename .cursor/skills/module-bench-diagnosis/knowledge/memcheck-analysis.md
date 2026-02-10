# Memcheck 分析指南

Valgrind Memcheck 用于检测 C/C++ 程序中的内存问题。

## 错误类型

| 错误类型 | 含义 | 严重程度 |
|----------|------|----------|
| **Definitely lost** | 确定的内存泄漏，无法访问的内存块 | 🔴 高 |
| **Indirectly lost** | 间接泄漏，因其他泄漏导致无法访问 | 🟡 中 |
| **Possibly lost** | 可能的泄漏，指针可能指向块中间 | 🟡 中 |
| **Still reachable** | 程序结束时仍可访问但未释放 | 🟢 低 |
| **Invalid read** | 读取无效内存（越界/已释放） | 🔴 高 |
| **Invalid write** | 写入无效内存（越界/已释放） | 🔴 高 |
| **Uninitialised value** | 使用未初始化的值 | 🔴 高 |
| **Mismatched free** | new/delete 与 malloc/free 不匹配 | 🟡 中 |

## 搜索命令

```bash
# 完整 Memcheck 报告
grep "Memchek Cpu Test Summary" <log> -A 500

# 搜索特定错误类型
grep -E "definitely lost|Invalid read|Invalid write|Uninitialised" <log> -A 10
```

## 报告格式解析

```
==12345== 1,024 bytes in 1 blocks are definitely lost in loss record 1 of 10
==12345==    at 0x4C2BBAF: malloc (vg_replace_malloc.c:299)
==12345==    by 0x401234: MyClass::Allocate() (myclass.cc:50)
==12345==    by 0x401567: ProcessData() (processor.cc:100)
```

**解析要点**：
- `==12345==`：进程 ID
- `1,024 bytes in 1 blocks`：泄漏大小
- `definitely lost`：泄漏类型
- 堆栈中找业务代码位置（非 libc/vg_replace）

## 常见问题和修复

### 1. 内存泄漏 (Definitely lost)

**原因**：分配的内存未释放

**修复**：
```cpp
// 错误
void process() {
    char* buf = new char[1024];
    // 忘记 delete[] buf;
}

// 正确
void process() {
    std::unique_ptr<char[]> buf(new char[1024]);
    // 自动释放
}
```

### 2. 未初始化读取 (Uninitialised value)

**原因**：使用未初始化的变量

**修复**：
```cpp
// 错误
int x;
if (x > 0) { ... }  // x 未初始化

// 正确
int x = 0;
if (x > 0) { ... }
```

### 3. 无效读写 (Invalid read/write)

**原因**：访问已释放内存或越界

**修复**：
```cpp
// 错误
std::vector<int> v = {1, 2, 3};
int x = v[10];  // 越界

// 正确
if (index < v.size()) {
    int x = v[index];
}
```

## 输出模板

```markdown
### Memcheck 分析

| 错误类型 | 数量 | 模块 | 代码位置 |
|----------|------|------|---------|
| Definitely lost | 1 | planning | optimizer.cc:123 |
| Uninitialised value | 3 | perception | tracker.cc:456 |

**调用链**：
- ProcessData() → MyClass::Allocate() → malloc()

**修复建议**：
1. optimizer.cc:123 使用 `std::unique_ptr` 管理内存
2. tracker.cc:456 初始化变量
```

