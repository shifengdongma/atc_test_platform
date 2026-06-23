# 低空平台配置
BASE_URL = "https://dkkgsit-test.testdolphin.com"

# 达梦数据库配置
DB_HOST = "10.165.32.32"
DB_PORT = 5237
DB_USER = "SYSDBA"
DB_PASSWORD = "Kedacom123"
DB_SCHEMA = "ATC_DKWRJ_TEST"
# DB_SCHEMA = "ATC_DKWRJ_DEV"

# Redis 配置
redis_ip = "dolphin-test.kedacom.com"
redis_port = "21003"
redis_password = "s4^dJ5^xM6^e"

# hx_Kafka 配置
kafka_url = "10.165.19.213:30011"
# 非空时，生产者向 kafka_url 发送的同批消息会同步写入该集群（消费者仍只用 kafka_url）
kafka_url2 = ""

