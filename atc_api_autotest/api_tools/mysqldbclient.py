#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MySQL 数据库连接客户端（纯客户端类，不包含项目配置）

项目 MySQL 配置请使用 common/config.py 的 load_mysql_config() 获取。
达梦数据库配置保持原有方式，在 dmdbclient.py 中不变。

用法:
    from common.config import load_mysql_config
    from mysqldbclient import MysqlDbClient

    cfg = load_mysql_config()
    client = MysqlDbClient(host=cfg.host, port=cfg.port, user=cfg.user,
                           password=cfg.password, database=cfg.database,
                           charset=cfg.charset)
"""

import pymysql


class MysqlDbClient:
    """MySQL 数据库连接客户端

    所有连接参数必须显式传入，不再从 env.py/环境变量隐秘读取。
    项目配置统一由 common/config.py 管理。

    用法:
        from common.config import load_mysql_config
        from mysqldbclient import MysqlDbClient
        cfg = load_mysql_config()
        client = MysqlDbClient(host=cfg.host, port=cfg.port, user=cfg.user,
                               password=cfg.password, database=cfg.database,
                               charset=cfg.charset)
        client.connect()
        data = client.query(table_name="sim_json_files", limit=5)
        client.close()
    """

    def __init__(self, host="127.0.0.1", port=3306, user="root",
                 password="", database="utm_simulator", charset="utf8mb4",
                 read_timeout=60, write_timeout=60):
        """初始化客户端。

        Args:
            host: MySQL 主机地址
            port: MySQL 端口
            user: 用户名
            password: 密码
            database: 数据库名
            charset: 字符集
            read_timeout: 读取超时秒数
            write_timeout: 写入超时秒数
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.conn = None
        self.cursor = None

    def connect(self):
        """建立数据库连接"""
        try:
            self.conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
                read_timeout=self.read_timeout,
                write_timeout=self.write_timeout,
            )
            self.cursor = self.conn.cursor()
            print(f"[MysqlDbClient] 成功连接到 MySQL {self.host}:{self.port}, 数据库: {self.database}")
            return True
        except Exception as e:
            print(f"[MysqlDbClient] 数据库连接失败: {e}")
            self.conn = None
            self.cursor = None
            return False

    def query(self, table_name, columns=None, where=None, limit=None):
        """通用查询方法

        Args:
            table_name (str): 表名
            columns (str/list/tuple, optional): 字段名，为 None 时查询所有字段（*）
            where (str, optional): WHERE 条件语句（不含 WHERE 关键字）
            limit (int, optional): 限制返回记录数

        Returns:
            list[dict]: 查询结果，每条记录为一个字典，key 为字段名
        """
        if not self.cursor:
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return None

        # 处理字段
        if columns is None:
            col_str = "*"
        elif isinstance(columns, (list, tuple)):
            col_str = ", ".join(str(c) for c in columns)
        else:
            col_str = str(columns)

        # 构建 SQL（MySQL 用反引号包裹表名，防止关键字冲突）
        sql = f"SELECT {col_str} FROM `{table_name}`"
        if where:
            sql += f" WHERE {where}"
        if limit is not None and isinstance(limit, int):
            sql += f" LIMIT {limit}"

        try:
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()
            print(f"[MysqlDbClient] 查询表: {table_name}, 返回 {len(rows)} 条记录")
            return rows
        except Exception as e:
            print(f"[MysqlDbClient] 查询失败: {e}")
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
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return None

        if columns is None:
            col_str = "*"
        elif isinstance(columns, (list, tuple)):
            col_str = ", ".join(str(c) for c in columns)
        else:
            col_str = str(columns)

        sql = f"SELECT {col_str} FROM `{table_name}`"
        if where:
            sql += f" WHERE {where}"
        if limit is not None and isinstance(limit, int):
            sql += f" LIMIT {limit}"

        try:
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()
            # DictCursor 返回的是 dict，转为 tuple
            if rows and isinstance(rows[0], dict):
                rows = [tuple(row.values()) for row in rows]
            print(f"[MysqlDbClient] 查询表: {table_name}, 返回 {len(rows)} 条记录")
            return rows
        except Exception as e:
            print(f"[MysqlDbClient] 查询失败: {e}")
            return None

    def get_table_columns(self, table_name):
        """获取指定表的所有字段名

        Args:
            table_name (str): 表名

        Returns:
            list[str]: 字段名列表
        """
        if not self.cursor:
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return None

        try:
            sql = (
                f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                f"WHERE TABLE_SCHEMA = '{self.database}' AND TABLE_NAME = '{table_name}'"
            )
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()
            columns = [row['COLUMN_NAME'] for row in rows]
            return columns
        except Exception as e:
            print(f"[MysqlDbClient] 获取表字段失败: {e}")
            return None

    def print_table_schema(self, table_name):
        """打印表结构信息

        Args:
            table_name (str): 表名
        """
        if not self.cursor:
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return

        try:
            sql = (
                f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, "
                f"IS_NULLABLE, COLUMN_COMMENT, COLUMN_DEFAULT "
                f"FROM INFORMATION_SCHEMA.COLUMNS "
                f"WHERE TABLE_SCHEMA = '{self.database}' AND TABLE_NAME = '{table_name}'"
            )
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()

            print(f"\n--- 表 {self.database}.{table_name} 的结构 ---")
            print(f"{'字段名':<20} {'类型':<15} {'长度':<8} {'可空':<6} {'默认值':<12} {'注释'}")
            print("-" * 90)
            for row in rows:
                col_name = row['COLUMN_NAME']
                data_type = row['DATA_TYPE']
                max_len = row['CHARACTER_MAXIMUM_LENGTH'] or '-'
                nullable = row['IS_NULLABLE']
                default = row['COLUMN_DEFAULT'] or '-'
                comment = row['COLUMN_COMMENT'] or ''
                print(f"{col_name:<20} {data_type:<15} {str(max_len):<8} {nullable:<6} {str(default):<12} {comment}")
            print("-" * 90)
        except Exception as e:
            print(f"[MysqlDbClient] 打印表结构失败: {e}")

    def execute(self, sql):
        """执行自定义 SQL 语句

        Args:
            sql (str): SQL 语句

        Returns:
            list[dict] / None: 查询结果字典列表，非查询语句返回 None
        """
        if not self.cursor:
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return None

        try:
            self.cursor.execute(sql)
            desc = self.cursor.description
            if desc:
                rows = self.cursor.fetchall()
                print(f"[MysqlDbClient] 执行 SQL 成功，返回 {len(rows)} 条记录")
                return rows
            else:
                self.conn.commit()
                print("[MysqlDbClient] 执行 SQL 成功")
                return None
        except Exception as e:
            print(f"[MysqlDbClient] SQL 执行失败: {e}")
            return None

    def insert(self, table_name, data):
        """插入单条记录

        Args:
            table_name (str): 表名
            data (dict): 要插入的数据，key 为字段名，value 为值

        Returns:
            int / None: 插入成功的自增 ID，失败返回 None
        """
        if not self.cursor:
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return None

        columns = ", ".join(f"`{k}`" for k in data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        values = list(data.values())
        sql = f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})"

        try:
            self.cursor.execute(sql, values)
            self.conn.commit()
            last_id = self.cursor.lastrowid
            print(f"[MysqlDbClient] 插入成功，自增 ID: {last_id}")
            return last_id
        except Exception as e:
            self.conn.rollback()
            print(f"[MysqlDbClient] 插入失败: {e}")
            return None

    def insert_many(self, table_name, data_list):
        """批量插入记录

        Args:
            table_name (str): 表名
            data_list (list[dict]): 要插入的数据列表

        Returns:
            int / None: 插入成功的行数，失败返回 None
        """
        if not self.cursor:
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return None

        if not data_list:
            print("[MysqlDbClient] 数据列表为空")
            return 0

        columns = ", ".join(f"`{k}`" for k in data_list[0].keys())
        placeholders = ", ".join(["%s"] * len(data_list[0]))
        values = [list(d.values()) for d in data_list]
        sql = f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})"

        try:
            affected = self.cursor.executemany(sql, values)
            self.conn.commit()
            print(f"[MysqlDbClient] 批量插入成功，影响行数: {affected}")
            return affected
        except Exception as e:
            self.conn.rollback()
            print(f"[MysqlDbClient] 批量插入失败: {e}")
            return None

    def update(self, table_name, data, where):
        """更新记录

        Args:
            table_name (str): 表名
            data (dict): 要更新的字段和值
            where (str): WHERE 条件（不含 WHERE 关键字）

        Returns:
            int / None: 影响行数，失败返回 None
        """
        if not self.cursor:
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return None

        set_clause = ", ".join(f"`{k}` = %s" for k in data.keys())
        values = list(data.values())
        sql = f"UPDATE `{table_name}` SET {set_clause} WHERE {where}"

        try:
            affected = self.cursor.execute(sql, values)
            self.conn.commit()
            print(f"[MysqlDbClient] 更新成功，影响行数: {affected}")
            return affected
        except Exception as e:
            self.conn.rollback()
            print(f"[MysqlDbClient] 更新失败: {e}")
            return None

    def delete(self, table_name, where):
        """删除记录

        Args:
            table_name (str): 表名
            where (str): WHERE 条件（不含 WHERE 关键字）

        Returns:
            int / None: 影响行数，失败返回 None
        """
        if not self.cursor:
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return None

        sql = f"DELETE FROM `{table_name}` WHERE {where}"

        try:
            affected = self.cursor.execute(sql)
            self.conn.commit()
            print(f"[MysqlDbClient] 删除成功，影响行数: {affected}")
            return affected
        except Exception as e:
            self.conn.rollback()
            print(f"[MysqlDbClient] 删除失败: {e}")
            return None

    def show_tables(self):
        """查看当前数据库中所有表

        Returns:
            list[str]: 表名列表
        """
        if not self.cursor:
            print("[MysqlDbClient] 数据库未连接，请先调用 connect()")
            return None

        try:
            sql = f"SHOW TABLES"
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()
            tables = [list(row.values())[0] for row in rows]
            print(f"[MysqlDbClient] 数据库 {self.database} 共 {len(tables)} 张表")
            return tables
        except Exception as e:
            print(f"[MysqlDbClient] 获取表列表失败: {e}")
            return None

    def close(self):
        """关闭数据库连接"""
        if self.cursor:
            self.cursor.close()
            self.cursor = None
        if self.conn:
            self.conn.close()
            self.conn = None
        print("[MysqlDbClient] 数据库连接已关闭")

    def __enter__(self):
        """支持 with 语句"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句自动关闭"""
        self.close()


def main():
    """脚本独立运行示例"""
    client = MysqlDbClient()

    if client.connect():
        # 查看所有表
        print("\n--- 当前数据库中的表 ---")
        tables = client.show_tables()
        if tables:
            for t in tables:
                print(f"  - {t}")

            # 查看第一张表的结构
            first_table = tables[0]
            client.print_table_schema(first_table)

            # 查询示例
            print(f"\n--- 查询 {first_table} 前 5 条数据 ---")
            data = client.query(table_name=first_table, limit=5)
            if data:
                for row in data:
                    print(row)

        client.close()


if __name__ == "__main__":
    main()
