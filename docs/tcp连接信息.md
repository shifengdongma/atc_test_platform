一、环境搭建
1，现场部署后端服务la-atc-data-exchange-afr-agent
2，现场部署后端服务la-atc-beidou-grid-backend
3，在la-atc-data-exchange-afr-agent服务的统一配置中配置代理程序地址和联调无人机的编号
4，代理程序通过tcp的端口进行链接
5，访问仿真代理程序系统，配置TCP服务的地址和端口
 
// 仿真代理程序系统页面
https://dkkgsit-test.testdolphin.com/la-atc-beidou-grid-backend/web
// 配置TCP服务的地址和端口
// 内网
host: dkkgsit-test.testdolphin.com
port: 28598

6，访问tcp状态页面，查看tcp客户端的链接情况，需要配置TCP服务器地址，即SIT的https://dkkgsit-test.testdolphin.com/la-atc-data-exchange-afr-agent的地址。配置完成后点击刷新列表，预期配置后目标客户端有新的连接。这个ip地址就是代理程序的ip地址，可以用于步骤3， 在统一配置中配置代理程序地址和联调无人机的编号
 
//tcp状态页面
https://dkkgsit-test.testdolphin.com/la-atc-beidou-grid-backend/tcp
二、测试模拟无人机上态势大屏
1, 模拟器中起飞模拟的无人机，地点选择附近无人机比较少的区域, 便于观察
2，代理程序根据通信协议上报数据。
3，观察态势大屏上是否可以看到模拟的无人机。
备注：仿真代理程序可以通过界面上的模拟飞行来达到类型的效果，配合键盘上面的上下左右键可以控制无人机上升，下降，左转和右转
// 仿真代理程序系统页面
https://dkkgsit-test.testdolphin.com/la-atc-beidou-grid-backend/web
 
三、下发飞行计划
1，在运营人管理/航空器管理中将模拟的无人机登记
https://dkkgsit-test.testdolphin.com/atc/drone-management
2，新建飞行计划，并将飞行计划分到测试的模拟无人机
3，代理程序观察日志中是否有下发飞行计划的日志
四、其他指令联调
1，访问tcp网站，查看tcp客户端的链接情况。
https://dkkgsit-test.testdolphin.com/la-atc-beidou-grid-backend/tcp
2， 选择对应的指令模板和代理程序客户端
3， 调整json中的部分参数，比如uav_id等
 
4， 点击发送到客户端
5， 代理程序观察是否有对应的指令消息（仿真代理程序可以通过在线日志查看）
https://dkkgsit-test.testdolphin.com/la-atc-beidou-grid-backend/api/tcp/logs
 

五、冲突碰撞测试
1，局参数设置中关闭只有带有飞行计划的航空器才做冲突告警检测
2，启动两架模拟的无人机，并控制无人机的方向，使其不断接近，观察告警
