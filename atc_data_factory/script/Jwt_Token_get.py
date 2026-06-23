import requests
import urllib3
import json
import base64
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
#
# 其他脚本调用方法:
#   from api_auto_test_cases.Jwt_Token_get import get_jwt_token
#
#   # 1. 默认调用 —— 首次登录，有效期内自动返回缓存（24h）
#   token = get_jwt_token()
#   headers = {"jwt-token": token}
#
#   # 2. 切换环境/账号 —— 不同参数自动隔离缓存
#   token = get_jwt_token(
#       base_url="https://dkkgdev.devdolphin.com",
#       username="rbac",
#       password="123456",
#       client_id="xxx",
#       client_secret="yyy"
#   )
#
#   # 3. 强制刷新 —— 忽略缓存，重新获取新 token
#   token = get_jwt_token(force_refresh=True)

# 模块级 token 缓存: {cache_key: {"token": str, "exp": int}}
_token_cache = {}


def _parse_token_exp(token: str) -> int:
    """解析 JWT Token 的 exp 过期时间戳（秒），解析失败返回 0"""
    try:
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return int(payload.get("exp", 0))
    except Exception:
        return 0


def _make_cache_key(base_url: str, username: str, client_id: str) -> str:
    """根据关键参数生成缓存 key"""
    return f"{base_url}|{username}|{client_id}"


def get_jwt_token(
    base_url: str = "https://dkkgsit-test.testdolphin.com",
    username: str = "atcAdmin",
    password: str = "atcAdmin_123",
    client_id: str = "la-atc-biz-backend",
    client_secret: str = "ZDW2YRYB37bt",
    force_refresh: bool = False,
) -> str:
    """
    获取 JWT Token，有效期内优先返回缓存，避免重复登录。

    Args:
        force_refresh: 为 True 时强制重新获取，忽略缓存。

    Returns:
        JWT Token 字符串，获取失败时返回空字符串。
    """
    cache_key = _make_cache_key(base_url, username, client_id)

    # 检查缓存是否有效（预留 60 秒缓冲，防止边界过期）
    if not force_refresh and cache_key in _token_cache:
        cached = _token_cache[cache_key]
        token = cached.get("token", "")
        exp = cached.get("exp", 0)
        if token and exp > time.time() + 60:
            return token

    # 缓存不存在或已过期，重新获取
    login_url = f"{base_url}/cloud-rbac/access_token"
    params = {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password,
    }

    try:
        resp = requests.post(login_url, params=params, verify=False, timeout=30)
        result = resp.json()

        token = None
        if result.get("code") == "0" and isinstance(result.get("result"), dict):
            token = result["result"].get("jwt_token") or result["result"].get("access_token")
        if not token:
            for key in ("jwt_token", "access_token", "jwt-token", "token"):
                if key in result:
                    token = result[key]
                    break

        if token:
            exp = _parse_token_exp(token)
            _token_cache[cache_key] = {"token": token, "exp": exp}
            return token
    except Exception:
        pass

    return ""


if __name__ == "__main__":
    token = get_jwt_token()
    print(token)
