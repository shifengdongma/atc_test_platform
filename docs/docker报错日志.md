[root@localhost ~]# docker exec utm-simulator python3 -c "import sys; sys.path.insert(0,'/app'); sys.path.insert(0,'/app/database'); import mysql_db_manager; mysql_db_manager.init_tables(); rows=mysql_db_manager.query_all('sim_json_files'); print('sim_json_files:',len(rows),'rows')"
[config] _load_mysql_config: 从 env.py 加载 MySQL 配置 host=10.165.32.147, path=/app/utm_simulator/env.py
[config] _load_mysql_config: 环境变量覆盖 — host: 10.165.32.147 -> 10.165.32.147, port=3306, user=utm, password=***, database=utm_simulator
[config] _load_mysql_config: 最终 — host=10.165.32.147, port=3306, user=utm, database=utm_simulator, configured=True
[config] _load_mysql_config: 配置来源 — 环境变量 UTM_MYSQL_HOST
[mysql_db_manager] MySQL 配置: host=10.165.32.147, port=3306, database=utm_simulator
[MysqlDbClient] 数据库连接失败: 'cryptography' package is required for sha256_password or caching_sha2_password auth methods
[mysql_db_manager] MySQL 连接失败 (10.165.32.147:3306/utm_simulator)
sim_json_files: 0 rows
[root@localhost ~]# 