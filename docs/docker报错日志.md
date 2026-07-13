docker容器日志：
10:33:56 ERROR _internal:97 - Error on request:
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/werkzeug/serving.py", line 371, in run_wsgi
    execute(self.server.app)
  File "/usr/local/lib/python3.11/site-packages/werkzeug/serving.py", line 337, in execute
    write(b"")
  File "/usr/local/lib/python3.11/site-packages/werkzeug/serving.py", line 262, in write
    assert status_set is not None, "write() before start_response"
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: write() before start_response
{"ts": "2026-07-13T02:33:56.128872+00:00", "level": "ERROR", "module": "_internal", "line": 97, "func": "_log", "msg": "Error on request:\nTraceback (most recent call last):\n  File \"/usr/local/lib/python3.11/site-packages/werkzeug/serving.py\", line 371, in run_wsgi\n    execute(self.server.app)\n  File \"/usr/local/lib/python3.11/site-packages/werkzeug/serving.py\", line 337, in execute\n    write(b\"\")\n  File \"/usr/local/lib/python3.11/site-packages/werkzeug/serving.py\", line 262, in write\n    assert status_set is not None, \"write() before start_response\"\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError: write() before start_response", "thread": "Thread-7774 (process_request_thread)"}

本地日志：
[信息] 使用 UAV ID: EXTD57470099C4A1978F, 实名登记: UAS57EXTD5747099
[错误] 数据库客户端不可用，请确保已安装 dmPython 且 dmdbclient.py 在路径中
[错误] 无法获取航线 '铁门关至吐鲁番' 的数据