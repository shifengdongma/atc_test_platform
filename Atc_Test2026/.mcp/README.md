# MCP 服务器配置

本目录用于存放 MCP (Model Context Protocol) 服务器配置文件。

## 目录结构

```
.mcp/
├── README.md           # 本文件
├── servers.json        # MCP 服务器注册配置
└── <server-name>/      # 各服务器独立配置目录
    └── config.json
```

## 使用说明

1. 在 `servers.json` 中注册需要使用的 MCP 服务器
2. 每个服务器的详细配置放在独立子目录中
3. 敏感信息（API Key、Token 等）请勿提交到版本控制

## 常用 MCP 服务器类型

- **文件系统**: 文件读写、目录操作
- **数据库**: SQL 查询、数据管理
- **API 网关**: HTTP 请求、接口测试
- **代码分析**: 静态检查、代码审查
