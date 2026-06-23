# DOPS 登录脚本

## 功能说明

本脚本使用 Playwright 库自动登录 DOPS 系统，实现了以下功能：
- 启动 Chrome 浏览器
- 访问登录页面
- 自动输入用户名和密码
- 点击登录按钮
- 等待登录成功

## 环境配置

### 1. 安装依赖

```bash
# 安装 Playwright 库
pip install -r requirements.txt
```

### 2. 配置登录信息

编辑 `dops_登录.py` 文件，修改以下配置：

```python
# 登录信息
url = "https://10.165.32.24/dops/#/admin/login"
username = "your_username"  # 替换为实际用户名
password = "your_password"  # 替换为实际密码
```

### 3. 首次运行

脚本会自动检测并使用系统已安装的 Chrome 浏览器，无需下载额外的浏览器驱动。

如果系统没有安装 Chrome 浏览器，脚本会尝试使用 Playwright 内置浏览器（需要先安装浏览器驱动）。

**使用系统 Chrome 浏览器的优势**：
- 无需下载额外的浏览器驱动
- 使用熟悉的浏览器环境
- 更快的启动速度

## 运行脚本

```bash
python dops_登录.py
```

## 可能遇到的问题及解决方法

### 1. 浏览器驱动下载失败

**解决方法**：
- 脚本已配置为优先使用系统 Chrome 浏览器，无需下载驱动
- 如果需要使用 Playwright 内置浏览器，确保网络连接正常
- 可以手动下载驱动并配置路径

### 2. 登录失败

**解决方法**：
- 检查用户名和密码是否正确
- 检查 XPath 和属性选择器是否正确
- 检查网络连接和目标系统是否可访问

### 3. 证书错误

**解决方法**：
- 脚本已添加 `--ignore-certificate-errors` 参数，会自动忽略证书错误

## 依赖说明

- Python 3.7+
- Playwright 1.48.0

## 脚本结构

- `dops_登录.py` - 主登录脚本
- `requirements.txt` - 依赖配置文件
- `README.md` - 本说明文件
