# -*- coding: utf-8 -*-
"""SceneEmitter 连接参数测试：显式参数覆盖 + 未传参时回退 env.py 模块值。

修复背景：环境切换后 web 进程内 env 模块不 reload，SceneEmitter 原先直接用
_env.redis_* 会把航线写入旧环境 Redis，下游 ATC 无法关联飞行计划。
本测试验证新加的可选 redis 参数行为。
"""

from unittest.mock import MagicMock, patch

from tools.run_kafka_scene import SceneEmitter, UAVData


def _patched_emitter(**kwargs):
    """mock _redis 模块与 KafkaProducerClient 后构造 SceneEmitter。"""
    redis_mod = MagicMock()
    with patch("tools.run_kafka_scene._redis", redis_mod), \
         patch("tools.run_kafka_scene.KafkaProducerClient") as kafka_cls:
        emitter = SceneEmitter(**kwargs)
        return emitter, redis_mod, kafka_cls


def test_default_fallback_to_env(mock_env):
    """未传 Redis 参数时，回退到 env.py 模块值（独立运行行为不变）。"""
    emitter, redis_mod, kafka_cls = _patched_emitter()

    kw = redis_mod.Redis.call_args.kwargs
    assert kw["host"] == "test-redis.local"
    assert kw["port"] == 6379
    assert kw["password"] == "testpass"
    redis_mod.Redis.return_value.ping.assert_called_once()


def test_override_params():
    """显式传入 Redis 参数时，覆盖 env.py 模块值（web 端切换环境后传当前配置）。"""
    emitter, redis_mod, kafka_cls = _patched_emitter(
        redis_host="new-redis.local",
        redis_port="6380",
        redis_password="newpass",
    )

    kw = redis_mod.Redis.call_args.kwargs
    assert kw["host"] == "new-redis.local"
    assert kw["port"] == 6380
    assert kw["password"] == "newpass"


def test_emit_once_logs_flush_failure(mock_env):
    """_emit_once 在 flush 超时后通过日志回调告警，并记录最近一批遥测供前端渲染。"""
    logs = []
    emitter, redis_mod, kafka_cls = _patched_emitter(log_callback=logs.append)
    emitter.uav_data_list = [UAVData("UAV_00001", [{
        "uniqueProductIdentificationCode": "UAV_00001",
        "longitude": 120.6,
        "latitude": 31.3,
    }])]
    emitter.kafka.send_bulk.return_value = {
        "sent": 1, "failed": 0, "primary_flush_ok": False, "mirror_flush_ok": True,
    }

    emitter._emit_once()

    assert emitter.stats["sent"] == 1
    assert len(emitter.last_emit_records) == 1
    assert any("flush 超时" in l for l in logs)
