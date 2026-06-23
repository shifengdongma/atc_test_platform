# https://testerhome.com/articles/43844

perf-test/
├── assets/                          # 测试数据文件
│   ├── apps.json                    # 应用数据
│   ├── perf_docs_list.jsonl         # 文档列表（压测用）
│   ├── shared_kbs.json              # 共享知识库数据
│   ├── spaces.json                  # 空间数据
│   └── test_full.json               # 完整测试数据
├── references/                      # 参考文档
│   ├── api-notes.md                 # API 接口说明
│   └── locust-cookbook.md           # Locust 使用手册
├── scripts/                         # 脚本文件
│   ├── common/                      # 公共工具模块
│   │   ├── __init__.py
│   │   ├── asset_store.py           # 资产存储管理
│   │   ├── batch_runner.py          # 批量执行器
│   │   └── cli_utils.py             # 命令行工具
│   ├── add_users_to_space.py        # 添加用户到空间
│   ├── create_apps.py               # 批量创建应用
│   ├── create_shared_kbs.py         # 批量创建共享知识库
│   ├── create_spaces.py             # 批量创建空间
│   ├── create_users.py              # 批量创建用户
│   ├── gen_doc_variants.py          # 生成文档变体
│   ├── locust_create_users_and_join_space.py   # 压测：创建用户并加入空间
│   ├── locust_describe_space_list_perf.py      # 压测：查询空间列表
│   ├── locust_list_app_perf.py                 # 压测：查询应用列表
│   └── locust_list_shared_knowledge_perf.py    # 压测：查询共享知识库列表
└── SKILL.md                         # Skill 说明文档