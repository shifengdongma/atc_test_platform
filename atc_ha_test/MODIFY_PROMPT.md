# HA 一键缩容测试脚本优化修改提示词

## 目标文件
`utm_moc52_develop/utm_test_cases/高可用测试/ha_scale_test.py`

## 修改要求

### 1. 配置方式改进
- 使用 `argparse` 替代文件头部的硬编码配置
- 支持命令行参数：`--service`, `--namespace`, `--rounds`, `--dry-run`, `--wait`, `--master`
- 保留默认值（从原配置区读取），确保向后兼容

```python
# 实现示例
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="HA 一键缩容测试")
    parser.add_argument("--service", "-s", default=TARGET_SERVICE, help="目标服务名")
    parser.add_argument("--namespace", default=TARGET_NAMESPACE, help="命名空间")
    parser.add_argument("--cluster", default=CLUSTER_NAME, help="集群名称")
    parser.add_argument("--kind", default=TARGET_KIND, help="资源类型")
    parser.add_argument("--rounds", "-r", type=int, default=ROUNDS, help="测试轮次")
    parser.add_argument("--wait", "-w", type=int, default=WAIT_SECONDS, help="等待秒数")
    parser.add_argument("--master", choices=["auto", "A", "B"], default=MASTER_NODE, help="主集群")
    parser.add_argument("--dry-run", action="store_true", help="只模拟流程不执行")
    parser.add_argument("--analysis", type=int, default=ANALYSIS_MINUTES, help="日志分析窗口(分钟)")
    return parser.parse_args()
```

---

### 2. 日志系统标准化
- 使用标准 `logging` 模块替代自定义 `Tee` 类
- 同时输出到控制台和文件
- 统一日志格式

```python
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(log_file: str):
    logger = logging.getLogger("ha_scale_test")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # 控制台
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    # 文件
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
```

---

### 3. 检查点解耦
- 定义抽象基类 `Checkpoint`
- 实现 `RedisCheckpoint`, `EsCheckpoint`, `DmCheckpoint`, `ServicesCheckpoint`
- 支持动态配置检查点列表

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class CheckpointResult:
    name: str
    status: str  # "一致" | "不一致" | "检查失败"
    detail: str = ""
    timestamp: str = ""

class Checkpoint(ABC):
    @property
    @abstractmethod
    def name(self) -> str: pass

    @abstractmethod
    def run(self) -> CheckpointResult: pass

class RedisCheckpoint(Checkpoint):
    @property
    def name(self) -> str: return "Redis"

    def run(self) -> CheckpointResult:
        # 原 `_check_redis` 逻辑
        ...

class EsCheckpoint(Checkpoint):
    @property
    def name(self) -> str: return "ES"

    def run(self) -> CheckpointResult:
        # 原 `_check_es` 逻辑
        ...
```

- 在 `HaScaleTester` 中整合：

```python
class HaScaleTester:
    def __init__(self, ...):
        self.checkpoints: List[Checkpoint] = [
            RedisCheckpoint(),
            EsCheckpoint(),
            DmCheckpoint(),
            ServicesCheckpoint(),
        ]

    def run_checkpoints(self) -> Dict[str, CheckpointResult]:
        results = {}
        for cp in self.checkpoints:
            results[cp.name] = cp.run()
        return results
```

---

### 4. 并行日志下载
- A/B 双集群日志并行下载

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_log_analysis(self, analysis_minutes: Optional[int] = None):
    ...

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(analyzer.download_cluster_logs, cluster_a)
        future_b = executor.submit(analyzer.download_cluster_logs, cluster_b)

        logs_a = future_a.result()
        logs_b = future_b.result()

    # 后续分析逻辑保持不变
    ...
```

---

### 5. 常量统一管理
- 提取魔法数字为配置类

```python
class TestConfig:
    # 超时配置
    POLL_TIMEOUT_SECONDS = 300
    CLUSTER_API_TIMEOUT = 10
    RECOVERY_TIMEOUT = 300

    # 等待配置
    SWITCH_DETECT_INTERVAL = 5       # 主集群检测间隔(秒)
    SWITCH_DETECT_EXTRA_WAIT = 120   # 检测到切换后额外等待(秒)
    DEFAULT_POLL_INTERVAL = 5        # 状态轮询间隔(秒)

    # 日志配置
    MIN_ANALYSIS_MINUTES = 5
    ROUND_COOLDOWN_FACTOR = 30       # 轮次间隔 = analysis_minutes * this

    # 重试配置
    MAX_API_ERROR_COUNT = 2
```

---

### 6. 异常恢复独立方法
- 提取 `_attempt_recovery` 方法

```python
def _attempt_recovery(self, master_key: str) -> bool:
    """尽最大努力恢复服务，异常时不抛出"""
    original = self.original_replicas
    if original is None or original == self.scale_to_zero:
        return True  # 无需恢复

    current_ready, current_replicas = self._get_service_replicas(master_key)
    if current_replicas == original:
        print("[恢复] 当前副本数已是目标值，无需恢复")
        return True

    print(f"[恢复] 尝试恢复服务至 {original} 副本...")
    success = self.scale_service(master_key, original)
    if success:
        self._wait_for_replicas(master_key, original, original)
    return success
```

---

### 7. 测试结果持久化
- 支持 JSON 报告输出

```python
def save_report_json(self, output_path: str):
    import json

    report = {
        "test_config": {
            "service": self.target_service,
            "namespace": self.target_namespace,
            "cluster": self.cluster_name,
            ...
        },
        "round_results": self.round_results,
        "summary": {
            "total_rounds": len(self.round_results),
            "passed": sum(1 for r in self.round_results if not r.get("error")),
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
```

- 命令行增加 `--report-json` 参数

---

### 8. WS 检查可选配置
- 新增配置项控制是否启用

```python
# 配置区新增
ENABLE_WS_CHECK: bool = True        # 是否在切换后执行 WS 检查
WS_CHECK_DURATION: int = 30         # WS 数据采集持续时间(秒)

class HaScaleTester:
    def __init__(self, ..., enable_ws_check: bool = ENABLE_WS_CHECK):
        self.enable_ws_check = enable_ws_check

    def run_single_round(self, ...):
        ...
        if switched and self.enable_ws_check:
            ws_result = run_ws_check(duration=WS_CHECK_DURATION)
            ...
```

---

## 优先级

| 优先级 | 修改项 | 理由 |
|--------|--------|------|
| P1 | 日志系统标准化 | 当前 Tee 类不符合最佳实践 |
| P1 | 检查点解耦 | 提升可维护性和可测试性 |
| P2 | 配置方式改进 | 提升易用性，支持非侵入式运行 |
| P2 | 并行日志下载 | 减少测试耗时 |
| P3 | 常量统一管理 | 提升可读性 |
| P3 | 异常恢复独立方法 | 提升代码清晰度 |
| P3 | 结果持久化 | 便于集成 CI/CD |
| P4 | WS 检查可选配置 | 细粒度控制 |

---

## 注意事项

1. **向后兼容**：修改后 CLI 参数默认值需与原配置一致
2. **错误处理**：保持现有的"尽最大努力恢复"逻辑
3. **日志输出**：保持现有的详细程度和格式
4. **依赖**：新增 `argparse`（标准库）、`concurrent.futures`（标准库）、`logging`（标准库），无需额外安装