# -*- coding: utf-8 -*-
"""
IOMP登录鉴权
接口参考：https://oa.kedacom.com/confluence/pages/viewpage.action?pageId=215616104
主要实现：获取 IOMP JWT Token、刷新token、获取当前登录人username
用法示例:
    from api_tools.iomp_api_common import get_iomp_token, get_iomp_username
    token = get_iomp_token()                      # 默认调用，带缓存
    token = get_iomp_token(force_refresh=True)    # 强制刷新
    username = get_iomp_username()                # 通过 token 解析当前登录用户名
"""

import requests
import time

# 模块级 token 缓存: {cache_key: {"token": str, "refresh_token": str, "exp": int}}
_token_cache = {}

# IOMP token 有效期 30 分钟（秒）
_TOKEN_EXPIRE = 30 * 60


def _extract_token(result: dict):
    """从接口响应中提取 jwtToken 和 refreshToken"""
    token = None
    refresh_token = None
    data = result
    if isinstance(result.get("result"), dict):
        data = result["result"]
    for key in ("jwtToken", "jwt_token"):
        if key in data:
            token = data[key]
            break
    for key in ("refreshToken", "refresh_token"):
        if key in data:
            refresh_token = data[key]
            break
    return token, refresh_token


def _refresh_iomp_token(refresh_token: str, base_url: str = "http://10.165.32.24:8801") -> tuple:
    """
    使用 refreshToken 刷新 IOMP token

    Returns:
        (jwt_token, refresh_token) 刷新失败返回 (None, None)
    """
    url = f"{base_url}/iomp/api/v2/token/refresh"
    try:
        resp = requests.post(
            url,
            json={"refreshToken": refresh_token},
            timeout=30
        )
        result = resp.json()
        if result.get("code") == "0" or result.get("status") == 200:
            return _extract_token(result)
        else:
            print(f"[IOMP] 刷新 token 接口返回异常: {result}")
    except Exception as e:
        print(f"[IOMP] 刷新 token 请求失败: {e}")
    return None, None


def get_iomp_token(
    url: str = "http://10.165.32.24:8801/iomp/api/v2/token",
    accesskey: str = "20zhfhha3xstc1zl",
    force_refresh: bool = False,
) -> str:
    """
    获取 IOMP JWT Token，有效期内优先返回缓存，过期后自动刷新。

    Args:
        url: IOMP token 接口地址
        accesskey: 接入密钥
        force_refresh: 为 True 时强制重新获取，忽略缓存

    Returns:
        JWT Token 字符串，获取失败时返回空字符串
    """
    cache_key = f"{url}|{accesskey}"
    base_url = url.rsplit("/", 2)[0]  # 从完整 URL 提取 base_url

    now = time.time()

    # 检查缓存是否有效（预留 60 秒缓冲）
    if not force_refresh and cache_key in _token_cache:
        cached = _token_cache[cache_key]
        token = cached.get("token", "")
        exp = cached.get("exp", 0)
        refresh_token = cached.get("refresh_token", "")

        if token and exp > now + 60:
            return token

        # token 已过期或即将过期，尝试用 refreshToken 刷新
        if refresh_token:
            print("[IOMP] token 即将过期，尝试刷新...")
            new_token, new_refresh = _refresh_iomp_token(refresh_token, base_url)
            if new_token:
                _token_cache[cache_key] = {
                    "token": new_token,
                    "refresh_token": new_refresh or refresh_token,
                    "exp": now + _TOKEN_EXPIRE,
                }
                print("[IOMP] token 刷新成功")
                return new_token
            else:
                print("[IOMP] token 刷新失败，回退重新获取")

    # 缓存不存在、已过期或刷新失败，重新获取
    try:
        resp = requests.post(
            url,
            json={"accesskey": accesskey},
            timeout=30
        )
        result = resp.json()

        token, refresh_token = _extract_token(result)

        if token:
            _token_cache[cache_key] = {
                "token": token,
                "refresh_token": refresh_token or "",
                "exp": now + _TOKEN_EXPIRE,
            }
            return token
        else:
            print(f"[IOMP] 接口未返回 token: {result}")
    except Exception as e:
        print(f"[IOMP] 获取 token 失败: {e}")

    return ""


def get_iomp_username(
    base_url: str = "http://10.165.32.24:8801",
    token: str = "",
) -> str:
    """
    调用 IOMP /iomp/api/v2/token/user 接口，通过 JWT Token 解析当前登录用户名。

    Args:
        base_url: IOMP 基础地址，如 http://10.165.32.24:8801
        token: JWT Token 字符串；为空时自动调用 get_iomp_token() 获取

    Returns:
        username 字符串，解析失败时返回空字符串
    """
    if not token:
        token = get_iomp_token()
    if not token:
        print("[IOMP] 无法获取 token，解析 username 失败")
        return ""

    url = f"{base_url}/iomp/api/v2/token/user"
    headers = {
        "authorization": token,  # 接口要求小写 authorization
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        result = resp.json()
        if result.get("code") == "0" or result.get("status") == 200:
            result_data = result.get("result", {})
            if isinstance(result_data, dict):
                username = result_data.get("username", "")
                if username:
                    return username
            print(f"[IOMP] 解析 username 失败，响应缺少 username 字段: {result}")
        else:
            print(f"[IOMP] 获取 username 接口返回异常: {result}")
    except Exception as e:
        print(f"[IOMP] 获取 username 请求失败: {e}")

    return ""


if __name__ == "__main__":
    token = get_iomp_token()
    print(f"token: {token}")
    username = get_iomp_username(token=token)
    print(f"username: {username}")
