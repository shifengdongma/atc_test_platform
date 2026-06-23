# ATC配置检查技能 - 详细参考

## 环境配置详情

### dkkgsit 混合云环境

#### 空间信息
- 空间名称：dkkgsit
- 部署平台地址：https://ctsp.kedacom.com/iomp
- 存储名称：nfs-dkkgsit
- TCP网关：dol-ingress-tcp:dp
- HTTP网关：dol-ingress-kedacom:dp
- 运维平台地址：https://dolphin-test.kedacom.com/dops/
- 二级域名：dkkgsit-test.testdolphin.com

#### Kafka 配置

**1. 非核心业务使用的Kafka**
- 空间：dkkgsit-kafka
- 服务名：kafka-dkkgsit
- 集群服务地址：kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092
- 外网地址：10.165.19.227:30123

**2. 核心业务使用的Kafka**
- 核心服务使用空间：dkhx-kafka
- 核心服务使用空间：kafka-dkhx
- 集群服务地址：kafka-dkhx-0.kafka-dkhx.dkhx-kafka:9092

#### Elasticsearch 配置
- 空间：dkkgsit-es
- 服务名：es-dkkgsit
- 版本：7.8.1
- 集群服务地址：es-dkkgsit.dkkgsit-es:9200

#### Redis 配置

**1. 低空空管 redis-atc**
- 项目空间：dkkgsit
- 项目名称：redis-atc
- redis版本：7.0.8
- 内存：256
- 密码：s^mP2^qP7^sP
- 外网地址：dolphin-test.kedacom.com:21001

**2. 低空运维 redis-ops**
- 项目空间：dkkgsit
- 项目名称：redis-ops
- redis版本：7.0.8
- 内存：256
- 密码：sN8^wA0^mM8^
- 外网地址：dolphin-test.kedacom.com:21002

**3. 低空地图 redis-gis**
- 项目空间：dkkgsit
- 项目名称：redis-gis
- redis版本：7.0.8
- 内存：256
- 密码：s6^oS2^vW9^j

**4. 低空守护 redis-daemon**
- 项目空间：dkkgsit
- 项目名称：redis-daemon
- redis版本：7.0.8
- 内存：256
- 密码：saP4^jA1^fD6

**5. 算法 redis-utm**
- 项目空间：dkkgsit
- 项目名称：redis-utm
- redis版本：7.0.8
- 内存：256
- 密码：s^eH2^uB4^oR

#### EMQX 配置
- MQTT协议连接地址：mqtt://10.165.19.100:21883
- WS协议连接地址：ws://10.165.19.100:21884
- 平台地址：http://10.165.19.100:21083
- 平台账号：admin
- 平台密码：s^pM4^dV9^uA
- 公网ip：180.101.84.6，端口：21883 和 28883
- tcp://180.101.84.6:21883 (用于wifi接收器)
- UDP：180.101.84.6：28883 (用于ADS-B测试)

#### 项目部署地址

**1. 统一权限**
- 地址：https://dkkgsit-test.testdolphin.com/cloud-rbac/
- 管理员账号：rbac
- 管理员密码：123456
- 注：如果使用达梦数据，需要执行以下操作
  - ALTER TABLE "f_error_code" MODIFY "explanation" VARCHAR2(512);
  - 并删除flyway_schema_history的最后一条success=0的记录，再重启cloud-rbac

**2. 低空空管自动化系统**
- 地址：https://dkkgsit-test.testdolphin.com/atc/login
- 账号：atcAdmin
- 密码：atcAdmin_123

**3. 地图**
- 地址：https://dkkgsit-test.testdolphin.com/portal/kgis-cloud/#/home
- 管理员账号：kgis_admin
- 管理员密码：kedacom123
- 低空账号：atc_front
- 低空密码：kedacom123

#### MinIO 配置
- 平台地址：http://10.165.19.100:20902/
- 账号：admin
- 密码：kedacom123

---

## 配置项映射表

### 完整配置映射

| 配置Key | 对应环境值 (dkkgsit) | 数据来源 |
|---------|---------------------|----------|
| spring.datasource.url | - | 需用户指定 |
| spring.datasource.username | - | 需用户指定 |
| spring.datasource.password | - | 需用户指定 |
| spring.redis.host (ops-mqtt) | redis-ops | redis-ops服务名（内网） |
| spring.redis.host (biz-backend) | redis-atc | redis-atc服务名（内网） |
| spring.redis.port | 6379 | Redis默认端口 |
| spring.redis.password (ops) | sN8^wA0^mM8^ | redis-ops密码 |
| spring.redis.password (atc) | s^mP2^qP7^sP | redis-atc密码 |
| spring.kafka.bootstrap-servers | kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 | 非核心业务Kafka |
| spring.elasticsearch.rest.uris | es-dkkgsit.dkkgsit-es:9200 | ES集群服务地址 |
| firmware.download-url-prefix | https://dkkgsit-test.testdolphin.com | 二级域名 |
| commons.oauth2.client.serverUri | http://dkkgsit-test.testdolphin.com/cloud-rbac | 统一权限地址 |
| commons.oauth2.client.serverInUri | http://cloud-rbac:8080 | 统一权限内网地址 |
| commons.oauth2.client.clientUri | https://dkkgsit-test.testdolphin.com | 二级域名 |
| feign.gis.url | http://dkkgsit-test.testdolphin.com/portal | GIS服务地址 |
| algorithm.service.urls | http://utm-conflicts-v3:8080 | 算法服务地址 |
| emqx.api.baseUrl | http://10.165.19.100:21083 | EMQX平台地址 |
| spring.redis.host (ops) | dolphin-test.kedacom.com | redis-ops |
| spring.redis.port (ops) | 21002 | redis-ops端口 |
| spring.redis.password (ops) | sN8^wA0^mM8^ | redis-ops密码 |
| spring.kafka.bootstrap-servers (core) | kafka-dkhx-0.kafka-dkhx.dkhx-kafka:9092 | 核心业务Kafka |
| mqtt.broker.username | atc_ha | MQTT用户名 |
| mqtt.broker.password | atc_ha | MQTT密码 |
| mqtt.broker.url | tcp://10.165.19.100:21883 | MQTT协议连接地址 |

---

## 服务与Redis实例对应关系

| 服务 | Redis实例 | 地址 | 端口 | 密码 |
|------|-----------|------|------|------|
| la-atc-ops-mqtt | redis-ops | redis-ops | 6379 | sN8^wA0^mM8^ |
| la-atc-ops-server | redis-ops | redis-ops | 6379 | sN8^wA0^mM8^ |
| la-atc-biz-backend | redis-atc | redis-atc | 6379 | s^mP2^qP7^sP |
| la-atc-ws-backend | redis-atc | redis-atc | 6379 | s^mP2^qP7^sP |
| la-atc-daemon-server | redis-atc | redis-atc | 6379 | s^mP2^qP7^sP |
| 地图服务 | redis-gis | - | - | s6^oS2^vW9^j |
| 守护服务 | redis-daemon | - | - | saP4^jA1^fD6 |
| 算法服务 | redis-utm | - | - | s^eH2^uB4^oR |

---

## 服务特定配置

### la-atc-biz-backend 服务配置

#### 数据库配置（达梦）
| 配置项 | 值 |
|--------|-----|
| spring.datasource.url | jdbc:dm://10.165.32.32:5237?useUnicode=true&schema=ATC_DKWRJ_TEST&characterEncoding=utf-8&serverTimezone=UTC&useSSL=false&autoReconnect=true&rewriteBatchedStatements=true |
| spring.datasource.username | ATC_DKWRJ_TEST |
| spring.datasource.password | ATCdkwrj_123 |
| spring.datasource.driver-class-name | dm.jdbc.driver.DmDriver |

#### Redis配置
| 配置项 | 值 |
|--------|-----|
| spring.redis.host | redis-atc |
| spring.redis.port | 6379 |
| spring.redis.password | s^mP2^qP7^sP |

#### Elasticsearch配置
| 配置项 | 值 |
|--------|-----|
| spring.elasticsearch.rest.uris | http://es-dkkgsit.dkkgsit-es:9200 |
| spring.data.elasticsearch.cluster-nodes | es-dkkgsit.dkkgsit-es:9200 |

#### Kafka配置
| 配置项 | 值 |
|--------|-----|
| spring.kafka.bootstrap-servers | kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 |
| spring.kafka.secondary.servers.uav_runtime_data.topic | uav_runtime_data |
| spring.kafka.secondary.servers.uav_resend_data.topic | uav_resend_data |
| spring.kafka.secondary.servers.uav_runtime_data.consumer.group-id | atctest-biz-backend |
| spring.kafka.secondary.servers.uav_resend_data.consumer.group-id | atctest-biz-backend |

#### GIS/地图服务配置
| 配置项 | 值 |
|--------|-----|
| feign.gis.url | http://dkkgsit-test.testdolphin.com/portal |
| feign.gis.userName | atc_front |
| feign.gis.secretKey | 6d19783959d9469b9ea2c6cb1b225369 |
| gis.version | V3.0.0 |
| atc.synCTServer.appName | atc_front |
| atc.synCTServer.landingSite.serviceName | atc_landing_site_test |

#### 算法服务配置
| 配置项 | 值 |
|--------|-----|
| algorithm.service.urls | http://utm-conflicts-v3:8080 |
| algorithm.detect.service.url | http://utm-conflicts-v3:8080 |
| algorithm.service.switch.enabled | true |

#### OAuth2认证配置
| 配置项 | 值 |
|--------|-----|
| commons.oauth2.client.serverUri | http://dkkgsit-test.testdolphin.com/cloud-rbac |
| commons.oauth2.client.serverInUri | http://cloud-rbac:8080 |
| commons.oauth2.client.clientUri | https://dkkgsit-test.testdolphin.com/la-atc-biz-backend |
| commons.oauth2.client.client_id | la-atc-biz-backend |
| commons.oauth2.client.clientSecret | ZDW2YRYB37bt |
| commons.oauth2.client.username | atcAdmin |
| commons.oauth2.client.password | atcAdmin_123 |
| commons.oauth2.client.serverName | cloud-rbac |
| commons.oauth2.client.jwtEnable | true |
| common.auth.serverUri | http://dkkgsit-test.testdolphin.com/cloud-rbac |

#### 权限控制配置
| 配置项 | 值 | 说明 |
|--------|-----|------|
| role.admin.name | 单位管理员 | 单位管理员角色名称 |
| role.admin.code | ACT_OPERATION_ADMIN | 单位管理员角色标识 |
| role.admin.id | 8a747e4f9b58639c019c1d82cf5100e2 | 单位管理员角色id |
| role.operator.name | 单位操作员 | 单位操作员角色名称 |
| role.operator.code | ACT_OPERATION_OPERATOR | 单位操作员角色标识 |
| role.operator.id | 8a747e4f9b58639c019c1d82cff300e9 | 单位操作员角色id |
| role.people.name | 独立从业者 | 独立从业者角色名称 |
| role.people.code | ACT_OPERATION_PEOPLE | 独立从业者角色标识 |
| role.people.id | 8a747e4f9b58639c019c1d82d05800ef | 独立从业者角色id |

#### 部门配置
| 配置项 | 值 | 说明 |
|--------|-----|------|
| department.air-traffic-control.name | 空管部门 | 空管部门根部门名称 |
| department.air-traffic-control.code | la-atc-control-unit | 空管部门根部门编号 |
| department.air-traffic-control.id | f8799992b9d64561aa73bfe6a9dad66b | 空管部门根部门id |
| department.operation-unit.name | 运营单位 | 运营单位根部门名称 |
| department.operation-unit.code | la-atc-operation-unit | 运营单位根部门编号 |
| department.operation-unit.id | 3c764d75ec3247ab880b898957ba690e | 运营单位根部门id |
| department.operation-personal.name | 运营个人 | 运营个人根部门名称 |
| department.operation-personal.code | la-atc-operation-personal | 运营个人根部门编号 |
| department.operation-personal.id | 366c2d2d9b66455aaaec6bb834ed9031 | 运营个人根部门id |

#### 其他配置
| 配置项 | 值 |
|--------|-----|
| file.upload-path | /atc/file |
| redis.cluster.sync.enabled | false |
| redis.cluster.sync.current-cluster | cluster-a |

---

### la-atc-ops-server 服务配置

#### Redis配置
| 配置项 | 值 |
|--------|-----|
| spring.redis.host | redis-ops |
| spring.redis.port | 6379 |
| spring.redis.password | sN8^wA0^mM8^ |
| spring.redis.database | 9 |

#### 数据库配置（达梦）
| 配置项 | 值 |
|--------|-----|
| spring.datasource.url | jdbc:dm://10.165.32.32:5237?useUnicode=true&schema=ATC_DKWRJ_TEST&characterEncoding=utf-8&serverTimezone=UTC&useSSL=false&autoReconnect=true&rewriteBatchedStatements=true |
| spring.datasource.username | ATC_DKWRJ_TEST |
| spring.datasource.password | ATCdkwrj_123 |

#### Elasticsearch配置
| 配置项 | 值 |
|--------|-----|
| spring.elasticsearch.rest.uris | http://es-dkkgsit.dkkgsit-es:9200 |

#### Kafka配置
| 配置项 | 值 |
|--------|-----|
| spring.kafka.bootstrap-servers | kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 |
| spring.kafka.secondary.servers.receiver_log.consumer.group-id | ops-receiver-log-query-response-gp |
| spring.kafka.secondary.servers.receiver_log.listener.concurrency | 3 |
| spring.kafka.secondary.servers.receiver_log.listener.ack-mode | manual |
| spring.kafka.secondary.servers.receiver_log.consumer.enable-auto-commit | false |
| spring.kafka.secondary.servers.receiver_log.consumer.auto-offset-reset | latest |
| spring.kafka.secondary.servers.receiver_log.consumer.max-poll-records | 500 |

#### EMQX监控大盘配置
| 配置项 | 值 |
|--------|-----|
| emqx.api.baseUrl | http://10.165.33.127:28083 |
| emqx.api.username | admin |
| emqx.api.password | s^iU4^dV7^xX |
| dolphin.ops.base-url | https://10.165.32.24 |
| dolphin.ops.username | admin |
| dolphin.ops.password | IMNyQBC1SZ0CAmyelp2RBp4VsUk1adrsNhQDgmXkST2U0funK74Z/Zx25SsIcFF6ne/HSoEA2DaALlX5iP6OnQ== |

#### OAuth2配置
| 配置项 | 值 |
|--------|-----|
| commons.oauth2.client.serverUri | http://dkkgsit-test.testdolphin.com/cloud-rbac |
| commons.oauth2.client.serverInUri | http://dkkgsit-test.testdolphin.com |
| commons.oauth2.client.clientUri | http://dkkgsit-test.testdolphin.com/la-atc-ops-server |
| commons.oauth2.client.client_id | la-atc-ops-server |
| commons.oauth2.client.clientSecret | jN1qjGZSlVfE |
| commons.oauth2.client.username | ezviewAdmin |
| commons.oauth2.client.password | X64dxh&CZy?Y |
| commons.oauth2.client.grantType | password |
| commons.oauth2.client.jwtEnable | true |

#### GIS配置
| 配置项 | 值 |
|--------|-----|
| feign.gis.url | http://dkkgsit-test.testdolphin.com/portal |
| feign.gis.userName | atc_front |
| feign.gis.secretKey | 6d19783959d9469b9ea2c6cb1b225369 |
| gis.version | V3.0.0 |
| atc.synCTServer.appName | atc_front |
| atc.synCTServer.receiver.serviceName | atc_receiver |

#### 固件升级配置
| 配置项 | 值 |
|--------|-----|
| firmware.download-url-prefix | https://dkkgsit-test.testdolphin.com/la-atc-ops-front/static/server/ |
| firmware.upgrade-timeout | 3600 |
| file.upload-path | /atc/file |
| file.allowed-extensions | pdf,jpg,png,jpeg,zip,docx,xlsx,txt,doc,xlsx,json,xml,csv,ppt,pptx,zip,rar,tar,bin,pkg |

---

### la-atc-ws-backend 服务配置

#### Redis配置
| 配置项 | 值 |
|--------|-----|
| spring.redis.host | redis-atc |
| spring.redis.port | 6379 |
| spring.redis.password | s^mP2^qP7^sP |

#### 数据库配置（达梦）
| 配置项 | 值 |
|--------|-----|
| spring.datasource.url | jdbc:dm://10.165.32.32:5237?useUnicode=true&schema=ATC_DKWRJ_TEST&characterEncoding=utf-8&serverTimezone=UTC&useSSL=false&autoReconnect=true&rewriteBatchedStatements=true |
| spring.datasource.username | ATC_DKWRJ_TEST |
| spring.datasource.password | ATCdkwrj_123 |

#### Elasticsearch配置
| 配置项 | 值 |
|--------|-----|
| spring.elasticsearch.rest.uris | http://es-dkkgsit.dkkgsit-es:9200 |
| spring.data.elasticsearch.cluster-nodes | es-dkkgsit.dkkgsit-es:9200 |
| spring.elasticsearch.clusters.es_dev.rest-nodes | es-dkkgsit.dkkgsit-es:9200 |

#### Kafka配置
| 配置项 | 值 |
|--------|-----|
| spring.kafka.bootstrap-servers | kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 |
| spring.kafka.consumer.group-id | la-atc-ws-backend-atc |
| spring.kafka.secondary.servers.uav_runtime_data.topic | uav_runtime_data |
| spring.kafka.secondary.servers.uav_runtime_trace.topic | uav_runtime_trace |
| spring.kafka.secondary.servers.uav_runtime_trace.bootstrap-servers | kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 |
| spring.kafka.secondary.servers.uavData.topic.uavData | topic_uavData_test |
| commons.websocket.kafka.topic | atc-iaf-ws-kafka |
| commons.websocket.kafka.groupId | atc-ws-consumer |

#### MQTT配置
| 配置项 | 值 |
|--------|-----|
| mqtt.uav-fly-status.host | tcp://10.165.33.127:20883 |
| mqtt.uav-fly-status.client-id | atc-data-mock |
| mqtt.uav-fly-status.topic-name | atc/Gb46750 |
| mqtt.uav-fly-status.user-name | atc/drone/uavStatus/1001 |
| mqtt.uav-fly-status.password | public |

#### WebSocket配置
| 配置项 | 值 |
|--------|-----|
| stomp.server.url | wss://dkkgsit-test.testdolphin.com/la-atc-ws-backend/ws/stomp |

#### 算法配置
| 配置项 | 值 |
|--------|-----|
| algorithm.redis.host | redis-atc |
| algorithm.redis.port | 6379 |
| algorithm.redis.password | s^mP2^qP7^sP |
| uav.engine.mode | algorithm |
| uav.predict.position.algorithm | differential |
| uav.trace.scale | 2 |
| uav.trace.max-collision-distance | 20 |

#### 业务服务配置
| 配置项 | 值 |
|--------|-----|
| atc.biz.service.url | http://dkkgsit-test.testdolphin.com/la-atc-biz-backend |

#### 飞行轨迹模拟配置
| 配置项 | 值 |
|--------|-----|
| flight.track.mock.data.send | true |
| flight.track.mock.data.send.interval | 333 |
| flight.track.mock.segment.num | 180 |
| flight.track.mock.data.batch.num | 1000 |

#### OAuth2配置
| 配置项 | 值 |
|--------|-----|
| commons.oauth2.client.serverUri | http://dkkgsit-test.testdolphin.com/cloud-rbac |
| commons.oauth2.client.serverInUri | http://cloud-rbac:8080 |
| commons.oauth2.client.clientUri | https://dkkgsit-test.testdolphin.com/la-atc-ws-backend |
| commons.oauth2.client.client_id | la-atc-ws-backend |
| commons.oauth2.client.clientSecret | PZFGSrmN1jBu |
| commons.oauth2.client.username | atcAdmin |
| commons.oauth2.client.password | atcAdmin_123 |
| commons.oauth2.client.serverName | cloud-rbac |
| commons.oauth2.client.jwtEnable | true |
| common.auth.serverUri | http://dkkgsit-test.testdolphin.com/cloud-rbac |

---

### la-atc-daemon-server 服务配置

#### Redis配置
| 配置项 | 值 |
|--------|-----|
| spring.redis.host | redis-atc |
| spring.redis.port | 6379 |
| spring.redis.password | s^mP2^qP7^sP |
| spring.redis.database | 7 |

#### 中间件实例配置
| 实例类型 | 配置 |
|----------|------|
| Redis | host: 10.165.33.175, port: 26379, databaseIndex: 8, password: sJ8^nB9^oA5^ |
| MySQL | host: 10.165.32.24, port: 3306, database: daemon_health_check, username: root, password: s6^bN5^oB7^a |
| Elasticsearch | host: es-dkkgsit.dkkgsit-es:9200, port: 9200, scheme: http |
| Kafka | bootstrapServers: kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 |
| MQTT | brokerUrl: tcp://10.165.33.127:20883, username: atc_ha, password: atc_ha |

#### OAuth2配置
| 配置项 | 值 |
|--------|-----|
| commons.oauth2.client.client_id | la-atc-daemon-server |
| commons.oauth2.client.clientSecret | la-atc-daemon-server |
| commons.oauth2.client.serverUri | ${default.common.rbac-domain}/cloud-rbac |
| commons.oauth2.client.serverInUri | ${default.common.rbac-domain} |
| commons.oauth2.client.clientUri | http://localhost:8080/xinf-server |
| commons.oauth2.client.username | sysmgr |
| commons.oauth2.client.password | keda123$ |
| commons.oauth2.client.jwtEnable | true |

#### 其他配置
| 配置项 | 值 |
|--------|-----|
| default.common.redis-host | 10.165.35.186 |
| default.common.rbac-domain | https://dkkgsit-test.testdolphin.com |
| spring.flyway.enabled | false |
| license.data | 1 |
| register.global | false |
| register.remoteUrl | http://yfrb-amd.devdolphin.com/register-center |
| register.type | remote |
| health-check.cluster-id | cluster_A |
| health-check.is-master | true |
| keepalived.daemonSetName | dol-keepalivedvip |
| keepalived.deleteInterval | 60000 |
| vip.url | https://10.165.32.35/dolphin-agent/cluster.txt |
| stomp.client.verifiedWsUrl | ws://127.0.0.1:8080/la-atc-daemon-server/verified |
| stomp.client.unverifiedWsUrl | ws://127.0.0.1:8080/la-atc-daemon-server/unverified |

---

### al-atc-data-exchange-mqtt 服务配置

#### Kafka配置
| 配置项 | 值 |
|--------|-----|
| spring.kafka.bootstrap-servers | kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 |
| kafka.topic.uav-runtime-data | uav_runtime_data |
| kafka.topic.uav-resend-data | uav_resend_data |

#### MQTT配置
| 配置项 | 值 |
|--------|-----|
| mqtt.uav-fly-status.host | tcp://10.165.19.100:21883 |
| mqtt.uav-fly-status.client-id | atc-data-sync-${random.uuid} |
| mqtt.uav-fly-status.topic-name | $share/atc-datasync/atc/drone/uavStatus/# |
| mqtt.uav-fly-status.user-name | atc |
| mqtt.uav-fly-status.password | atc |
| mqtt.uav-fly-resend-status.host | tcp://10.165.19.100:21883 |
| mqtt.uav-fly-resend-status.client-id | atc-data-sync-${random.uuid} |
| mqtt.uav-fly-resend-status.topic-name | $share/datasync/atc/drone/uavResendStatus/# |
| mqtt.uav-fly-resend-status.user-name | atc |
| mqtt.uav-fly-resend-status.password | atc |

---

## 配置检查规则

### 规则1: Redis配置检查
- host不能为空
- port必须是数字且在有效范围内(1-65535)
- password不能为空

### 规则2: Kafka配置检查
- bootstrap-servers格式应为 `host:port` 或 `host1:port1,host2:port2`
- 根据服务类型选择正确的Kafka集群

### 规则3: ES配置检查
- uris格式应为 `host:port` 或 `http://host:port`
- 多个地址用逗号分隔

### 规则4: 域名配置检查
- 必须以 http:// 或 https:// 开头
- 域名应与环境的二级域名一致

### 规则5: EMQX配置检查
- baseUrl应为有效的HTTP地址
- mqtt.broker.url应以 tcp:// 开头
