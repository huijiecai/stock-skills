# 安装说明

## 依赖问题说明

**问题**：akshare最新版本需要Python 3.9+，当前系统是Python 3.8.10

**解决方案（三选一）**：

### 方案1：升级Python到3.9+（推荐）

```bash
# 使用brew安装新版Python
brew install python@3.11

# 创建虚拟环境
python3.11 -m venv /Users/huijiecai/Project/stock/.venv

# 激活并安装依赖
source /Users/huijiecai/Project/stock/.venv/bin/activate
pip install -r requirements.txt
```

### 方案2：使用pyenv管理Python版本

```bash
# 安装pyenv
brew install pyenv

# 安装Python 3.11
pyenv install 3.11.7

# 在项目目录设置Python版本
cd /Users/huijiecai/Project/stock
pyenv local 3.11.7

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 方案3：使用conda（如果有Anaconda/Miniconda）

```bash
# 创建新环境
conda create -n stock python=3.11
conda activate stock

# 安装依赖
pip install -r requirements.txt
```

## 验证安装

安装完成后，运行测试：

```bash
cd /Users/huijiecai/Project/stock/.cursor/skills/longtou-strategy
python test.py
```

## 快速测试（不需要网络数据）

如果你想先测试逻辑匹配功能（不需要联网获取数据）：

```bash
python -c "
from modules import LogicMatcher
matcher = LogicMatcher()
print(f'逻辑库加载成功：{len(matcher.get_all_logics())} 个逻辑')
"
```

## MVP已完成的文件

✅ 所有核心代码已经完成：
- `SKILL.md` - SKILL主文件
- `modules/data_fetcher.py` - 数据获取
- `modules/logic_matcher.py` - 逻辑匹配
- `modules/screener.py` - 筛选器
- `logic_library/current_logics.yaml` - 逻辑库配置
- `test.py` - 测试脚本

只需要解决Python版本问题即可使用！
