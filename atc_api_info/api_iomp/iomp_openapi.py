import requests
import json

# 配置部分 - 请在此处修改IP和accesskey
IOMP_IP = '10.165.32.25'
IOMP_PORT = 8801
ACCESS_KEY = '3791khbrwxc9j66p'

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
    print("=== IOMP登录鉴权 ===")
    print(f"IP: {IOMP_IP}")
    print(f"端口: {IOMP_PORT}")
    print(f"Access Key: {ACCESS_KEY}")
    print()
    
    success, jwt_token = get_iomp_token(IOMP_IP, IOMP_PORT, ACCESS_KEY)
    
    if success:
        print("\n鉴权成功！")
        
        print("\n=== 获取当前登录人 ===")
        get_current_user(IOMP_IP, IOMP_PORT, jwt_token)
    else:
        print("\n鉴权失败！")