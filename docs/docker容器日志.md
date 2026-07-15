[root@localhost ~]# docker exec utm-simulator python3 -c "import pymysql; print(pymysql.__version__)"
2.2.8
[root@localhost ~]# docker exec utm-simulator python3 -c "import sys; sys.path.insert(0,'/app/atc_api_autotest/api_tools'); from mysqldbclient import MysqlDbClient; print('OK')"
OK
[root@localhost ~]# docker exec utm-simulator python3 -c "import sys; sys.path.insert(0,'/app/common'); from config import load_mysql_config; c=load_mysql_config(); print('host=%s port=%s user=%s db=%s configured=%s'%(c.host,c.port,c.user,c.database,c.configured))"
[config] _load_mysql_config: 从 env.py 加载 MySQL 配置 host=10.165.32.147, path=/app/utm_simulator/env.py
[config] _load_mysql_config: 环境变量覆盖 — host: 10.165.32.147 -> 10.165.32.147, port=3306, user=utm, password=***, database=utm_simulator
[config] _load_mysql_config: 最终 — host=10.165.32.147, port=3306, user=utm, database=utm_simulator, configured=True
[config] _load_mysql_config: 配置来源 — 环境变量 UTM_MYSQL_HOST
host=10.165.32.147 port=3306 user=utm db=utm_simulator configured=True
[root@localhost ~]# docker exec utm-simulator timeout 5 bash -c "echo >/dev/tcp/10.165.32.147/3306 && echo TCP可达 || echo TCP不可达"
TCP可达
[root@localhost ~]# docker exec utm-simulator python3 -c "import pymysql; c=pymysql.connect(host='10.165.32.147',port=3306,user='utm',password='<密码>',database='utm_simulator',connect_timeout=5); print('MySQL OK'); c.close()"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/usr/local/lib/python3.11/site-packages/pymysql/connections.py", line 312, in __init__
    self.password = self.password.encode("latin1")
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
UnicodeEncodeError: 'latin-1' codec can't encode characters in position 1-2: ordinal not in range(256)
[root@localhost ~]# docker exec utm-simulator python3 -c "import pymysql; c=pymysql.connect(host='10.165.32.147',port=3306,user='utm',password='<密码>',database='utm_simulator',ssl={'ssl':{}},connect_timeout=5); print('MySQL OK'); c.close()"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/usr/local/lib/python3.11/site-packages/pymysql/connections.py", line 312, in __init__
    self.password = self.password.encode("latin1")
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
UnicodeEncodeError: 'latin-1' codec can't encode characters in position 1-2: ordinal not in range(256)
[root@localhost ~]# docker exec utm-simulator hostname -I
172.19.0.2 172.18.0.7 
[root@localhost ~]# docker exec utm-simulator python3 -c "import sys; sys.path.insert(0,'/app'); sys.path.insert(0,'/app/database'); import mysql_db_manager; mysql_db_manager.init_tables(); rows=mysql_db_manager.query_all('sim_json_files'); print('sim_json_files:',len(rows),'rows')"
[config] _load_mysql_config: 从 env.py 加载 MySQL 配置 host=10.165.32.147, path=/app/utm_simulator/env.py
[config] _load_mysql_config: 环境变量覆盖 — host: 10.165.32.147 -> 10.165.32.147, port=3306, user=utm, password=***, database=utm_simulator
[config] _load_mysql_config: 最终 — host=10.165.32.147, port=3306, user=utm, database=utm_simulator, configured=True
[config] _load_mysql_config: 配置来源 — 环境变量 UTM_MYSQL_HOST
[mysql_db_manager] MySQL 配置: host=10.165.32.147, port=3306, database=utm_simulator
[MysqlDbClient] 数据库连接失败: (1045, "Access denied for user 'utm'@'172.18.0.1' (using password: YES)")
[mysql_db_manager] MySQL 连接失败 (10.165.32.147:3306/utm_simulator)
sim_json_files: 0 rows
[root@localhost ~]# 