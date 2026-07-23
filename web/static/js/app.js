/* -*- coding: utf-8 -*- */
/* UTM 模拟器控制台 — 主逻辑 */

(function() {
'use strict';

// ── 常量 ────────────────────────────────────────────────────────
const API_BASE = '';

// ── 状态 ────────────────────────────────────────────────────────
let isRunning = false;
let logs = [];
let history = [];

// ── DOM 引用 ────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const dom = {
  // 连接状态
  connDot: $('#connection-dot'),
  connText: $('#connection-text'),
  simBadge: $('#sim-status-badge'),

  // 配置
  modeSelect: $('#mode-select'),
  targetDrones: $('#target-drones'),
  dronesValue: $('#drones-value'),
  nfzEnabled: $('#nfz-enabled'),
  nfzCount: $('#nfz-count'),
  cfgRedisHost: $('#cfg-redis-host'),
  cfgRedisPort: $('#cfg-redis-port'),
  cfgKafkaUrl: $('#cfg-kafka-url'),
  apiMode: $('#api-mode'),

  // 按钮
  btnStart: $('#btn-start'),
  btnStop: $('#btn-stop'),
  btnTestConn: $('#btn-test-conn'),
  connTestResult: $('#conn-test-result'),

  // 监控
  indRedis: $('#ind-redis'),
  redisStatus: $('#redis-status'),
  indKafka: $('#ind-kafka'),
  kafkaStatus: $('#kafka-status'),
  dronesCount: $('#drones-count'),
  redisTp: $('#redis-tp'),
  uptime: $('#uptime'),
  errorCount: $('#error-count'),
  logStream: $('#log-stream'),

  // 历史
  historyList: $('#history-list'),

  // 地图按钮
  btnLoadPlans: $('#btn-load-plans'),
  btnLoadNfzs: $('#btn-load-nfzs'),
  btnClearMap: $('#btn-clear-map'),
  mapStats: $('#map-stats'),
  mapLegend: $('#map-legend'),

  // plan 模式航线选择
  planRouteList: $('#plan-route-list'),
  planSelectAll: $('#btn-plan-select-all'),
  planDeselectAll: $('#btn-plan-deselect-all'),
  planRouteSummary: $('#plan-route-summary'),
};

// ── WebSocket 连接 ──────────────────────────────────────────────
const socket = io({ transports: ['websocket', 'polling'] });

socket.on('connect', () => {
  dom.connDot.className = 'dot green';
  dom.connText.textContent = '已连接';
  fetchStatus();
  fetchConfig();
});

socket.on('disconnect', () => {
  dom.connDot.className = 'dot red';
  dom.connText.textContent = '已断开';
});

socket.on('status', (data) => {
  updateMonitor(data);
});

socket.on('status_change', (data) => {
  addLog(data.message);
  if (data.event === 'started') {
    setRunningState(true);
  } else if (data.event === 'stopped') {
    setRunningState(false);
  } else if (data.event === 'starting') {
    dom.simBadge.textContent = '启动中';
    dom.simBadge.className = 'badge starting';
  }
});

socket.on('log', (data) => {
  addLog(data.message);
});

// ── API 调用 ────────────────────────────────────────────────────
async function apiGet(path) {
  const resp = await fetch(API_BASE + path);
  return resp.json();
}

async function apiPost(path, body) {
  const resp = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return resp.json();
}

async function fetchStatus() {
  const data = await apiGet('/api/sim/status');
  updateMonitor(data);
  if (data.running) {
    setRunningState(true);
  }
}

async function fetchConfig() {
  const data = await apiGet('/api/sim/config');
  dom.modeSelect.value = data.mode || 'scene';
  dom.targetDrones.value = data.target_drones || 100;
  dom.dronesValue.textContent = data.target_drones || 100;
  dom.nfzEnabled.checked = data.nfz_enabled !== false;
  dom.nfzCount.value = data.nfz_count || 3;
  dom.nfzCount.disabled = !dom.nfzEnabled.checked;
  dom.apiMode.checked = data.api_mode || false;
  dom.cfgRedisHost.value = data.redis_ip || '127.0.0.1';
  dom.cfgRedisPort.value = data.redis_port || '6379';
  dom.cfgKafkaUrl.value = data.kafka_url || '127.0.0.1:9092';
}

// ── 监控面板更新 ────────────────────────────────────────────────
function updateMonitor(data) {
  if (data.redis_connected !== undefined) {
    dom.indRedis.className = 'indicator ' + (data.redis_connected ? 'green' : 'red');
    dom.redisStatus.textContent = data.redis_connected ? '已连接' : '未连接';
  }
  if (data.kafka_connected !== undefined) {
    dom.indKafka.className = 'indicator ' + (data.kafka_connected ? 'green' : 'red');
    dom.kafkaStatus.textContent = data.kafka_connected ? '已连接' : '未连接';
  }
  if (data.active_drones !== undefined) {
    dom.dronesCount.textContent = data.active_drones;
    addChartData('drones', data.active_drones);
  }
  if (data.redis_msg_per_sec !== undefined) {
    dom.redisTp.innerHTML = `${data.redis_msg_per_sec} <small>条/秒</small>`;
    addChartData('redis', data.redis_msg_per_sec);
  }
  if (data.uptime_sec !== undefined) {
    dom.uptime.textContent = formatDuration(data.uptime_sec);
  }
  if (data.errors !== undefined) {
    dom.errorCount.textContent = data.errors;
  }
  if (data.logs) {
    logs = data.logs;
    renderLogs();
  }
}

// ── 日志 ─────────────────────────────────────────────────────────
function addLog(msg) {
  logs.push(msg);
  if (logs.length > 50) logs = logs.slice(-50);
  renderLogs();
}

function renderLogs() {
  if (logs.length === 0) {
    dom.logStream.innerHTML = '<div class="log-empty">等待日志...</div>';
    return;
  }
  dom.logStream.innerHTML = logs.map(l => `<div class="log-line">${escHtml(l)}</div>`).join('');
  dom.logStream.scrollTop = dom.logStream.scrollHeight;
}

function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── 运行状态 ─────────────────────────────────────────────────────
function setRunningState(running) {
  isRunning = running;
  dom.btnStart.disabled = running;
  dom.btnStop.disabled = !running;
  dom.modeSelect.disabled = running;
  dom.targetDrones.disabled = running;
  dom.nfzEnabled.disabled = running;
  dom.nfzCount.disabled = running || !dom.nfzEnabled.checked;
  dom.apiMode.disabled = running;
  // 禁用 scene 模式参数
  var sceneParams = document.getElementById('scene-params');
  if (sceneParams) {
    sceneParams.querySelectorAll('input,select,button').forEach(function(el) { el.disabled = running; });
  }
  var replayParams = document.getElementById('replay-params');
  if (replayParams) {
    replayParams.querySelectorAll('input,select,button').forEach(function(el) { el.disabled = running; });
  }
  var planParams = document.getElementById('plan-params');
  if (planParams) {
    planParams.querySelectorAll('input,button').forEach(function(el) { el.disabled = running; });
  }
  dom.simBadge.textContent = running ? '运行中' : '已停止';
  dom.simBadge.className = 'badge ' + (running ? 'running' : 'stopped');
}

function formatDuration(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// ── 事件绑定 ─────────────────────────────────────────────────────

// 滑块同步
dom.targetDrones.addEventListener('input', () => {
  dom.dronesValue.textContent = dom.targetDrones.value;
});

// 禁飞区开关
dom.nfzEnabled.addEventListener('change', () => {
  dom.nfzCount.disabled = !dom.nfzEnabled.checked || isRunning;
});

	// 启动仿真（支持所有模式的参数）
	dom.btnStart.addEventListener('click', async () => {
	  const mode = dom.modeSelect.value;
	  const body = {
	    mode: mode,
	    target_drones: parseInt(dom.targetDrones.value),
	    nfz_enabled: dom.nfzEnabled.checked,
	    nfz_count: parseInt(dom.nfzCount.value) || 0,
	  };
	  // scene 模式参数
	  if (mode === 'scene') {
	    var sfSel = document.getElementById('scene-file-select');
	    body.scene_files = sfSel ? Array.from(sfSel.selectedOptions).map(o => o.value) : [];
	    body.scene_interval = parseInt(document.getElementById('scene-interval')?.value || 1000);
	    body.timestamp_mode = document.getElementById('scene-timestamp-mode')?.value || 'replace';
	    body.scene_loop = document.getElementById('scene-loop')?.checked || false;
	  }
	  // plan 模式参数
	  if (mode === 'plan') {
	    body.plan_selected_uids = getSelectedPlanUids();
	  }
	  const result = await apiPost('/api/sim/start', body);
	  if (result.success) {
	    addLog('✅ ' + result.message);
	    setRunningState(true);
	    addHistory(true, mode + ' | ' + body.target_drones + ' 架');
	  } else {
	    addLog('❌ ' + result.message);
	    addHistory(false, result.message);
	  }
	});

// 停止仿真
dom.btnStop.addEventListener('click', async () => {
  const result = await apiPost('/api/sim/stop');
  if (result.success) {
    addLog('✅ ' + result.message);
    setRunningState(false);
  } else {
    addLog('⚠️ ' + result.message);
  }
});

// 测试连接
dom.btnTestConn.addEventListener('click', async () => {
  dom.connTestResult.textContent = '测试中...';
  const result = await apiGet('/api/sim/test-connection');
  const redisOk = result.redis ? 'OK' : 'FAIL';
  const kafkaOk = result.kafka ? 'OK' : 'FAIL';
  dom.connTestResult.textContent = 'Redis ' + redisOk + ' Kafka ' + kafkaOk;
});

// 保存连接配置
document.getElementById('btn-save-conn').addEventListener('click', async () => {
  const resultEl = document.getElementById('conn-save-result');
  resultEl.textContent = '保存中...';
  const body = {
    redis_ip: dom.cfgRedisHost.value,
    redis_port: dom.cfgRedisPort.value,
    kafka_url: dom.cfgKafkaUrl.value,
  };
  try {
    const result = await apiPost('/api/sim/config/save', body);
    if (result.success) {
      resultEl.textContent = 'OK: ' + result.message;
      addLog('连接配置已保存: ' + body.redis_ip + ':' + body.redis_port);
    } else {
      resultEl.textContent = 'FAIL: ' + (result.message || result.error || '');
    }
  } catch (e) {
    resultEl.textContent = 'Error: ' + e.message;
  }
});

// 加载航线
dom.btnLoadPlans.addEventListener('click', () => {
  loadFlightPlans();
});

// 加载禁飞区
dom.btnLoadNfzs.addEventListener('click', () => {
  loadNoFlyZones();
});

// 清除地图
dom.btnClearMap.addEventListener('click', () => {
  clearMap();
});

// ── 运行历史 ─────────────────────────────────────────────────────
function addHistory(success, detail) {
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  history.unshift({ time, success, detail });
  if (history.length > 20) history = history.slice(0, 20);
  renderHistory();
}

function renderHistory() {
  if (history.length === 0) {
    dom.historyList.innerHTML = '<li class="empty-hint">暂无运行记录</li>';
    return;
  }
  dom.historyList.innerHTML = history.map(h =>
    `<li class="${h.success ? 'success' : 'error'}">[${h.time}] ${h.detail}</li>`
  ).join('');
}

// ── 地图功能桥接 ─────────────────────────────────────────────────
async function loadFlightPlans() {
  try {
    const data = await apiGet('/api/sim/plans?limit=200');
    if (data.error) {
      addLog('⚠️ 获取航线失败: ' + data.error);
      return;
    }
    drawFlightPlans(data.plans || []);
    dom.mapStats.textContent =
      `航线: ${data.plans?.length || 0} | 总计: ${data.total || 0} | 禁飞区: ${window._currentNfzCount || 0}`;
    addLog(`已加载 ${data.plans?.length || 0}/${data.total || 0} 条航线到地图`);

    // 同步更新 plan 模式航线选择列表
    populatePlanRouteList(data.plans || []);
  } catch (e) {
    addLog('❌ 加载航线异常: ' + e.message);
  }
}

async function loadNoFlyZones() {
  try {
    const data = await apiGet('/api/sim/nfzs');
    if (data.error) {
      addLog('⚠️ 获取禁飞区失败: ' + data.error);
      return;
    }
    drawNoFlyZones(data.nfzs || []);
    window._currentNfzCount = data.nfzs?.length || 0;
    dom.mapStats.textContent =
      `航线: ${currentPlanCount || 0} | 总计: -- | 禁飞区: ${data.nfzs?.length || 0}`;
    addLog(`已加载 ${data.nfzs?.length || 0} 个禁飞区到地图`);
  } catch (e) {
    addLog('❌ 加载禁飞区异常: ' + e.message);
  }
}

// ── Plan 模式：航线选择列表 ────────────────────────────────────────
function populatePlanRouteList(plans) {
  // plans = [{uid, routeData, fpCount, minTakeoff, maxLand, ...}, ...]
  if (!dom.planRouteList) return;
  if (!plans || plans.length === 0) {
    dom.planRouteList.innerHTML = '<div class="empty-hint">Redis 中暂无航线数据</div>';
    dom.planRouteSummary.textContent = '';
    return;
  }
  var html = '';
  for (var i = 0; i < plans.length; i++) {
    var p = plans[i];
    var uid = p._uid || p.uniqueProductIdentificationCode || '未知';
    var fpCount = p._fpCount || 0;
    var checked = ' checked';
    html += '<label class="plan-route-item">' +
      '<input type="checkbox" class="plan-route-cb" value="' + escHtml(uid) + '"' + checked + '>' +
      '<span class="plan-route-uid">' + escHtml(uid) + '</span>' +
      '<span class="plan-route-info">' + fpCount + ' 个计划</span>' +
    '</label>';
  }
  dom.planRouteList.innerHTML = html;
  updatePlanRouteSummary();
}

function getSelectedPlanUids() {
  var cbs = document.querySelectorAll('.plan-route-cb:checked');
  var uids = [];
  for (var i = 0; i < cbs.length; i++) {
    uids.push(cbs[i].value);
  }
  return uids;
}

function updatePlanRouteSummary() {
  if (!dom.planRouteSummary) return;
  var total = document.querySelectorAll('.plan-route-cb').length;
  var sel = document.querySelectorAll('.plan-route-cb:checked').length;
  dom.planRouteSummary.textContent = '已选 ' + sel + ' / ' + total + ' 条航线';
}

// 全选
if (dom.planSelectAll) {
  dom.planSelectAll.addEventListener('click', function() {
    document.querySelectorAll('.plan-route-cb').forEach(function(cb) { cb.checked = true; });
    updatePlanRouteSummary();
  });
}

// 取消全选
if (dom.planDeselectAll) {
  dom.planDeselectAll.addEventListener('click', function() {
    document.querySelectorAll('.plan-route-cb').forEach(function(cb) { cb.checked = false; });
    updatePlanRouteSummary();
  });
}

// 供 map.js 使用的全局变量
let currentPlanCount = 0;
window._currentNfzCount = 0;

// 导出供 map.js 调用
window.drawFlightPlans = function(plans) {
  currentPlanCount = plans.length;
  if (typeof drawPlansOnMap === 'function') {
    drawPlansOnMap(plans);
  }
};

window.drawNoFlyZones = function(nfzs) {
  if (typeof drawNfzsOnMap === 'function') {
    drawNfzsOnMap(nfzs);
  }
};

window.clearMap = function() {
  if (typeof clearMapLayers === 'function') {
    clearMapLayers();
  }
  currentPlanCount = 0;
  window._currentNfzCount = 0;
  dom.mapStats.textContent = '航线: 0 | 航点: 0 | 禁飞区: 0';
};

// ── 初始化 ───────────────────────────────────────────────────────
function init() {
  fetchStatus();
  fetchConfig();
  initCharts();
  initMap();
  initDataPanel();
  addLog('UTM 模拟器控制台已就绪');
}

// ── 数据管理面板 ──────────────────────────────────────────────────
let selectedDataFile = null;

function initDataPanel() {
  // Tab 切换
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const tab = btn.dataset.tab;
      if (tab === 'tab-config') {
        document.getElementById('panel-config').style.display = '';
        document.getElementById('panel-data').style.display = 'none';
      } else {
        document.getElementById('panel-config').style.display = 'none';
        document.getElementById('panel-data').style.display = '';
        refreshFileList();
      }
    });
  });

  // 导出日志
  document.getElementById('btn-export-log').addEventListener('click', () => {
    const text = logs.join('\n');
    const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'utm-sim-log-' + new Date().toISOString().slice(0,19).replace(/:/g,'-') + '.txt';
    a.click();
    URL.revokeObjectURL(url);
    addLog('📥 日志已导出');
  });

  // 刷新文件列表
  document.getElementById('btn-refresh-files').addEventListener('click', refreshFileList);

  // 返回配置面板
  document.getElementById('btn-back-config').addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('[data-tab="tab-config"]').classList.add('active');
    document.getElementById('panel-config').style.display = '';
    document.getElementById('panel-data').style.display = 'none';
  });

  // 数据生成
  document.getElementById('btn-generate').addEventListener('click', generateData);

  // 文件上传
  document.getElementById('file-upload').addEventListener('change', uploadFile);

  // 从数据启动
  document.getElementById('btn-launch-data').addEventListener('click', launchFromData);
}

async function refreshFileList() {
  const container = document.getElementById('data-file-list');
  try {
    const data = await apiGet('/api/data/files');
    if (data.error) { container.innerHTML = '<div class="empty-hint">' + data.error + '</div>'; return; }
    if (!data.files || data.files.length === 0) {
      container.innerHTML = '<div class="empty-hint">mock/ 目录为空，点击"生成数据"或上传文件</div>';
      return;
    }
    container.innerHTML = data.files.map(f =>
      '<div class="file-item' + (selectedDataFile === f.name ? ' selected' : '') + '" data-file="' + f.name + '">' +
        '<span><span class="fn">' + f.name + '</span><br><span class="fi">' + f.records + ' 条 | ' + f.size_kb + ' KB</span></span>' +
        '<span class="fi">' + f.sample_keys.slice(0,3).join(', ') + '</span>' +
      '</div>'
    ).join('');

    container.querySelectorAll('.file-item').forEach(item => {
      item.addEventListener('click', () => {
        document.querySelectorAll('.file-item').forEach(i => i.classList.remove('selected'));
        item.classList.add('selected');
        selectedDataFile = item.dataset.file;
        previewFile(selectedDataFile);
      });
    });
  } catch (e) {
    container.innerHTML = '<div class="empty-hint">加载失败: ' + e.message + '</div>';
  }
}

async function previewFile(filename) {
  const container = document.getElementById('data-preview');
  try {
    const data = await apiGet('/api/data/files/' + filename + '?limit=10');
    if (data.error) { container.innerHTML = '<div class="empty-hint">' + data.error + '</div>'; return; }
    let text = 'File: ' + filename + '\nType: ' + data.type + '\n';
    if (data.type === 'list') {
      text += 'Total: ' + data.total + ' records\n\n';
      text += JSON.stringify(data.data.slice(0, 5), null, 2);
      if (data.total > 10) text += '\n... (' + (data.total - 10) + ' more)';
    } else if (data.type === 'dict') {
      text += 'Keys: ' + data.keys.join(', ') + '\n';
      text += JSON.stringify(data.data, null, 2).substring(0, 2000);
    }
    container.textContent = text;
  } catch (e) {
    container.innerHTML = '<div class="empty-hint">预览失败: ' + e.message + '</div>';
  }
}

async function generateData() {
  const count = parseInt(document.getElementById('gen-count').value) || 10;
  const lat = parseFloat(document.getElementById('gen-lat').value) || 31.315;
  const lon = parseFloat(document.getElementById('gen-lon').value) || 120.665;
  const radius = parseFloat(document.getElementById('gen-radius').value) || 800;
  const pattern = document.getElementById('gen-pattern').value;
  const duration = parseInt(document.getElementById('gen-duration').value) || 10;

  const resultEl = document.getElementById('gen-result');
  resultEl.textContent = '生成中...';
  try {
    const result = await apiPost('/api/data/files/generate', {
      count, center_lat: lat, center_lon: lon, radius, pattern, duration_min: duration
    });
    if (result.success) {
      resultEl.textContent = '已生成: ' + result.file + ' (' + result.count + ' 条)';
      addLog('已生成数据: ' + result.file + ' (' + count + ' 架, ' + pattern + ')');
      refreshFileList();
    } else {
      resultEl.textContent = '失败: ' + (result.error || 'unknown');
    }
  } catch (e) {
    resultEl.textContent = '异常: ' + e.message;
  }
}

async function uploadFile() {
  const fileInput = document.getElementById('file-upload');
  const file = fileInput.files[0];
  if (!file) return;

  const resultEl = document.getElementById('upload-result');
  resultEl.textContent = '上传中...';
  const formData = new FormData();
  formData.append('file', file);
  try {
    const resp = await fetch('/api/data/files/upload', { method: 'POST', body: formData });
    const result = await resp.json();
    resultEl.textContent = result.success ? 'OK: ' + result.message : '失败: ' + (result.error || '');
    if (result.success) { refreshFileList(); addLog('已上传: ' + file.name); }
  } catch (e) {
    resultEl.textContent = '异常: ' + e.message;
  }
}

async function launchFromData() {
  if (!selectedDataFile) {
    addLog('请先在文件列表中选择一个数据文件');
    return;
  }
  addLog('从 ' + selectedDataFile + ' 启动 scene 模式...');
  try {
    const result = await apiPost('/api/sim/start', { mode: 'scene', data_file: selectedDataFile });
    if (result.success) {
      addLog('已启动: ' + result.message);
      setRunningState(true);
      addHistory(true, 'scene | ' + selectedDataFile);
      document.querySelector('.tab-btn[data-tab="tab-config"]').click();
    } else {
      addLog('启动失败: ' + result.message);
    }
  } catch (e) {
    addLog('异常: ' + e.message);
  }
}

// ── 模式说明映射 ─────────────────────────────────────────────────
const MODE_DESCRIPTIONS = {
  scene: '🎬 场景文件注入：选择场景JSON文件按配置间隔发射，支持3种时间戳模式(replace/align/preserve)。适合特定场景的精确回放测试。',
  plan: '📐 Redis计划插值：从Redis读取飞行计划，沿路线段数学插值生成平滑遥测。实时监听Redis计划变更。适合UTM系统集成测试。'
};

function updateModeDescription() {
  const descEl = document.getElementById('mode-description');
  if (descEl) {
    descEl.textContent = MODE_DESCRIPTIONS[dom.modeSelect.value] || '';
  }
  // 显示/隐藏 mode-specific 参数
  const sceneParams = document.getElementById('scene-params');
  const replayParams = document.getElementById('replay-params');
  const planParams = document.getElementById('plan-params');
  const mode = dom.modeSelect.value;
  if (sceneParams) sceneParams.style.display = (mode === 'scene') ? '' : 'none';
  if (planParams) planParams.style.display = (mode === 'plan') ? '' : 'none';
  // scene 模式时刷新场景文件列表
  if (mode === 'scene') refreshSceneFileList();
  // plan 模式：刷新已有航线列表勾选状态
  if (mode === 'plan') updatePlanRouteSummary();
}

// ── 数据生成 Tab 切换 ────────────────────────────────────────────
function initDataGenTabs() {
  document.querySelectorAll('.gen-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      document.querySelectorAll('.gen-tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      document.querySelectorAll('.gen-tab-content').forEach(c => c.classList.remove('active'));
      const target = document.getElementById('gentab-' + this.dataset.gentab);
      if (target) target.classList.add('active');
      // 加载批量预设
      if (this.dataset.gentab === 'batch') loadBatchPresets();
    });
  });
  // 子 Tab 切换
  document.querySelectorAll('.sub-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      const parent = this.closest('.gen-tab-content');
      parent.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      parent.querySelectorAll('.sub-tab-content').forEach(c => c.classList.remove('active'));
      const target = document.getElementById('subtab-' + this.dataset.subtab);
      if (target) target.classList.add('active');
    });
  });
}

// ── 模式选择器联动 ──────────────────────────────────────────────
dom.modeSelect.addEventListener('change', updateModeDescription);

// ── 场景文件列表 ─────────────────────────────────────────────────
async function refreshSceneFileList() {
  const sel = document.getElementById('scene-file-select');
  if (!sel) return;
  try {
    const data = await apiGet('/api/data/files');
    if (data.files) {
      sel.innerHTML = data.files.map(f =>
        '<option value="' + f.name + '">' + f.name + ' (' + f.records + '条)</option>'
      ).join('');
    }
  } catch (e) { sel.innerHTML = '<option>加载失败</option>'; }
}

// 刷新按钮事件
var btnRefScene = document.getElementById('btn-refresh-scene-files');
if (btnRefScene) btnRefScene.addEventListener('click', refreshSceneFileList);

// ── 批量预设 ─────────────────────────────────────────────────────

// 一键全部预设
var btnBatchAll = document.getElementById('btn-gen-batch-all');
if (btnBatchAll) {
  btnBatchAll.addEventListener('click', async function() {
    var resultEl = document.getElementById('gen-batch-result');
    resultEl.textContent = '生成全部预设中，请耐心等待...';
    this.disabled = true;
    var result = await apiPost('/api/data/batch', {});
    this.disabled = false;
    resultEl.textContent = result.success ? '全部预设生成完成' : ('失败: ' + (result.error || ''));
    if (result.success) { refreshFileList(); addLog('全部批量预设已生成'); }
  });
}

// ── 场景生成函数 ─────────────────────────────────────────────────
function _getVal(id, def) {
  var el = document.getElementById(id);
  if (!el) return def;
  var v = el.value;
  if (el.type === 'checkbox') return el.checked;
  if (el.type === 'number' || el.type === 'range') {
    var n = parseFloat(v);
    return isNaN(n) ? def : n;
  }
  return v || def;
}

// 单机航线飞行
var btnSingleRoute = document.getElementById('btn-gen-single-route');
if (btnSingleRoute) {
  btnSingleRoute.addEventListener('click', async function() {
    var resultEl = document.getElementById('gen-single-result');
    resultEl.textContent = '生成中...';
    var result = await apiPost('/api/data/scene/single', {
      uid: _getVal('s-uid', 'UAV_TEST_001'),
      route_name: _getVal('s-route-name', null),
      points: _getVal('s-points', null),
      start_lon: _getVal('s-start-lon', null),
      start_lat: _getVal('s-start-lat', null),
      end_lon: _getVal('s-end-lon', null),
      end_lat: _getVal('s-end-lat', null),
      altitude: _getVal('s-altitude', 30),
      speed: _getVal('s-speed', 15),
      interval: _getVal('s-interval', 1000),
      operating_status: 2,
    });
    if (result.success) {
      resultEl.textContent = 'OK: ' + (result.file || '').split('/').pop() + ' (' + result.points + ' 点)';
      addLog('单机航线已生成: ' + result.uid + ' (' + result.points + ' 轨迹点)');
      refreshFileList();
    } else {
      resultEl.textContent = '失败: ' + (result.error || '');
    }
  });
}

// 单机偏离航路
var btnSingleDeviate = document.getElementById('btn-gen-single-deviate');
if (btnSingleDeviate) {
  btnSingleDeviate.addEventListener('click', async function() {
    var resultEl = document.getElementById('gen-deviate-result');
    resultEl.textContent = '生成中...';
    var result = await apiPost('/api/data/scene/deviate', {
      uid: _getVal('sd-uid', 'UAV_DEVIATE_001'),
      points: _getVal('sd-points', null),
      start_lon: _getVal('sd-start-lon', null),
      start_lat: _getVal('sd-start-lat', null),
      end_lon: _getVal('sd-end-lon', null),
      end_lat: _getVal('sd-end-lat', null),
      altitude: _getVal('sd-altitude', 30),
      speed: _getVal('sd-speed', 15),
      deviate: true,
      deviate_offset: _getVal('sd-deviate-offset', 0.001),
      deviate_start_index: _getVal('sd-deviate-start', 5),
    });
    if (result.success) {
      resultEl.textContent = 'OK: ' + (result.file || '').split('/').pop() + ' (' + result.points + ' 点)';
      addLog('偏离航路已生成: ' + result.uid);
      refreshFileList();
    } else {
      resultEl.textContent = '失败: ' + (result.error || '');
    }
  });
}

// 状态变更
var btnStatusChange = document.getElementById('btn-gen-status-change');
if (btnStatusChange) {
  btnStatusChange.addEventListener('click', async function() {
    var resultEl = document.getElementById('gen-status-result');
    resultEl.textContent = '生成中...';
    var result = await apiPost('/api/data/scene/deviate', {
      uid: _getVal('ss-uid', 'UAV_STATUS_001'),
      points: _getVal('ss-points', null),
      start_lon: _getVal('ss-start-lon', null),
      start_lat: _getVal('ss-start-lat', null),
      end_lon: _getVal('ss-end-lon', null),
      end_lat: _getVal('ss-end-lat', null),
      altitude: 30, speed: 15,
      deviate: false,
      operating_status: parseInt(_getVal('ss-oper-status', '2')),
    });
    if (result.success) {
      resultEl.textContent = 'OK: ' + (result.file || '').split('/').pop();
      refreshFileList();
    } else {
      resultEl.textContent = '失败: ' + (result.error || '');
    }
  });
}

// 平行飞行
var btnParallel = document.getElementById('btn-gen-parallel');
if (btnParallel) {
  btnParallel.addEventListener('click', async function() {
    var resultEl = document.getElementById('gen-parallel-result');
    resultEl.textContent = '生成中（可能需要较长时间）...';
    this.disabled = true;
    var result = await apiPost('/api/data/scene/parallel', {
      count: _getVal('mp-count', 30),
      center_lng: _getVal('mp-center-lng', 85.070136),
      center_lat: _getVal('mp-center-lat', 40.818724),
      altitude: _getVal('mp-altitude', 50),
      speed: _getVal('mp-speed', 15),
      heading: _getVal('mp-heading', 90),
      spacing: _getVal('mp-spacing', 2000),
      layout: _getVal('mp-layout', 'hex'),
      points: _getVal('mp-points', 1200),
    });
    this.disabled = false;
    if (result.success) {
      resultEl.textContent = 'OK: ' + result.count + ' 架 → ' + (result.file || '').split('/').pop();
      addLog('平行飞行已生成: ' + result.count + ' 架无人机');
      refreshFileList();
    } else {
      resultEl.textContent = '失败: ' + (result.error || '');
    }
  });
}

// 高级偏离
var btnDeviateAdv = document.getElementById('btn-gen-deviate-adv');
if (btnDeviateAdv) {
  btnDeviateAdv.addEventListener('click', async function() {
    var resultEl = document.getElementById('gen-deviate-adv-result');
    resultEl.textContent = '生成中...';
    var result = await apiPost('/api/data/scene/deviate-adv', {
      route_name: _getVal('da-route-name', '铁门关至吐鲁番'),
      deviate_offset: _getVal('da-deviate-offset', 3000),
      deviate_start: _getVal('da-deviate-start', 20),
      deviate_transition: _getVal('da-deviate-transition', null),
      deviate_mode: _getVal('da-deviate-mode', 'horizontal'),
      deviate_altitude_offset: _getVal('da-alt-offset', 0),
      speed: _getVal('da-speed', 15),
    });
    if (result.success) {
      resultEl.textContent = 'OK: ' + (result.file || '').split('/').pop();
      addLog('高级偏离数据已生成');
      refreshFileList();
    } else {
      resultEl.textContent = '失败: ' + (result.error || '');
    }
  });
}

// 碰撞预警
var btnCollision = document.getElementById('btn-gen-collision');
if (btnCollision) {
  btnCollision.addEventListener('click', async function() {
    var resultEl = document.getElementById('gen-collision-result');
    resultEl.textContent = '生成中...';
    var result = await apiPost('/api/data/scene/collision', {
      route_names: _getVal('col-route-names', '跨顺义三河段,三河区航路'),
      uids: _getVal('col-uids', 'CW000000000000000004,CH000000000000000003'),
      meeting_threshold: _getVal('col-meeting-threshold', 10),
      collision_time: _getVal('col-collision-time', 300),
    });
    if (result.success) {
      resultEl.textContent = 'OK: 碰撞场景已生成';
      addLog('碰撞预警场景已生成 → mock/');
      refreshFileList();
    } else {
      resultEl.textContent = '失败: ' + (result.error || '');
    }
  });
}

// 状态告警
var btnStatusAlert = document.getElementById('btn-gen-status-alert');
if (btnStatusAlert) {
  btnStatusAlert.addEventListener('click', async function() {
    var scene3 = document.getElementById('sa-scene3').checked;
    var scene5 = document.getElementById('sa-scene5').checked;
    var scene35 = document.getElementById('sa-scene35').checked;
    if (!scene3 && !scene5 && !scene35) {
      document.getElementById('gen-status-alert-result').textContent = '请至少选择一种告警类型';
      return;
    }
    var resultEl = document.getElementById('gen-status-alert-result');
    resultEl.textContent = '生成中...';
    var result = await apiPost('/api/data/scene/status', {
      count: _getVal('sa-count', 1),
      center_lng: _getVal('sa-center-lng', 120.7418),
      center_lat: _getVal('sa-center-lat', 31.3689),
      altitude: _getVal('sa-altitude', 50),
      speed: _getVal('sa-speed', 15),
      flight_minutes: _getVal('sa-flight-min', 1),
      scene3: scene3, scene5: scene5, 'scene3-5': scene35,
    });
    if (result.success) {
      resultEl.textContent = 'OK: 状态告警场景已生成';
      addLog('状态告警场景已生成');
      refreshFileList();
    } else {
      resultEl.textContent = '失败: ' + (result.error || '');
    }
  });
}

// 更新 fetchConfig 以处理新配置
var _origFetchConfig = fetchConfig;
fetchConfig = async function() {
  await _origFetchConfig();
  updateModeDescription();
  var data = await apiGet('/api/sim/config');
  if (data.scene_interval !== undefined) {
    var si = document.getElementById('scene-interval');
    if (si) si.value = data.scene_interval;
  }
  if (data.timestamp_mode !== undefined) {
    var stm = document.getElementById('scene-timestamp-mode');
    if (stm) stm.value = data.timestamp_mode;
  }
  if (data.scene_loop !== undefined) {
    var sl = document.getElementById('scene-loop');
    if (sl) sl.checked = data.scene_loop;
  }
};



// 启动时初始化新功能
var _origInit = init;
init = function() {
  _origInit();
  initDataGenTabs();
  updateModeDescription();
};

document.addEventListener('DOMContentLoaded', init);

})();