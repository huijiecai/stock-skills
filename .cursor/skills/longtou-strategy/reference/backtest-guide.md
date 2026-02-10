# 回测分析执行指南

当用户请求"回测分析"或"历史回测"时，执行以下Python代码：

## 基础回测（30天，100只样本）

```python
import sys
import os

# 动态获取skill路径
workspace_root = os.getcwd()
skill_path = os.path.join(workspace_root, '.cursor/skills/longtou-strategy')
sys.path.insert(0, skill_path)

from modules import BacktestEngine, PatternAnalyzer

# 1. 初始化回测引擎
engine = BacktestEngine(days=30)

# 2. 获取交易日
trading_days = engine.get_trading_days(30)

# 3. 获取涨停股票数据
limit_up_data = engine.get_limit_up_stocks_batch(trading_days)

# 4. 计算续板率和后续表现
backtest_df = engine.calculate_continuation_rate(limit_up_data, sample_size=100)

# 5. 模式分析
analyzer = PatternAnalyzer(backtest_df)

# 时间模式
time_pattern = analyzer.analyze_time_pattern()

# 行业模式
industry_pattern = analyzer.analyze_industry_pattern()

# 赚钱模式
winning_patterns = analyzer.find_winning_patterns(top_n=5)

# 亏钱模式
losing_patterns = analyzer.find_losing_patterns(top_n=3)

# 优化建议
suggestions = analyzer.generate_suggestions()
```

## 快速回测（使用脚本）

```python
import subprocess
import os

workspace_root = os.getcwd()
script_path = os.path.join(
    workspace_root, 
    '.cursor/skills/longtou-strategy/scripts/run_backtest.py'
)

# 运行回测脚本
result = subprocess.run(
    ['python', script_path, '--days', '30', '--sample', '100'],
    capture_output=True,
    text=True
)

print(result.stdout)
```

## 输出格式

按以下格式输出回测结果：

```markdown
# 📊 历史回测分析报告

**回测周期**：最近30个交易日  
**分析样本**：100只涨停股票  

---

## 🔥 赚钱模式TOP5

### 1. 早盘涨停
- **特征**：9:30-10:00涨停
- **样本数**：25只
- **T+1平均收益**：+5.2%
- **T+1胜率**：68%
- **T+3平均收益**：+8.1%

### 2. 文化传媒板块
- **特征**：文化传媒相关股票
- **样本数**：18只
- **T+1平均收益**：+4.3%
- **T+1胜率**：61%
- **T+3平均收益**：+6.5%

...（其他模式）

---

## ⚠️ 亏钱模式（需要避免）

### 1. 尾盘涨停
- **特征**：14:00后涨停
- **样本数**：12只
- **T+1平均收益**：-2.1%
- **T+1胜率**：33%
- **⚠️ 风险**：续板率低，容易高开低走

...（其他模式）

---

## 💡 策略优化建议

1. ✅ **提高'早盘涨停'权重（+20分）**  
   早盘涨停收益率5.2%，明显优于尾盘涨停-2.1%

2. 🔥 **重点关注'文化传媒'板块**  
   T+1平均收益4.3%，胜率61%

3. ⚠️ **降低'尾盘涨停'权重（-30分）**  
   尾盘涨停平均收益-2.1%，风险较大

4. 🗑️ **建议移除'XX板块'逻辑**  
   T+1平均收益-1.5%，无赚钱效应

---

## 📝 执行步骤

根据以上分析结果，建议执行以下操作：

1. **调整人气排名权重**（修改 `modules/screener.py`）
   - 早盘涨停：+20分
   - 尾盘涨停：-30分

2. **更新逻辑库**（修改 `logics.yaml`）
   - 提高"文化传媒"逻辑强度到⭐⭐⭐⭐⭐
   - 移除无效逻辑

3. **下次回测时间**：建议每周执行一次回测

---

💾 **详细数据**：已保存到 `data/backtest/backtest_YYYYMMDD_days30.csv`
```

## 注意事项

1. **回测耗时**：
   - 30天 + 100只样本 ≈ 10-15分钟
   - 如果用户希望快速验证，可以先用5天 + 20只样本测试

2. **数据可用性**：
   - akshare的历史数据可能不完整
   - 部分股票可能无后续行情（停牌、退市等）
   - 统计结果仅供参考

3. **自动保存**：
   - 回测数据自动保存到 `data/backtest/`
   - 包括CSV原始数据和JSON分析报告
   - 可用于后续深度分析

## 进阶用法

### 自定义回测参数

```python
# 更长周期回测
engine = BacktestEngine(days=60)

# 更大样本量
backtest_df = engine.calculate_continuation_rate(limit_up_data, sample_size=200)

# 只分析特定行业
filtered_df = backtest_df[backtest_df['所属行业'] == '文化传媒']
analyzer = PatternAnalyzer(filtered_df)
```

### 对比不同周期

```python
# 对比30天 vs 60天的模式变化
engine_30 = BacktestEngine(days=30)
engine_60 = BacktestEngine(days=60)

# 分别分析，对比结果
...
```
