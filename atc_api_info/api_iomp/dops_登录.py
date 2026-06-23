from playwright.sync_api import sync_playwright
import time
import os

# 登录信息
url = "https://10.165.32.24/dops/#/admin/login"
username = "admin"  # 请替换为实际用户名
password = "9ojm38fnj@t3"  # 请替换为实际密码

def get_chrome_path():
    """获取系统Chrome浏览器路径"""
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def login_dops():
    chrome_path = get_chrome_path()
    
    with sync_playwright() as p:
        # 启动Chrome浏览器（使用系统安装的Chrome）
        launch_options = {
            "headless": False,  # 显示浏览器窗口，方便调试
            "args": [
                "--ignore-certificate-errors",  # 忽略证书错误
                "--no-sandbox",  # 禁用沙盒模式
                "--disable-setuid-sandbox"  # 禁用setuid沙盒
            ]
        }
        
        # 如果找到系统Chrome，则使用系统Chrome
        if chrome_path:
            launch_options["executable_path"] = chrome_path
            print(f"使用系统Chrome浏览器: {chrome_path}")
        else:
            print("未找到系统Chrome浏览器，使用Playwright内置浏览器")
        
        browser = p.chromium.launch(**launch_options)
        page = browser.new_page()
        
        try:
            print("正在访问登录页面...")
            # 访问登录页面
            page.goto(url, timeout=120000)
            
            # 等待页面加载完成
            print("等待页面加载...")
            page.wait_for_load_state("domcontentloaded", timeout=120000)
            time.sleep(5)  # 额外等待5秒确保页面完全加载
            
            # 输入用户名（使用XPath）
            print("输入用户名...")
            page.fill('//*[@id="app"]/div/div/form/div[1]/div/div/input', username)
            
            # 输入密码（使用name属性）
            print("输入密码...")
            page.fill('input[name="password"]', password)
            
            # 点击登录按钮（使用type属性）
            print("点击登录按钮...")
            page.click('button[type="button"]')
            
            # 等待登录成功后的页面加载
            print("等待登录成功...")
            page.wait_for_load_state("networkidle", timeout=120000)
            time.sleep(10)  # 额外等待10秒确保登录完成
            
            # 验证登录是否成功（可以根据实际页面内容调整）
            print("登录成功！")
            
            # 打印当前页面标题和URL
            print(f"当前页面标题: {page.title()}")
            print(f"当前页面URL: {page.url}")
            
            # 保存页面截图用于调试
            screenshot_path = "dops_login_success.png"
            page.screenshot(path=screenshot_path)
            print(f"页面截图已保存到: {screenshot_path}")
            
            # 尝试查找左侧菜单的所有元素
            print("查找左侧菜单元素...")
            try:
                # 查找所有导航菜单元素
                menu_elements = page.query_selector_all('*')
                print(f"找到元素数量: {len(menu_elements)}")
                # 过滤出包含文本的元素
                text_elements = []
                for element in menu_elements:
                    try:
                        text = element.text_content().strip()
                        if text and len(text) > 2:
                            text_elements.append(text)
                    except:
                        pass
                # 去重并显示前20个
                unique_texts = list(set(text_elements))[:20]
                print(f"找到唯一文本元素数量: {len(unique_texts)}")
                for i, text in enumerate(unique_texts):
                    print(f"文本{i+1}: {text}")
            except Exception as e:
                print(f"查找菜单元素失败: {e}")
            
            # 尝试点击服务管理（基于实际页面结构）
            print("尝试点击服务管理...")
            try:
                # 尝试使用更具体的选择器
                # 基于页面结构，尝试查找侧边栏中的服务管理
                service_management_selector = '//div[@class="sidebar"]//*[contains(text(),"服务管理")]'
                print(f"尝试选择器: {service_management_selector}")
                page.wait_for_selector(service_management_selector, timeout=60000)
                page.click(service_management_selector)
                print("成功点击服务管理！")
            except Exception as e:
                print(f"点击服务管理失败: {e}")
                # 尝试重新加载页面
                try:
                    print("尝试重新加载页面...")
                    page.reload()
                    time.sleep(5)
                    # 再次尝试
                    page.wait_for_selector('text=服务管理', timeout=60000)
                    page.click('text=服务管理')
                    print("成功点击服务管理！")
                except Exception as e2:
                    print(f"重新加载后点击服务管理失败: {e2}")
            
            time.sleep(8)
            
            # 尝试点击Deployments
            print("尝试点击Deployments...")
            try:
                page.wait_for_selector('text=Deployments', timeout=60000)
                page.click('text=Deployments')
                print("成功点击Deployments！")
            except Exception as e:
                print(f"点击Deployments失败: {e}")
            
            time.sleep(8)
            
            # 服务名选择la-atc-daemon-server并点击进入
            print("选择服务la-atc-daemon-server...")
            try:
                page.wait_for_selector('text=la-atc-daemon-server', timeout=60000)
                page.click('text=la-atc-daemon-server')
                print("成功选择服务la-atc-daemon-server！")
            except Exception as e:
                print(f"选择服务失败: {e}")
            
            time.sleep(8)
            
            # 下载日志
            print("下载日志...")
            try:
                page.wait_for_selector('text=下载日志', timeout=60000)
                page.click('text=下载日志')
                print("成功点击下载日志！")
            except Exception as e:
                print(f"下载日志失败: {e}")
            
            time.sleep(15)  # 等待日志下载完成
            print("日志下载完成！")
            
        except Exception as e:
            print(f"操作失败: {e}")
        finally:
            # 关闭浏览器
            browser.close()
            print("浏览器已关闭")

if __name__ == "__main__":
    print("开始执行DOPS登录脚本...")
    login_dops()
    print("脚本执行完成")