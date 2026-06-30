'''

"""atctest环境变量"""
redis_ip = "dolphin-test.kedacom.com"
redis_port = "21103"
redis_password = "s4^dJ5^xM6^e"
kafka_url = "10.165.19.213:30092"

'''
"""dkkgsit环境变量"""
redis_ip = "dolphin-test.kedacom.com"
redis_port = "21003"
redis_password = "s4^dJ5^xM6^e"
kafka_url = "10.165.19.213:30011"
# 非空时，生产者向 kafka_url 发送的同批消息会同步写入该集群（消费者仍只用 kafka_url）
kafka_url2 = ""
