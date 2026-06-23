"""
Confluence Python Client

所有配置从 config.yaml 文件加载。

使用示例:
    from python.confluence_client import create_client
    
    client = create_client()  # 自动加载 config.yaml
    results = client.search("API文档")
"""

from .confluence_client import (
    ConfluenceClient,
    create_client,
    PageInfo,
    SearchResult,
    SpaceInfo,
    CommentInfo,
)
from .config import (
    ConfluenceConfig,
    load_config,
    get_confluence_config,
    find_config_file,
)

__all__ = [
    # 客户端
    "ConfluenceClient",
    "create_client",
    # 数据类
    "PageInfo",
    "SearchResult", 
    "SpaceInfo",
    "CommentInfo",
    # 配置
    "ConfluenceConfig",
    "load_config",
    "get_confluence_config",
    "find_config_file",
]
