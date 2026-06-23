import time
from datetime import datetime, timedelta
from kafka import KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import KafkaError
from kafka.structs import TopicPartition

# 配置项
# Kafka服务器地址列表
KAFKA_SERVERS = [
    '10.165.32.24:29092',  # 第一个Kafka地址
    '10.165.32.25:29092'   # 第二个Kafka地址
]

# 每个Kafka服务器对应的两个topic名称
TOPICS_PER_KAFKA = [
    ['uav_runtime_data', 'uav_runtime_trace'],  # 第一个Kafka的两个topic
    ['uav_runtime_data', 'uav_runtime_trace']   # 第二个Kafka的两个topic
]

# 查询时间范围（分钟）
QUERY_TIME_RANGE = 3

def get_kafka_ip_last_octet(server):
    """获取Kafka服务器IP的最后一位"""
    if ':' in server:
        ip = server.split(':')[0]
        if '.' in ip:
            return ip.split('.')[-1]
    return server

def check_topic_has_new_data(server, topic, start_time):
    """检查指定 topic 在指定时间范围内是否有新数据，并返回新增数量和最新时间"""
    try:
        # 创建消费者（不在构造函数中订阅 topic）
        consumer = KafkaConsumer(
            bootstrap_servers=[server],
            auto_offset_reset='earliest',  # 从最早的消息开始
            enable_auto_commit=False,
            consumer_timeout_ms=5000
        )
        
        # 获取 topic 的分区信息
        partitions = consumer.partitions_for_topic(topic)
        if not partitions:
            consumer.close()
            return False, 0, '无'
        
        # 统计新增数据数量
        new_data_count = 0
        latest_timestamp = None
        start_timestamp_ms = int(start_time * 1000)  # 转换为毫秒
        
        # 遍历所有分区
        for partition in partitions:
            tp = TopicPartition(topic, partition)
            
            # 分配分区
            consumer.assign([tp])
            
            # 获取该分区的最新 offset
            end_offset = consumer.end_offsets([tp])[tp]
            
            # 如果分区为空，跳过
            if end_offset == 0:
                continue
            
            # 从最新的 100 条消息开始查找
            start_offset = max(0, end_offset - 100)
            consumer.seek(tp, start_offset)
            
            # 消费消息
            msgs = consumer.poll(timeout_ms=2000, max_records=100)
            
            for message in msgs.get(tp, []):
                # 检查消息时间戳
                if message.timestamp >= start_timestamp_ms:
                    new_data_count += 1
                    # 记录最新的时间戳
                    if latest_timestamp is None or message.timestamp > latest_timestamp:
                        latest_timestamp = message.timestamp
        
        consumer.close()
        
        # 将毫秒时间戳转换为秒
        latest_time_str = datetime.fromtimestamp(latest_timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S') if latest_timestamp else '无'
        
        return new_data_count > 0, new_data_count, latest_time_str
        
    except KafkaError as e:
        print(f"Error checking topic {topic} on {server}: {e}")
        return False, 0, '无'

def main():
    # 计算查询开始时间（当前时间前 N 分钟）
    current_time = datetime.now()
    start_time = current_time - timedelta(minutes=QUERY_TIME_RANGE)
    start_timestamp = start_time.timestamp()
    
    print("=" * 180)
    print(f"查询时间：{start_time.strftime('%Y-%m-%d %H:%M:%S')} 至 {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"最后一天数据时间：{(current_time - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 180)
    print("Kafka   | Topic1           | 数量 1 | 最新时间 1       | Topic2           | 数量 2 | 最新时间 2       | 新增")
    print("-" * 180)
    
    # 遍历每个 Kafka 服务器
    for i, server in enumerate(KAFKA_SERVERS):
        if i >= len(TOPICS_PER_KAFKA):
            continue
        
        topics = TOPICS_PER_KAFKA[i]
        if len(topics) < 2:
            continue
        
        topic1, topic2 = topics[0], topics[1]
        
        # 检查每个 topic 是否有新数据
        has_data_topic1, count_topic1, latest_time_topic1 = check_topic_has_new_data(server, topic1, start_timestamp)
        has_data_topic2, count_topic2, latest_time_topic2 = check_topic_has_new_data(server, topic2, start_timestamp)
        
        # 判断是否有新增数据
        has_new_data = has_data_topic1 or has_data_topic2
        
        # 获取 Kafka 服务器标识（使用完整 IP 地址）
        kafka_server_name = f"kafka{get_kafka_ip_last_octet(server)}"
        
        # 输出结果
        print(f"{kafka_server_name:<7} | {topic1:<16} | {count_topic1:>6} | {latest_time_topic1:>18} | {topic2:<16} | {count_topic2:>6} | {latest_time_topic2:>18} | {'是' if has_new_data else '否':>4}")

if __name__ == "__main__":
    main()
