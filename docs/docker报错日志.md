============================================
 ATC/UTM 无人机模拟器 Web 控制台
 版本: unknown
 启动时间: 2026-07-14 17:51:16
============================================
[1/3] 检查运行环境...
  ✓ env.py 配置文件已挂载
  ✓ Python 3.11.15
[2/3] 连通性检测...
  ✓ Redis 可达 (dolphin-test.kedacom.com:21003)
  ✓ Kafka 可达 (10.165.19.213:30011)

=== 数据库配置诊断 ===
  [MySQL]
    ✓ UTM_MYSQL_HOST=10.165.32.147
    PORT=3306, DB=utm_simulator, USER=utm
  [达梦]
    UTM_DM_HOST=10.165.32.32, PORT=5237, SCHEMA=ATC_DKWRJ_TEST
    OpenSSL 1.1 库检测:
      ✓ libssl.so.1.1 已安装
      ✓ libcrypto.so.1.1 已安装
  [代码版本]
    ✓ json_data_manager.py: 包含 query_available_routes
=========================

[3/3] 启动 Web 控制台...
  监听地址: http://0.0.0.0:5000
============================================
  ✓ LD_PRELOAD 已设置 (OpenSSL 1.1 优先加载)
[web_server] async_mode=eventlet (os=posix)
/usr/local/lib/python3.11/site-packages/engineio/async_drivers/eventlet.py:1: EventletDeprecationWarning: 
Eventlet is deprecated. It is currently being maintained in bugfix mode, and
we strongly recommend against using it for new projects.

If you are already using Eventlet, we recommend migrating to a different
framework.  For more detail see
https://eventlet.readthedocs.io/en/latest/asyncio/migration.html

  from eventlet.green.threading import Event
utm_moc52 Web 服务启动: http://0.0.0.0:5000
  - 配置: Redis=dolphin-test.kedacom.com:21003
  - 配置: Kafka=10.165.19.213:30011
  按 Ctrl+C 停止服务
[config] _load_mysql_config: 从 env.py 加载 MySQL 配置 host=10.165.32.147, path=/app/utm_simulator/env.py
[config] _load_mysql_config: 环境变量覆盖 — host: 10.165.32.147 -> 10.165.32.147, port=3306, user=utm, password=***, database=utm_simulator
[config] _load_mysql_config: 最终 — host=10.165.32.147, port=3306, user=utm, database=utm_simulator, configured=True
[config] _load_mysql_config: 配置来源 — 环境变量 UTM_MYSQL_HOST
[mysql_db_manager] MySQL 配置: configured=True, host=10.165.32.147, port=3306, database=utm_simulator
[MysqlDbClient] 数据库连接失败: (1045, "Access denied for user 'utm'@'172.18.0.1' (using password: YES)")
[mysql_db_manager] MySQL 连接失败 (10.165.32.147:3306/utm_simulator)，降级到 SQLite
[DB] 表已就绪: sim_env_config
[DB] 表已就绪: sim_json_files
[DB] 表已就绪: sim_scheduled_tasks
[DB] 表已就绪: sim_task_logs
[DB] 表已就绪: sim_alarm_types
[json_data_manager] OpenSSL 1.1 库检测通过: libssl.so.1.1 + libcrypto.so.1.1 可用
[json_data_manager] _get_dm_client: 首次尝试达梦连接，LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/usr/lib:
[json_data_manager] _get_dm_client: 加载 dmdbclient.py from /app/database/../atc_api_autotest/api_tools/dmdbclient.py
[DmDbClient] 数据库连接失败: [CODE:-70089]Encryption module failed to load
[DmDbClient] 提示: 达梦加密模块需要 libssl.so.1.1 (OpenSSL 1.1)，请确保 Docker 镜像已安装 libssl1.1 兼容库