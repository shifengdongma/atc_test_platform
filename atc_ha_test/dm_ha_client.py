#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
达梦数据库连接客户端
支持模块化配置与外部调用，配置源统一从 ha_env.py 获取
支持 A/B 双集群同时连接与对比查询
"""

import dmPython
import sys
import os

# 将当前目录加入路径，确保能导入同级目录的 ha_env
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from ha_env import (
        dm_a_host, dm_a_port, dm_a_user, dm_a_password, dm_a_schema,
        dm_b_host, dm_b_port, dm_b_user, dm_b_password, dm_b_schema,
    )
except ImportError:
    raise ImportError(
        "无法从 ha_env.py 导入数据库配置，请确认文件存在且变量名正确。"
    )

# ==================== 全局配置区域（从 ha_env.py 统一获取）====================
# A 集群数据库
DB_HOST = dm_a_host
DB_PORT = dm_a_port
DB_USER = dm_a_user
DB_PASSWORD = dm_a_password
DB_SCHEMA = dm_a_schema

# A/B 集群配置字典，便于外部脚本批量创建客户端
DB_CONFIG_A = {
    "host": dm_a_host,
    "port": dm_a_port,
    "user": dm_a_user,
    "password": dm_a_password,
    "schema": dm_a_schema,
}

DB_CONFIG_B = {
    "host": dm_b_host,
    "port": dm_b_port,
    "user": dm_b_user,
    "password": dm_b_password,
    "schema": dm_b_schema,
}
# =====================================================

class DmDbClient:
    """达梦数据库连接客户端

    支持作为模块被外部导入调用：
        from dm_ha_client import DmDbClient, DB_CONFIG_A, DB_CONFIG_B
        client = DmDbClient(**DB_CONFIG_A)
        client.connect()
        data = client.query(table_name="uav_info", columns=["id", "name"])
        client.close()
    """

    def __init__(self, host=None, port=None, user=None, password=None, schema=None):
        """初始化客户端，参数为空时自动使用全局配置（A 集群）"""
        self.host = host if host is not None else DB_HOST
        self.port = port if port is not None else DB_PORT
        self.user = user if user is not None else DB_USER
        self.password = password if password is not None else DB_PASSWORD
        self.schema = schema if schema is not None else DB_SCHEMA
        self.conn = None
        self.cursor = None

    def connect(self):
        """建立数据库连接"""
        try:
            self.conn = dmPython.connect(
                user=self.user,
                password=self.password,
                server=self.host,
                port=self.port,
                schema=self.schema
            )
            self.cursor = self.conn.cursor()
            print(f"[DmDbClient] 成功连接到达梦数据库 {self.host}:{self.port}, 模式: {self.schema}")
            return True
        except Exception as e:
            print(f"[DmDbClient] 数据库连接失败: {e}")
            return False

    def query(self, table_name, columns=None, where=None, limit=None):
        """通用查询方法

        Args:
            table_name (str): 表名（不含模式前缀）
            columns (str/list/tuple, optional): 字段名，支持字符串或列表。
                                               为 None 时查询所有字段（*）。
            where (str, optional): WHERE 条件语句（不含 WHERE 关键字）
            limit (int, optional): 限制返回记录数

        Returns:
            list[dict]: 查询结果，每条记录为一个字典，key 为字段名
        """
        if not self.cursor:
            print("[DmDbClient] 数据库未连接，请先调用 connect()")
            return None

        # 处理字段
        if columns is None:
            col_str = "*"
        elif isinstance(columns, (list, tuple)):
            col_str = ", ".join(str(c) for c in columns)
        else:
            col_str = str(columns)

        # 构建 SQL
        sql = f"SELECT {col_str} FROM {self.schema}.{table_name}"
        if where:
            sql += f" WHERE {where}"
        if limit is not None and isinstance(limit, int):
            sql += f" LIMIT {limit}"

        try:
            self.cursor.execute(sql)
            desc = self.cursor.description
            if desc is None:
                return []
            col_names = [d[0] for d in desc]
            rows = self.cursor.fetchall()

            # 转换为字典列表
            result = [dict(zip(col_names, row)) for row in rows]

            print(f"[DmDbClient] 查询表: {self.schema}.{table_name}")
            print(f"[DmDbClient] 返回 {len(result)} 条记录")

            return result
        except Exception as e:
            print(f"[DmDbClient] 查询失败: {e}")
            return None

    def query_to_list(self, table_name, columns=None, where=None, limit=None):
        """查询并返回纯列表格式（不含字段名）

        Args:
            table_name (str): 表名
            columns (str/list/tuple, optional): 字段名
            where (str, optional): WHERE 条件
            limit (int, optional): 限制条数

        Returns:
            list[tuple]: 查询结果列表
        """
        if not self.cursor:
            print("[DmDbClient] 数据库未连接，请先调用 connect()")
            return None

        if columns is None:
            col_str = "*"
        elif isinstance(columns, (list, tuple)):
            col_str = ", ".join(str(c) for c in columns)
        else:
            col_str = str(columns)

        sql = f"SELECT {col_str} FROM {self.schema}.{table_name}"
        if where:
            sql += f" WHERE {where}"
        if limit is not None and isinstance(limit, int):
            sql += f" LIMIT {limit}"

        try:
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()
            print(f"[DmDbClient] 查询表: {self.schema}.{table_name}, 返回 {len(rows)} 条记录")
            return rows
        except Exception as e:
            print(f"[DmDbClient] 查询失败: {e}")
            return None

    def get_table_columns(self, table_name):
        """获取指定表的所有字段名

        Args:
            table_name (str): 表名

        Returns:
            list[str]: 字段名列表
        """
        if not self.cursor:
            print("[DmDbClient] 数据库未连接，请先调用 connect()")
            return None

        try:
            sql = (
                f"SELECT COLUMN_NAME FROM USER_TAB_COLUMNS "
                f"WHERE TABLE_NAME = '{table_name.upper()}'"
            )
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()
            columns = [row[0] for row in rows]
            return columns
        except Exception as e:
            print(f"[DmDbClient] 获取表字段失败: {e}")
            return None

    def print_table_schema(self, table_name):
        """打印表结构信息

        Args:
            table_name (str): 表名
        """
        if not self.cursor:
            print("[DmDbClient] 数据库未连接，请先调用 connect()")
            return

        try:
            sql = (
                f"SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE, COMMENTS "
                f"FROM USER_TAB_COLUMNS WHERE TABLE_NAME = '{table_name.upper()}'"
            )
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()

            print(f"\n--- 表 {self.schema}.{table_name} 的结构 ---")
            print(f"{'字段名':<20} {'类型':<15} {'长度':<8} {'可空':<6} {'注释'}")
            print("-" * 70)
            for row in rows:
                col_name, data_type, data_length, nullable, comments = row
                comments = comments if comments else ""
                print(f"{col_name:<20} {data_type:<15} {data_length:<8} {nullable:<6} {comments}")
            print("-" * 70)
        except Exception as e:
            print(f"[DmDbClient] 打印表结构失败: {e}")

    def execute(self, sql, silent=False):
        """执行自定义 SQL 语句

        Args:
            sql (str): SQL 语句
            silent (bool): 为 True 时静默输出成功日志，仅保留错误日志

        Returns:
            list[dict] / None: 查询结果字典列表，非查询语句返回 None
        """
        if not self.cursor:
            print("[DmDbClient] 数据库未连接，请先调用 connect()")
            return None

        try:
            self.cursor.execute(sql)
            desc = self.cursor.description
            if desc:
                col_names = [d[0] for d in desc]
                rows = self.cursor.fetchall()
                result = [dict(zip(col_names, row)) for row in rows]
                if not silent:
                    print(f"[DmDbClient] 执行 SQL 成功，返回 {len(result)} 条记录")
                return result
            else:
                self.conn.commit()
                if not silent:
                    print("[DmDbClient] 执行 SQL 成功")
                return None
        except Exception as e:
            print(f"[DmDbClient] SQL 执行失败: {e}")
            return None

    def close(self):
        """关闭数据库连接"""
        if self.cursor:
            self.cursor.close()
            self.cursor = None
        if self.conn:
            self.conn.close()
            self.conn = None
        print("[DmDbClient] 数据库连接已关闭")

    def __enter__(self):
        """支持 with 语句"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句自动关闭"""
        self.close()


class DualDmDbClient:
    """A/B 双集群达梦数据库对比查询客户端

    封装两个 DmDbClient 实例，支持同时对 A/B 集群执行相同查询并返回结果。
    适用于高可用场景下的数据一致性校验。

    使用示例：
        from dm_ha_client import DualDmDbClient
        dual = DualDmDbClient()
        if dual.connect():
            result_a, result_b = dual.query_both("uav_info", columns=["id"], limit=5)
            dual.close()
    """

    def __init__(self):
        self.client_a = DmDbClient(**DB_CONFIG_A)
        self.client_b = DmDbClient(**DB_CONFIG_B)

    def connect(self):
        """同时连接 A/B 两个数据库"""
        ok_a = self.client_a.connect()
        ok_b = self.client_b.connect()
        return ok_a and ok_b

    def query_both(self, table_name, columns=None, where=None, limit=None):
        """对 A/B 集群执行相同的查询

        Returns:
            tuple(list[dict], list[dict]): (A集群结果, B集群结果)
        """
        result_a = self.client_a.query(table_name, columns, where, limit)
        result_b = self.client_b.query(table_name, columns, where, limit)
        return result_a, result_b

    def query_both_to_list(self, table_name, columns=None, where=None, limit=None):
        """对 A/B 集群执行相同的查询，返回纯列表格式

        Returns:
            tuple(list[tuple], list[tuple]): (A集群结果, B集群结果)
        """
        result_a = self.client_a.query_to_list(table_name, columns, where, limit)
        result_b = self.client_b.query_to_list(table_name, columns, where, limit)
        return result_a, result_b

    def execute_both(self, sql):
        """对 A/B 集群执行相同的 SQL

        Returns:
            tuple(list[dict]/None, list[dict]/None): (A集群结果, B集群结果)
        """
        result_a = self.client_a.execute(sql)
        result_b = self.client_b.execute(sql)
        return result_a, result_b

    def close(self):
        """关闭 A/B 两个数据库连接"""
        self.client_a.close()
        self.client_b.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def main():
    """脚本独立运行示例：分别演示单库连接与双库对比查询"""
    print("=" * 60)
    print("示例 1：单库连接（默认 A 集群）")
    print("=" * 60)
    client = DmDbClient()

    if client.connect():
        print("\n--- 步骤 1：查看 uav_info 表结构 ---")
        client.print_table_schema("uav_info")

        # 获取字段列表
        columns = client.get_table_columns("uav_info")
        print(f"\n字段列表: {columns}")

        # 示例 1：查询 uav_info 表全部字段
        print("\n--- 示例 1：查询 uav_info 全部数据 ---")
        data = client.query(table_name="uav_info")
        if data:
            for row in data[:3]:  # 只打印前3条
                print(row)

        # 示例 2：查询指定字段（使用前两个真实字段）
        print("\n--- 示例 2：查询 uav_info 指定字段 ---")
        if columns and len(columns) >= 2:
            data = client.query(
                table_name="uav_info",
                columns=columns[:2]
            )
            if data:
                for row in data[:3]:
                    print(row)

        # 示例 3：带条件查询
        print("\n--- 示例 3：带条件查询 ---")
        data = client.query(
            table_name="uav_info",
            columns="*",
            where="ROWNUM <= 5"
        )
        if data:
            for row in data:
                print(row)

        # 示例 4：查询并返回纯列表
        print("\n--- 示例 4：返回纯列表格式 ---")
        if columns and len(columns) >= 2:
            rows = client.query_to_list(
                table_name="uav_info",
                columns=columns[:2],
                limit=3
            )
            if rows:
                for row in rows:
                    print(row)

        client.close()

    print("\n" + "=" * 60)
    print("示例 2：A/B 双库对比查询")
    print("=" * 60)
    dual = DualDmDbClient()
    if dual.connect():
        result_a, result_b = dual.query_both("uav_info", columns=["*"], limit=3)
        print(f"\n[A 集群] 返回 {len(result_a) if result_a else 0} 条记录")
        if result_a:
            for row in result_a:
                print(row)
        print(f"\n[B 集群] 返回 {len(result_b) if result_b else 0} 条记录")
        if result_b:
            for row in result_b:
                print(row)
        dual.close()


if __name__ == "__main__":
    main()
