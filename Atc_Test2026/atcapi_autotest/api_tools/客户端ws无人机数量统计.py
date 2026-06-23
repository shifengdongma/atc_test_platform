#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
接收机查询统计脚本 (WebSocket版)
功能：连接低空空管WebSocket服务，接收flightTrack消息，统计每秒uavIdentifyCode数量

WebSocket信息：
- URL: wss://dkkgsit-test.testdolphin.com/la-atc-ws-backend/ws/stomp/304/ravwj0ql/websocket
- 过滤: 包含flightTrack字段的消息
- 统计: 每秒内uavIdentifyCode字段出现数量

输出格式：
时间(年月日时分秒) | uavIdentifyCode数量

使用说明：
1. 直接运行: python 接收机查询统计.py
2. 修改下方【配置区域】的参数后运行
3. 或使用命令行参数覆盖配置
4. 按 Ctrl+C 停止统计
"""

# ============================================
# 【配置区域】- 修改以下参数即可快速配置
# ============================================

# WebSocket URL
# SockJS base URL（脚本会自动完成握手，生成 session 并扩展为完整 WebSocket URL）
# 如需使用浏览器复制的完整 SockJS URL，直接覆盖即可
WS_URL = "wss://dkkgsit-test.testdolphin.com/la-atc-ws-backend/ws/stomp"

# JWT认证令牌（从浏览器获取，如过期请更新）
JWT_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJhdXRoVXNlckRldGFpbHMiOiJ7XCJ1c2VyXCI6IHtcImNvZGVcIjogXCJhdGNBZG1pblwifX0iLCJzdWIiOiJhdGNBZG1pbiIsImRlZmF1bHRHcmFudFNjb3BlIjoiIiwiYW1yIjoibWZhIiwiaXNzIjoiaHR0cDovL2Rldi5jdHNwLmtlZGFjb20uY29tL2Nsb3VkLXJiYWMiLCJhdXRoVGltZSI6MTc3ODkxOTc1NDg2MiwiYWNjZXNzVG9rZW4iOiJtakNBK2Q1QklsVmp6OXczTDgyRTBvd2w4QjZRUlVMdG5kK09uMWxqZWtTUVJEQUhyYzZIcEwwMlN5RTN6dWlsQVdwOEpEd1pGQ3dmNC9uZTVqUS9PUXlkYU5USlNKcXhodWNsQ0hxSU5RYz0iLCJub25jZSI6bnVsbCwiYXVkIjoibGEtYXRjLWJpei1iYWNrZW5kIiwiYWNyIjoidXJuOm1hY2U6aW5jb21tb246aWFwOnNpbHZlciIsImF6cCI6IiIsInRlbmFudElkIjpudWxsLCJleHAiOjE3Nzg5MTk3NTQsImlhdCI6MTc3ODgzMzM1NH0.RYwTGnbTyhibF4BACmbjuy8bJTZDbUsJG1vmrQbsdSV2-pIWK1AD6RsvMH392Pt2r0PXGy8mhVxlGkmNqi8XWg"

# STOMP订阅目标（从浏览器开发者工具复制，例如：/flightTrack/SEAT0001）
# 注意：低空空管系统使用 /flightTrack/{seatCode} 格式，没有 /topic 前缀
# SEAT0001 是席位代码，请替换为实际登录的席位代码
STOMP_DESTINATION = "/flightTrack/SEAT0001"

# 告警数据推送订阅目标（席位级告警统计，如不需要可留空）
ALARM_DESTINATION = "/dataPush/seat/SEAT0001"

# 是否验证SSL证书
VERIFY_SSL = False

# 是否打印原始消息（调试用）
DEBUG_RAW = False

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
from typing import Dict, Any

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


def get_token_from_env() -> str:
    """从环境变量获取JWT Token"""
    return os.environ.get("ATC_JWT_TOKEN", "")


class ReceiverWsStats:
    """接收机WebSocket统计客户端"""

    def __init__(
        self,
        url: str = None,
        jwt_token: str = None,
        destination: str = None,
        verify_ssl: bool = None,
        debug: bool = None,
    ):
        self.url = url or WS_URL
        self.jwt_token = jwt_token or get_token_from_env() or JWT_TOKEN
        self.destination = destination if destination is not None else STOMP_DESTINATION
        self.alarm_destination = ALARM_DESTINATION
        self.verify_ssl = verify_ssl if verify_ssl is not None else VERIFY_SSL
        self.debug = debug if debug is not None else DEBUG_RAW

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

        # 创建日志文件
        os.makedirs(TESTREPORT_DIR, exist_ok=True)
        log_filename = datetime.now().strftime("%Y%m%d%H%M%S") + "_wsclient.log"
        self._log_path = os.path.join(TESTREPORT_DIR, log_filename)
        self._log_fp = open(self._log_path, "w", encoding="utf-8")
        print(f"[日志] 统计输出已写入: {self._log_path}")

    def __del__(self):
        """析构时关闭日志文件句柄。"""
        if hasattr(self, '_log_fp') and self._log_fp:
            try:
                self._log_fp.close()
            except Exception:
                pass

    def _write_log(self, line: str) -> None:
        """将一行内容写入日志文件（线程安全，由调用方持有 self.lock）。"""
        if hasattr(self, '_log_fp') and self._log_fp:
            self._log_fp.write(line + "\n")
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
                self._write_log(line)
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
                self._write_log(line)

    def _extract_uav_count(self, data: Dict[str, Any]) -> int:
        """从消息数据中提取无人机数量"""
        count = 0

        # 情况1: uavs 列表（低空空管新版格式）
        uavs = data.get("uavs")
        if isinstance(uavs, list):
            count += len(uavs)

        # 情况2: flightTrack 是列表（旧版兼容）
        ft = data.get("flightTrack")
        if isinstance(ft, list):
            for item in ft:
                if isinstance(item, dict) and "uavIdentifyCode" in item:
                    count += 1
        elif isinstance(ft, dict) and "uavIdentifyCode" in ft:
            count += 1

        # 情况3: data 嵌套包装
        nested_data = data.get("data")
        if isinstance(nested_data, dict):
            nd_ft = nested_data.get("flightTrack")
            if isinstance(nd_ft, list):
                for item in nd_ft:
                    if isinstance(item, dict) and "uavIdentifyCode" in item:
                        count += 1
            elif isinstance(nd_ft, dict) and "uavIdentifyCode" in nd_ft:
                count += 1
            if "uavIdentifyCode" in nested_data:
                val = nested_data["uavIdentifyCode"]
                if isinstance(val, list):
                    count += len(val)
                else:
                    count += 1

        return count

    def _process_body(self, body: str):
        """解析消息体并统计"""
        body = body.rstrip("\x00").strip()
        if not body:
            return

        if self.debug:
            print(f"\n[DEBUG] 原始消息体: {body[:500]}")

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return

        if not isinstance(data, dict):
            return

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
                if total_count > 0:
                    self._update_and_print(uav_count=0, alarm_count=0, flow_count=total_count)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
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

        count = self._extract_uav_count(data)
        if count > 0:
            self._update_and_print(uav_count=count, alarm_count=0)

    def _handle_payload(self, payload: str):
        """处理实际载荷（可能是STOMP帧）"""
        if not isinstance(payload, str):
            return

        # STOMP 心跳：裸的 \n 或 \n\x00（必须回复，否则服务端30秒后断开）
        stripped = payload.rstrip("\x00").strip()
        if stripped == "":
            if self.ws:
                self.ws.send(json.dumps(["\n"]))
            return

        # 识别 STOMP 命令帧（CONNECTED, MESSAGE, ERROR 等）
        stomp_cmd = None
        if "\n" in payload:
            first_line = payload.split("\n", 1)[0].strip()
            if first_line in ("CONNECTED", "MESSAGE", "ERROR", "RECEIPT"):
                stomp_cmd = first_line

        if stomp_cmd == "CONNECTED":
            print(f"[{self._now_str()}] STOMP握手成功 (CONNECTED)")
            return
        elif stomp_cmd == "ERROR":
            print(f"[{self._now_str()}] STOMP错误: {payload[:300]}")
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
        # STOMP CONNECT 是强制握手步骤，无论是否订阅都必须发送
        connect_frame = (
            "CONNECT\n"
            "heart-beat:0,0\n"
            "accept-version:1.2,1.1,1.0\n"
            "\n\x00"
        )
        sockjs_msg = json.dumps([connect_frame])
        print(f"[{self._now_str()}] 发送STOMP CONNECT...")
        if self.ws:
            self.ws.send(sockjs_msg)

        destinations = []
        if self.destination:
            destinations.append(("sub-0", self.destination))
        if self.alarm_destination:
            destinations.append(("sub-1", self.alarm_destination))

        if not destinations:
            print(f"[{self._now_str()}] 未配置STOMP_DESTINATION，跳过SUBSCRIBE（服务端可能主动推送）")
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
                print(f"[{self._now_str()}] 发送STOMP SUBSCRIBE: {dest}")
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

        # 生成 session ID（8 位随机字符）
        session = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        server_id = "000"
        ws_scheme = "wss" if parsed.scheme in ("wss", "https") else "ws"
        return f"{ws_scheme}://{parsed.netloc}{path}/{server_id}/{session}/websocket"

    def on_message(self, ws, message):
        """WebSocket消息回调"""
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="ignore")

        if self.debug:
            print(f"[DEBUG] 收到原始消息: {message[:200]}")

        # SockJS 协议处理
        if message == "o":
            self.connected = True
            print(f"[{self._now_str()}] SockJS连接已打开")
            self._send_stomp_connect()
            return
        elif message == "h":
            if self.ws:
                self.ws.send("h")
            return
        elif message.startswith("c"):
            print(f"[{self._now_str()}] SockJS连接关闭: {message}")
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
            self._handle_payload(message)

    def on_open(self, ws):
        print(f"[{self._now_str()}] WebSocket连接已建立")

    def on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        print(f"\n[{self._now_str()}] WebSocket连接已关闭 (code={close_status_code}, msg={close_msg})")

    def on_error(self, ws, error):
        print(f"\n[{self._now_str()}] WebSocket错误: {error}")

    def start(self):
        self.running = True
        self._user_stopped = False

        while self.running:
            try:
                websocket.enableTrace(self.debug)

                # SockJS URL 解析：支持传入 base URL 自动生成完整 WebSocket URL
                self.url = self._resolve_sockjs_url(self._base_url)
                print(f"[{self._now_str()}] 实际连接地址: {self.url}")

                sslopt = {"cert_reqs": ssl.CERT_NONE} if not self.verify_ssl else None
                header = []
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
                print(f"[{self._now_str()}] 连接异常: {e}")
            finally:
                if self._user_stopped:
                    break

                # 自动重连（指数退避）
                delay = self._reconnect_delay
                print(f"[{self._now_str()}] 连接断开，{delay}秒后自动重连...")
                time.sleep(delay)
                self._reconnect_delay = min(delay * 2, self._max_reconnect_delay)

        print(f"[{self._now_str()}] 统计已停止")

    def stop(self):
        self._user_stopped = True
        self.running = False
        if self.ws:
            self.ws.close()
        if hasattr(self, '_log_fp') and self._log_fp:
            try:
                self._log_fp.close()
                self._log_fp = None
                print(f"\n[日志] 文件已保存: {self._log_path}")
            except Exception:
                pass


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

    args = parser.parse_args()

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
