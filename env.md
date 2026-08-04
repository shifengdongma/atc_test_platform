# cluster_api
cluster_api = "https://10.165.26.246/dolphin-agent/cluster.txt"
# vip地址
atc_vip = "10.165.26.246"
atc_a = "10.165.26.119"
atc_b = "10.165.26.139"

#海豚部署  #wuweibin Kedacom@123  admin/kedacom123#
iomp_ip_a = "10.165.26.119"
iomp_port_a = 8801
ACCESS_KEY_a = "a5ip23kn3szen5bq" # 海豚部署访问密钥
iomp_a = f"http://{iomp_ip_a}:{iomp_port_a}/iomp/#/"

iomp_ip_b = "10.165.26.139"
iomp_port_b = 8801
ACCESS_KEY_b = "yp1yl2ujis29mwrs"  # 海豚部署访问密钥
iomp_b = f"http://{iomp_ip_b}:{iomp_port_b}/iomp/#/"

# 海豚运维
dops_a = "https://10.165.26.119/dops"  # admin/xo49@g7mm1rg
dops_b = "https://10.165.26.139/dops"  # admin/@65vkczt7jfx

# ElasticSearch
es_hosts = ["10.165.26.119:29200", "10.165.26.139:29200"]

# kafka（参考 env.py 风格，默认走 VIP，支持 A/B 节点切换）
#kafka_url = "10.165.26.246:29092"
kafka_url_a = "10.165.26.119:39092"
kafka_url_b = "10.165.26.139:39092"

# redis-hx（参考 env.py 风格，默认走 VIP，支持 A/B 节点切换）
redis_ip_a = "10.165.26.119"
redis_port_a = "26379"
redis_password_a = "sN1^tG1^rI3^"
redis_ip_b = "10.165.26.139"
redis_port_b = "26379"
redis_password_b = "suK1^nS4^jX5"

# 达梦数据库
dm_vip = "10.165.32.217" #
# 达梦数据库系统用户        dmdba        Kedacom123
# 数据库管理员        SYSDBA        Kedacom123
# 数据库审计员        SYSAUDITOR        Kedacom123
# A集群数据库
dm_a_host = "10.165.32.217"          # 数据库地址,配置环境119 A集群
dm_a_port = 5236                    # 数据库端口,配置环境119 A集群
dm_a_user = "SYSDBA"                # 用户名,配置环境119 A集群
dm_a_password = "Kedacom123"        # 密码,配置环境119 A集群
dm_a_schema = "ATC_DKWRJ_TEST"      # 默认模式,配置环境119 A集群
# B集群数据库
dm_b_host = "10.165.32.217"          # 数据库地址,配置环境139 B集群
dm_b_port = 5236                    # 数据库端口,配置环境139 B集群
dm_b_user = "SYSDBA"                # 用户名,配置环境139 B集群
dm_b_password = "Kedacom123"        # 密码,配置环境139 B集群
dm_b_schema = "ATC_DKWRJ_TEST"      # 默认模式,配置环境139 B集群    

