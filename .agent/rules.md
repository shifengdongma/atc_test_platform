# atc_test_platform 项目规则

本文件为灵码在 `atc_test_platform` 项目中的行为规则，用于指导 AI 助手在此项目目录下的代码生成、调试和文件操作。

## Python 环境配置（强制）

### 默认 Conda 环境
- **环境名称**: `utm`
- **Python 版本**: 3.11.15
- **conda.exe 路径**: `C:\wbData\anaconda3\Scripts\conda.exe`
- **激活方式**: `conda activate utm` 或 `conda run -n utm python`

### 运行 Python 脚本的规范
1. **必须先激活环境**：执行任何 Python 脚本前，必须先运行 `conda activate utm`
2. **IDE 执行时自动切换**：在 IDE 中运行脚本时，应自动使用 `conda run -n utm python` 执行
3. **使用环境内的 pip**：安装依赖时必须使用 `utm` 环境中的 pip

### IDE 脚本执行配置（强制）
当在 IDE 中运行 Python 脚本时，应自动使用 utm 环境。配置方式：

**方式 1：通过 conda run 执行**
```powershell
# 使用 utm 环境运行脚本
conda run -n utm python <script_path>

# 完整命令示例
conda run -n utm python d:/AI_Test_2026/atc_test_platform/atc_test_cases/dkkgdev/utm_dev_随机模拟器发射.py
```

**方式 2：IDE 配置默认解释器**
- 在 IDE 中将默认 Python 解释器设置为 utm 环境的路径：
  `C:\wbData\anaconda3\envs\utm\python.exe`

**方式 3：脚本内自动切换（不推荐）**
如需脚本独立运行，可在脚本开头添加自动检测代码：
```python
import subprocess
import os

current_env = os.environ.get('CONDA_DEFAULT_ENV', '')
if current_env != 'utm':
    conda_path = r"C:\wbData\anaconda3\Scripts\conda.exe"
    if os.path.exists(conda_path):
        script_path = os.path.abspath(__file__)
        subprocess.run([conda_path, 'run', '-n', 'utm', 'python', script_path] + sys.argv[1:])
        sys.exit(0)
```

### 环境检查示例
```bash
conda activate utm
python --version  # 应输出 Python 3.11.x
which python      # 应指向 utm 环境路径
```

---

## 项目目录说明

本项目包含多个子模块：

| 目录 | 说明 |
|------|------|
| `utm_moc52_devlop/` | UTM MOC52 开发代码 |
| `utm_simulator/` | 模拟器相关代码 |
| `atc_ha_test/` | 高可用测试脚本 |
| `atc_data_factory/` | 数据工厂脚本 |
| `atc_perf_test/` | 性能测试 |
| `atc_ai_test/` | AI 测试 |
| `atc_api_info/` | API 信息 |
| `utm_test_cases/` | 测试用例 |

---

## 代码修改工作流（强制）

### 先方案，后执行
1. **必须先发方案**：在进行任何代码生成、修改、删除操作前，必须先向用户展示完整的方案
2. **方案内容**：包括修改的文件列表、每处改动的具体说明、预期效果
3. **等待确认**：明确告知用户"请确认后再执行"，在收到用户明确同意（如"确认"、"执行"、"改"）后方可操作
4. **禁止擅自修改**：未获得用户确认前，不得执行任何文件写入、编辑、删除操作

### 方案示例格式
```
拟修改以下文件：
1. file_a.py - 修改函数 X，原因是 Y
2. file_b.py - 新增配置项 Z

确认后我将执行修改。
```

---

## 通用规范

- Python 脚本使用 UTF-8 编码
- 添加必要的错误处理和日志输出
- 关键操作添加时间戳记录

---

*适用范围: d:\AI_Test_2026\atc_test_platform 及其子目录*
