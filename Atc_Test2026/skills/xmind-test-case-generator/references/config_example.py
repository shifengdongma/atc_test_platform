"""
XMind 测试用例生成器 - 配置示例

本文件展示了如何通过配置自定义规则来生成特定业务场景的测试用例。
"""

# 示例1：淘宝下单功能的配置
TAOBAO_CONFIG = {
    'precondition_rules': {
        'default': '系统正常运行',
        'keywords': {
            '购物车': '用户已登录，购物车中有商品',
            '选品': '用户已登录，购物车中有商品',
            '结算': '用户已登录，购物车中有商品',
            '收货地址': '用户已登录，进入结算页面',
            '地址': '用户已登录，进入结算页面',
            '订单信息': '用户已登录，已选择商品并进入订单确认页',
            '订单确认': '用户已登录，已选择商品并进入订单确认页',
            '支付': '用户已登录，已确认订单信息，准备支付',
            '支付流程': '用户已登录，已确认订单信息，准备支付',
            '订单生成': '用户已登录，已完成支付',
            '订单查询': '用户已登录，已完成支付',
            '我的订单': '用户已登录，已完成支付',
        }
    },
    'test_step_rules': {
        '正向用例': lambda name, parent: f"1. 进入相关功能页面\n2. 执行操作：{name}\n3. 验证操作成功\n4. 验证功能正常",
        '负向用例': lambda name, parent: f"1. 进入相关功能页面\n2. 执行无效操作：{name}\n3. 验证系统提示错误信息\n4. 验证操作被拒绝",
        '边界值用例': lambda name, parent: f"1. 进入相关功能页面\n2. 输入边界值：{name}\n3. 验证系统处理\n4. 验证边界值处理正确",
        '异常用例': lambda name, parent: f"1. 进入相关功能页面\n2. 模拟异常场景：{name}\n3. 验证系统响应\n4. 验证系统不会崩溃",
    },
    'expected_result_rules': {
        '正向用例': lambda name, parent: f"操作成功，{name}功能正常，符合预期",
        '负向用例': lambda name, parent: f"系统正确提示错误信息，拒绝无效操作，{name}场景处理正确",
        '边界值用例': lambda name, parent: f"系统正确处理边界值情况：{name}，边界值验证通过",
        '异常用例': lambda name, parent: f"系统正确处理异常情况，不会崩溃，{name}异常场景处理正确",
    }
}

# 示例2：用户信息功能的配置
USER_INFO_CONFIG = {
    'precondition_rules': {
        'default': '系统正常运行',
        'keywords': {
            '登录': '用户已登录系统',
            '用户': '用户已登录系统',
            '上传': '用户已登录，准备上传文件',
            '头像': '用户已登录，准备上传文件',
            '输入': '用户已登录，进入设置页面',
            '昵称': '用户已登录，进入设置页面',
            '显示': '用户已登录，进入个人主页',
            '粉丝': '用户已登录，进入个人主页',
            '关注': '用户已登录，进入个人主页',
        }
    },
    'test_step_rules': {
        '正向用例': lambda name, parent: f"1. 进入相关功能页面\n2. 执行操作：{name}\n3. 验证操作成功\n4. 验证功能正常",
        '负向用例': lambda name, parent: f"1. 进入相关功能页面\n2. 执行无效操作：{name}\n3. 验证系统提示错误信息\n4. 验证操作被拒绝",
        '边界值用例': lambda name, parent: f"1. 进入相关功能页面\n2. 输入边界值：{name}\n3. 验证系统处理\n4. 验证边界值处理正确",
        '异常用例': lambda name, parent: f"1. 进入相关功能页面\n2. 模拟异常场景：{name}\n3. 验证系统响应\n4. 验证系统不会崩溃",
    },
    'expected_result_rules': {
        '正向用例': lambda name, parent: f"操作成功，{name}功能正常，符合预期",
        '负向用例': lambda name, parent: f"系统正确提示错误信息，拒绝无效操作，{name}场景处理正确",
        '边界值用例': lambda name, parent: f"系统正确处理边界值情况：{name}，边界值验证通过",
        '异常用例': lambda name, parent: f"系统正确处理异常情况，不会崩溃，{name}异常场景处理正确",
    }
}

# 使用示例：
# from xmind_generator import XMindGenerator
# from config_example import TAOBAO_CONFIG
# 
# generator = XMindGenerator(config=TAOBAO_CONFIG)
# # 然后正常使用 generator 生成 XMind 文件
