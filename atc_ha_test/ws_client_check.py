#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
接收机查询统计脚本 (WebSocket版) — 高可用环境支持
功能：连接低空空管WebSocket服务，接收flightTrack消息，统计每秒uavIdentifyCode数量

高可用环境支持：
- Token 从 ha_Jwt_Token_get.py 动态获取（支持缓存复用）
- WebSocket 地址从 ha_env.py 获取并拼接
- 同时管理 4 个连接：A/B 集群 × stomp/daemon

使用说明：
1. 直接运行: python ws_client_check.py
2. 按 Ctrl+C 停止统计
"""

# ============================================
# 【配置区域】- 修改以下参数即可快速配置
# ============================================

# WebSocket URL（单连接模式时生效，高可用模式自动从 ha_env.py 拼接）
WS_URL = "wss://dkkgsit-test.testdolphin.com/la-atc-ws-backend/ws/stomp"

# JWT认证令牌（单连接模式兜底，高可用模式自动从 ha_Jwt_Token_get.py 获取）
JWT_TOKEN = ""

# STOMP订阅目标（从浏览器开发者工具复制，例如：/flightTrack/SEAT0001）
STOMP_DESTINATION = "/flightTrack/SEAT0001"

# 告警数据推送订阅目标（席位级告警统计，如不需要可留空）
ALARM_DESTINATION = "/dataPush/seat/SEAT0001"

# 是否验证SSL证书
VERIFY_SSL = False

# 是否打印原始消息（调试用）
DEBUG_RAW = False

# 是否启用高可用模式（同时连接 4 个端点）
HA_MODE = True

# ============================================
# 【配置区域结束】- 以下代码无需修改
# ============================================

import argparse
import json
import os
import random
import ssl
import string
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Dict, Any, List

# 日志输出目录（脚本同级父目录下的 testreport）
TESTREPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "testreport"
)

try:
    import websocket
except ImportError:
    print("错误: 缺少websocket-client库，请先安装: pip install websocket-client")
    sys.exit(1)

# 导入高可用环境配置和 Token 获取模块
try:
    import ha_env
    from ha_Jwt_Token_get import get_jwt_token
except ImportError as _e:
    print(f"[警告] 导入 ha_env / ha_Jwt_Token_get 失败: {_e}")
    ha_env = None
    get_jwt_token = None


def _get_ha_connections() -> List[Dict[str, Any]]:
    """构建高可用环境 4 个连接配置"""
    if ha_env is None:
        return []
    return [
        {
            "name": "A集群-stomp",
            "url": f"wss://{ha_env.atc_a}/la-atc-ws-backend/ws/stomp",
            "type": "stomp",
            "destination": STOMP_DESTINATION,
            "alarm_destination": ALARM_DESTINATION,
        },
        {
            "name": "B集群-stomp",
            "url": f"wss://{ha_env.atc_b}/la-atc-ws-backend/ws/stomp",
            "type": "stomp",
            "destination": STOMP_DESTINATION,
            "alarm_destination": ALARM_DESTINATION,
        },
        {
            "name": "A集群-daemon",
            "url": f"wss://{ha_env.atc_a}/la-atc-daemon-server/unverified",
            "type": "stomp",
            "destination": "/topic/clusterChange",
            "alarm_destination": "",
        },
        {
            "name": "B集群-daemon",
            "url": f"wss://{ha_env.atc_b}/la-atc-daemon-server/unverified",
            "type": "stomp",
            "destination": "/topic/clusterChange",
            "alarm_destination": "",
        },
    ]


def get_token() -> str:
    """获取JWT Token：优先环境变量，其次动态获取，最后兜底配置"""
    token = os.environ.get("ATC_JWT_TOKEN", "")
    if token:
        return token
    if get_jwt_token is not None:
        try:
            token = get_jwt_token()
            if token:
                return token
        except Exception:
            pass
    return JWT_TOKEN


class ReceiverWsStats:
    """接收机WebSocket统计客户端"""

    def __init__(
        self,
        url: str = None,
        jwt_token: str = None,
        destination: str = None,
        verify_ssl: bool = None,
        debug: bool = None,
        conn_name: str = "default",
        conn_type: str = "stomp",
        log_fp=None,  # 外部传入的统一日志句柄（None 则创建独立日志文件）
    ):
        self.url = url or WS_URL
        self.jwt_token = jwt_token if jwt_token is not None else get_token()
        self.destination = destination if destination is not None else STOMP_DESTINATION
        self.alarm_destination = ALARM_DESTINATION
        self.verify_ssl = verify_ssl if verify_ssl is not None else VERIFY_SSL
        self.debug = debug if debug is not None else DEBUG_RAW
        self.conn_name = conn_name
        self.conn_type = conn_type  # "stomp" 或 "raw"

        self.ws = None
        self.running = False
        self.connected = False
        self._base_url = self.url  # 保存原始 URL，重连时重新解析
        self._reconnect_delay = 3  # 初始重连延迟（秒）
        self._max_reconnect_delay = 30  # 最大重连延迟
        self._user_stopped = False  # 标记是否用户主动停止

        # 按秒统计
        self.lock = threading.Lock()
        self.current_second = ""
        self.current_uav_count = 0
        self.current_flow_count = 0
        self._last_alarm_count = 0  # 告警数量持久化（跨秒保留）
        self._has_flow = False

        # 累积统计（用于最终报告）
        self.stats = {
            "msg_count": 0,           # 总消息数
            "uav_total": 0,           # 累计 uavIdentifyCode 数量
            "uav_distribution": {},   # {uav_count: 出现次数} — 每次flightTrack消息的uav数量分布
            "warning_tags_total": 0,  # warningTags 存在的 uav 数量（uav 级别累加）
            "warning_tags_msg_count": 0,  # warningTags 存在的消息次数（消息级别）
            "flow_count": 0,          # flowStatistic 消息数
            "totalCount_distribution": {},  # {totalCount: 出现次数} — 每次flowStatistic的totalCount分布
            "totalCount_100_count": 0, # totalCount=100 的次数
            "totalCount_sum": 0,      # totalCount 累计值
            "master_cluster": "",     # 当前主集群
            "cluster_changes": 0,     # 集群状态变化次数
            "cluster_change_history": [],  # [(时间戳, 旧主集群, 新主集群)]
        }

        # 日志输出：优先使用外部传入的句柄，否则创建独立日志文件
        self._external_log_fp = log_fp
        if log_fp is None:
            os.makedirs(TESTREPORT_DIR, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            safe_name = conn_name.replace("/", "-").replace("\\", "-")
            log_filename = f"{ts}_{safe_name}_wsclient.log"
            self._log_path = os.path.join(TESTREPORT_DIR, log_filename)
            self._log_fp = open(self._log_path, "w", encoding="utf-8")
            print(f"[{conn_name}] 日志: {self._log_path}")
        else:
            self._log_path = None
            self._log_fp = None

    def __del__(self):
        """析构时关闭自己创建的日志文件句柄（不关闭外部传入的）。"""
        if hasattr(self, '_log_fp') and self._log_fp:
            try:
                self._log_fp.close()
            except Exception:
                pass

    def _write_log(self, line: str) -> None:
        """将一行内容写入日志文件（线程安全，由调用方持有 self.lock）。
        优先使用外部传入的日志句柄，否则使用自己创建的独立日志文件。"""
        target = self._external_log_fp if self._external_log_fp else self._log_fp
        if target:
            prefix = f"[{self.conn_name}] "
            target.write(prefix + line + "\n")
            target.flush()

    def _write_internal_log(self, line: str) -> None:
        """仅写入自己创建的独立日志文件（不进入外部 log_fp，避免刷屏终端）。"""
        if self._log_fp:
            prefix = f"[{self.conn_name}] "
            self._log_fp.write(prefix + line + "\n")
            self._log_fp.flush()

    def _now_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _update_and_print(self, uav_count: int = 0, alarm_count: int = 0, flow_count: int = 0):
        """更新当前秒计数并写入日志文件（不再输出到终端）"""
        now_key = self._now_str()
        with self.lock:
            if now_key != self.current_second:
                self.current_second = now_key
                self.current_uav_count = uav_count
                self.current_flow_count = flow_count
                self._has_flow = flow_count > 0
                # 告警持久化：有更新才替换
                if alarm_count > 0:
                    self._last_alarm_count = alarm_count
                # totalCount 优先用 flow，否则用 uav 累加
                total_count = self.current_flow_count if self._has_flow else self.current_uav_count
                alarm_str = f" | 告警：{self._last_alarm_count}" if self._last_alarm_count > 0 else ""
                line = f"{now_key} | 接收统计数量: {self.current_uav_count} | totalCount：{total_count}{alarm_str}"
                self._write_internal_log(line)
            else:
                if flow_count > 0:
                    self.current_flow_count = flow_count
                    self._has_flow = True
                if uav_count > 0:
                    self.current_uav_count += uav_count
                # 告警持久化：有更新才替换
                if alarm_count > 0:
                    self._last_alarm_count = alarm_count
                # totalCount 优先用 flow，否则用 uav 累加
                total_count = self.current_flow_count if self._has_flow else self.current_uav_count
                alarm_str = f" | 告警：{self._last_alarm_count}" if self._last_alarm_count > 0 else ""
                line = f"{now_key} | 接收统计数量: {self.current_uav_count} | totalCount：{total_count}{alarm_str}"
                self._write_internal_log(line)

    def _extract_stats(self, data: Dict[str, Any]) -> tuple:
        """从消息数据中提取无人机数量和 warningTags 统计
        返回: (uav_count, warning_tags_uav_count, has_warning_tags)
            - uav_count: 该消息中 uavIdentifyCode 的数量
            - warning_tags_uav_count: 包含 warningTags 的 uav 数量
            - has_warning_tags: 该消息中是否存在至少一个 uav 有 warningTags（用于消息次数统计）
        """
        uav_count = 0
        warning_tags_uav_count = 0

        def _count_from_item(item: Dict[str, Any]) -> None:
            nonlocal uav_count, warning_tags_uav_count
            if not isinstance(item, dict):
                return
            if "uavIdentifyCode" in item:
                uav_count += 1
            # warningTags 统计：存在且非空列表/字典
            wt = item.get("warningTags")
            if isinstance(wt, list) and len(wt) > 0:
                warning_tags_uav_count += 1
            elif isinstance(wt, dict) and wt:
                warning_tags_uav_count += 1

        # 情况1: uavs 列表（低空空管新版格式）
        uavs = data.get("uavs")
        if isinstance(uavs, list):
            for u in uavs:
                _count_from_item(u)

        # 情况2: flightTrack 是列表或字典
        ft = data.get("flightTrack")
        if isinstance(ft, list):
            for item in ft:
                _count_from_item(item)
        elif isinstance(ft, dict):
            _count_from_item(ft)

        # 情况3: data 嵌套包装
        nested_data = data.get("data")
        if isinstance(nested_data, dict):
            nd_ft = nested_data.get("flightTrack")
            if isinstance(nd_ft, list):
                for item in nd_ft:
                    _count_from_item(item)
            elif isinstance(nd_ft, dict):
                _count_from_item(nd_ft)
            if "uavIdentifyCode" in nested_data:
                val = nested_data["uavIdentifyCode"]
                if isinstance(val, list):
                    uav_count += len(val)
                    for item in val:
                        _count_from_item(item)
                else:
                    uav_count += 1
            # 嵌套 data 中的 warningTags（消息级别）
            wt = nested_data.get("warningTags")
            if isinstance(wt, list) and len(wt) > 0:
                warning_tags_uav_count += 1
            elif isinstance(wt, dict) and wt:
                warning_tags_uav_count += 1

        has_warning_tags = warning_tags_uav_count > 0
        return uav_count, warning_tags_uav_count, has_warning_tags

    def _process_body(self, body: str):
        """解析消息体并统计"""
        body = body.rstrip("\x00").strip()
        if not body:
            return

        if self.debug:
            print(f"\n[{self.conn_name}][DEBUG] 原始消息体: {body[:500]}")

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return

        if not isinstance(data, dict):
            return

        with self.lock:
            self.stats["msg_count"] += 1

        # 告警统计消息（来自 /dataPush/seat/SEAT0001）
        if data.get("type") == "alarmStatistic" and "value" in data:
            try:
                alarm_count = int(data["value"])
                self._update_and_print(uav_count=0, alarm_count=alarm_count)
            except (ValueError, TypeError):
                pass
            return

        # 流量统计消息（来自 /dataPush/seat/SEAT0001），value 是嵌套 JSON 字符串
        if data.get("type") == "flowStatistic" and "value" in data:
            try:
                flow_data = json.loads(data["value"])
                total_count = flow_data.get("totalCount", 0)
                with self.lock:
                    self.stats["flow_count"] += 1
                    self.stats["totalCount_sum"] += total_count
                    self.stats["totalCount_distribution"][total_count] = self.stats["totalCount_distribution"].get(total_count, 0) + 1
                    if total_count == 100:
                        self.stats["totalCount_100_count"] += 1
                if total_count > 0:
                    self._update_and_print(uav_count=0, alarm_count=0, flow_count=total_count)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            return

        # 集群健康状态消息（来自 daemon 端点的 /topic/clusterChange）
        if "clusters" in data and isinstance(data.get("clusters"), list):
            clusters_info = []
            new_master = ""
            for c in data["clusters"]:
                cid = c.get("clusterId", "?")
                is_master = c.get("isMaster", False)
                master = "主" if is_master else "备"
                health = "健康" if c.get("healthStatus") else "异常"
                clusters_info.append(f"{cid}({master}/{health})")
                if is_master:
                    new_master = cid
            with self.lock:
                old_master = self.stats["master_cluster"]
                # 只统计真正的集群切换（A↔B），初始识别（old_master为空）不计入变化
                if new_master and old_master and old_master != new_master:
                    self.stats["cluster_changes"] += 1
                    self.stats["cluster_change_history"].append(
                        (self._now_str(), old_master, new_master)
                    )
                self.stats["master_cluster"] = new_master
            line = f"{self._now_str()} | 集群状态: {', '.join(clusters_info)} | 主集群: {new_master}"
            self._write_internal_log(line)
            return

        # 过滤 uavs / flightTrack 字段
        has_uavs = "uavs" in data and isinstance(data.get("uavs"), list)
        has_flight_track = "flightTrack" in data
        has_nested_data = "data" in data and isinstance(data.get("data"), dict)

        if not has_uavs and not has_flight_track and not has_nested_data:
            return
        if has_nested_data and not has_uavs:
            nested = data["data"]
            if "flightTrack" not in nested and "uavs" not in nested:
                return

        uav_count, warning_tags_uav_count, has_warning_tags = self._extract_stats(data)
        with self.lock:
            self.stats["uav_total"] += uav_count
            self.stats["warning_tags_total"] += warning_tags_uav_count  # uav 级别累加（保留）
            if has_warning_tags:
                self.stats["warning_tags_msg_count"] += 1  # 消息次数统计
            if uav_count > 0:
                self.stats["uav_distribution"][uav_count] = self.stats["uav_distribution"].get(uav_count, 0) + 1
        if uav_count > 0:
            self._update_and_print(uav_count=uav_count, alarm_count=0)

    def _handle_payload(self, payload: str):
        """处理实际载荷（可能是STOMP帧）"""
        if not isinstance(payload, str):
            return

        # STOMP 心跳：裸的 \n 或 \n\x00（必须回复，否则服务端30秒后断开）
        stripped = payload.rstrip("\x00").strip()
        if stripped == "":
            if self.conn_type == "stomp" and self.ws:
                self.ws.send(json.dumps(["\n"]))
            return

        # 识别 STOMP 命令帧（CONNECTED, MESSAGE, ERROR 等）
        stomp_cmd = None
        if "\n" in payload:
            first_line = payload.split("\n", 1)[0].strip()
            if first_line in ("CONNECTED", "MESSAGE", "ERROR", "RECEIPT"):
                stomp_cmd = first_line

        if stomp_cmd == "CONNECTED":
            print(f"[{self.conn_name}][{self._now_str()}] STOMP握手成功 (CONNECTED)")
            return
        elif stomp_cmd == "ERROR":
            print(f"[{self.conn_name}][{self._now_str()}] STOMP错误: {payload[:300]}")
            return

        if "\n\n" in payload:
            parts = payload.split("\n\n", 1)
            if len(parts) == 2:
                self._process_body(parts[1])
            else:
                self._process_body(payload)
        else:
            self._process_body(payload)

    def _send_stomp_connect(self):
        """发送STOMP CONNECT帧（必须），如有destination则延迟发送SUBSCRIBE"""
        # raw 类型不走 STOMP 协议
        if self.conn_type == "raw":
            print(f"[{self.conn_name}][{self._now_str()}] raw 模式，跳过 STOMP 握手")
            return

        # STOMP CONNECT 是强制握手步骤，无论是否订阅都必须发送
        connect_frame = (
            "CONNECT\n"
            "heart-beat:0,0\n"
            "accept-version:1.2,1.1,1.0\n"
            "\n\x00"
        )
        sockjs_msg = json.dumps([connect_frame])
        print(f"[{self.conn_name}][{self._now_str()}] 发送STOMP CONNECT...")
        if self.ws:
            self.ws.send(sockjs_msg)

        destinations = []
        if self.destination:
            destinations.append(("sub-0", self.destination))
        if self.alarm_destination:
            destinations.append(("sub-1", self.alarm_destination))

        if not destinations:
            print(f"[{self.conn_name}][{self._now_str()}] 未配置STOMP_DESTINATION，跳过SUBSCRIBE（服务端可能主动推送）")
            return

        def delayed_subscribe():
            time.sleep(0.3)
            for sub_id, dest in destinations:
                sub_frame = (
                    f"SUBSCRIBE\n"
                    f"id:{sub_id}\n"
                    f"destination:{dest}\n"
                    f"ack:auto\n"
                    f"\n\x00"
                )
                sub_msg = json.dumps([sub_frame])
                print(f"[{self.conn_name}][{self._now_str()}] 发送STOMP SUBSCRIBE: {dest}")
                if self.ws:
                    self.ws.send(sub_msg)
                time.sleep(0.2)

        threading.Thread(target=delayed_subscribe, daemon=True).start()

    def _resolve_sockjs_url(self, url: str) -> str:
        """基于 SockJS base URL 获取完整 WebSocket URL（自动 info 握手 + session 生成）"""
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.rstrip("/")

        # 如果已经是完整 WebSocket URL，直接返回
        if path.endswith("/websocket"):
            return url

        # 请求 SockJS info
        info_scheme = "https" if parsed.scheme in ("wss", "https") else "http"
        info_url = f"{info_scheme}://{parsed.netloc}{path}/info"

        try:
            req = urllib.request.Request(
                info_url,
                headers={"Origin": f"{info_scheme}://{parsed.netloc}"}
            )
            ctx = ssl.create_default_context()
            if not self.verify_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                info = json.loads(resp.read().decode("utf-8"))
                if not info.get("websocket", True):
                    raise RuntimeError("服务端不支持 WebSocket 传输")
        except Exception as e:
            print(f"[{self._now_str()}] SockJS info 请求失败: {e}，尝试直接连接")
            # 回退：尝试原生 WebSocket 路径
            ws_scheme = "wss" if parsed.scheme in ("wss", "https") else "ws"
            return f"{ws_scheme}://{parsed.netloc}{path}/websocket"

        # 生成 session ID（8 位随机字符）和 server_id（3 位随机数字，参考浏览器行为）
        session = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        server_id = str(random.randint(0, 999)).zfill(3)
        ws_scheme = "wss" if parsed.scheme in ("wss", "https") else "ws"
        return f"{ws_scheme}://{parsed.netloc}{path}/{server_id}/{session}/websocket"

    def on_message(self, ws, message):
        """WebSocket消息回调"""
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="ignore")

        if self.debug:
            print(f"[{self.conn_name}][DEBUG] 收到原始消息: {message[:200]}")

        # SockJS 协议处理
        if message == "o":
            self.connected = True
            print(f"[{self.conn_name}][{self._now_str()}] SockJS连接已打开")
            self._send_stomp_connect()
            return
        elif message == "h":
            if self.ws:
                self.ws.send("h")
            return
        elif message.startswith("c"):
            print(f"[{self.conn_name}][{self._now_str()}] SockJS连接关闭: {message}")
            return
        elif message.startswith("a"):
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
            # raw 类型也直接处理裸消息（可能不是 SockJS 包装）
            self._handle_payload(message)

    def on_open(self, ws):
        print(f"[{self.conn_name}][{self._now_str()}] WebSocket连接已建立")
        # raw 类型且非 SockJS 时，on_open 直接触发（不会收到 "o" 帧）
        if self.conn_type == "raw":
            self.connected = True
            self._send_stomp_connect()

    def on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        print(f"\n[{self.conn_name}][{self._now_str()}] WebSocket连接已关闭 (code={close_status_code}, msg={close_msg})")

    def on_error(self, ws, error):
        print(f"\n[{self.conn_name}][{self._now_str()}] WebSocket错误: {error}")

    def start(self):
        self.running = True
        self._user_stopped = False

        while self.running:
            try:
                websocket.enableTrace(self.debug)

                # SockJS URL 解析：支持传入 base URL 自动生成完整 WebSocket URL
                self.url = self._resolve_sockjs_url(self._base_url)
                print(f"[{self.conn_name}][{self._now_str()}] 实际连接地址: {self.url}")

                sslopt = {"cert_reqs": ssl.CERT_NONE} if not self.verify_ssl else None
                header = []
                # 参考浏览器 HAR，添加 Origin（使用 VIP 地址）
                if ha_env is not None:
                    header.append(f"Origin: https://{ha_env.atc_vip}")
                if self.jwt_token:
                    header.append(f"jwt-token: {self.jwt_token}")

                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                    header=header,
                )
                self.ws.run_forever(sslopt=sslopt)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[{self.conn_name}][{self._now_str()}] 连接异常: {e}")
            finally:
                if self._user_stopped:
                    break

                # 自动重连（指数退避）
                delay = self._reconnect_delay
                print(f"[{self.conn_name}][{self._now_str()}] 连接断开，{delay}秒后自动重连...")
                time.sleep(delay)
                self._reconnect_delay = min(delay * 2, self._max_reconnect_delay)

        print(f"[{self.conn_name}][{self._now_str()}] 统计已停止")

    def get_stats_report(self) -> Dict[str, Any]:
        """获取当前统计报告"""
        with self.lock:
            return dict(self.stats)

    def stop(self):
        self._user_stopped = True
        self.running = False
        if self.ws:
            self.ws.close()
        # 只关闭自己创建的日志文件，不关闭外部传入的句柄
        if hasattr(self, '_log_fp') and self._log_fp:
            try:
                self._log_fp.close()
                self._log_fp = None
            except Exception:
                pass
        if self._log_path:
            print(f"\n[{self.conn_name}] 日志文件已保存: {self._log_path}")


class MultiWsClient:
    """高可用多连接管理器：并行管理多个 WebSocket 连接"""

    def __init__(self, connections: List[Dict[str, Any]], debug: bool = False, log_fp=None, save_report: bool = True):
        self.connections = connections
        self.debug = debug
        self.log_fp = log_fp  # 外部传入的统一日志句柄（None 则各连接创建独立日志）
        self.clients: List[ReceiverWsStats] = []
        self.threads: List[threading.Thread] = []
        self._stop_event = threading.Event()
        self._stopped = False
        self.save_report = save_report

    def start(self, duration: int = 0):
        """启动所有连接（每个连接独立线程）
        Args:
            duration: 运行时长（秒），0 表示无限运行直到 Ctrl+C
        """
        # HAR 分析表明高可用环境的 WebSocket 端点不需要 jwt-token header
        # 发送 jwt-token 反而会导致 A 集群和 daemon 端点握手失败
        print(f"\n{'='*60}")
        print(f"高可用模式启动：共 {len(self.connections)} 个连接")
        if duration > 0:
            print(f"自动停止时间: {duration} 秒后")
        print(f"{'='*60}\n")

        for cfg in self.connections:
            client = ReceiverWsStats(
                url=cfg["url"],
                jwt_token="",  # 高可用模式：根据 HAR 分析，不使用 jwt-token
                destination=cfg.get("destination", ""),
                verify_ssl=VERIFY_SSL,
                debug=self.debug,
                conn_name=cfg["name"],
                conn_type=cfg.get("type", "stomp"),
                log_fp=self.log_fp,  # 传入统一日志句柄（为 None 则创建独立日志文件）
            )
            self.clients.append(client)
            t = threading.Thread(target=client.start, daemon=True)
            t.start()
            self.threads.append(t)
            time.sleep(0.5)  # 错开启动，避免瞬时并发过大

        if duration > 0:
            print(f"\n所有连接已启动，{duration} 秒后自动停止\n")
            try:
                self._stop_event.wait(duration)
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()
        else:
            print("\n所有连接已启动，按 Ctrl+C 停止\n")
            # 主线程保持运行，等待中断
            try:
                while not self._stop_event.is_set():
                    self._stop_event.wait(1)
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()

    def stop(self):
        """停止所有连接并输出统计报告（幂等）"""
        if self._stopped:
            return
        self._stopped = True
        self._stop_event.set()
        print("\n正在停止所有连接...")
        for client in self.clients:
            client.stop()
        for t in self.threads:
            t.join(timeout=5)
        print("所有连接已停止")
        self._print_report()

    def run_check(self, duration: int = 30) -> dict:
        """
        运行指定时长的 WS 数据采集，返回结构化的检查结果字典。
        用于切换后检查集群切换、轨迹和告警数据情况。
        """
        self.start(duration=duration)
        # start 已自动调用 stop，此时连接已关闭
        return self._get_check_result()

    def _get_check_result(self) -> dict:
        """整理各连接的统计结果，返回结构化检查数据"""
        result = {
            "cluster_switch": {},
            "track_data": {},
            "alarm_data": {},
        }
        for client in self.clients:
            stats = client.get_stats_report()
            if "stomp" in client.conn_name:
                result["track_data"][client.conn_name] = {
                    "msg_count": stats.get("msg_count", 0),
                    "uav_total": stats.get("uav_total", 0),
                    "uav_distribution": dict(stats.get("uav_distribution", {})),
                    "warning_tags_msg_count": stats.get("warning_tags_msg_count", 0),
                    "flow_count": stats.get("flow_count", 0),
                    "totalCount_sum": stats.get("totalCount_sum", 0),
                    "totalCount_distribution": dict(stats.get("totalCount_distribution", {})),
                    "totalCount_100_count": stats.get("totalCount_100_count", 0),
                }
            elif "daemon" in client.conn_name:
                result["cluster_switch"][client.conn_name] = {
                    "master_cluster": stats.get("master_cluster", ""),
                    "cluster_changes": stats.get("cluster_changes", 0),
                    "cluster_change_history": list(stats.get("cluster_change_history", [])),
                }
        return result

    def _print_report(self):
        """输出所有连接的统计汇总报告（A/B 集群合并对比）
        同时输出到终端和 log/ws_客户端信息检查_日期时分秒.txt
        """
        import io
        buf = io.StringIO()

        def _p(*args, **kwargs):
            """同时输出到终端和缓冲区"""
            print(*args, **kwargs)
            print(*args, file=buf, **kwargs)

        _p(f"{'='*80}")
        _p("高可用 WebSocket 统计汇总报告（A/B 集群对比）")
        _p(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        _p(f"{'='*80}")

        # 按类型分组收集数据
        stomp_clients = [c for c in self.clients if c.conn_name.endswith("-stomp")]
        daemon_clients = [c for c in self.clients if c.conn_name.endswith("-daemon")]

        # --- stomp 对比 ---
        if stomp_clients:
            _p("")
            _p("【STOMP 连接对比（la-atc-ws-backend）】")
            _p(f"{'-'*80}")
            _p(f"{'指标':<25} {'A集群':<18} {'B集群':<18} {'一致性判定':<12}")
            _p(f"{'-'*80}")

            data = {}
            for client in stomp_clients:
                label = "A集群" if "A集群" in client.conn_name else "B集群"
                data[label] = client.get_stats_report()

            a_stats = data.get("A集群", {})
            b_stats = data.get("B集群", {})

            # 总消息数
            a_msg = a_stats.get("msg_count", 0)
            b_msg = b_stats.get("msg_count", 0)
            msg_ok = "一致" if a_msg == b_msg else f"差异 {abs(a_msg - b_msg)}"
            _p(f"{'总消息数':<25} {a_msg:<18} {b_msg:<18} {msg_ok:<12}")

            # uavIdentifyCode 数量分布对比
            a_uav = a_stats.get("uav_distribution", {})
            b_uav = b_stats.get("uav_distribution", {})
            all_uav_keys = sorted(set(list(a_uav.keys()) + list(b_uav.keys())))
            if all_uav_keys:
                _p("")
                _p("  -- uavIdentifyCode 数量分布（每次 flightTrack 消息）--")
                _p(f"    {'数量值':<16} {'A集群':<12} {'B集群':<12} {'一致性判定':<12}")
                _p(f"    {'-'*56}")
                for k in all_uav_keys:
                    a_cnt = a_uav.get(k, 0)
                    b_cnt = b_uav.get(k, 0)
                    ok = "一致" if a_cnt == b_cnt else f"差异 {abs(a_cnt - b_cnt)}"
                    _p(f"    {str(k):<16} {a_cnt:<12} {b_cnt:<12} {ok:<12}")

            # warningTags 对比（消息次数）
            a_wt = a_stats.get("warning_tags_msg_count", 0)
            b_wt = b_stats.get("warning_tags_msg_count", 0)
            wt_ok = "一致" if a_wt == b_wt else f"差异 {abs(a_wt - b_wt)}"
            _p("")
            _p(f"    warningTags 存在消息次数: {a_wt} / {b_wt} ({wt_ok})")

            # totalCount 分布对比
            a_tc = a_stats.get("totalCount_distribution", {})
            b_tc = b_stats.get("totalCount_distribution", {})
            all_tc_keys = sorted(set(list(a_tc.keys()) + list(b_tc.keys())))
            if all_tc_keys:
                _p("")
                _p("  -- dataPush totalCount 分布（每次 flowStatistic 消息）--")
                _p(f"    {'totalCount':<16} {'A集群':<12} {'B集群':<12} {'一致性判定':<12}")
                _p(f"    {'-'*56}")
                for k in all_tc_keys:
                    a_cnt = a_tc.get(k, 0)
                    b_cnt = b_tc.get(k, 0)
                    ok = "一致" if a_cnt == b_cnt else f"差异 {abs(a_cnt - b_cnt)}"
                    _p(f"    {str(k):<16} {a_cnt:<12} {b_cnt:<12} {ok:<12}")

            # totalCount=100 次数
            a_100 = a_stats.get("totalCount_100_count", 0)
            b_100 = b_stats.get("totalCount_100_count", 0)
            a_flow = a_stats.get("flow_count", 0)
            b_flow = b_stats.get("flow_count", 0)
            ok_100 = "一致" if a_100 == b_100 else f"差异 {abs(a_100 - b_100)}"
            _p("")
            _p(f"    totalCount=100 次数: {a_100}/{a_flow} / {b_100}/{b_flow} ({ok_100})")

        # --- daemon 对比 ---
        if daemon_clients:
            _p("")
            _p("【DAEMON 连接对比（la-atc-daemon-server）】")
            _p(f"{'-'*80}")
            _p(f"{'指标':<25} {'A集群':<18} {'B集群':<18} {'一致性判定':<12}")
            _p(f"{'-'*80}")

            data = {}
            for client in daemon_clients:
                label = "A集群" if "A集群" in client.conn_name else "B集群"
                data[label] = client.get_stats_report()

            a_stats = data.get("A集群", {})
            b_stats = data.get("B集群", {})

            a_msg = a_stats.get("msg_count", 0)
            b_msg = b_stats.get("msg_count", 0)
            msg_ok = "一致" if a_msg == b_msg else f"差异 {abs(a_msg - b_msg)}"
            _p(f"{'总消息数':<25} {a_msg:<18} {b_msg:<18} {msg_ok:<12}")

            a_master = a_stats.get("master_cluster", "") or "未识别"
            b_master = b_stats.get("master_cluster", "") or "未识别"
            master_ok = "一致" if a_master == b_master else f"不一致"
            _p(f"{'当前主集群':<25} {a_master:<18} {b_master:<18} {master_ok:<12}")

            a_changes = a_stats.get("cluster_changes", 0)
            b_changes = b_stats.get("cluster_changes", 0)
            changes_ok = "一致" if a_changes == b_changes else f"差异 {abs(a_changes - b_changes)}"
            _p(f"{'集群状态变化次数':<25} {a_changes:<18} {b_changes:<18} {changes_ok:<12}")

            # 变化记录 + 切换方向检测
            a_history = a_stats.get("cluster_change_history", [])
            b_history = b_stats.get("cluster_change_history", [])
            if a_history or b_history:
                _p("")
                _p("集群状态变化记录:")
                for i in range(max(len(a_history), len(b_history))):
                    a_rec = a_history[i] if i < len(a_history) else ("", "", "")
                    b_rec = b_history[i] if i < len(b_history) else ("", "", "")
                    a_str = f"{a_rec[0]} {a_rec[1]}→{a_rec[2]}" if a_rec[0] else "-"
                    b_str = f"{b_rec[0]} {b_rec[1]}→{b_rec[2]}" if b_rec[0] else "-"
                    _p(f"  A集群: {a_str}")
                    _p(f"  B集群: {b_str}")

                # 检测 A↔B 切换方向
                all_changes = []
                for ts, old, new in a_history + b_history:
                    if old and new and old != "初始" and new != "初始":
                        old_short = old.replace("cluster_", "").upper()
                        new_short = new.replace("cluster_", "").upper()
                        all_changes.append((ts, old_short, new_short))
                seen = set()
                unique_changes = []
                for item in sorted(all_changes, key=lambda x: x[0]):
                    key = (item[0], item[1], item[2])
                    if key not in seen:
                        seen.add(key)
                        unique_changes.append(item)
                if unique_changes:
                    _p("")
                    _p(">>> 集群切换方向检测")
                    for ts, old_s, new_s in unique_changes:
                        _p(f"  {ts}  [{old_s} → {new_s}]  集群发生切换")
                else:
                    _p("")
                    _p(">>> 集群切换方向: 无切换（始终为同一主集群）")

        _p("")
        _p(f"{'='*80}")

        # 写入报告文件
        if self.save_report:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            log_dir = os.path.join(script_dir, "..", "tmp", "log")
            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = os.path.join(log_dir, f"ws_客户端信息检查_{timestamp}.txt")
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(buf.getvalue())
                print(f"[报告已保存] {report_path}")
            except Exception as e:
                print(f"[报告保存失败] {e}")


def run_ws_check(duration: int = 30, debug: bool = False) -> dict:
    """
    便捷函数：运行 WS 切换后检查。
    启动高可用模式下的 4 个连接，采集指定时长后返回检查结果。
    返回: {
        "cluster_switch": { "A集群-daemon": {...}, "B集群-daemon": {...} },
        "track_data":     { "A集群-stomp": {...}, "B集群-stomp": {...} },
        "alarm_data":     {},
    }
    """
    conns = _get_ha_connections()
    if not conns:
        print("[错误] 高可用模式需要 ha_env.py 配置，请检查文件是否存在")
        return {}
    multi = MultiWsClient(connections=conns, debug=debug)
    return multi.run_check(duration=duration)


def main():
    parser = argparse.ArgumentParser(
        description="接收机WebSocket查询统计工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 直接运行（使用配置文件的WS_URL）
  python 接收机查询统计.py

  # 指定STOMP订阅目标
  python 接收机查询统计.py --destination /topic/flightTrack

  # 使用自定义JWT Token
  python 接收机查询统计.py --token "your_jwt_token"

  # 使用环境变量设置Token（推荐）
  set ATC_JWT_TOKEN=your_jwt_token
  python 接收机查询统计.py

  # 开启调试模式查看原始消息
  python 接收机查询统计.py --debug

环境变量:
  ATC_JWT_TOKEN    设置JWT认证令牌，优先级高于配置文件
        """,
    )
    parser.add_argument("--url", default=WS_URL, help="WebSocket URL")
    parser.add_argument(
        "--destination",
        default=STOMP_DESTINATION,
        help="STOMP订阅目标（如 /topic/flightTrack）",
    )
    parser.add_argument(
        "--token",
        default="",
        help="JWT认证令牌 (默认: 使用配置文件中的 JWT_TOKEN)",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        default=VERIFY_SSL,
        help="验证SSL证书 (默认: 不验证)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=DEBUG_RAW,
        help="打印原始消息用于调试",
    )
    parser.add_argument(
        "--ha",
        action="store_true",
        default=HA_MODE,
        help="启用高可用模式：同时连接 A/B 集群的 stomp 和 daemon 端点",
    )
    parser.add_argument(
        "--no-ha",
        action="store_true",
        default=False,
        help="强制关闭高可用模式（使用单连接）",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="运行时长（秒），0 表示无限运行直到 Ctrl+C",
    )

    args = parser.parse_args()
    use_ha = args.ha and not args.no_ha

    # 高可用模式
    if use_ha:
        conns = _get_ha_connections()
        if not conns:
            print("[错误] 高可用模式需要 ha_env.py 配置，请检查文件是否存在")
            sys.exit(1)
        multi = MultiWsClient(connections=conns, debug=args.debug)
        try:
            multi.start(duration=args.duration)
        except KeyboardInterrupt:
            print("\n\n用户中断，正在关闭所有连接...")
            multi.stop()
            print("\n统计已结束")
        return

    # 单连接模式（兼容原有行为）
    stats = ReceiverWsStats(
        url=args.url,
        jwt_token=args.token,
        destination=args.destination,
        verify_ssl=args.verify_ssl,
        debug=args.debug,
    )

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动接收机WebSocket统计...")
    print(f"WebSocket地址: {args.url}")
    if args.destination:
        print(f"STOMP订阅目标: {args.destination}")
    print("输出格式: 时间(年月日时分秒) | uavIdentifyCode数量")
    print("按 Ctrl+C 停止\n")

    try:
        stats.start()
    except KeyboardInterrupt:
        print("\n\n用户中断，正在关闭连接...")
        stats.stop()
        print("\n统计已结束")


if __name__ == "__main__":
    main()
