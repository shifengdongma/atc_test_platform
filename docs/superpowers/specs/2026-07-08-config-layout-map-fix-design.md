# 仿真配置页布局优化 + 地图加载修复 — 设计文档

**日期**: 2026-07-08
**版本**: v1.0

---

## 1. 仿真配置页布局优化

### 1.1 当前状态

`config.html` 使用 `.config-2col` 两栏网格（`grid-template-columns: 1fr 1fr`）：
- 左栏：仿真参数配置（运行模式、无人机数量、禁飞区、连接信息、启动/停止按钮、运行历史）
- 右栏：定时任务列表 + header 中的 "➕ 新建任务" 按钮

"新建/编辑定时任务" 是模态框（`#task-modal`），包含任务名称、仿真模式、JSON 文件、目标架数、运行时长、执行日期/时间、重复方式等字段。

### 1.2 目标布局

- **左半块（约 55%）**：仿真参数配置，保持现有内容不变
- **右半块（约 45%）**：
  - 上半部分：内联"新建定时任务"表单（紧凑型）
  - 下半部分：已有定时任务列表（可滚动）
  - 去掉模态框，所有操作在页面内完成

### 1.3 改动文件

| 文件 | 操作 |
|------|------|
| `utm_simulator/web/pages/config.html` | 修改：右侧面板改为上表单+下列表，移除模态框 |
| `utm_simulator/web/static/js/config.js` | 修改：内联表单保存逻辑替代模态框逻辑，去掉 `showTaskModal`/`hideTaskModal` |
| `utm_simulator/web/static/css/style.css` | 修改：新增内联表单样式 |

### 1.4 内联表单字段（紧凑型）

保留核心字段，去掉冗余：
- 任务名称 *
- 仿真模式（下拉）
- JSON 数据文件（下拉 + 刷新按钮）
- 目标架数
- 执行日期 * / 执行时间 *
- 重复方式
- 创建后立即启用（checkbox）
- 保存按钮

编辑已有任务时，表单顶部显示"编辑: <任务名>"，表单预填现有值，保存时更新而非新建。

### 1.5 CSS 调整

```css
.config-2col { grid-template-columns: 1.2fr 1fr; }  /* 左栏略宽 */
.task-inline-form { /* 紧凑表单，字段水平排列 */ }
.task-inline-form .form-row { display: flex; gap: 8px; align-items: center; }
```

---

## 2. 地图加载缓慢/空白修复

### 2.1 根因分析

1. **瓦片源 URL 过期**：`map.js` 使用高德旧版瓦片域名 `webrd0{s}.is.autonavi.com`。高德在 2024-2025 年迁移了瓦片服务，旧域名响应变慢或间歇性不可用。`errorTileUrl: ''` 导致瓦片失败时静默空白。

2. **`run.js` 残留 bug**：第 128 行 `setTimeout(loadScheduledTasks, 1500);` 调用了一个不存在的函数（`ReferenceError`）。虽然不直接导致地图空白，但会在控制台报错。

3. **无加载失败反馈**：用户看到 `🗺️ 地图加载中...` 后如果瓦片全部加载失败，没有任何错误提示。

### 2.2 修复方案

| 项目 | 修复 |
|------|------|
| 主瓦片源 | 高德旧域名 → **OpenStreetMap**（稳定可靠，全球可用） |
| 备用瓦片源 | 保留 CartoDB，新增高德新域名作为可选手动切换 |
| `loadScheduledTasks` bug | 删除 run.js 第 128-129 行 |
| 加载失败反馈 | 瓦片 `tileerror` 事件 → 显示"地图瓦片加载失败"提示 |
| 加载状态改进 | 用 spinner 替代纯文字提示，map 初始化成功后隐藏 |

### 2.3 新瓦片配置

```javascript
const TILE_PROVIDERS = {
  osm: {
    name: 'OpenStreetMap',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: { maxZoom: 19, attribution: '© OpenStreetMap' },
  },
  cartodb: {
    name: 'CartoDB',
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
    options: { subdomains: 'abcd', maxZoom: 19 },
  },
};
```

默认使用 OSM，保留 CartoDB 作为备选。

### 2.4 改动文件

| 文件 | 操作 |
|------|------|
| `utm_simulator/web/static/js/map.js` | 修改：瓦片源替换 OSM，新增 tileerror 处理，改进加载状态 |
| `utm_simulator/web/static/js/run.js` | 修改：删除 `loadScheduledTasks` 调用 |
| `utm_simulator/web/pages/run.html` | 修改：地图加载提示改为 spinner |

---

## 3. 验证方式

1. **布局验证**：打开 `/config` 页面，确认左参数右任务布局，内联表单可正常新建/编辑任务
2. **地图验证**：打开 `/run` 页面，确认 OSM 瓦片在 2 秒内加载完成，不再空白
3. **回归测试**：确认"启动仿真""加载航线""加载禁飞区"功能正常
4. **Console 检查**：确认无 `ReferenceError: loadScheduledTasks is not defined` 错误

---

## 4. 不涉及的部分

- 后端 API 无改动
- 定时任务调度逻辑不变
- 航线/禁飞区绘制逻辑不变
- 其他页面（data、env、logs、generate）不变
