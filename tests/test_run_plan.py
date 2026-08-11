# -*- coding: utf-8 -*-
"""PlanRunner 测试：连接参数 + 30s 周期性航线刷新 + 过期计划可见化。

修复背景：
1. 环境切换后 web 进程内 env 模块不 reload，PlanRunner 原先直接用
   模块级常量会连到旧环境 Redis/Kafka（可选参数覆盖行为）。
2. PlanRunner 只在加入计划时写一次 Redis 航线，下游 ATC 因时间过期
   取消追踪导致目标不可见；对齐 scene/replay 的 30s 周期性刷新。
3. Redis 中航线全部过期时原先静默跳过，前端只看到"0 活跃无人机"。
"""

import copy
import json
import time
from unittest.mock import patch

from tools.run_plan import KAFKA_TRACE_TOPIC, PlanRunner, RoutePlanSim


def _patched_runner(**kwargs):
    """mock 三个客户端类后构造 PlanRunner，返回 (runner, 三个 mock 类)。"""
    with patch("tools.run_plan.RedisClient") as redis_cls, \
         patch("tools.run_plan.KafkaProducerClient") as producer_cls, \
         patch("tools.run_plan.KafkaConsumerClient") as consumer_cls:
        runner = PlanRunner(**kwargs)
        return runner, redis_cls, producer_cls, consumer_cls


def test_default_fallback_to_env(mock_env):
    """未传连接参数时，回退到 env.py 模块值（独立运行行为不变）。"""
    runner, redis_cls, producer_cls, consumer_cls = _patched_runner()

    assert redis_cls.call_args.args == ("test-redis.local", "6379", "testpass")
    assert producer_cls.call_args.args == ("test-kafka.local:9092",)
    assert producer_cls.call_args.kwargs["bootstrap_servers_mirror"] == ""
    assert consumer_cls.call_args.kwargs["bootstrap_servers"] == "test-kafka.local:9092"
    consumer_cls.return_value.subscribe.assert_called_once_with([KAFKA_TRACE_TOPIC])


def test_override_params():
    """显式传入连接参数时，覆盖 env.py 模块值（web 环境切换后传当前配置）。"""
    runner, redis_cls, producer_cls, consumer_cls = _patched_runner(
        redis_host="new-redis.local",
        redis_port="6380",
        redis_password="newpass",
        kafka_bootstrap_servers="new-kafka.local:9093",
        kafka_bootstrap_servers_mirror="mirror-kafka.local:9094",
    )

    assert redis_cls.call_args.args == ("new-redis.local", "6380", "newpass")
    assert producer_cls.call_args.args == ("new-kafka.local:9093",)
    assert producer_cls.call_args.kwargs["bootstrap_servers_mirror"] == "mirror-kafka.local:9094"
    assert consumer_cls.call_args.kwargs["bootstrap_servers"] == "new-kafka.local:9093"


def test_empty_mirror_passthrough():
    """mirror 显式传空串时原样透传（归一化由 kafka_proc 内部处理）。"""
    runner, redis_cls, producer_cls, consumer_cls = _patched_runner(
        kafka_bootstrap_servers_mirror="",
    )

    assert producer_cls.call_args.kwargs["bootstrap_servers_mirror"] == ""


def _future_plan(sample_redis_route):
    """把样本计划的起降时间平移到未来，避免 tick 时被当作已着陆移除。"""
    plan = copy.deepcopy(sample_redis_route["flightPlanList"][0])
    plan["planTakeoffTime"] = time.time()
    plan["planLandTime"] = time.time() + 3600
    return plan


def test_tick_send_counts_and_surfaces_flush_failure(mock_env, sample_redis_route):
    """tick_send 累计发送计数，并在主集群 flush 超时时通过日志回调告警。"""
    logs = []
    runner, redis_cls, producer_cls, consumer_cls = _patched_runner(log_callback=logs.append)
    runner.kafka_producer.send_bulk.return_value = {
        "sent": 1, "failed": 0, "primary_flush_ok": False, "mirror_flush_ok": True,
    }
    with runner._lock:
        runner._plans["UAV_00001:1"] = RoutePlanSim(
            "UAV_00001", "TEST_SIGN", _future_plan(sample_redis_route)
        )
    runner.tick_send()

    assert runner.stats["sent"] == 1
    assert any("flush 超时" in l for l in logs)


def test_merge_from_redis_logs_new_plan_count(mock_env, sample_redis_route):
    """merge_from_redis 成功加入计划时，日志回调收到"新加入 N 条计划"（print→_log 转换）。"""
    logs = []
    runner, redis_cls, producer_cls, consumer_cls = _patched_runner(log_callback=logs.append)
    route = copy.deepcopy(sample_redis_route)
    route["flightPlanList"][0]["planTakeoffTime"] = time.time()
    route["flightPlanList"][0]["planLandTime"] = time.time() + 3600
    runner.redis_client.hgetall.return_value = {
        "UAV_00001": json.dumps(route, ensure_ascii=False),
    }

    runner.merge_from_redis()

    assert any("本轮从 Redis 新加入 1 条计划" in l for l in logs)
    assert runner.stats["sent"] == 0
    # 加入计划后路由对象被缓存，供周期性刷新使用
    assert "UAV_00001" in runner._route_objs


def test_merge_from_redis_logs_expired_plans(mock_env, sample_redis_route):
    """Redis 航线存在但全部计划已过期时，日志明确提示（不再静默 0 活跃）。"""
    logs = []
    runner, redis_cls, producer_cls, consumer_cls = _patched_runner(log_callback=logs.append)
    route = copy.deepcopy(sample_redis_route)
    route["flightPlanList"][0]["planTakeoffTime"] = time.time() - 7200
    route["flightPlanList"][0]["planLandTime"] = time.time() - 3600
    runner.redis_client.hgetall.return_value = {
        "UAV_00001": json.dumps(route, ensure_ascii=False),
    }

    runner.merge_from_redis()

    assert runner._plans == {}
    assert any("planLandTime 已过期" in l for l in logs)


def _runner_with_loaded_plan(logs, sample_redis_route):
    """构造已加载 1 条未来计划的 runner（_plans + _route_objs 均已填充）。"""
    runner, redis_cls, producer_cls, consumer_cls = _patched_runner(log_callback=logs.append)
    plan = _future_plan(sample_redis_route)
    with runner._lock:
        runner._plans["UAV_00001:1"] = RoutePlanSim("UAV_00001", "TEST_SIGN", plan)
    runner._route_objs["UAV_00001"] = {
        "uniqueProductIdentificationCode": "UAV_00001",
        "flightPlanList": [copy.deepcopy(plan)],
    }
    return runner


def test_refresh_redis_routes_writes_to_redis(mock_env, sample_redis_route):
    """_refresh_redis_routes 将航线起降时间平移到当前时刻并重写 Redis（后台线程调用）。"""
    logs = []
    runner = _runner_with_loaded_plan(logs, sample_redis_route)

    runner._refresh_redis_routes()

    runner.redis_client.hset.assert_called_once()
    args = runner.redis_client.hset.call_args.args
    assert args[0] == "BIZ_DATA:UAV_ROUTE"
    assert args[1] == "UAV_00001"
    written = json.loads(args[2])
    plan = written["flightPlanList"][0]
    assert abs(plan["planTakeoffTime"] - time.time()) < 5
    assert any("已周期性刷新 1 条 Redis 航线" in l for l in logs)


def test_tick_send_does_not_block_on_redis_refresh(mock_env, sample_redis_route):
    """tick_send 不再执行 Redis 航线刷新（已移至后台 watch 线程），保持每秒准时。"""
    logs = []
    runner = _runner_with_loaded_plan(logs, sample_redis_route)

    runner.tick_send()

    # tick_send 不应触发 Redis hset（刷新已移至 _watch_redis_loop）
    runner.redis_client.hset.assert_not_called()
    # 但应该正常发送遥测（send_bulk 被调用）
    runner.kafka_producer.send_bulk.assert_called_once()


def test_expired_plan_removed_and_route_cache_cleaned(mock_env, sample_redis_route):
    """计划结束后从 _plans 移除，并停止对其 Redis 航线的周期性刷新。"""
    logs = []
    runner = _runner_with_loaded_plan(logs, sample_redis_route)
    with runner._lock:
        runner._plans["UAV_00001:1"].land = time.time() - 1

    runner.tick_send()

    assert runner._plans == {}
    assert runner._route_objs == {}
    assert any("计划已结束并移除" in l for l in logs)
