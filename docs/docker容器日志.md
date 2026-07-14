root@02f26de5c6ba:/app/utm_simulator# LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/dmssl:/usr/lib/x86_64-linux-gnu python3 -c "import dmPython; dmPython.connect(user='SYSDBA', password='', server='10.165.32.32', port=5237, schema='ATC_DKWRJ_TEST'); print('OK')"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
dmPython.DatabaseError: [CODE:-2501]Invalid username or password
root@02f26de5c6ba:/app/utm_simulator# python3 -c "
import ctypes, os
# 预加载 dmssl 目录下的加密库
for lib in ['libcrypto.so', 'libssl.so']:
    path = f'/usr/local/lib/python3.11/site-packages/dmssl/{lib}'
    if os.path.exists(path):
        ctypes.CDLL(path, ctypes.RTLD_GLOBAL)
        print(f'已预加载: {path}')
import dmPython
dmPython.connect(user='SYSDBA', password='', server='10.165.32.32', port=5237, schema='ATC_DKWRJ_TEST')
print('OK')
"
已预加载: /usr/local/lib/python3.11/site-packages/dmssl/libcrypto.so
已预加载: /usr/local/lib/python3.11/site-packages/dmssl/libssl.so
Traceback (most recent call last):
  File "<string>", line 10, in <module>
dmPython.DatabaseError: [CODE:-70089]Encryption module failed to load
root@02f26de5c6ba:/app/utm_simulator# python3 -c "
import pymysql
try:
    conn = pymysql.connect(host='10.165.32.147', port=3306, user='utm', password='eEkJ3GfJ3Pt8iH5r', database='utm_simulator', ssl={})
    print('OK - MySQL连接成功')
    conn.close()
except Exception as e:
    print(f'FAIL - {e}')
"
OK - MySQL连接成功
root@02f26de5c6ba:/app/utm_simulator# 