# -*- coding: utf-8 -*-
"""
态势监控日志采集器 — 连接 ATC WebSocket STOMP 服务，实时采集下游系统态势数据

通过 SockJS + STOMP 协议连接 ATC 后端 WebSocket，订阅:
- /flightTrack/SEAT0001     → 解析 UAV 数量（监视目标数）
- /dataPush/seat/SEAT0001    → 解析告警统计 + 飞行计划统计

采集到的数据通过 LogStreamer.push() 桥接到系统日志模块，前端可在"态势监控日志"分组查看。

参考实现: atc_api_autotest/api_tools/客户端ws无人机数量统计.py

依赖: websocket-client (pip install websocket-client)
"""

from __future__ import annotations

import json
import os
import random
import ssl
import string
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional

# 确保项目根目录在 sys.path 中
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# ── 常量 ──────────────────────────────────────────────────────────
ATC_WS_BASE_URL = "wss://dkkgsit-test.testdolphin.com/la-atc-ws-backend/ws/stomp"
STOMP_FLIGHT_TRACK = "/flightTrack/SEAT0001"
STOMP_DATA_PUSH = "/dataPush/seat/SEAT0001"

# UAV 数量推送间隔（秒），避免 flightTrack 每秒推送刷屏
UAV_REPORT_INTERVAL_SEC = 10.0

# ── 日志类型 ──────────────────────────────────────────────────────
LOG_TYPE_UAV = "situation_uav"
LOG_TYPE_PLAN = "situation_plan"
LOG_TYPE_ALARM = "situation_alarm"

# ── 枚举值中文标签 ──────────────────────────────────────────────
# operatingStatus 运行状态（0-5）
OPERATING_STATUS_LABELS = {
    0: "未起飞", 1: "起飞中", 2: "飞行中", 3: "悬停", 4: "降落中", 5: "已降落",
}
# classification 无人机分类（1-5）
CLASSIFICATION_LABELS = {
    1: "C1-微型", 2: "C2-轻型", 3: "C3-小型", 4: "C4-中型", 5: "C5-大型",
}


class SituationMonitor:
    """态势监控采集器：连接 ATC WebSocket，解析态势数据，推送到 LogStreamer。"""

    def __init__(
        self,
        base_url: str = ATC_WS_BASE_URL,
        streamer=None,
        jwt_token: Optional[str] = None,
        verify_ssl: bool = False,
    ) -> None:
        """
        Args:
            base_url: ATC WebSocket STOMP 服务 SockJS 基础地址
            streamer: LogStreamer 实例（通过 log_streamer.get_streamer() 获取）
            jwt_token: JWT 认证令牌（不传则从环境变量 ATC_JWT_TOKEN 读取，或自动获取）
            verify_ssl: 是否验证 SSL 证书
        """
        self._base_url = base_url
        self._streamer = streamer
        self._jwt_token = jwt_token
        self._verify_ssl = verify_ssl

        self._ws = None
        self._running = False
        self._connected = False
        self._user_stopped = False
        self._reconnect_delay = 3.0
        self._max_reconnect_delay = 30.0
        self._thread: Optional[threading.Thread] = None

        # UAV 计数去重 — 每 UAV_REPORT_INTERVAL_SEC 推送一次
        self._last_uav_report_time = 0.0
        self._last_uav_count = 0
        self._last_alarm_count = -1  # -1 表示未收到过告警数据
        self._last_plan_count = -1

        # 告警详情去重 — 通过内容哈希避免相同告警重复推送
        self._last_warnings_hash = ""

    # ── Token 获取 ──────────────────────────────────────────────

    def _get_token(self) -> str:
        """获取 JWT Token，优先级：构造参数 > 环境变量 > 自动登录。"""
        if self._jwt_token:
            return self._jwt_token

        token = os.environ.get("ATC_JWT_TOKEN", "")
        if token:
            self._jwt_token = token
            return token

        # 尝试自动获取（复用 sim_api_bridge 的 JWT 获取逻辑）
        try:
            # 尝试从 atc_api_autotest 的 Jwt_Token_get 获取
            _atc_root = os.path.join(os.path.dirname(_root), "atc_api_autotest")
            _atc_tools = os.path.join(_atc_root, "api_tools")
            if _atc_tools not in sys.path:
                sys.path.insert(0, _atc_tools)
            from Jwt_Token_get import get_jwt_token
            token = get_jwt_token(base_url="https://dkkgsit-test.testdolphin.com")
            if token:
                self._jwt_token = token
                return token
        except Exception:
            pass

        # 尝试从 atc_ha_test 的 ha_Jwt_Token_get 获取
        try:
            _ha_root = os.path.join(os.path.dirname(_root), "atc_ha_test")
            if _ha_root not in sys.path:
                sys.path.insert(0, _ha_root)
            from ha_Jwt_Token_get import get_jwt_token as ha_get_jwt_token
            token = ha_get_jwt_token()
            if token:
                self._jwt_token = token
                return token
        except Exception:
            pass

        print("[SituationMonitor] ⚠️ 无法获取 JWT Token，将尝试无认证连接")
        return ""

    # ── 生命周期 ────────────────────────────────────────────────

    def start(self) -> None:
        """启动态势监控后台线程。"""
        if self._running:
            return
        self._running = True
        self._user_stopped = False
        self._thread = threading.Thread(target=self._run_forever, daemon=True, name="situation-monitor")
        self._thread.start()
        print("[SituationMonitor] 态势监控已启动")

    def stop(self) -> None:
        """停止态势监控。"""
        self._user_stopped = True
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5.0)
        print("[SituationMonitor] 态势监控已停止")

    # ── 主循环 ──────────────────────────────────────────────────

    def _run_forever(self) -> None:
        """后台主循环：连接 → 订阅 → 接收消息 → 断线重连。"""
        while self._running:
            try:
                self._connect_and_listen()
            except Exception as e:
                print(f"[SituationMonitor] 连接异常: {e}")
                traceback.print_exc()

            if self._user_stopped or not self._running:
                break

            # 断线重连（指数退避）
            delay = self._reconnect_delay
            print(f"[SituationMonitor] {delay:.0f}s 后重连...")
            time.sleep(delay)
            self._reconnect_delay = min(delay * 2, self._max_reconnect_delay)

    # ── WebSocket 连接与 STOMP 握手 ─────────────────────────────

    def _connect_and_listen(self) -> None:
        """建立 WebSocket 连接，完成 STOMP 握手，阻塞接收消息。"""
        import websocket

        # SockJS URL 解析
        ws_url = self._resolve_sockjs_url(self._base_url)
        print(f"[SituationMonitor] 连接: {ws_url}")

        # 构建请求头
        header = []
        token = self._get_token()
        if token:
            header.append(f"jwt-token: {token}")

        sslopt = {"cert_reqs": ssl.CERT_NONE} if not self._verify_ssl else None

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            header=header,
        )
        # 重置重连延迟
        self._reconnect_delay = 3.0
        self._ws.run_forever(sslopt=sslopt)

    def _resolve_sockjs_url(self, url: str) -> str:
        """SockJS /info 握手，生成完整 WebSocket URL。"""
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.rstrip("/")

        if path.endswith("/websocket"):
            return url

        info_scheme = "https" if parsed.scheme in ("wss", "https") else "http"
        info_url = f"{info_scheme}://{parsed.netloc}{path}/info"

        try:
            req = urllib.request.Request(
                info_url,
                headers={"Origin": f"{info_scheme}://{parsed.netloc}"}
            )
            ctx = ssl.create_default_context()
            if not self._verify_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                info = json.loads(resp.read().decode("utf-8"))
                if not info.get("websocket", True):
                    raise RuntimeError("服务端不支持 WebSocket 传输")
        except Exception as e:
            print(f"[SituationMonitor] SockJS /info 失败: {e}，使用回退路径")
            ws_scheme = "wss" if parsed.scheme in ("wss", "https") else "ws"
            return f"{ws_scheme}://{parsed.netloc}{path}/websocket"

        session = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        server_id = "000"
        ws_scheme = "wss" if parsed.scheme in ("wss", "https") else "ws"
        return f"{ws_scheme}://{parsed.netloc}{path}/{server_id}/{session}/websocket"

    # ── WebSocket 事件回调 ──────────────────────────────────────

    def _on_open(self, ws) -> None:
        """WebSocket 连接建立。"""
        self._connected = True
        print("[SituationMonitor] WebSocket 已连接")

    def _on_error(self, ws, error) -> None:
        print(f"[SituationMonitor] WebSocket 错误: {error}")

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        self._connected = False
        print(f"[SituationMonitor] WebSocket 断开 (code={close_status_code})")

    def _on_message(self, ws, message) -> None:
        """SockJS 消息处理入口。"""
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="ignore")

        # SockJS 协议帧
        if message == "o":
            # 连接打开 → 发送 STOMP CONNECT
            self._connected = True
            print("[SituationMonitor] SockJS 已打开，发送 STOMP CONNECT...")
            self._send_stomp_connect()
            return
        elif message == "h":
            # 心跳 → 回复
            if self._ws:
                self._ws.send("h")
            return
        elif message.startswith("c"):
            print(f"[SituationMonitor] SockJS 关闭: {message[:50]}")
            return
        elif message.startswith("a"):
            # SockJS JSON 数组消息: a["payload1", "payload2"]
            try:
                arr = json.loads(message[1:])
                if isinstance(arr, list):
                    for payload in arr:
                        self._handle_payload(payload)
            except json.JSONDecodeError:
                self._handle_payload(message[1:])
        elif message.startswith('["') and message.endswith('"]'):
            try:
                arr = json.loads(message)
                if isinstance(arr, list):
                    for payload in arr:
                        self._handle_payload(payload)
            except json.JSONDecodeError:
                self._handle_payload(message)
        else:
            self._handle_payload(message)

    # ── STOMP 握手 ──────────────────────────────────────────────

    def _send_stomp_connect(self) -> None:
        """发送 STOMP CONNECT + 延迟发送 SUBSCRIBE。"""
        if not self._ws:
            return

        connect_frame = (
            "CONNECT\n"
            "heart-beat:0,0\n"
            "accept-version:1.2,1.1,1.0\n"
            "\n\x00"
        )
        self._ws.send(json.dumps([connect_frame]))
        print("[SituationMonitor] STOMP CONNECT 已发送")

        # 延迟订阅（避免竞态）
        def _delayed_subscribe():
            time.sleep(0.3)
            if not self._ws or not self._running:
                return
            # 订阅 1: 飞行轨迹（监视目标数）
            sub1 = (
                f"SUBSCRIBE\n"
                f"id:sub-0\n"
                f"destination:{STOMP_FLIGHT_TRACK}\n"
                f"ack:auto\n"
                f"\n\x00"
            )
            self._ws.send(json.dumps([sub1]))
            print(f"[SituationMonitor] SUBSCRIBE: {STOMP_FLIGHT_TRACK}")

            time.sleep(0.2)
            if not self._ws or not self._running:
                return
            # 订阅 2: 数据推送（告警统计 + 飞行计划统计）
            sub2 = (
                f"SUBSCRIBE\n"
                f"id:sub-1\n"
                f"destination:{STOMP_DATA_PUSH}\n"
                f"ack:auto\n"
                f"\n\x00"
            )
            self._ws.send(json.dumps([sub2]))
            print(f"[SituationMonitor] SUBSCRIBE: {STOMP_DATA_PUSH}")

        threading.Thread(target=_delayed_subscribe, daemon=True).start()

    # ── STOMP 载荷解析 ──────────────────────────────────────────

    def _handle_payload(self, payload: str) -> None:
        """处理 STOMP 帧载荷。"""
        if not isinstance(payload, str):
            return

        stripped = payload.rstrip("\x00").strip()
        if stripped == "":
            # 心跳 → 回复 SockJS 心跳
            if self._ws:
                self._ws.send(json.dumps(["\n"]))
            return

        # 识别 STOMP 命令帧首行
        stomp_cmd = None
        if "\n" in payload:
            first_line = payload.split("\n", 1)[0].strip()
            if first_line in ("CONNECTED", "MESSAGE", "ERROR", "RECEIPT"):
                stomp_cmd = first_line

        if stomp_cmd == "CONNECTED":
            print("[SituationMonitor] STOMP 握手成功 (CONNECTED)")
            return
        elif stomp_cmd == "ERROR":
            print(f"[SituationMonitor] STOMP 错误: {payload[:300]}")
            return

        # 提取 STOMP MESSAGE 体（headers 与 body 之间用 \n\n 分隔）
        if "\n\n" in payload:
            parts = payload.split("\n\n", 1)
            if len(parts) == 2:
                self._process_body(parts[1])
            else:
                self._process_body(payload)
        else:
            self._process_body(payload)

    def _process_body(self, body: str) -> None:
        """解析消息体 JSON，提取态势数据并推送结构化详情。"""
        body = body.rstrip("\x00").strip()
        if not body:
            return

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return

        if not isinstance(data, dict):
            return

        # 1. 告警统计（alarmStatistic）— 辅助计数，主要告警详情来自 flightTrack 的 warningTags
        if data.get("type") == "alarmStatistic" and "value" in data:
            try:
                alarm_count = int(data["value"])
                if alarm_count != self._last_alarm_count:
                    self._last_alarm_count = alarm_count
                    self._push_log(LOG_TYPE_ALARM, f"实时告警数: {alarm_count}",
                                   detail={"total": alarm_count, "source": "alarmStatistic"})
            except (ValueError, TypeError):
                pass
            return

        # 2. 飞行计划统计（flowStatistic）— 提取全部 6 个子计数
        if data.get("type") == "flowStatistic" and "value" in data:
            try:
                flow_data = json.loads(data["value"])
                plan_count = flow_data.get("totalCount", 0)
                if plan_count != self._last_plan_count:
                    self._last_plan_count = plan_count
                    waiting = flow_data.get("waitingCount", 0)
                    active = flow_data.get("activeCount", 0)
                    completed = flow_data.get("completedCount", 0)
                    rejected = flow_data.get("rejectedCount", 0)
                    cancelled = flow_data.get("cancelledCount", 0)
                    msg = (f"实时飞行计划数: {plan_count} "
                           f"(待{waiting}/执{active}/完{completed}/拒{rejected}/取{cancelled})")
                    detail = {
                        "totalCount": plan_count,
                        "waitingCount": waiting,
                        "activeCount": active,
                        "completedCount": completed,
                        "rejectedCount": rejected,
                        "cancelledCount": cancelled,
                    }
                    self._push_log(LOG_TYPE_PLAN, msg, detail=detail)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            return

        # 3. 飞行轨迹 / UAV 数据 — 提取 UAV 详情 + 告警标签
        has_uavs = "uavs" in data and isinstance(data.get("uavs"), list)
        has_flight_track = "flightTrack" in data
        has_nested_data = "data" in data and isinstance(data.get("data"), dict)

        if not has_uavs and not has_flight_track and not has_nested_data:
            return
        if has_nested_data and not has_uavs:
            nested = data["data"]
            if "flightTrack" not in nested and "uavs" not in nested:
                return

        # ── 监视目标日志（含 UAV 详细列表） ──
        uav_count = self._extract_uav_count(data)
        if uav_count > 0:
            now = time.time()
            if uav_count != self._last_uav_count or (now - self._last_uav_report_time) >= UAV_REPORT_INTERVAL_SEC:
                self._last_uav_count = uav_count
                self._last_uav_report_time = now
                uav_details = self._extract_uav_details(data)
                uav_detail = {"count": uav_count, "uavs": uav_details} if uav_details else None
                self._push_log(LOG_TYPE_UAV, f"监视目标数: {uav_count} 架", detail=uav_detail)

        # ── 实时告警日志（从 UAV 的 warningTags 中提取） ──
        warnings = self._extract_warning_details(data)
        if warnings:
            # 通过 JSON 内容哈希去重，避免相同告警反复推送
            warnings_hash = json.dumps(warnings, sort_keys=True, ensure_ascii=False)
            if warnings_hash != self._last_warnings_hash:
                self._last_warnings_hash = warnings_hash
                self._push_log(LOG_TYPE_ALARM, f"实时告警: {len(warnings)} 条",
                               detail={"total": len(warnings), "warnings": warnings})

    def _extract_uav_count(self, data: Dict[str, Any]) -> int:
        """从消息中提取 UAV 数量。"""
        count = 0

        # 新版格式: uavs 列表
        uavs = data.get("uavs")
        if isinstance(uavs, list):
            count += len(uavs)

        # 旧版格式: flightTrack 列表
        ft = data.get("flightTrack")
        if isinstance(ft, list):
            count += sum(1 for x in ft if isinstance(x, dict) and "uavIdentifyCode" in x)
        elif isinstance(ft, dict) and "uavIdentifyCode" in ft:
            count += 1

        # 嵌套 data 字段
        nested_data = data.get("data")
        if isinstance(nested_data, dict):
            nd_ft = nested_data.get("flightTrack")
            if isinstance(nd_ft, list):
                count += sum(1 for x in nd_ft if isinstance(x, dict) and "uavIdentifyCode" in x)
            elif isinstance(nd_ft, dict) and "uavIdentifyCode" in nd_ft:
                count += 1
            if "uavIdentifyCode" in nested_data:
                val = nested_data["uavIdentifyCode"]
                if isinstance(val, list):
                    count += len(val)
                else:
                    count += 1

        return count

    def _get_uav_list(self, data: Dict[str, Any]) -> Optional[List[Dict]]:
        """从三种已知格式中提取 UAV 列表（统一入口）。"""
        if isinstance(data.get("uavs"), list):
            return data["uavs"]
        if isinstance(data.get("flightTrack"), list):
            return data["flightTrack"]
        if isinstance(data.get("data"), dict):
            nd = data["data"]
            if isinstance(nd.get("flightTrack"), list):
                return nd["flightTrack"]
            if isinstance(nd.get("uavs"), list):
                return nd["uavs"]
        return None

    def _extract_uav_details(self, data: Dict[str, Any]) -> Optional[List[Dict]]:
        """从 flightTrack/uavs 消息中提取每架 UAV 的关键字段列表。"""
        uavs = self._get_uav_list(data)
        if not uavs:
            return None

        details = []
        for uav in uavs:
            if not isinstance(uav, dict) or "uavIdentifyCode" not in uav:
                continue
            status = uav.get("operatingStatus")
            classification = uav.get("classification")
            item = {
                "uavIdentifyCode": uav.get("uavIdentifyCode", ""),
                "longitude": uav.get("longitude"),
                "latitude": uav.get("latitude"),
                "geodeticAltitude": uav.get("geodeticAltitude"),
                "trackAngle": uav.get("trackAngle"),
                "speed": uav.get("speed"),
                "verticalSpeed": uav.get("verticalSpeed"),
                "operatingStatus": status,
                "operatingStatusLabel": OPERATING_STATUS_LABELS.get(status, f"未知({status})") if status is not None else "",
                "classification": classification,
                "classificationLabel": CLASSIFICATION_LABELS.get(classification, f"未知({classification})") if classification is not None else "",
                "realNameRegistrationSign": uav.get("realNameRegistrationSign", ""),
                "timestamp": uav.get("timestamp"),
            }
            warnings = uav.get("warningTags", [])
            if isinstance(warnings, list) and len(warnings) > 0:
                item["warningCount"] = len(warnings)
            details.append(item)
        return details if details else None

    def _extract_warning_details(self, data: Dict[str, Any]) -> Optional[List[Dict]]:
        """从 flightTrack 消息的 warningTags 中提取告警详情列表。"""
        uavs = self._get_uav_list(data)
        if not uavs:
            return None

        warnings = []
        for uav in uavs:
            if not isinstance(uav, dict):
                continue
            uav_code = uav.get("uavIdentifyCode", "")
            tags = uav.get("warningTags", [])
            if not isinstance(tags, list):
                continue
            for tag in tags:
                if isinstance(tag, dict):
                    warnings.append({
                        "uavCode": uav_code,
                        "warningType": tag.get("type", ""),
                        "message": tag.get("message", ""),
                        "timestamp": tag.get("timestamp", uav.get("timestamp", "")),
                    })
        return warnings if warnings else None

    # ── 日志推送 ────────────────────────────────────────────────

    def _push_log(self, log_type: str, message: str, detail: Optional[Dict] = None) -> None:
        """推送日志到 LogStreamer，可附带结构化详情。

        Args:
            log_type: 日志类型（LOG_TYPE_* 常量）
            message: 摘要文本
            detail: 可选的结构化详情（如 UAV 列表、告警列表等）
        """
        if self._streamer:
            try:
                self._streamer.push(log_type, message, detail=detail)
            except Exception as e:
                print(f"[SituationMonitor] 推送日志失败: {e}")
        else:
            # 无 streamer 时直接打印
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] [{log_type}] {message}")


# ── 模块级单例 ────────────────────────────────────────────────────

_monitor: Optional[SituationMonitor] = None


def get_monitor(streamer=None) -> SituationMonitor:
    """获取态势监控采集器单例。"""
    global _monitor
    if _monitor is None:
        _monitor = SituationMonitor(streamer=streamer)
    elif streamer is not None and _monitor._streamer is None:
        _monitor._streamer = streamer
    return _monitor
