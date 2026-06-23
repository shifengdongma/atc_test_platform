# dkkgdev环境信息
# ElasticSearch
es_hosts = ["10.165.76.41:20909"]

# kafka（参考 env.py 风格，默认走 VIP，支持 A/B 节点切换）
#kafka_url = "10.165.26.246:29092"
kafka_url = "10.165.77.69:30012"

# redis-hx（参考 env.py 风格，默认走 VIP，支持 A/B 节点切换）
redis_ip = "10.165.78.1"
redis_port = "21002"
redis_password = "ssJ5^vC7^aC3"

# 达梦数据库
# 达梦数据库系统用户	dmdba	Kedacom123
# 数据库管理员	SYSDBA	Kedacom#123
# 数据库审计员	SYSAUDITOR	Kedacom#123
# A集群数据库
dm_a_host = "10.165.32.32"          # 数据库地址
dm_a_port = 5237                    # 数据库端口
dm_a_user = "SYSDBA"                # 用户名
dm_a_password = "Kedacom123"        # 密码
dm_a_schema = "ATC_DKWRJ_DEV"      # 默认模式


