# -*- coding: utf-8 -*-
"""临时诊断脚本：查看 env1 Redis BIZ_DATA:UAV_ROUTE 航线状态（用后即删）。"""
import json
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
import redis  # noqa: E402

def _ago(ts, now):
    try:
        d = float(ts) - now
        return f"{'已过' if d < 0 else '剩余'}{abs(d):.0f}s"
    except Exception:
        return str(ts)

r = redis.Redis(host="dolphin-test.kedacom.com", port=21003,
                password="s4^dJ5^xM6^e", db=0, decode_responses=True,
                socket_connect_timeout=5, socket_timeout=5)
try:
    r.ping()
    print("Redis 连接 OK")
except Exception as e:
    print("Redis 连接失败:", e)
    raise SystemExit(1)

now = time.time()
key = "BIZ_DATA:UAV_ROUTE"
print(f"BIZ_DATA:UAV_ROUTE: type={r.type(key)}, ttl={r.ttl(key)}")
data = r.hgetall(key)
print(f"航线数量 (hash fields): {len(data)}")
future_plans = 0
total_plans = 0
for uid, raw in data.items():
    try:
        obj = json.loads(raw)
    except Exception:
        print(f"  [{uid}] JSON 解析失败: {raw[:80]!r}")
        continue
    fps = obj.get("flightPlanList") or []
    info = []
    for fp in fps:
        total_plans += 1
        to = fp.get("planTakeoffTime")
        ld = fp.get("planLandTime")
        info.append(f"to={to} ({_ago(to, now)}) land={ld} ({_ago(ld, now)})")
        if ld is not None and float(ld) > now:
            future_plans += 1
    print(f"  [{uid}] reg={obj.get('realNameRegistrationSign', '-')} plans={len(fps)}: " + " | ".join(info[:3]))
print(f"\n总计划数={total_plans}, 未着陆(land>now)={future_plans}")
print("结论:", "PLAN 模式可加载" if future_plans > 0 else "PLAN 模式加载 0 条（全部过期或无计划）")
