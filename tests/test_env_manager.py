# -*- coding: utf-8 -*-
"""env_manager._update_env_py docstring 安全测试。

背景：env.py 头部 docstring 内含与真实常量同名的模板示例行，全文正则替换会
改写 docstring 副本并污染文档；空值保护的 re.search 也可能误命中 docstring。
本测试验证替换只作用于真实常量区。
"""

import env_manager as env_mgr


def _write_env_py(tmp_path):
    """构造与项目 env.py 同形状的临时文件（头部 docstring + 真实常量）。"""
    path = tmp_path / "env.py"
    content = (
        "'''\n"
        "示例 docstring 内含同名赋值：\n"
        'redis_ip = "doc-ip"\n'
        'redis_password = "doc-password"\n'
        "'''\n"
        'redis_ip = "real-ip"\n'
        'redis_port = "6379"\n'
        'redis_password = "real-password"\n'
        'kafka_url = "real-kafka:9092"\n'
    )
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_update_env_py_skips_docstring(tmp_path):
    """替换只作用于真实常量，docstring 内示例行保持不变。"""
    path = _write_env_py(tmp_path)
    env_mgr._update_env_py({"redis_ip": "new-ip"}, env_path=path)

    content = open(path, encoding="utf-8").read()
    assert 'redis_ip = "new-ip"' in content    # 真实常量被更新
    assert 'redis_ip = "doc-ip"' in content    # docstring 示例未被污染


def test_update_env_py_empty_value_keeps_real_constant(tmp_path):
    """空值保护只查真实常量区：docstring 副本不再导致误判。"""
    path = _write_env_py(tmp_path)
    env_mgr._update_env_py({"redis_ip": "new-ip", "redis_password": ""}, env_path=path)

    content = open(path, encoding="utf-8").read()
    assert 'redis_password = "real-password"' in content  # 真实密码未被空值覆盖
    assert 'redis_ip = "new-ip"' in content
