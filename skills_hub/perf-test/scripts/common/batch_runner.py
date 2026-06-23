"""批量执行器模块"""

import asyncio
from typing import Callable, List, Any


class BatchRunner:
    """批量执行器类"""

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers

    async def run_async(self, func: Callable, items: List[Any]) -> List[Any]:
        """异步批量执行"""
        semaphore = asyncio.Semaphore(self.max_workers)

        async def run_with_semaphore(item):
            async with semaphore:
                return await func(item)

        tasks = [run_with_semaphore(item) for item in items]
        return await asyncio.gather(*tasks)

    def run_sync(self, func: Callable, items: List[Any]) -> List[Any]:
        """同步批量执行"""
        results = []
        for item in items:
            results.append(func(item))
        return results
