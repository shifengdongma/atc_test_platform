# uav_emitter 项目规则

## 环境配置

### Python 环境
- 使用 conda 的 `utm` 环境
- 激活命令: `conda activate utm`

### 工作目录
- 执行脚本时默认使用 `uav_emitter` 目录作为工作目录
- 所有相对路径都基于该目录解析

## 执行规范

### 运行 emitter.py
```powershell
# 1. 激活环境
conda activate utm

# 2. 切换到项目目录
cd c:/Users/wdjlw/iCloudDrive/AI_Python2026/无人机模拟器工具/无人机飞行数据自动化工具yfk0422/uav_emitter

# 3. 执行脚本
python emitter.py
```

## 项目结构
- `config.yaml` - 配置文件（Kafka配置、激活场景）
- `emitter.py` - 主发射程序
- `kafka_proc.py` - Kafka 处理模块
- `scenes/` - 场景数据目录
  - 各场景子目录包含 JSON 飞行数据文件和 scene.yaml

## 配置说明
- `active_scenes` 指定要激活的场景
- 每个场景目录下的 `scene.yaml` 定义该场景包含的 UAV 数据文件
