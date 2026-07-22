# -*- coding: utf-8 -*-
"""
sim_env_config 表重建脚本

自动检测并杀掉卡在 metadata lock 上的连接，然后 DROP + CREATE 新表。

用法: python database/rebuild_sim_env_config.py
"""
import sys, os
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, 'common'))

import pymysql
from config import load_mysql_config

_CREATE_SQL = """CREATE TABLE sim_env_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    redis_ip VARCHAR(128) DEFAULT '',
    redis_port VARCHAR(16) DEFAULT '6379',
    redis_pwd VARCHAR(128) DEFAULT '',
    kafka_url VARCHAR(256) DEFAULT '',
    kafka_url2 VARCHAR(256) DEFAULT '',
    is_default TINYINT DEFAULT 0,
    dm_host VARCHAR(128) DEFAULT '' COMMENT '达梦数据库地址',
    dm_port INT DEFAULT 5236 COMMENT '达梦数据库端口',
    dm_user VARCHAR(128) DEFAULT 'SYSDBA' COMMENT '达梦用户名',
    dm_password VARCHAR(128) DEFAULT '' COMMENT '达梦密码',
    dm_schema VARCHAR(128) DEFAULT '' COMMENT '达梦模式名',
    mysql_host VARCHAR(128) DEFAULT '' COMMENT 'MySQL地址',
    mysql_port INT DEFAULT 3306 COMMENT 'MySQL端口',
    mysql_user VARCHAR(128) DEFAULT '' COMMENT 'MySQL用户',
    mysql_password VARCHAR(128) DEFAULT '' COMMENT 'MySQL密码',
    mysql_database VARCHAR(128) DEFAULT '' COMMENT 'MySQL数据库名',
    atc_cluster_api VARCHAR(256) DEFAULT '' COMMENT '集群API地址',
    atc_vip VARCHAR(128) DEFAULT '' COMMENT 'ATC VIP地址',
    atc_node_a VARCHAR(128) DEFAULT '' COMMENT 'ATC A节点',
    atc_node_b VARCHAR(128) DEFAULT '' COMMENT 'ATC B节点',
    es_hosts VARCHAR(512) DEFAULT '' COMMENT 'ES地址(JSON)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仿真环境配置表'"""


def main():
    cfg = load_mysql_config()
    if not cfg.configured:
        print("❌ MySQL 未配置")
        return False

    print(f"连接 {cfg.host}:{cfg.port}/{cfg.database}")
    conn = pymysql.connect(
        host=cfg.host, port=cfg.port, user=cfg.user,
        password=cfg.password, database=cfg.database,
        charset=cfg.charset,
        connect_timeout=15, read_timeout=60, write_timeout=60,
    )
    cur = conn.cursor()
    cur.execute("SET SESSION lock_wait_timeout = 5")

    # ── 1. 杀掉 metadata lock 等待连接 ─────────────────────────
    cur.execute(
        "SELECT ID, USER, DB, COMMAND, TIME, STATE "
        "FROM information_schema.PROCESSLIST "
        "WHERE DB=%s AND ID != CONNECTION_ID()",
        (cfg.database,)
    )
    killed = 0
    for row in cur.fetchall():
        rid, ruser, rcmd, rtime, rstate = row[0], row[1], row[3], row[4], row[5]
        if rcmd == "Sleep":
            continue
        try:
            cur.execute(f"KILL {rid}")
            killed += 1
            print(f"  KILL {rid} ({rstate}, {rtime}s)")
        except Exception:
            pass
    if killed:
        print(f"已杀 {killed} 个卡死连接")
    else:
        print("无卡死连接")

    # ── 2. DROP ───────────────────────────────────────────────
    print("DROP TABLE sim_env_config ...")
    cur.execute("DROP TABLE IF EXISTS sim_env_config")
    print("  OK")

    # ── 3. CREATE ─────────────────────────────────────────────
    print("CREATE TABLE sim_env_config ...")
    cur.execute(_CREATE_SQL)
    conn.commit()
    print("  OK")

    # ── 4. 验证 ───────────────────────────────────────────────
    cur.execute("SHOW COLUMNS FROM sim_env_config")
    cols = [row[0] for row in cur.fetchall()]
    print(f"\n✅ sim_env_config 重建完成: {len(cols)} 列")

    conn.close()
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("sim_env_config 表重建")
    print("=" * 60)
    success = main()
    sys.exit(0 if success else 1)
