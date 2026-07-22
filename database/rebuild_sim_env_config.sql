-- ============================================================
-- sim_env_config 表重建脚本（解决 ALTER TABLE 挂死问题）
--
-- 当前表: 10 列 (id, name, redis_ip, redis_port, redis_pwd,
--         kafka_url, kafka_url2, is_default, created_at, updated_at)
-- 目标表: 22 列 (新增 dm_* x5, mysql_* x5, atc_* x4, es_hosts)
--
-- 用法: mysql -h 10.165.32.147 -u utm -p utm_simulator < this_file.sql
-- ============================================================

START TRANSACTION;

-- 1. 备份现有数据到临时表
CREATE TEMPORARY TABLE sim_env_config_backup AS SELECT * FROM sim_env_config;

-- 2. 删除旧表
DROP TABLE sim_env_config;

-- 3. 创建完整表结构
CREATE TABLE `sim_env_config` (
    `id`              INT AUTO_INCREMENT PRIMARY KEY,
    `name`            VARCHAR(128) NOT NULL,
    `redis_ip`        VARCHAR(128) DEFAULT '',
    `redis_port`      VARCHAR(16) DEFAULT '6379',
    `redis_pwd`       VARCHAR(128) DEFAULT '',
    `kafka_url`       VARCHAR(256) DEFAULT '',
    `kafka_url2`      VARCHAR(256) DEFAULT '',
    `is_default`      TINYINT DEFAULT 0,
    `dm_host`         VARCHAR(128) DEFAULT '' COMMENT '达梦数据库地址',
    `dm_port`         INT DEFAULT 5236 COMMENT '达梦数据库端口',
    `dm_user`         VARCHAR(128) DEFAULT 'SYSDBA' COMMENT '达梦用户名',
    `dm_password`     VARCHAR(128) DEFAULT '' COMMENT '达梦密码',
    `dm_schema`       VARCHAR(128) DEFAULT '' COMMENT '达梦模式名',
    `mysql_host`      VARCHAR(128) DEFAULT '' COMMENT 'MySQL地址',
    `mysql_port`      INT DEFAULT 3306 COMMENT 'MySQL端口',
    `mysql_user`      VARCHAR(128) DEFAULT '' COMMENT 'MySQL用户',
    `mysql_password`  VARCHAR(128) DEFAULT '' COMMENT 'MySQL密码',
    `mysql_database`  VARCHAR(128) DEFAULT '' COMMENT 'MySQL数据库名',
    `atc_cluster_api` VARCHAR(256) DEFAULT '' COMMENT '集群API地址',
    `atc_vip`         VARCHAR(128) DEFAULT '' COMMENT 'ATC VIP地址',
    `atc_node_a`      VARCHAR(128) DEFAULT '' COMMENT 'ATC A节点',
    `atc_node_b`      VARCHAR(128) DEFAULT '' COMMENT 'ATC B节点',
    `es_hosts`        VARCHAR(512) DEFAULT '' COMMENT 'ES地址(JSON)',
    `created_at`      DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仿真环境配置表';

-- 4. 还原数据
INSERT INTO sim_env_config (
    id, name, redis_ip, redis_port, redis_pwd,
    kafka_url, kafka_url2, is_default,
    created_at, updated_at
)
SELECT
    id, name, redis_ip, redis_port, redis_pwd,
    kafka_url, kafka_url2, is_default,
    created_at, updated_at
FROM sim_env_config_backup;

-- 5. 验证
SELECT COUNT(*) AS row_count FROM sim_env_config;
SHOW COLUMNS FROM sim_env_config;

COMMIT;
