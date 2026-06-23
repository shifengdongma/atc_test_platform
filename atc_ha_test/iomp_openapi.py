import requests
import json
from ha_env import iomp_ip_a, iomp_port_a, ACCESS_KEY_a, iomp_ip_b, iomp_port_b, ACCESS_KEY_b

# 配置部分 - 从 ha_env.py 导入，支持A/B双节点
IOMP_NODES = [
    {'ip': iomp_ip_a, 'port': iomp_port_a, 'access_key': ACCESS_KEY_a, 'name': 'A节点'},
    {'ip': iomp_ip_b, 'port': iomp_port_b, 'access_key': ACCESS_KEY_b, 'name': 'B节点'},
]

def get_iomp_token(ip: str, port: int, access_key: str) -> tuple[bool, str]:
    """
    获取IOMP登录鉴权token
    
    Args:
        ip: IOMP服务IP地址
        port: IOMP服务端口
        access_key: 访问密钥
        
    Returns:
        tuple[bool, str]: (登录是否成功, jwt_token)
    """
    url = f"http://{ip}:{port}/iomp/api/v2/token"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    data = {
        'accesskey': access_key
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            status = result.get('status')
            
            if status == 200:
                jwt_token = result.get('result', {}).get('jwtToken')
                if jwt_token:
                    print(f"登录接口 | OK | 状态码: {response.status_code}")
                    return True, jwt_token
                else:
                    print("登录接口 | FAIL | 未获取到jwtToken")
                    return False, ""
            else:
                print(f"登录接口 | FAIL | 状态码: {status}")
                return False, ""
        else:
            print(f"登录接口 | FAIL | HTTP状态码: {response.status_code}")
            return False, ""
            
    except requests.exceptions.RequestException as e:
        print(f"登录接口 | ERROR | 异常: {e}")
        return False, ""
    except json.JSONDecodeError as e:
        print(f"登录接口 | ERROR | 解析响应失败: {e}")
        return False, ""

def get_current_user(ip: str, port: int, jwt_token: str) -> str:
    """
    获取当前登录人username
    
    Args:
        ip: IOMP服务IP地址
        port: IOMP服务端口
        jwt_token: 登录时获取的JWT token
        
    Returns:
        str: 用户名
    """
    url = f"http://{ip}:{port}/iomp/api/v2/token/user"
    
    headers = {
        'Authorization': jwt_token
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            username = result.get('result', {}).get('username', '')
            if username:
                print(f"获取当前登录人 | OK | 状态码: {response.status_code} | 用户名: {username}")
                return username
            else:
                print(f"获取当前登录人 | FAIL | 状态码: {response.status_code} | 未获取到用户名")
                return ""
        else:
            print(f"获取当前登录人 | FAIL | 状态码: {response.status_code}")
            return ""
            
    except requests.exceptions.RequestException as e:
        print(f"获取当前登录人 | ERROR | 异常: {e}")
        return ""
    except json.JSONDecodeError as e:
        print(f"获取当前登录人 | ERROR | 解析响应失败: {e}")
        return ""

if __name__ == "__main__":
    for node in IOMP_NODES:
        print(f"\n{'='*60}")
        print(f"=== IOMP登录鉴权 - {node['name']} ({node['ip']}) ===")
        print(f"{'='*60}")
        print(f"IP: {node['ip']}")
        print(f"端口: {node['port']}")
        print(f"Access Key: {node['access_key']}")
        print()
        
        success, jwt_token = get_iomp_token(node['ip'], node['port'], node['access_key'])
        
        if success:
            print(f"\n{node['name']} 鉴权成功！")
            
            print(f"\n=== 获取当前登录人 ===")
            get_current_user(node['ip'], node['port'], jwt_token)
        else:
            print(f"\n{node['name']} 鉴权失败！")