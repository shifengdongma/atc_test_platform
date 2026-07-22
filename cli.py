# -*- coding: utf-8 -*-
"""
UTM 模拟器统一命令行入口

整合 main.py / run_kafka_alive.py / run_plan.py / web_server.py / validators.py
的入口，提供统一子命令。

用法:
    python cli.py run --mode dynamic --count 100       # 启动动态仿真
    python cli.py replay --file kafka_data.json         # 预生成数据回放
    python cli.py plan                                  # Redis 计划插值
    python cli.py server                                # 启动 Web 可视化服务
    python cli.py validate --file mock/kafka_data.json  # 数据校验
    python cli.py check --redis                         # Redis 连通性检查
    python cli.py check --kafka                         # Kafka 连通性检查
    python cli.py status                                # 查看当前仿真状态
"""

import sys
import os

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# 子模块路径
for _sub in ('database', 'common', 'core', 'services', 'tools'):
    _p = os.path.join(_root, _sub)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)


def cmd_run(args):
    """启动仿真（dynamic/replay/plan 三种模式）。"""
    from core.sim_manager import SimulationManager
    from common.config import load_config
    cfg = load_config()
    if args.count:
        cfg.simulation.target_drones = args.count

    print(f"启动仿真: mode={args.mode}, drones={cfg.simulation.target_drones}")
    mgr = SimulationManager(cfg)
    mgr.start(
        mode=args.mode,
        target_drones=args.count,
        replay_data_file=args.file,
        replay_route_file=args.route,
    )

    try:
        import time
        while mgr._running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到停止信号")
    finally:
        mgr.stop()
        print("仿真已停止")


def cmd_replay(args):
    """预生成数据回放（run_kafka_alive.py 模式）。"""
    args.mode = "replay"
    cmd_run(args)


def cmd_plan(args):
    """Redis 计划插值模式。"""
    args.mode = "plan"
    args.count = args.count or 0
    cmd_run(args)


def cmd_server(args):
    """启动 Web 可视化后端服务。"""
    from web.server import app, socketio
    host = args.host or os.environ.get("WEB_HOST", "0.0.0.0")
    port = args.port or int(os.environ.get("WEB_PORT", "5000"))
    print(f"Web 服务启动: http://{host}:{port}")
    socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)


def cmd_validate(args):
    """校验 JSON 数据文件格式。"""
    import json
    if not args.file:
        print("请指定要校验的文件: --file <path>")
        return

    if not os.path.exists(args.file):
        print(f"文件不存在: {args.file}")
        return

    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)

    from common.validators import validate_scenario, validate_telemetry, validate_redis_route, validate_telemetry_batch

    if isinstance(data, list):
        if len(data) == 0:
            print("文件为空数组")
            return
        first = data[0]
        if "uniqueProductIdentificationCode" in first and "longitude" in first:
            passed, failed, errors = validate_telemetry_batch(data)
            print(f"遥测数据校验: {len(data)} 条, 通过 {passed}, 失败 {failed}")
            for err in errors[:10]:
                print(f"  - {err}")
        else:
            ok, errors = validate_scenario({})  # list data treated differently
            print(f"场景数据: {len(data)} 条记录")
    elif "uniqueProductIdentificationCode" in data and "flightPlanList" in data:
        ok, errors = validate_redis_route(data)
        print(f"Redis 航线校验: {'PASS' if ok else 'FAIL'}")
        if not ok:
            for err in errors[:10]:
                print(f"  - {err}")
    elif "_meta" in data or "planTemplate" in data:
        ok, errors = validate_scenario(data)
        print(f"场景校验: {'PASS' if ok else 'FAIL'} ({len(errors)} 项)")
        if not ok:
            for err in errors[:10]:
                print(f"  - {err}")
    else:
        print("无法识别数据格式，尝试作为遥测数据校验...")
        ok, errors = validate_telemetry(data)
        print(f"遥测校验: {'PASS' if ok else 'FAIL'}")
        if not ok:
            for err in errors:
                print(f"  - {err}")


def cmd_check(args):
    """检查 Redis/Kafka 连通性。"""
    from common.config import load_config
    cfg = load_config()

    if args.redis:
        from core.redis_client import RedisClient
        print(f"检查 Redis: {cfg.redis.host}:{cfg.redis.port_int}")
        try:
            client = RedisClient(cfg.redis.host, str(cfg.redis.port_int), cfg.redis.password)
            if client.client:
                client.client.ping()
                print("  Redis: OK")
            else:
                print("  Redis: FAIL (无法连接)")
        except Exception as e:
            print(f"  Redis: FAIL ({e})")

    if args.kafka:
        from core.kafka_proc import KafkaProducerClient
        print(f"检查 Kafka: {cfg.kafka.bootstrap_servers}")
        try:
            producer = KafkaProducerClient(cfg.kafka.bootstrap_servers)
            if producer.is_connected():
                print("  Kafka: OK")
            else:
                print("  Kafka: FAIL (无法连接)")
            producer.close()
        except Exception as e:
            print(f"  Kafka: FAIL ({e})")


def cmd_status(args):
    """查看当前仿真状态（检查 Redis 中数据）。"""
    from core.redis_client import RedisClient
    from common.config import load_config
    cfg = load_config()

    try:
        client = RedisClient(cfg.redis.host, str(cfg.redis.port_int), cfg.redis.password)
        if not client.client:
            print("Redis: 未连接")
            return
        client.client.ping()
        print(f"Redis: OK ({cfg.redis.host}:{cfg.redis.port_int})")

        plans = client.hgetall("BIZ_DATA:UAV_ROUTE")
        plan_count = len(plans) if plans else 0
        print(f"飞行计划 (BIZ_DATA:UAV_ROUTE): {plan_count} 条")

        airspace = client.hgetall("BIZ_DATA:AIRSPACE")
        nfz_count = len(airspace) if airspace else 0
        print(f"空域/禁飞区 (BIZ_DATA:AIRSPACE): {nfz_count} 条")
    except Exception as e:
        print(f"状态查询失败: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="UTM 模拟器统一命令行工具")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # run: 启动仿真
    p_run = sub.add_parser("run", help="启动仿真")
    p_run.add_argument("--mode", choices=["dynamic", "replay", "plan"], default="dynamic")
    p_run.add_argument("--count", type=int, default=None)
    p_run.add_argument("--file", type=str, default=None, help="replay 数据文件路径")
    p_run.add_argument("--route", type=str, default=None, help="replay 航线文件路径")

    # replay: 预生成数据回放
    p_replay = sub.add_parser("replay", help="预生成数据回放")
    p_replay.add_argument("--count", type=int, default=None)
    p_replay.add_argument("--file", type=str, default=None)
    p_replay.add_argument("--route", type=str, default=None)

    # plan: Redis 计划插值
    p_plan = sub.add_parser("plan", help="Redis 计划插值模式")
    p_plan.add_argument("--count", type=int, default=None)

    # server: Web 服务
    p_server = sub.add_parser("server", help="启动 Web 可视化服务")
    p_server.add_argument("--host", type=str, default=None)
    p_server.add_argument("--port", type=int, default=None)

    # validate: 数据校验
    p_val = sub.add_parser("validate", help="校验 JSON 数据文件")
    p_val.add_argument("--file", type=str, required=True, help="要校验的 JSON 文件路径")

    # check: 连通性检查
    p_check = sub.add_parser("check", help="检查 Redis/Kafka 连通性")
    p_check.add_argument("--redis", action="store_true", help="检查 Redis")
    p_check.add_argument("--kafka", action="store_true", help="检查 Kafka")

    # status: 状态查询
    p_status = sub.add_parser("status", help="查看当前仿真状态")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "replay":
        cmd_replay(args)
    elif args.command == "plan":
        cmd_plan(args)
    elif args.command == "server":
        cmd_server(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
