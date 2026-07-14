# Docker 部署数据库连接问题修复计划

## Context

用户在 Linux 服务器上使用 Docker 部署 ATC/UTM 测试平台，遇到两个数据库连接问题：
1. **达梦数据库**: `[CODE:-70089]Encryption module failed to load`（4次）
2. **MySQL**: 连接到 `127.0.0.1` Connection refused → 降级到 SQLite

本地 Windows 运行正常，Docker 容器内 `python:3.11-slim` (Debian 12 Bookworm) 失败。

## 根因分析

### 达梦数据库 (-70089)

dmPython Linux wheel 的 `.so` 加密库动态链接 OpenSSL 1.1 (`libssl.so.1.1`)，但 `python:3.11-slim` (Debian 12 Bookworm) 只提供 OpenSSL 3.x (`libssl.so.3`)，SONAME 不匹配导致加密模块加载失败。

Dockerfile 已添加从 Debian 11 Bullseye 源安装 `libssl1.1` 的步骤（行31-36），修复思路正确。但需要验证：
- docker-compose.yml 中 `no_cache: true` 确保重建时不会缓存旧层
- 实际构建是否成功（apt update 是否报 GPG/网络错误）

### MySQL (127.0.0.1)

错误链：docker-compose.yml 环境变量 `${UTM_MYSQL_HOST:-1Panel-mysql-Jdmq}` → 如果用户未在 docker-compose 环境中设置 `UTM_MYSQL_HOST` → 默认值 `1Panel-mysql-Jdmq`（1Panel 容器名）→ 若容器不在 `1panel-network` 网络上 → DNS 解析失败 → 连接失败。

关键：用户的 env vars 中列出了 `UTM_MYSQL_HOST=10.165.32.147`，说明用户**想用外部 IP**。但 `docker-compose.yml` 的默认值覆盖了用户意图。

## 需要修改的文件

### 1. `docker/docker-compose.yml`

**问题 1**: `UTM_MYSQL_HOST` 默认值 `1Panel-mysql-Jdmq` 是特定于 1Panel 环境的容器名，不适用于用户的 IP 直连场景。
**修复**: 移除硬编码默认值，改为空默认，让 `common/config.py` 的 `configured` 机制处理未配置场景。

**问题 2**: 含特殊字符的环境变量（Redis 密码 `s4^dJ5^xM6^e .0`）在 YAML 中可能被误解析。
**修复**: 改用 YAML mapping 格式并加引号包裹变量。

具体改动：
```yaml
# 改前 (行40):
- UTM_MYSQL_HOST=${UTM_MYSQL_HOST:-1Panel-mysql-Jdmq}
# 改后: 移除环境特定默认值，未设置时为空，由 common/config.py 检测并跳过
- UTM_MYSQL_HOST=${UTM_MYSQL_HOST:-}

# 对含特殊字符的值加引号保护:
- UTM_REDIS_PASSWORD="${UTM_REDIS_PASSWORD:-}"
- UTM_MYSQL_PASSWORD="${UTM_MYSQL_PASSWORD:-}"
- UTM_DM_PASSWORD="${UTM_DM_PASSWORD:-}"
```

### 2. `database/mysql_db_manager.py`

**问题**: `_create_mysql_client()` 的 `except Exception` 分支（行72-74）在 `load_mysql_config()` 抛异常时创建默认 `MysqlDbClient(read_timeout=..., write_timeout=...)`，该对象使用默认 `host="127.0.0.1"`，Docker 内必然失败并输出误导性错误。

**修复**: 将 except 分支改为返回 `None`，让调用方降级到 SQLite 而不尝试连接。

```python
# 改前 (行72-74):
except Exception as e:
    print(f"[mysql_db_manager] 加载 MySQL 配置失败: {e}，使用默认值")
    return MysqlDbClient(read_timeout=read_timeout, write_timeout=write_timeout)

# 改后:
except Exception as e:
    print(f"[mysql_db_manager] 加载 MySQL 配置失败: {e}，跳过 MySQL")
    return None
```

### 3. `atc_api_autotest/api_tools/dmdbclient.py`

**问题**: 达梦连接失败时错误消息不够具体，用户无法知道是 OpenSSL 版本问题。
**修复**: 在 `connect()` 中检测 `-70089` 错误码，给出明确的修复建议。

```python
# 在 connect() 方法的 except 块中:
except Exception as e:
    err_msg = str(e)
    if "-70089" in err_msg or "Encryption module" in err_msg:
        print(f"[DmDbClient] 数据库连接失败: {e}")
        print(f"[DmDbClient] 提示: 达梦加密模块需要 libssl.so.1.1 (OpenSSL 1.1)，"
              "请确保 Docker 镜像已安装 libssl1.1")
    else:
        print(f"[DmDbClient] 数据库连接失败: {e}")
    return False
```

### 4. `database/json_data_manager.py`

**问题**: `_get_dm_client()` 连接失败后立即标记 `_dm_available = False`，但无冷却期，后续请求会不断重试。
**修复**: 添加冷却期机制（与 `mysql_db_manager.py` 一致的 60 秒冷却），避免短时间内重复打印错误。

### 5. `docker/Dockerfile` — 加固

**问题**: Debian 11 Bullseye 源可能因 Release 文件变化导致 apt update 失败。
**修复**: 添加 `--allow-releaseinfo-change` 标志和重试机制。

```dockerfile
# 改后:
RUN echo "deb http://mirrors.aliyun.com/debian bullseye main" > /etc/apt/sources.list.d/bullseye.list && \
    apt-get update -o Acquire::AllowReleaseInfoChange=true || \
    apt-get update -o Acquire::AllowReleaseInfoChange=true && \
    apt-get install -y --no-install-recommends libssl1.1 && \
    rm -f /etc/apt/sources.list.d/bullseye.list && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    ldconfig -p | grep -q libssl.so.1.1 || \
    (echo "ERROR: libssl.so.1.1 安装失败，达梦数据库将不可用" && false)
```

### 6. `common/config.py` — 审查通过（无需额外修改）

现有 `_load_mysql_config()` 逻辑正确：
- `configured` 标志正确区分"已配置"与"使用默认值"
- `os.environ.get("UTM_MYSQL_HOST")` 为空字符串时判断为 falsy → `configured=False` ✓
- 环境变量存在且非空时 → `configured=True` ✓

## 不需要修改的文件

- `database/log_streamer.py` — 已有 `configured` 检查，逻辑正确
- `common/log_setup.py` — 与数据库连接无关（虽在 git status 中显示 M）
- `utm_simulator/web_server.py` — 通过 `_get_json_mgr()` 和 `_get_streamer()` 间接使用，无需改动

## 验证方案

1. **构建镜像**: `docker compose -f docker/docker-compose.yml build`
2. **检查 libssl**: `docker run --rm utm-simulator:latest ldconfig -p | grep libssl.so.1.1`
3. **测试达梦连接**: 进入容器执行 `python -c "from dmdbclient import DmDbClient; c = DmDbClient(); c.connect()"`
4. **启动服务**: `docker compose -f docker/docker-compose.yml up`，确认：
   - 日志不再输出 `[MysqlDbClient] 数据库连接失败`（若未配置 MySQL 环境变量）
   - 日志不再输出 `[DmDbClient] 数据库连接失败: [CODE:-70089]`
5. **设置 MySQL 变量后重启**: 确认 MySQL 能正常连接
