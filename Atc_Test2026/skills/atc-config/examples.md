# ATC配置检查技能 - 使用示例

## 示例1: 检查配置文件

### 用户输入
```
帮我检查这个application.json配置文件，dkkgsit环境的
```

### 配置文件内容
```json
{
  "spring": {
    "datasource": {
      "url": "jdbc:mysql://localhost:3306/atc",
      "username": "root",
      "password": "123456"
    },
    "redis": {
      "host": "localhost",
      "port": 6379,
      "password": ""
    },
    "kafka": {
      "bootstrap-servers": "localhost:9092"
    },
    "elasticsearch": {
      "rest": {
        "uris": "http://localhost:9200"
      }
    }
  },
  "firmware": {
    "download-url-prefix": "http://localhost:8080"
  },
  "commons": {
    "oauth2": {
      "client": {
        "serverUri": "http://localhost:8081",
        "serverInUri": "http://localhost:8081",
        "clientUri": "http://localhost:8080"
      }
    }
  },
  "emqx": {
    "api": {
      "baseUrl": "http://localhost:18083"
    }
  },
  "mqtt": {
    "broker": {
      "username": "admin",
      "password": "public",
      "url": "tcp://localhost:1883"
    }
  }
}
```

### 检查结果

```markdown
## 配置检查报告 - dkkgsit

### 检查时间
2026-04-14 14:30:00

### 配置文件
application.json

### 检查结果摘要
- 通过项: 0
- 需修改项: 10
- 缺失项: 0

### 详细检查项

#### 需要修改的配置
| 配置项 | 当前值 | 建议值 | 说明 |
|--------|--------|--------|------|
| spring.redis.host | localhost | dolphin-test.kedacom.com | dkkgsit环境redis-atc地址 |
| spring.redis.port | 6379 | 21001 | dkkgsit环境redis-atc端口 |
| spring.redis.password | (空) | s^mP2^qP7^sP | dkkgsit环境redis-atc密码 |
| spring.kafka.bootstrap-servers | localhost:9092 | kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 | 非核心业务Kafka地址 |
| spring.elasticsearch.rest.uris | http://localhost:9200 | es-dkkgsit.dkkgsit-es:9200 | ES集群地址 |
| firmware.download-url-prefix | http://localhost:8080 | https://dkkgsit-test.testdolphin.com | 二级域名 |
| commons.oauth2.client.serverUri | http://localhost:8081 | https://dkkgsit-test.testdolphin.com/cloud-rbac | 统一权限地址 |
| commons.oauth2.client.serverInUri | http://localhost:8081 | https://dkkgsit-test.testdolphin.com/cloud-rbac | 统一权限内网地址 |
| commons.oauth2.client.clientUri | http://localhost:8080 | https://dkkgsit-test.testdolphin.com | 客户端地址 |
| emqx.api.baseUrl | http://localhost:18083 | http://10.165.19.100:21083 | EMQX平台地址 |
| mqtt.broker.password | public | s^pM4^dV9^uA | EMQX平台密码 |
| mqtt.broker.url | tcp://localhost:1883 | tcp://10.165.19.100:21883 | MQTT连接地址 |

### 建议操作
1. 将spring.redis.host修改为 dolphin-test.kedacom.com
2. 将spring.redis.port修改为 21001
3. 将spring.redis.password修改为 s^mP2^qP7^sP
4. 将spring.kafka.bootstrap-servers修改为 kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092
5. 将spring.elasticsearch.rest.uris修改为 es-dkkgsit.dkkgsit-es:9200
6. 将所有域名配置中的localhost替换为 dkkgsit-test.testdolphin.com
7. 将emqx.api.baseUrl修改为 http://10.165.19.100:21083
8. 将mqtt.broker.password修改为 s^pM4^dV9^uA
9. 将mqtt.broker.url修改为 tcp://10.165.19.100:21883
```

---

## 示例2: 生成特定配置

### 用户输入
```
给我生成dkkgsit环境的redis配置
```

### 输出
```json
{
  "spring": {
    "redis": {
      "host": "dolphin-test.kedacom.com",
      "port": 21001,
      "password": "s^mP2^qP7^sP",
      "database": 0,
      "timeout": 5000,
      "lettuce": {
        "pool": {
          "max-active": 8,
          "max-idle": 8,
          "min-idle": 0
        }
      }
    }
  }
}
```

---

## 示例3: 生成完整配置模板

### 用户输入
```
给我生成dkkgsit环境的完整application.yml模板
```

### 输出
```yaml
spring:
  datasource:
    url: jdbc:mysql://[数据库地址]:3306/atc?useUnicode=true&characterEncoding=utf-8
    username: [数据库用户名]
    password: [数据库密码]
    driver-class-name: com.mysql.cj.jdbc.Driver
  
  redis:
    host: dolphin-test.kedacom.com
    port: 21001
    password: s^mP2^qP7^sP
    database: 0
    timeout: 5000
  
  kafka:
    bootstrap-servers: kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092
  
  elasticsearch:
    rest:
      uris: es-dkkgsit.dkkgsit-es:9200

firmware:
  download-url-prefix: https://dkkgsit-test.testdolphin.com

commons:
  oauth2:
    client:
      serverUri: https://dkkgsit-test.testdolphin.com/cloud-rbac
      serverInUri: https://dkkgsit-test.testdolphin.com/cloud-rbac
      clientUri: https://dkkgsit-test.testdolphin.com

emqx:
  api:
    baseUrl: http://10.165.19.100:21083

mqtt:
  broker:
    username: admin
    password: s^pM4^dV9^uA
    url: tcp://10.165.19.100:21883
```

---

## 示例4: 对比两个环境配置

### 用户输入
```
对比dkkgsit和sit环境的kafka配置有什么不同
```

### 输出
```markdown
## 环境配置对比 - Kafka

| 配置项 | dkkgsit环境 | sit环境 | 说明 |
|--------|-------------|---------|------|
| 非核心业务Kafka | kafka-dkkgsit-0.kafka-dkkgsit.dkkgsit-kafka:9092 | [sit值] | dkkgsit使用dkkgsit-kafka空间 |
| 核心业务Kafka | kafka-dkhx-0.kafka-dkhx.dkhx-kafka:9092 | [sit值] | dkkgsit使用dkhx-kafka空间 |

### dkkgsit详细配置
- 空间：dkkgsit-kafka / dkhx-kafka
- 外网地址：10.165.19.227:30123

### 建议
请提供sit环境的配置信息以完成对比。
```

---

## 示例5: 验证配置格式

### 用户输入
```
帮我验证这个mqtt配置格式是否正确
```

### 配置文件
```json
{
  "mqtt": {
    "broker": {
      "url": "mqtt://10.165.19.100:21883",
      "username": "admin",
      "password": "s^pM4^dV9^uA"
    }
  }
}
```

### 输出
```markdown
## MQTT配置验证结果

### 检查结果
| 检查项 | 状态 | 说明 |
|--------|------|------|
| url格式 | ⚠️ 警告 | mqtt:// 协议可能不被支持，建议使用 tcp:// |
| username | ✅ 通过 | 已配置 |
| password | ✅ 通过 | 已配置 |

### 建议修改
```json
{
  "mqtt": {
    "broker": {
      "url": "tcp://10.165.19.100:21883",
      "username": "admin",
      "password": "s^pM4^dV9^uA"
    }
  }
}
```

### dkkgsit环境参考值
- url: tcp://10.165.19.100:21883
- username: admin
- password: s^pM4^dV9^uA
```
