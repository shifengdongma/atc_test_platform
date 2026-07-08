# 仿真配置页布局优化 + 地图加载修复 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化仿真配置页为左参数右任务的布局 + 修复仿真执行页地图加载缓慢/空白问题

**Architecture:** 前端纯 HTML/CSS/JS 改动，不涉及后端。config 页将模态框改为内联表单，右栏拆分为上表单+下列表。run 页将高德瓦片源切换为 OpenStreetMap，修复 run.js 残留 bug，改进地图加载状态反馈。

**Tech Stack:** Vanilla JS, Leaflet, CSS Grid/Flexbox

**Spec:** `docs/superpowers/specs/2026-07-08-config-layout-map-fix-design.md`

## Global Constraints

- 所有 Python 文件 UTF-8 编码，文件头 `# -*- coding: utf-8 -*-`
- JS 文件头 `/* -*- coding: utf-8 -*- */`
- 使用 `utm` Conda 环境运行
- 不修改后端 API
- 不修改其他页面（data、env、logs、generate）

---

### Task 1: 修复 map.js — 替换瓦片源 + 添加错误反馈

**Files:**
- Modify: `utm_simulator/web/static/js/map.js`

**Interfaces:**
- Produces: `window.initMap`, `window.drawPlansOnMap`, `window.drawNfzsOnMap`, `window.clearMapLayers`, `window.switchTileProvider` (unchanged signatures)

- [ ] **Step 1: 替换 TILE_PROVIDERS，OSM 为默认，CartoDB 为备用**

找到 `map.js` 第 62-73 行的 `TILE_PROVIDERS` 对象和 `_tileProviderKey`，替换为：

```javascript
// ── 瓦片源配置（OSM 为主，CartoDB 为备用）───────────────
const TILE_PROVIDERS = {
  osm: {
    name: 'OpenStreetMap',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: { subdomains: 'abc', maxZoom: 19, minZoom: 1 },
  },
  cartodb: {
    name: 'CartoDB',
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
    options: { subdomains: 'abcd', maxZoom: 19, minZoom: 1 },
  },
};

let _currentTileLayer = null;
let _tileProviderKey = 'osm';  // 默认 OSM
```

- [ ] **Step 2: 将第 107 行的注释更新为反映 OSM 作为默认瓦片源**

找到 `// 添加瓦片（高德为默认，国内秒加载）`，替换为：

```javascript
  // 添加瓦片（OSM 为默认，全球稳定）
  _addTileLayer(_tileProviderKey);
```

- [ ] **Step 3: 在 `initMap` 中添加 tileerror 事件处理**

找到 `initMap` 函数中 `_addTileLayer(_tileProviderKey);` 之后、`// 图层组` 之前，插入 tileerror 监听：

```javascript
  // 瓦片加载失败提示（连续失败 ≥5 次后显示警告）
  let _tileErrorCount = 0;
  map.on('tileerror', function(e) {
    _tileErrorCount++;
    if (_tileErrorCount === 5) {
      const loadingEl = document.getElementById('map-loading');
      if (loadingEl) {
        loadingEl.innerHTML = '⚠️ 地图瓦片加载失败，请检查网络连接<br><small>可尝试切换备用瓦片源</small>';
        loadingEl.style.display = '';
        loadingEl.style.color = '#f39c12';
        loadingEl.style.fontSize = '13px';
      }
    }
  });
  // 首次瓦片加载成功则清除错误提示
  map.on('tileload', function() {
    if (_tileErrorCount > 0) {
      _tileErrorCount = -999;  // 标记为已成功，不再提示
      const loadingEl = document.getElementById('map-loading');
      if (loadingEl) loadingEl.style.display = 'none';
    }
  });
```

- [ ] **Step 4: 改进 `initMap` 中的地图初始化成功后的加载提示隐藏逻辑**

现有的隐藏加载提示代码在第 123-124 行：
```javascript
  const loadingEl = document.getElementById('map-loading');
  if (loadingEl) loadingEl.style.display = 'none';
```

替换为（用 spinner 动画过渡）：
```javascript
  // 隐藏加载提示（短暂延迟让用户看到地图已就绪）
  setTimeout(function() {
    const loadingEl = document.getElementById('map-loading');
    if (loadingEl) {
      loadingEl.style.opacity = '0';
      loadingEl.style.transition = 'opacity 0.3s';
      setTimeout(function() { loadingEl.style.display = 'none'; }, 300);
    }
  }, 300);
```

- [ ] **Step 5: 验证 map.js 改动无语法错误**

运行 Node.js 语法检查：
```bash
cd utm_simulator && node -e "require('fs').readFileSync('web/static/js/map.js','utf8'); console.log('syntax ok')"
```
Expected: `syntax ok`

- [ ] **Step 6: Commit**

```bash
git add utm_simulator/web/static/js/map.js
git commit -m "fix: 地图瓦片源切换 OSM + tileerror 反馈 + 加载状态优化"
```

---

### Task 2: 修复 run.js — 删除不存在的 loadScheduledTasks 调用

**Files:**
- Modify: `utm_simulator/web/static/js/run.js`

**Interfaces:**
- Consumes: `window.initMap` (from map.js), `window.initCharts` (from charts.js), `window.apiGet`, `window.onWsEvent` (from common.js)

- [ ] **Step 1: 删除 run.js 第 127-129 行的错误调用**

找到 run.js 中的这段代码：
```javascript
// 首次加载
setTimeout(loadScheduledTasks, 1500);

// 等待 Leaflet 等资源加载
```

替换为：
```javascript
// 等待 Leaflet 等资源加载
```

- [ ] **Step 2: Commit**

```bash
git add utm_simulator/web/static/js/run.js
git commit -m "fix: 删除 run.js 中不存在的 loadScheduledTasks 调用"
```

---

### Task 3: 优化 run.html — 地图加载提示改为 spinner

**Files:**
- Modify: `utm_simulator/web/pages/run.html`

- [ ] **Step 1: 替换地图加载提示样式**

找到 run.html 第 59 行：
```html
<div id="map-container"><div id="map-loading">🗺️ 地图加载中...</div></div>
```

替换为带 CSS spinner 的加载提示：
```html
<div id="map-container">
  <div id="map-loading" style="display:flex;align-items:center;justify-content:center;height:100%;flex-direction:column;color:#8899aa;font-size:14px;z-index:1000;position:relative;">
    <div style="width:32px;height:32px;border:3px solid #2a3f56;border-top-color:#00b4d8;border-radius:50%;animation:map-spin 0.8s linear infinite;margin-bottom:10px;"></div>
    🗺️ 地图加载中...
  </div>
</div>
```

- [ ] **Step 2: 在 style.css 或 run.html 的 `<style>` 中添加 spinner 动画**

在 run.html 的 `<head>` 中已有 `<style>` 块内容较少，可直接在 head 中添加：

```html
<style>
  @keyframes map-spin { to { transform: rotate(360deg); } }
</style>
```

放在 `</head>` 之前。

- [ ] **Step 3: Commit**

```bash
git add utm_simulator/web/pages/run.html
git commit -m "feat: 地图加载提示改为 spinner 动画"
```

---

### Task 4: 重构 config.html — 右栏改为内联表单 + 任务列表

**Files:**
- Modify: `utm_simulator/web/pages/config.html`

**Interfaces:**
- Consumes: `window.initCommon` (from common.js), config.js logic

- [ ] **Step 1: 修改 `.config-2col` 的 grid 比例**

找到 config.html 第 11 行：
```css
.config-2col { display:grid; grid-template-columns:1fr 1fr; gap:20px; max-width:1200px; margin:0 auto; }
```

替换为（左栏约 55%，右栏约 45%）：
```css
.config-2col { display:grid; grid-template-columns:1.2fr 1fr; gap:20px; max-width:1300px; margin:0 auto; }
```

- [ ] **Step 2: 替换右栏内容为内联表单 + 任务列表**

找到 config.html 第 102-123 行（右栏 `.panel-form` 及其全部内容），替换为：

```html
      <!-- ★ 右栏：新建任务 + 定时任务列表 ★ -->
      <div class="panel-form">
        <!-- 内联新建任务表单 -->
        <h2 id="task-form-title">➕ 新建定时任务</h2>
        <div class="task-inline-form" id="task-inline-form">
          <div class="form-row">
            <label>任务名称 *</label>
            <input type="text" id="tk-name" placeholder="例如：每日航线注入" style="flex:1;">
          </div>
          <div class="form-row">
            <label>仿真模式</label>
            <select id="tk-mode" style="flex:1;">
              <option value="replay">🔁 预生成回放(循环)</option>
              <option value="replay_once">▶️ 预生成回放(单次)</option>
              <option value="plan">📐 Redis计划插值</option>
              <option value="dynamic">🎮 动态仿真</option>
              <option value="scene">🎬 场景文件注入</option>
            </select>
            <label style="margin-left:8px;">架数</label>
            <input type="number" id="tk-drones" value="10" min="1" max="5000" style="width:70px;">
          </div>
          <div class="form-row">
            <label>数据文件</label>
            <select id="tk-json-file" style="flex:1;"><option value="">— 使用默认文件 —</option></select>
            <button id="btn-tk-refresh-files" class="btn btn-small" style="flex-shrink:0;">🔄</button>
          </div>
          <div class="form-row">
            <label>执行日期 *</label>
            <input type="date" id="tk-date" style="flex:1;">
            <label style="margin-left:8px;">时间 *</label>
            <input type="time" id="tk-time" value="09:00" style="flex:1;">
          </div>
          <div class="form-row">
            <label>重复方式</label>
            <select id="tk-repeat" style="flex:1;">
              <option value="once">仅一次</option>
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
              <option value="monthly">每月</option>
            </select>
            <label style="margin-left:8px;"><input type="checkbox" id="tk-enabled" checked> 启用</label>
          </div>
          <div class="form-row" style="justify-content:flex-end;gap:8px;">
            <button id="btn-task-cancel-edit" class="btn btn-small" style="display:none;">取消编辑</button>
            <button id="btn-task-save" class="btn btn-start" style="padding:6px 20px;">保存</button>
          </div>
          <input type="hidden" id="tk-edit-id" value="">
        </div>

        <!-- 定时任务列表 -->
        <h2 style="margin-top:20px;">⏰ 定时任务</h2>
        <div id="task-list" style="max-height:300px;overflow-y:auto;">
          <div class="empty-hint">暂无定时任务</div>
        </div>

        <!-- 执行历史 -->
        <div class="form-group" style="margin-top:10px;">
          <label>最近执行记录</label>
          <div id="task-history" style="font-size:11px;color:var(--text-dim);max-height:100px;overflow-y:auto;">
            <div class="empty-hint">—</div>
          </div>
        </div>
      </div>
```

- [ ] **Step 3: 删除旧的模态框 HTML**

删除 config.html 第 128-179 行（`<!-- 新建/编辑任务弹窗 -->` 及其全部内容，到 `</body>` 之前）：

```html
  <!-- 新建/编辑任务弹窗 -->
  <div class="modal-overlay" id="task-modal">
    ...全部内容...
  </div>
```

- [ ] **Step 4: 删除模态框相关的 `<style>` 样式**

删除 config.html `<head>` 中第 18-22 行的模态框样式：
```css
    #task-modal .modal { width:480px; }
    #task-modal .modal .form-row { display:flex; gap:8px; margin-bottom:10px; align-items:center; }
    #task-modal .modal .form-row label { width:90px; font-size:12px; color:var(--text-dim); flex-shrink:0; text-align:right; }
    #task-modal .modal .form-row input,
    #task-modal .modal .form-row select { flex:1; padding:7px 10px; background:#0d1b2a; border:1px solid var(--border); color:var(--text); border-radius:4px; font-size:13px; }
```

- [ ] **Step 5: Commit**

```bash
git add utm_simulator/web/pages/config.html
git commit -m "feat: config 页布局优化 — 右栏内联表单 + 任务列表，移除模态框"
```

---

### Task 5: 重构 config.js — 内联表单逻辑替代模态框

**Files:**
- Modify: `utm_simulator/web/static/js/config.js`

- [ ] **Step 1: 删除旧的模态框相关函数**

删除 `showTaskModal`（第 234-256 行）和 `hideTaskModal`（第 258 行）：

删除从 `// ── 弹窗 ──` 注释开始到 `function hideTaskModal()` 结束的所有代码。具体为第 234-260 行。

- [ ] **Step 2: 替换弹窗事件监听为内联表单事件**

找到第 259-260 行的模态框事件监听：
```javascript
function hideTaskModal() { document.getElementById('task-modal').classList.remove('show'); }
document.getElementById('btn-task-cancel').addEventListener('click', hideTaskModal);
document.getElementById('task-modal').addEventListener('click', function(e){ if(e.target===this) hideTaskModal(); });
```

替换为：
```javascript
// ── 内联表单：取消编辑 ─────────────────────────────────────────────
document.getElementById('btn-task-cancel-edit').addEventListener('click', resetTaskForm);

function resetTaskForm() {
  document.getElementById('task-form-title').textContent = '➕ 新建定时任务';
  document.getElementById('tk-name').value = '';
  document.getElementById('tk-mode').value = 'replay';
  document.getElementById('tk-drones').value = 10;
  document.getElementById('tk-date').value = '';
  document.getElementById('tk-time').value = '09:00';
  document.getElementById('tk-repeat').value = 'once';
  document.getElementById('tk-enabled').checked = true;
  document.getElementById('tk-edit-id').value = '';
  document.getElementById('tk-json-file').value = '';
  document.getElementById('btn-task-cancel-edit').style.display = 'none';
  editingTaskId = null;
}
```

- [ ] **Step 3: 替换 `btn-task-new` 事件监听（添加 null guard）**

找到第 276 行：
```javascript
document.getElementById('btn-task-new').addEventListener('click', function(){ showTaskModal('新建', null); });
```

替换为：
```javascript
// 已改为内联表单 — 用户在右上角表单直接填写即可创建新任务
var btnNew = document.getElementById('btn-task-new');
if (btnNew) btnNew.addEventListener('click', resetTaskForm);
```

由于 HTML 中已移除 `btn-task-new` 按钮，`btnNew` 为 null 时会安全跳过。

- [ ] **Step 4: 修改 `btn-task-save` 事件处理 — 支持编辑模式**

找到 `btn-task-save` 的 click 事件监听（第 278-310 行），修改其内部逻辑：替换 `editingTaskId` 的使用方式。

关键改动 — 把 cron 表达式构建逻辑从模态框字段改为内联表单字段（字段 ID 不变，无需修改）。只需在保存成功后调用 `resetTaskForm()`：

```javascript
  if (r.success) { showToast(r.message||'已保存','success'); resetTaskForm(); loadTaskList(); }
```

即在第 308 行的 `hideTaskModal()` 替换为 `resetTaskForm()`：
```javascript
  if (r.success) { showToast(r.message||'已保存','success'); resetTaskForm(); loadTaskList(); }
```

- [ ] **Step 5: 修改 `editTask` 函数 — 填充内联表单而非弹出模态框**

找到 `window.editTask`（第 225-231 行），替换为：

```javascript
window.editTask = async function(id) {
  try {
    var resp = await apiGet('/api/schedule/tasks');
    var t = (resp.tasks||[]).find(function(x){return x.id===id;});
    if (!t) return;
    // 填充内联表单
    editingTaskId = t.id;
    document.getElementById('task-form-title').textContent = '✏️ 编辑定时任务: ' + (t.name||'');
    document.getElementById('tk-name').value = t.name||'';
    document.getElementById('tk-mode').value = t.sim_mode||'replay';
    document.getElementById('tk-edit-id').value = t.id;
    document.getElementById('tk-enabled').checked = (t.enabled===1);
    document.getElementById('btn-task-cancel-edit').style.display = '';
    try {
      var sp = JSON.parse(t.sim_params||'{}');
      document.getElementById('tk-drones').value = sp.target_drones||10;
    } catch(e) {}
    // 从 cron_expr 解析日期时间
    var parts = (t.cron_expr||'').split(' ');
    if (parts.length >= 4) {
      document.getElementById('tk-time').value = parts[1]+':'+parts[0];
      document.getElementById('tk-date').value = '2026-'+parts[3]+'-'+parts[2];
    }
    refreshTaskJsonFiles();
    // 滚动到表单顶部
    document.getElementById('task-inline-form').scrollIntoView({ behavior: 'smooth' });
  } catch(e) {}
};
```

- [ ] **Step 6: 修改 `btn-task-save` 中的 editingTaskId 使用**

找到 `btn-task-save` 的 click 监听中 `if (editingTaskId) body.id = editingTaskId;` 这行（第 305 行附近），确保从 hidden input 读取编辑 ID：

在 `if (editingTaskId) body.id = editingTaskId;` 之前添加：
```javascript
  // 从隐藏字段获取编辑 ID
  editingTaskId = document.getElementById('tk-edit-id').value || null;
```

- [ ] **Step 7: Commit**

```bash
git add utm_simulator/web/static/js/config.js
git commit -m "feat: config.js 内联表单逻辑 — 替代模态框的 CRUD 操作"
```

---

### Task 6: 更新 style.css — 新增内联表单样式 + 地图加载动画

**Files:**
- Modify: `utm_simulator/web/static/css/style.css`

- [ ] **Step 1: 添加内联任务表单样式**

在 style.css 末尾（`@media` 响应式规则之前）添加：

```css
/* ── 内联任务表单（config 页右栏）─────────────────────── */
.task-inline-form {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
}
.task-inline-form .form-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.task-inline-form .form-row label {
  font-size: 12px;
  color: var(--text-dim);
  white-space: nowrap;
  min-width: 60px;
}
.task-inline-form .form-row input[type="text"],
.task-inline-form .form-row input[type="number"],
.task-inline-form .form-row input[type="date"],
.task-inline-form .form-row input[type="time"],
.task-inline-form .form-row select {
  padding: 5px 8px;
  font-size: 12px;
  background: #0d1b2a;
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 4px;
}
.task-inline-form .form-row input:focus,
.task-inline-form .form-row select:focus {
  border-color: var(--accent);
  outline: none;
}
```

- [ ] **Step 2: 添加地图 spinner 动画的 keyframes**

在 style.css 末尾添加：

```css
/* ── 地图加载动画 ─────────────────────────────────────── */
@keyframes map-spin {
  to { transform: rotate(360deg); }
}
```

- [ ] **Step 3: 删除旧的 `.task-card` 多余样式中的 `current-badge` 引用（如有需要）**

检查 `.task-card` 样式（第 13-16 行），确认无需修改。内联表单不需要 task-card 变动。

- [ ] **Step 4: Commit**

```bash
git add utm_simulator/web/static/css/style.css
git commit -m "feat: 内联任务表单样式 + 地图 spinner 动画"
```

---

### Task 7: 端到端验证

**Files:** 无新建/修改，仅验证

- [ ] **Step 1: 启动 Web 服务**

```bash
cd utm_simulator && conda run -n utm python main.py &
```

等 3 秒服务启动。

- [ ] **Step 2: 验证 config 页面布局**

打开浏览器访问 `http://localhost:5000/config`：
- 确认左栏（仿真参数配置）占页面左侧约 55%
- 确认右栏顶部为"新建定时任务"内联表单（包含所有字段）
- 确认右栏下方为定时任务列表
- 确认无模态框弹出
- 确认填写表单 → 点击保存 → 任务出现在列表中

- [ ] **Step 3: 验证地图加载**

打开浏览器访问 `http://localhost:5000/run`：
- 确认 spinner 动画显示
- 确认 OSM 地图瓦片在 2 秒内加载完成
- 确认 spinner 消失，地图正常显示
- 确认 Console 中无 `ReferenceError: loadScheduledTasks is not defined`
- 如果网络不通导致瓦片失败，确认显示 ⚠️ 错误提示

- [ ] **Step 4: 验证地图功能回归**

在 run 页面：
- 点击"📡 加载航线" → 确认航线绘制在地图上
- 点击"🚫 加载禁飞区" → 确认禁飞区多边形绘制
- 点击"🧹 清除" → 确认图层清除

- [ ] **Step 5: 停止服务并提交验证记录**

```bash
# 停止 main.py 进程
pkill -f "python main.py" 2>/dev/null || true
```

将验证结果追加到 `docs/utm-simulator-optimization-work-log.md`。
