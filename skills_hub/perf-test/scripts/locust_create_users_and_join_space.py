"""压测：创建用户并加入空间"""

from locust import HttpUser, task, between


class PerfUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def create_user_and_join_space(self):
        """创建用户并加入空间"""
        pass
