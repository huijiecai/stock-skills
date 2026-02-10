# 龙头战法选股助手

A股龙头超短战法智能选股SKILL，基于"预期管理"理论自动筛选股票。

## 🎉 项目状态：MVP v1.0 已完成

- ✅ 核心功能完整
- ✅ Tushare Pro数据源稳定
- ✅ 测试通过，可以使用

---

## 📁 项目结构

```
longtou-strategy/
├── SKILL.md                      # ⭐ LLM入口（精简版，175行）
├── README.md                     # 本文档（开发者手册）
├── logics.yaml                   # 📋 逻辑库配置
├── requirements.txt              # 依赖列表
├── .gitignore                    # Git忽略配置
├── reference/                    # 📚 详细参考文档（按需加载）
│   ├── strategy-rules.md         # 战法规则和操作铁律
│   ├── execution-guide.md        # 执行代码指南
│   ├── output-format.md          # 输出格式规范
│   └── logic-management.md       # 逻辑库管理指南
├── data/                         # 🗂️ 数据缓存目录（自动生成）
│   ├── 20260210/                 # 按日期分文件夹
│   │   ├── limit_up_stocks.json
│   │   ├── continuous_limit_up.json
│   │   ├── stock_concepts.json   # ⭐ 核心：股票概念缓存
│   │   └── em_hot_rank.json
│   └── latest -> 20260210/       # 软链接指向最新
├── modules/                      # 核心模块（可复用的Python包）
│   ├── __init__.py
│   ├── config.py.template        # Token配置模板
│   ├── config.py                 # Token配置（不提交）
│   ├── data_fetcher.py           # 数据获取（优先读缓存）
│   ├── logic_matcher.py          # 逻辑匹配
│   ├── screener.py               # 筛选器
│   └── market_analyzer.py        # 市场分析
└── scripts/                      # 🔧 可执行脚本
    ├── fetch_daily_data.py       # ⭐ 每日数据拉取脚本
    └── test.py                   # 测试脚本
```

### 文档职责

- **SKILL.md**（175行）：LLM入口，精简版，包含核心用法和 reference 引用
- **reference/**：详细文档，LLM按需加载（避免每次都加载全部内容）
- **README.md**：开发者手册（你和其他使用者阅读）

---

## 🚀 快速开始

### 1. 环境准备

**要求**：Python 3.9+（推荐3.11+）

```bash
# 进入项目目录
cd <你的工作区路径>

# 创建虚拟环境（如果还没有）
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # Linux/Mac
# 或者
.venv\Scripts\activate  # Windows

# 安装依赖
cd .cursor/skills/longtou-strategy
pip install -r requirements.txt
```

### 2. 配置Tushare Token

创建 `modules/config.py` 文件：

```python
# Tushare Pro配置
TUSHARE_TOKEN = "你的token"
```

获取Token：https://tushare.pro/register

### 3. 拉取每日数据

**⭐ 每天早盘前（8:00-8:30）运行一次**，拉取当日数据并缓存：

```bash
# 确保在skill目录下
cd .cursor/skills/longtou-strategy
python scripts/fetch_daily_data.py
```

**为什么需要这一步？**
- 避免Tushare频率限制（每次查询概念都要等待）
- 大幅提升SKILL执行速度（秒级响应）
- 数据缓存在 `data/YYYYMMDD/` 目录

### 4. 测试

```bash
# 确保在skill目录下
cd .cursor/skills/longtou-strategy
python scripts/test.py
```

### 5. 使用SKILL

在Cursor中调用：

```
/longtou-strategy 筛选今日自选股
```

---

## 🎯 核心功能

### 已完成功能（MVP v1.0）

| 功能 | 状态 | 说明 |
|------|------|------|
| 早盘筛选 | ✅ | 筛选人气榜前30，匹配逻辑库 |
| 逻辑匹配 | ✅ | 基于Tushare概念匹配热点逻辑 |
| 市场状态判断 | ✅ | 冰点修复 or 增量主升 or 震荡观望 |
| 人气排名 | ✅ | 连板+时间+龙虎榜+东财人气（四维共振）|
| 地位判断 | ✅ | 龙头/补涨/首板 |
| 逻辑库管理 | ✅ | 手动维护YAML配置 |
| 个股分析 | ✅ | 分析特定股票 |
| **数据缓存** | ✅ | **每日拉取一次，避免频率限制** |

### 计划功能（第二版）

- ⏳ 盘中实时监控
- ⏳ 买卖信号检测
- ⏳ 微信推送
- ⏳ Web可视化界面
- ⏳ 历史复盘功能

---

## ⚙️ 每日工作流程

### 推荐工作流

```
【早上8:00-8:30】拉取数据
  ↓
python scripts/fetch_daily_data.py
  ↓
【早上8:30-9:30】盘前筛选
  ↓
/longtou-strategy 筛选今日自选股
  ↓
【盘中】根据需要分析个股
  ↓
/longtou-strategy 分析 横店影视
  ↓
【收盘后】每周或主线切换时更新逻辑库
  ↓
/longtou-strategy 更新逻辑库
```

### 数据拉取的优势

**架构改进**：
- **旧方案**：每次筛选都调用API → 慢、容易被限流、每只股票重复查询
- **新方案**：早盘拉取一次缓存 → 快、稳定、股票概念数据每天只查询1次

**性能对比**：
- 拉取30只股票概念：旧方案 ~15秒，新方案 ~0.5秒（缓存命中）
- Tushare API压力：旧方案每次筛选30次调用，新方案每日仅1次批量拉取

---

## 📚 逻辑库管理

### 什么是逻辑库？

逻辑库是你当前关注的热点题材清单，告诉系统：
- 当前市场在炒什么？
- 哪些是核心受益方？
- 逻辑强度有多高？
- 预计能持续多久？

### 如何维护？

**配置文件**：`logics.yaml`

**更新频率**：
- 每周复盘时更新
- 重大题材出现时及时更新
- 市场主线切换时更新

**配置示例**：

```yaml
逻辑库:
  - 名称: 影视传媒
    龙头股票: 欢瑞世纪
    龙头代码: "000892"
    炒作原因: 春节档电影票房创新高
    相关概念:
      - 影视动漫
      - 传媒
    逻辑强度: 5
    持续性: 1-2周
    驱动类型: 题材驱动
    推荐模式:
      - 冰点修复
    风险提示: 题材炒作，注意板块退潮
```

---

## 🎓 战法核心

### 预期管理四步法

1. **建立预期**：筛选符合条件的股票
2. **确认预期**（买入）：等待确认信号
3. **兑现预期**（卖出）：预期实现即离场
4. **复盘**：验证预期，迭代认知

### 三种情绪拐点模式

**只做情绪拐点，强势板块的领涨个股**：

1. **冰点修复**：情绪冰点后的修复机会
2. **龙头弱转强**：主线延续
3. **补涨分离**：主线以补涨延续

### 筛选铁律（缺一不可）

1. **人气底线**：进入当日人气榜前30
2. **逻辑正宗**：匹配热点逻辑，逻辑强度≥4星
3. **地位突出**：身位最高 OR 领涨性强 OR PK胜出
4. **市场状态**：
   - 冰点修复：昨日跌停>15家 + 连板≤2板
   - 增量主升：连板高度≥3板

---

## 💡 使用示例

### 早盘筛选

```
你：/longtou-strategy 筛选今日自选股

AI：[执行筛选]
    
    📊 市场状态：增量主升
    昨日跌停：3家 | 连板高度：7板
    
    🎯 今日重点自选股（11只）
    
    1. 横店影视 (603103) ⭐⭐⭐⭐⭐
       - 逻辑：影视传媒（题材驱动）
       - 地位：7连板龙头
       - 推荐模式：龙头弱转强
```

### 分析个股

```
你：分析一下横店影视

AI：[执行分析]
    
    横店影视 (603103)
    ✅ 匹配逻辑：影视传媒 ⭐⭐⭐⭐⭐
    ✅ 地位：7连板龙头（身位最高）
    ✅ 受益等级：核心
    
    操作建议：
    - 次日高开>3%+站稳均线可介入
    - 注意板块退潮风险
```

---

## 🔧 技术细节

### 数据源

- **AKShare**：涨停榜、龙虎榜、连板数据（免费）
- **Tushare Pro**：股票概念板块（免费，需积分）

### 人气排名算法

```
人气分数 = 连板数 × 20 + 涨停时间分 + 龙虎榜分

涨停时间分：
  - 9:35前：30分
  - 10:00前：20分
  - 10:30前：10分
  - 其他：5分

龙虎榜分：
  - 上榜：+25分
```

### 逻辑匹配算法

```
1. 使用Tushare获取股票概念
2. 遍历逻辑库，检查概念是否匹配
3. 匹配成功：
   - 检查逻辑强度（≥4星）
   - 判断受益等级（核心/次核心）
   - 过滤蹭热点股票
4. 返回匹配结果
```

---

## ⚠️ 重要提示

1. **不是自动交易系统**：SKILL仅提供筛选和分析
2. **需要人工判断**：系统无法替代盘感
3. **逻辑库需维护**：逻辑库质量直接影响筛选效果
4. **仅供参考**：所有分析仅供参考，不构成投资建议
5. **风险自负**：股市有风险，投资需谨慎

---

## 🐛 常见问题

### Q1: 无法获取股票概念？

**原因**：Tushare Token未配置或积分不足

**解决**：
1. 检查 `modules/config.py` 文件是否存在
2. 确认Token正确
3. 查看Tushare积分是否>=300

### Q2: 筛选结果为空？

**原因**：
- 今日无涨停股票
- 涨停股票都不符合逻辑库
- 逻辑强度设置太高

**解决**：
- 检查是否交易日
- 更新逻辑库
- 降低最小逻辑强度

### Q3: 如何添加新的热点逻辑？

编辑 `logics.yaml`，参考现有格式添加：

```yaml
- 名称: 你的逻辑名称
  龙头股票: 龙头名称
  龙头代码: "股票代码"
  炒作原因: 炒作原因
  相关概念:
    - 概念1（使用Tushare概念名称）
    - 概念2
  逻辑强度: 5
  持续性: 预计时间
  驱动类型: 政策/业绩/价格/题材
  推荐模式:
    - 适用模式
  风险提示: 风险点
```

---

## 📦 分享和部署

### 给他人使用此SKILL

#### 方式1：压缩包分享

```bash
cd .cursor/skills
tar -czf longtou-strategy.tar.gz \
    --exclude='modules/config.py' \
    --exclude='modules/__pycache__' \
    --exclude='.venv' \
    longtou-strategy/
```

**他人使用**：
1. 解压到 `.cursor/skills/` 目录
2. `cd longtou-strategy && pip install -r requirements.txt`
3. 复制 `modules/config.py.template` 为 `config.py` 并填入自己的 Tushare token
4. 运行 `python test.py` 测试

#### 方式2：Git仓库

```bash
cd .cursor/skills/longtou-strategy

# 初始化 git（如果还没有）
git init

# .gitignore 已配置，不会提交敏感文件
git add .
git commit -m "龙头战法选股助手 v1.0"

# 推送到远程仓库
git remote add origin <你的仓库地址>
git push -u origin main
```

**他人克隆使用**：
```bash
cd .cursor/skills
git clone <仓库地址> longtou-strategy
cd longtou-strategy
pip install -r requirements.txt
cp modules/config.py.template modules/config.py
# 编辑 config.py 填入自己的 token
python test.py
```

### 跨平台兼容性

- ✅ **Mac/Linux/Windows** 全平台兼容
- ✅ 使用动态路径，无硬编码
- ✅ 任何工作区都能使用
- ✅ 不依赖特定用户路径

### 升级说明

当SKILL更新时：

```bash
cd .cursor/skills/longtou-strategy

# Git方式
git pull

# 手动方式：直接覆盖文件（保留你的 config.py）

# 更新依赖
pip install -r requirements.txt --upgrade
```

---

## 🐛 常见问题

### Q1: 导入模块失败

**问题**：`ModuleNotFoundError: No module named 'akshare'`

**解决**：
```bash
source .venv/bin/activate  # 激活虚拟环境
pip install -r requirements.txt
```

### Q2: Tushare积分不足

**问题**：`APIError: 积分不足`

**解决**：
- Tushare Pro 注册后默认有 120 积分（够用）
- 每日消耗约 5-10 积分
- 可通过完成任务获取更多积分

### Q3: Tushare IP限制

**问题**：`您的IP数量超限，最大数量为2个！`

**原因**：
- Tushare限制每个token最多在2个IP上使用
- 如果在多台机器或网络切换（如VPN、移动网络、办公室WiFi），容易触发

**解决方案**：

**方案1：在固定机器上运行**（推荐）
```bash
# 在同一台电脑、同一网络环境下运行数据拉取脚本
python scripts/fetch_daily_data.py
```

**方案2：降级模式**（兜底）
- 脚本会自动检测IP限制，保存已成功拉取的部分数据
- 未成功的概念数据会在筛选时通过实时API获取（速度稍慢）
- 不影响核心功能使用

**方案3：等待IP清理**
- Tushare会定期清理IP记录（通常24小时）
- 或联系Tushare客服申请重置

### Q4: 路径错误

**问题**：找不到 `logics.yaml`

**解决**：
- 确保SKILL文件夹位于 `.cursor/skills/longtou-strategy/`
- 执行时工作目录应该是工作区根目录

---

## 📖 参考文档

- **SKILL文档**：`SKILL.md`（LLM使用）
- **战法思路**：`龙头战法/思路.md`（如果在同一工作区）
- **Tushare文档**：https://tushare.pro/document/2

---

## 🔄 版本历史

### v1.0 (2026-02-10)

- ✅ 完成MVP核心功能
- ✅ 集成Tushare Pro数据源
- ✅ 实现早盘筛选功能
- ✅ 实现逻辑匹配和市场状态分析
- ✅ 测试通过，稳定运行

---

## 📞 维护说明

本项目由AI助手协助开发，供个人学习和实战使用。

**文档规范**：
- `SKILL.md` - LLM阅读（执行时的操作手册）
- `README.md` - 开发者阅读（本文档，包含安装、开发、分享指南）
- 不创建额外文档，保持目录清爽

**重要提醒**：
- ⚠️ 不要提交 `modules/config.py`（包含你的 Tushare token）
- 📝 定期更新 `logics.yaml` 保持逻辑库最新
- 🔄 每周或市场主线切换时更新逻辑库

祝交易顺利！🚀📈
