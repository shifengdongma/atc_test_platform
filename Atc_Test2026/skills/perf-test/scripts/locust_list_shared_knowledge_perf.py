"""压测：查询共享知识库列表"""

from locust import HttpUser, task, between


class PerfUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def list_shared_knowledge(self):
        """查询共享知识库列表"""
        pass
