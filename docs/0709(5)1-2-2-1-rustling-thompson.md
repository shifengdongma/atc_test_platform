# 页面重构实施计划

## 背景

将现有6个功能页面重组为9个，合并"仿真配置"+"仿真执行"为统一的三栏"仿真执行"页，"定时任务"独立为单独页面，新增3个占位页面，为所有页面添加左侧功能导航栏。

## 实施步骤

### 1. 更新 `web/static/js/common.js` — 导航栏 + 侧边栏

- 更新 `NAV_PAGES` 数组为9项：`/run`(仿真执行), `/schedule`(定时任务), `/generate`(数据生成), `/data`(数据管理), `/basicdata`(基础数据), `/performance`(性能), `/ha`(高可用), `/env`(环境管理), `/logs`(系统日志)
- 新增 `window.renderSidebar(activePath)` 函数，在 `#left-sidebar` 中渲染垂直导航菜单
- 在 `initCommon()` 中同时调用 `renderNavbar()` 和 `renderSidebar()`

### 2. 更新 `web/static/css/style.css` — 新布局样式

- 添加 `.app-layout` — 水平flex容器，包裹侧边栏+主内容区
- 添加 `#left-sidebar` / `.sidebar-header` / `.sidebar-item` 侧边栏样式
- 添加 `.dashboard-3col` — 三栏等宽grid布局
- 添加 `.placeholder-page` — 占位页面居中样式
- 添加 `.env-selector` — 环境选择器样式

### 3. 更新 `utm_simulator/web_server.py` — 路由

- `/` 重定向从 `/config` 改为 `/run`
- `/config` 改为重定向到 `/run`
- 新增4个页面路由：`/schedule`, `/performance`, `/ha`, `/basicdata`

### 4. 创建5个新文件

| 文件 | 说明 |
|------|------|
| `web/pages/schedule.html` | 从config.html右栏提取的定时任务独立页面 |
| `web/static/js/schedule.js` | 从config.js提取任务管理逻辑 |
| `web/pages/performance.html` | 占位页 — 性能监控 |
| `web/pages/ha.html` | 占位页 — 高可用 |
| `web/pages/basicdata.html` | 占位页 — 基础数据 |

### 5. 重写 `web/pages/run.html` — 三栏合并页

**左栏(~33%)**：仿真参数配置（运行模式、场景/回放/plan参数、无人机数量、禁飞区、环境选择器[替代"连接信息"]、启动/停止/测试按钮、运行历史）

**中栏(~33%)**：实时监控（6张状态卡、2张趋势图、运行日志[含类型过滤复选框+导出按钮]）

**右栏(~33%)**：飞行计划可视化（Leaflet地图+工具栏+图例）

### 6. 重写 `web/static/js/run.js` — 合并逻辑

合并 config.js（模式切换、参数表单、启停控制、历史）+ run.js（监控更新updateMonitor、图表addChartData、地图loadFlightPlans/loadNoFlyZones、日志addLog）+ 环境选择器（loadEnvSelector加载env列表、激活按钮）+ 日志类型过滤

### 7. 修改4个现有页面 — 添加侧边栏包装

对 `generate.html`, `data.html`, `env.html`, `logs.html`：在 `<header>` 和 `<main>` 之间插入 `<div class="app-layout"><aside id="left-sidebar"></aside>`，`</main>`之后加 `</div>`

### 8. 简化 `web/pages/config.html` — 跳转页

将config.html替换为简单的meta-refresh跳转页，跳转到 `/run`

## 验证方式

1. 启动 Flask 服务：`conda run -n utm python utm_simulator/web_server.py`
2. 访问 `http://localhost:5000/` → 应重定向到 `/run`
3. 访问 `/run` → 三栏布局正常显示，左侧栏有9个导航项
4. 测试环境选择器：下拉框显示环境列表，点击激活生效
5. 访问 `/schedule` → 定时任务管理页正常，可创建/编辑/删除任务
6. 访问 `/performance`, `/ha`, `/basicdata` → 显示占位内容
7. 访问 `/generate`, `/data`, `/env`, `/logs` → 侧边栏正常显示
8. 访问 `/config` → 自动跳转到 `/run`
9. 确认"连接信息"(Redis/Kafka输入框+保存按钮)已从新run页删除
