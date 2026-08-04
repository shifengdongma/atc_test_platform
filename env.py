'''

"""atctest环境变量"""
# ATC IOMP API 基础地址 — 用于 JWT Token 获取和告警详情查询
BASE_URL = "https://dkkgsit-test.testdolphin.com"
redis_ip = "dolphin-test.kedacom.com"
redis_port = "21003"
redis_password = "s4^dJ5^xM6^e"
kafka_url = "10.165.19.213:30011"

'''
# ATC IOMP API 基础地址 — 用于 JWT Token 获取和告警详情查询
BASE_URL = "https://dkkgsit-test.testdolphin.com"

"""dkkgsit环境变量"""
redis_ip = "dolphin-test.kedacom.com"
redis_port = "21003"
redis_password = "s4^dJ5^xM6^e"
kafka_url = "10.165.19.213:30011"
# 非空时，生产者向 kafka_url 发送的同批消息会同步写入该集群（消费者仍只用 kafka_url）
kafka_url2 = ""

# MySQL 持久化配置 — 存储本项目产生的配置、JSON文件、任务日志
# 与 atc_api_autotest/env.py（ATC测试数据库）是两套不同的数据库
MYSQL_HOST = "10.165.32.147"
MYSQL_PORT = 3306
MYSQL_USER = "utm"
MYSQL_PASSWORD = "eEkJ3GfJ3Pt8iH5r"
MYSQL_DATABASE = "utm_simulator"
MYSQL_CHARSET = "utf8mb4"

# ── ATC 集群配置 ──────────────────────────────────────────────────
cluster_api = "https://10.165.26.246/dolphin-agent/cluster.txt"
atc_vip = "10.165.26.246"
atc_a = "10.165.26.119"
atc_b = "10.165.26.139"

# ── IOMP 海豚部署 (A/B) ──────────────────────────────────────────
iomp_ip_a = "10.165.26.119"
iomp_port_a = 8801
ACCESS_KEY_a = "a5ip23kn3szen5bq"
iomp_a = f"http://{iomp_ip_a}:{iomp_port_a}/iomp/#/"

iomp_ip_b = "10.165.26.139"
iomp_port_b = 8801
ACCESS_KEY_b = "yp1yl2ujis29mwrs"
iomp_b = f"http://{iomp_ip_b}:{iomp_port_b}/iomp/#/"

# ── DOPS 海豚运维 ─────────────────────────────────────────────────
dops_a = "https://10.165.26.119/dops"
dops_b = "https://10.165.26.139/dops"

# ── ElasticSearch ─────────────────────────────────────────────────
es_hosts = ['10.165.26.119:29200', '10.165.26.139:29200']

# ── Kafka A/B 节点 ────────────────────────────────────────────────
kafka_url_a = "10.165.26.119:39092"
kafka_url_b = "10.165.26.139:39092"

# ── Redis A/B 节点 ────────────────────────────────────────────────
redis_ip_a = "10.165.26.119"
redis_port_a = "6379"
redis_password_a = "sN1^tG1^rI3^"
redis_ip_b = "10.165.26.139"
redis_port_b = "6379"
redis_password_b = "suK1^nS4^jX5"

# ── 达梦数据库 ────────────────────────────────────────────────────
dm_vip = "10.165.32.217"
dm_a_host = "10.165.32.217"
dm_a_port = 5236
dm_a_user = "SYSDBA"
dm_a_password = "Kedacom123"
dm_a_schema = "ATC_DKWRJ_TEST"
dm_b_host = "10.165.32.217"
dm_b_port = 5236
dm_b_user = "SYSDBA"
dm_b_password = "Kedacom123"
dm_b_schema = "ATC_DKWRJ_TEST"

dm_alt_host = "10.165.32.217"
dm_alt_port = 5236

# ── 兼容旧 dmdbclient.py 的达梦别名 ─────────────────────────────────
DB_HOST = "10.165.32.217"
DB_PORT = 5236
DB_USER = "SYSDBA"
DB_PASSWORD = "Kedacom123"
DB_SCHEMA = "ATC_DKWRJ_TEST"
