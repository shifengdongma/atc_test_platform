#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
达梦数据库连接客户端
支持模块化配置与外部调用
"""

import dmPython
import os
import sys

# 将项目根目录加入 sys.path，确保能导入 env.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from env import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_SCHEMA
except ImportError:
    # Docker 环境中 env.py 可能未挂载，从环境变量读取
    DB_HOST = os.environ.get("UTM_DM_HOST", "10.165.32.32")
    DB_PORT = int(os.environ.get("UTM_DM_PORT", "5237"))
    DB_USER = os.environ.get("UTM_DM_USER", "SYSDBA")
    DB_PASSWORD = os.environ.get("UTM_DM_PASSWORD", "")
    DB_SCHEMA = os.environ.get("UTM_DM_SCHEMA", "ATC_DKWRJ_TEST")

class DmDbClient:
    """达梦数据库连接客户端

    支持作为模块被外部导入调用：
        from dmdbclient import DmDbClient, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_SCHEMA
        client = DmDbClient(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_SCHEMA)
        client.connect()
        data = client.query(table_name="uav_info", columns=["id", "name"])
        client.close()
    """

    def __init__(self, host=None, port=None, user=None, password=None, schema=None):
        """初始化客户端，参数为空时自动使用全局配置"""
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
            err_msg = str(e)
            print(f"[DmDbClient] 数据库连接失败: {e}")
            if "-70089" in err_msg or "Encryption module" in err_msg:
                print("[DmDbClient] 提示: 达梦加密模块需要 libssl.so.1.1 (OpenSSL 1.1)，"
                      "请确保 Docker 镜像已安装 libssl1.1 兼容库")
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

    def execute(self, sql):
        """执行自定义 SQL 语句

        Args:
            sql (str): SQL 语句

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
                print(f"[DmDbClient] 执行 SQL 成功，返回 {len(result)} 条记录")
                return result
            else:
                self.conn.commit()
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


def main():
    """脚本独立运行示例"""
    # 使用默认全局配置创建客户端
    client = DmDbClient()

    if client.connect():
        # 先查看表结构，确认真实字段名
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


if __name__ == "__main__":
    main()
