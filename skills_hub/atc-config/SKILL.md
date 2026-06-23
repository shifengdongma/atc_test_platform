---
name: atc-config
description: 低空空管系统配置文件检查和验证工具。当用户上传JSON配置文件、输入"配置dkkgsit"、"检查测试环境配置"、"sit测试环境"等关键词时调用此技能。根据环境信息自动填充和验证配置项。
---

# ATC配置检查技能

## 用途
帮助检查和验证低空空管系统的JSON配置文件，根据指定环境（如dkkgsit）自动填充正确的配置值。

## 触发条件
- 用户上传JSON配置文件
- 用户输入包含"配置"、"dkkgsit"、"检查配置"、"测试环境"、"sit环境"等关键词
- 用户需要验证或生成ATC系统配置

## 环境配置映射

### dkkgsit环境关键配置值

| 配置项 | 配置值 | 说明 |
|--------|--------|------|
| spring.datasource.url | jdbc:dm://10.165.32.32:5237?schema=ATC_DKWRJ_TEST | 达梦数据库地址 |
| spring.datasource.username | ATC_DKWRJ_TEST | 数据库用户 |
| spring.datasource.password | ATCdkwrj_123 | 数据库密码 |
| spring.redis.host (ops-mqtt) | redis-ops | redis-ops服务名（内网） |
| spring.redis.host (biz-backend) | redis-atc | redis-atc服务名（内网） |
| spring.redis.port | 6379 | Redis默认端口 |
| spring.redis.password (ops) | sN8^wA0^mM8^ | redis-ops密码 |
| spring.redis.password (atc) | s^mP2^qP7^sP | redis-atc密码 |
| spring.kafka.bootstrap-servers | kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 | 非核心业务Kafka |
| spring.elasticsearch.rest.uris | es-dkkgsit.dkkgsit-es:9200 | ES地址 |
| firmware.download-url-prefix | https://dkkgsit-test.testdolphin.com | 域名改为对应环境域名 |
| commons.oauth2.client.serverUri | http://dkkgsit-test.testdolphin.com/cloud-rbac | 统一权限地址 |
| commons.oauth2.client.serverInUri | http://cloud-rbac:8080 | 统一权限内网地址 |
| commons.oauth2.client.clientUri | https://dkkgsit-test.testdolphin.com | 客户端地址 |
| emqx.api.baseUrl | http://10.165.19.100:21083 | EMQX平台地址 |
| mqtt.broker.username | atc_ha | MQTT用户名 |
| mqtt.broker.password | atc_ha | MQTT密码 |
| mqtt.broker.url | tcp://10.165.19.100:21883 | MQTT连接地址（ops-mqtt） |
| mqtt.broker.url (ws/daemon) | tcp://10.165.33.127:20883 | MQTT连接地址（ws-backend/daemon） |
| feign.gis.url | http://dkkgsit-test.testdolphin.com/portal | GIS服务地址 |
| feign.gis.userName | atc_front | GIS服务用户名 |
| algorithm.service.urls | http://utm-conflicts-v3:8080 | 算法服务地址 |
| emqx.api.baseUrl (ops-server) | http://10.165.33.127:28083 | EMQX API地址（ops-server） |
| emqx.api.username | admin | EMQX API用户名 |
| emqx.api.password | s^iU4^dV7^xX | EMQX API密码 |

## 工作流程

### 1. 识别环境
当用户提及环境时，确定目标环境：
- **dkkgsit**: 混合云测试环境
- **sit**: SIT测试环境
- 其他自定义环境

### 2. 分析配置文件
如果用户上传了JSON配置文件：
1. 解析JSON结构
2. 识别所有配置项
3. 标记需要填充或检查的配置项

### 3. 配置检查清单

#### 数据库配置
- [ ] spring.datasource.url 是否正确
- [ ] spring.datasource.username 是否正确
- [ ] spring.datasource.password 是否正确

#### Redis配置
- [ ] spring.redis.host 是否指向正确的Redis实例
- [ ] spring.redis.port 是否正确
- [ ] spring.redis.password 是否正确

#### Kafka配置
- [ ] spring.kafka.bootstrap-servers 是否指向正确的Kafka集群
- [ ] 区分核心业务和非核心业务Kafka

#### Elasticsearch配置
- [ ] spring.elasticsearch.rest.uris 是否正确

#### EMQX/MQTT配置
- [ ] emqx.api.baseUrl 是否正确
- [ ] mqtt.broker.url 是否正确
- [ ] mqtt.broker.username 是否正确
- [ ] mqtt.broker.password 是否正确

#### 域名配置
- [ ] firmware.download-url-prefix 是否使用正确的二级域名
- [ ] commons.oauth2.client.serverUri 是否正确
- [ ] commons.oauth2.client.serverInUri 是否正确
- [ ] commons.oauth2.client.clientUri 是否正确

#### Redis连接池配置
- [ ] spring.redis.timeout 是否合理（建议3000ms）
- [ ] spring.redis.lettuce.pool.max-active 是否合理（建议8）
- [ ] spring.redis.lettuce.pool.max-idle 是否合理（建议8）
- [ ] spring.redis.lettuce.pool.min-idle 是否合理（建议0）
- [ ] spring.redis.lettuce.pool.max-wait 是否合理（建议-1ms）
- [ ] spring.redis.database 是否正确（la-atc-ops-mqtt使用9）

#### Kafka生产者配置
- [ ] spring.kafka.producer.key-serializer 是否为StringSerializer
- [ ] spring.kafka.producer.value-serializer 是否为StringSerializer
- [ ] spring.kafka.producer.acks 是否为all
- [ ] spring.kafka.producer.retries 是否合理（建议3）
- [ ] spring.kafka.producer.batch-size 是否合理（建议16384）
- [ ] spring.kafka.producer.buffer-memory 是否合理（建议33554432）

#### Kafka消费者配置
- [ ] spring.kafka.consumer.group-id 是否正确
- [ ] spring.kafka.consumer.key-deserializer 是否为StringDeserializer
- [ ] spring.kafka.consumer.value-deserializer 是否为StringDeserializer
- [ ] spring.kafka.consumer.enable-auto-commit 是否为false
- [ ] spring.kafka.consumer.auto-offset-reset 是否为latest
- [ ] spring.kafka.consumer.max-poll-records 是否合理（建议100）
- [ ] spring.kafka.listener.ack-mode 是否为manual
- [ ] spring.kafka.listener.concurrency 是否合理（建议3）

#### MQTT Broker配置
- [ ] mqtt.broker.client-id 是否正确
- [ ] mqtt.broker.keep-alive 是否合理（建议30）
- [ ] mqtt.broker.connection-timeout 是否合理（建议30）
- [ ] mqtt.broker.clean-session 是否为false
- [ ] mqtt.broker.automatic-reconnect 是否为true
- [ ] mqtt.broker.max-inflight 是否合理（建议1000）

#### MQTT线程池配置
- [ ] mqtt.message-executor.core-pool-size 是否合理（建议20）
- [ ] mqtt.message-executor.max-pool-size 是否合理（建议100）
- [ ] mqtt.message-executor.queue-capacity 是否合理（建议2000）
- [ ] mqtt.message-executor.keep-alive-seconds 是否合理（建议60）

#### 通用线程池配置
- [ ] thread-pool.core-pool-size 是否合理（建议10）
- [ ] thread-pool.max-pool-size 是否合理（建议50）
- [ ] thread-pool.queue-capacity 是否合理（建议1000）
- [ ] thread-pool.keep-alive-seconds 是否合理（建议60）
- [ ] thread-pool.thread-name-prefix 是否正确

#### 服务端口配置
- [ ] server.port 是否正确（建议8080）
- [ ] server.servlet.context-path 是否正确（建议/atc-mqtt）

#### 设备心跳配置
- [ ] device.heartbeat.interval 是否合理（建议30）
- [ ] device.heartbeat.offline-threshold 是否合理（建议90）

#### 设备认证配置
- [ ] device.auth.id-pattern 是否正确（建议^[A-Za-z0-9]{20}$）
- [ ] device.auth.default-password 是否正确

#### Kafka Topics配置检查
- [ ] kafka.topics.device-report 是否为atc-device-report
- [ ] kafka.topics.device-register 是否为atc-device-register
- [ ] kafka.topics.device-heartbeat 是否为atc-device-heartbeat
- [ ] kafka.topics.drone-data 是否为atc-drone-data
- [ ] kafka.topics.drone-data-resend 是否为atc-drone-data-resend
- [ ] kafka.topics.command-upgrade 是否为atc-command-upgrade
- [ ] kafka.topics.command-config 是否为atc-command-config
- [ ] kafka.topics.command-restart 是否为atc-command-restart
- [ ] kafka.topics.command-log 是否为atc-command-log
- [ ] kafka.topics.log-upload 是否为atc-log-upload

#### MQTT Topics配置检查
- [ ] mqtt.topics.dev-report 是否为atc/dev/report/+
- [ ] mqtt.topics.dev-control 是否为atc/dev/control/+
- [ ] mqtt.topics.device-register-up 是否为atc/dev/register/up
- [ ] mqtt.topics.device-register-down 是否为atc/dev/register/down
- [ ] mqtt.topics.device-heartbeat 是否为atc/wifi/heartBeat/+
- [ ] mqtt.topics.wifi-report 是否为atc/wifi/report/+
- [ ] mqtt.topics.wifi-control 是否为atc/wifi/control/+
- [ ] mqtt.topics.batch-upgrade 是否为atc/wifi/control/batch/upgrade
- [ ] mqtt.topics.log-upload 是否为atc/log/upload/+
- [ ] mqtt.topics.log-control 是否为atc/log/control/+
- [ ] mqtt.topics.drone-uav-status 是否为atc/drone/uavStatus/+
- [ ] mqtt.topics.drone-uav-resend 是否为atc/drone/uavResendStatus/+

#### 日志级别配置
- [ ] logging.level.root 是否为INFO
- [ ] logging.level.com.la.atc.mqtt 是否为DEBUG
- [ ] logging.level.org.springframework.integration.mqtt 是否为DEBUG

### 4. 输出结果

生成配置检查报告：

```markdown
## 配置检查报告 - [环境名称]

### 检查时间
[当前时间]

### 配置文件
[文件路径/名称]

### 检查结果摘要
- 通过项: X
- 需修改项: X
- 缺失项: X

### 详细检查项

#### 通过的配置
| 配置项 | 当前值 | 状态 |
|--------|--------|------|
| ... | ... | ✅ |

#### 需要修改的配置
| 配置项 | 当前值 | 建议值 | 说明 |
|--------|--------|--------|------|
| ... | ... | ... | ... |

#### 缺失的配置
| 配置项 | 建议值 | 说明 |
|--------|--------|------|
| ... | ... | ... |

### 建议操作
1. [具体操作建议]
2. [具体操作建议]
```

## 示例

### 示例1: 检查dkkgsit环境配置

用户: "帮我检查这个配置文件，dkkgsit环境的"

操作:
1. 读取用户上传的JSON配置文件
2. 对照dkkgsit环境信息
3. 检查每个配置项是否正确
4. 生成检查报告

### 示例2: 生成dkkgsit配置

用户: "给我生成dkkgsit的redis配置"

输出:
```json
{
  "spring": {
    "redis": {
      "host": "redis-ops",
      "port": 6379,
      "password": "sN8^wA0^mM8^"
    }
  }
}
```

## 服务与Redis实例对应关系

| 服务 | Redis实例 | Host | Port | Password | Database |
|------|-----------|------|------|----------|----------|
| la-atc-ops-mqtt | redis-ops | redis-ops | 6379 | sN8^wA0^mM8^ | 9 |
| la-atc-ops-server | redis-ops | redis-ops | 6379 | sN8^wA0^mM8^ | 9 |
| la-atc-biz-backend | redis-atc | redis-atc | 6379 | s^mP2^qP7^sP | - |
| la-atc-ws-backend | redis-atc | redis-atc | 6379 | s^mP2^qP7^sP | - |
| la-atc-daemon-server | redis-atc | redis-atc | 6379 | s^mP2^qP7^sP | 7 |

## MQTT配置差异

| 服务 | MQTT地址 | 用户名 | 密码 |
|------|----------|--------|------|
| la-atc-ops-mqtt | tcp://10.165.19.100:21883 | atc_ha | atc_ha |
| la-atc-ws-backend | tcp://10.165.33.127:20883 | atc/drone/uavStatus/1001 | public |
| la-atc-daemon-server | tcp://10.165.33.127:20883 | atc_ha | atc_ha |
| al-atc-data-exchange-mqtt | tcp://10.165.19.100:21883 | atc | atc |

## 数据库配置（达梦）

| 配置项 | 值 |
|--------|-----|
| spring.datasource.url | jdbc:dm://10.165.32.32:5237?useUnicode=true&schema=ATC_DKWRJ_TEST&characterEncoding=utf-8&serverTimezone=UTC&useSSL=false&autoReconnect=true&rewriteBatchedStatements=true |
| spring.datasource.username | ATC_DKWRJ_TEST |
| spring.datasource.password | ATCdkwrj_123 |
| spring.datasource.driver-class-name | dm.jdbc.driver.DmDriver |

## 注意事项

1. **密码安全**: 配置文件中包含敏感信息，注意保密
2. **环境区分**: 不同环境使用不同的配置值，务必确认当前目标环境
3. **Redis实例**: 系统使用多个Redis实例（redis-atc、redis-ops、redis-gis等），根据服务选择正确的实例
4. **Kafka集群**: 区分核心业务和非核心业务使用的Kafka集群
5. **MQTT地址差异**: 不同服务可能使用不同的MQTT Broker地址（10.165.19.100:21883 或 10.165.33.127:20883）
6. **EMQX API**: ops-server使用独立的EMQX API地址（10.165.33.127:28083）

## 参考文件

- 环境信息: `dkkgsit混合云环境信息.md`
- 配置项说明: `config_key.md`
