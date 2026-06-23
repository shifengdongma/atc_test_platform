"""压测：查询应用列表"""

from locust import HttpUser, task, between


class PerfUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def list_app(self):
        """查询应用列表"""
        pass
