"""压测：查询空间列表"""

from locust import HttpUser, task, between


class PerfUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def describe_space_list(self):
        """查询空间列表"""
        pass
