13:11:40 ERROR app:875 - Exception on /api/schedule/tasks [POST]
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/flask/app.py", line 1511, in wsgi_app
    response = self.full_dispatch_request()
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/flask/app.py", line 919, in full_dispatch_request
    rv = self.handle_user_exception(e)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/flask/app.py", line 917, in full_dispatch_request
    rv = self.dispatch_request()
         ^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/flask/app.py", line 902, in dispatch_request
    return self.ensure_sync(self.view_functions[rule.endpoint])(**view_args)  # type: ignore[no-any-return]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/utm_simulator/web_server.py", line 2196, in api_schedule_create
    tid = sch.add_task(data)
          ^^^^^^^^^^^^^^^^^^
  File "/app/utm_simulator/../database/scheduler.py", line 196, in add_task
    return insert(TASK_TABLE, data)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/utm_simulator/../database/mysql_db_manager.py", line 308, in insert
    cur.execute(sql, list(data.values()))
  File "/usr/local/lib/python3.11/site-packages/pymysql/cursors.py", line 153, in execute
    result = self._query(query)
             ^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/pymysql/cursors.py", line 322, in _query
    conn.query(q)
  File "/usr/local/lib/python3.11/site-packages/pymysql/connections.py", line 558, in query
    self._affected_rows = self._read_query_result(unbuffered=unbuffered)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/pymysql/connections.py", line 822, in _read_query_result
    result.read()
  File "/usr/local/lib/python3.11/site-packages/pymysql/connections.py", line 1200, in read
    first_packet = self.connection._read_packet()
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/pymysql/connections.py", line 772, in _read_packet
    packet.raise_for_error()
  File "/usr/local/lib/python3.11/site-packages/pymysql/protocol.py", line 221, in raise_for_error
    err.raise_mysql_exception(self._data)
  File "/usr/local/lib/python3.11/site-packages/pymysql/err.py", line 143, in raise_mysql_exception
    raise errorclass(errno, errval)
pymysql.err.OperationalError: (1213, 'Deadlock found when trying to get lock; try restarting transaction')