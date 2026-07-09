/* -*- coding: utf-8 -*- */
/* 仿真执行页 JS — 合并版：参数配置 + 实时监控 + 地图可视化 + 环境选择器 */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var isRunning = false;
var history = [];
var logs = [];

// ── 模式描述 ────────────────────────────────────────────────────────
var modeDescriptions = {
  dynamic: '🎮 动态仿真：实时生成飞行计划，Simulator引擎计算遥测，持续运行。适合开发调试和实时测试。',
  replay: '🔁 预生成回放(循环)：读取mock目录JSON循环发射，每轮刷新Redis航线，永不停止。适合长期稳定注入。',
  replay_once: '▶️ 预生成回放(单次)：JSON回放一次，耗尽自动停止并输出精度报告。适合单次回归测试。',
  scene: '🎬 场景文件注入：选择JSON按间隔发射，支持3种时间戳模式。适合特定场景精确回放。',
  plan: '📐 Redis计划插值：从Redis读飞行计划，沿航段插值生成遥测。实时监听Redis变更。'
};
var modeScriptTags = {
  dynamic: 'simulation_core.py (Simulator 引擎 → sim_manager.py)',
  replay: 'tools/run_kafka_alive.py (循环回放 → sim_manager.py)',
  replay_once: 'tools/run_kafka.py (DataSource 单次回放)',
  scene: 'tools/run_kafka_scene.py (SceneEmitter 场景注入)',
  plan: 'tools/run_plan.py (PlanRunner Redis插值)'
};

// ── DOM refs — 配置区 ───────────────────────────────────────────────
var elMode = $('#mode-select');
var elDesc = $('#mode-description');
var elDrones = $('#target-drones');
var elDronesVal = $('#drones-value');
var elNfzOn = $('#nfz-enabled');
var elNfzCnt = $('#nfz-count');
var elBtnStart = $('#btn-start');
var elBtnStop = $('#btn-stop');
var elBtnTest = $('#btn-test-conn');
var elConnTest = $('#conn-test-result');
var elBadge = $('#sim-status-badge');
var elHistory = $('#history-list');

// ── DOM refs — 监控区 ───────────────────────────────────────────────
var dom = {
  indRedis: $('#ind-redis'), redisStatus: $('#redis-status'),
  indKafka: $('#ind-kafka'), kafkaStatus: $('#kafka-status'),
  dronesCount: $('#drones-count'), kafkaTp: $('#kafka-tp'),
  uptime: $('#uptime'), errorCount: $('#error-count'),
  logStream: $('#log-stream'), btnExport: $('#btn-export-log'),
  btnClearLog: $('#btn-clear-log'),
  btnPlans: $('#btn-load-plans'), btnNfzs: $('#btn-load-nfzs'), btnClear: $('#btn-clear-map'),
  mapStats: $('#map-stats'),
};

// ── DOM refs — 环境选择器 ────────────────────────────────────────────
var elEnvSelect = $('#env-select');
var elEnvActivate = $('#btn-env-activate');
var elEnvStatus = $('#env-status');
var elEnvCurrent = $('#env-current-info');

// ── 运行状态管理 ─────────────────────────────────────────────────────
function setRunningState(running) {
  isRunning = running;
  if (elBtnStart) elBtnStart.disabled = running;
  if (elBtnStop) elBtnStop.disabled = !running;
  if (elMode) elMode.disabled = running;
  if (elDrones) elDrones.disabled = running;
  if (elNfzOn) elNfzOn.disabled = running;
  if (elNfzCnt) elNfzCnt.disabled = running || !elNfzOn.checked;
  ['scene-params','replay-params','plan-params'].forEach(function(id) {
    var p = document.getElementById(id);
    if (p) p.querySelectorAll('input,select,button').forEach(function(e) { e.disabled = running; });
  });
  if (elBadge) {
    elBadge.textContent = running ? '运行中' : '已停止';
    elBadge.className = 'badge ' + (running ? 'running' : 'stopped');
  }
}

// ── 模式切换 ────────────────────────────────────────────────────────
function updateMode() {
  if (elDesc) elDesc.textContent = modeDescriptions[elMode.value] || '';
  var scriptTag = document.getElementById('mode-script-tag');
  if (scriptTag) scriptTag.textContent = modeScriptTags[elMode.value] || '';
  ['scene-params','replay-params','plan-params'].forEach(function(id) {
    var p = document.getElementById(id);
    if (p) p.style.display = 'none';
  });
  if (elMode.value === 'scene') {
    var sp = document.getElementById('scene-params');
    if (sp) sp.style.display = '';
    refreshSceneFileList();
  } else if (elMode.value === 'replay' || elMode.value === 'replay_once') {
    var rp = document.getElementById('replay-params');
    if (rp) rp.style.display = '';
    refreshReplayFileList();
  } else if (elMode.value === 'plan') {
    var pp = document.getElementById('plan-params');
    if (pp) pp.style.display = '';
    loadPlanRouteList();
  }
}

// ── 文件列表加载 ────────────────────────────────────────────────────
async function refreshSceneFileList() {
  var sel = document.getElementById('scene-file-select');
  if (!sel) return;
  try {
    var data = await apiGet('/api/data/files');
    if (data.files) {
      sel.innerHTML = data.files.map(function(f) {
        return '<option value="' + f.name + '">' + f.name + ' (' + f.records + '条)</option>';
      }).join('');
    }
  } catch(e) { sel.innerHTML = '<option>加载失败</option>'; }
}

async function refreshReplayFileList() {
  try {
    var data = await apiGet('/api/data/files');
    if (data.files) {
      var dataSel = document.getElementById('replay-data-file');
      var routeSel = document.getElementById('replay-route-file');
      if (dataSel) {
        dataSel.innerHTML = data.files.map(function(f) {
          return '<option value="' + f.name + '"' + (f.name.indexOf('kafka_data') >= 0 ? ' selected' : '') + '>' + f.name + '</option>';
        }).join('');
      }
      if (routeSel) {
        routeSel.innerHTML = data.files.map(function(f) {
          return '<option value="' + f.name + '"' + (f.name.indexOf('redis_route') >= 0 ? ' selected' : '') + '>' + f.name + '</option>';
        }).join('');
      }
    }
  } catch(e) {}
}

async function loadPlanRouteList() {
  var list = document.getElementById('plan-route-list');
  if (!list) return;
  try {
    var data = await apiGet('/api/sim/plans?limit=200');
    if (typeof window.populatePlanRouteList === 'function') {
      window.populatePlanRouteList(data.plans || []);
    }
  } catch(e) {
    list.innerHTML = '<div class="empty-hint">加载航线失败，请检查服务连接</div>';
  }
}

// ── 加载配置 ────────────────────────────────────────────────────────
async function fetchConfig() {
  try {
    var data = await apiGet('/api/sim/config');
    if (elMode) elMode.value = data.mode || 'dynamic';
    if (elDrones) { elDrones.value = data.target_drones || 1; }
    if (elDronesVal) elDronesVal.textContent = data.target_drones || 1;
    if (elNfzOn) elNfzOn.checked = data.nfz_enabled !== false;
    if (elNfzCnt) { elNfzCnt.value = data.nfz_count || 3; elNfzCnt.disabled = !elNfzOn.checked; }
    updateMode();
  } catch(e) {}
}

// ── 环境选择器 ──────────────────────────────────────────────────────
async function loadEnvSelector() {
  try {
    var data = await apiGet('/api/env/list');
    var html = '<option value="">— 选择环境 —</option>';
    if (data.envs) {
      data.envs.forEach(function(e) {
        var sel = e.is_default ? ' selected' : '';
        html += '<option value="' + e.id + '"' + sel + '>' + escHtml(e.name) + '</option>';
      });
    }
    if (elEnvSelect) elEnvSelect.innerHTML = html;
    // 显示当前激活环境
    if (elEnvCurrent) {
      var cur = data.current || {};
      if (cur.name) {
        elEnvCurrent.textContent = '当前激活: ' + cur.name + ' | Redis ' + (cur.redis_ip||'?') + ':' + (cur.redis_port||'?') + ' | Kafka ' + (cur.kafka_url||'?');
      } else {
        elEnvCurrent.textContent = '';
      }
    }
  } catch(e) {}
}

if (elEnvActivate) elEnvActivate.addEventListener('click', async function() {
  var id = elEnvSelect ? elEnvSelect.value : '';
  if (!id) { showToast('请选择环境', 'error'); return; }
  var result = await apiPost('/api/env/' + id + '/activate');
  if (result.success) {
    showToast('已激活: ' + result.message, 'success');
    loadEnvSelector();
  } else {
    showToast(result.message || '激活失败', 'error');
  }
});

// ── 启动/停止仿真 ──────────────────────────────────────────────────
if (elBtnStart) elBtnStart.addEventListener('click', async function() {
  var mode = elMode.value;
  var body = {
    mode: mode,
    target_drones: parseInt(elDrones.value),
    nfz_enabled: elNfzOn ? elNfzOn.checked : false,
    nfz_count: elNfzCnt ? parseInt(elNfzCnt.value) || 0 : 0
  };
  if (mode === 'scene') {
    var sfSel = document.getElementById('scene-file-select');
    body.scene_files = sfSel ? Array.from(sfSel.selectedOptions).map(function(o) { return o.value; }) : [];
    body.scene_interval = parseInt((document.getElementById('scene-interval')||{}).value || 1000);
    body.timestamp_mode = (document.getElementById('scene-timestamp-mode')||{}).value || 'replace';
    body.scene_loop = (document.getElementById('scene-loop')||{}).checked || false;
  }
  if (mode === 'replay' || mode === 'replay_once') {
    body.data_file = (document.getElementById('replay-data-file')||{}).value || 'kafka_data.json';
    body.route_file = (document.getElementById('replay-route-file')||{}).value || 'redis_route.json';
  }
  if (mode === 'plan') {
    var hasCheckboxes = document.querySelectorAll('.plan-route-cb').length > 0;
    if (hasCheckboxes && typeof window.getSelectedPlanUids === 'function') {
      body.plan_selected_uids = window.getSelectedPlanUids();
    }
  }
  var result = await apiPost('/api/sim/start', body);
  if (result.success) {
    setRunningState(true);
    history.unshift({ time: new Date().toLocaleTimeString('zh-CN',{hour12:false}), success: true, detail: mode + ' | ' + body.target_drones + ' 架' });
    if (history.length > 20) history = history.slice(0, 20);
    renderHistory();
    showToast('仿真已启动: ' + mode, 'success');
  } else {
    showToast(result.message || '启动失败', 'error');
  }
});

if (elBtnStop) elBtnStop.addEventListener('click', async function() {
  var result = await apiPost('/api/sim/stop');
  if (result.success) {
    setRunningState(false);
    showToast('仿真已停止', 'success');
  } else {
    showToast(result.message || '停止失败', 'error');
  }
});

// ── 测试连接 ───────────────────────────────────────────────────────
if (elBtnTest) elBtnTest.addEventListener('click', async function() {
  if (elConnTest) elConnTest.textContent = '测试中...';
  var result = await apiGet('/api/sim/test-connection');
  if (elConnTest) elConnTest.textContent = 'Redis: ' + (result.redis?'OK':'FAIL') + ' | Kafka: ' + (result.kafka?'OK':'FAIL');
});

// ── 历史记录 ────────────────────────────────────────────────────────
function renderHistory() {
  if (!elHistory) return;
  if (history.length === 0) { elHistory.innerHTML = '<li class="empty-hint">暂无运行记录</li>'; return; }
  elHistory.innerHTML = history.map(function(h) {
    return '<li class="' + (h.success?'success':'error') + '">[' + h.time + '] ' + h.detail + '</li>';
  }).join('');
}

// ── 事件绑定 — 模式/参数切换 ─────────────────────────────────────────
if (elMode) elMode.addEventListener('change', updateMode);
if (elDrones) elDrones.addEventListener('input', function() { if (elDronesVal) elDronesVal.textContent = elDrones.value; });
if (elNfzOn) elNfzOn.addEventListener('change', function() { if (elNfzCnt) elNfzCnt.disabled = !elNfzOn.checked || isRunning; });

// Plan 刷新按钮
var btnPlanRefresh = document.getElementById('btn-plan-refresh-routes');
if (btnPlanRefresh) btnPlanRefresh.addEventListener('click', loadPlanRouteList);

// Scene 刷新按钮
var btnRefScene = document.getElementById('btn-refresh-scene-files');
if (btnRefScene) btnRefScene.addEventListener('click', refreshSceneFileList);

// Replay 刷新按钮
var btnRefReplay = document.getElementById('btn-refresh-replay-files');
if (btnRefReplay) btnRefReplay.addEventListener('click', refreshReplayFileList);

// ── 监控更新 ────────────────────────────────────────────────────────
function updateMonitor(data) {
  if (data.redis_connected) {
    if (dom.indRedis) dom.indRedis.className = 'indicator green';
    if (dom.redisStatus) dom.redisStatus.textContent = '已连接';
  } else {
    if (dom.indRedis) dom.indRedis.className = 'indicator red';
    if (dom.redisStatus) dom.redisStatus.textContent = '未连接';
  }
  if (data.kafka_connected) {
    if (dom.indKafka) dom.indKafka.className = 'indicator green';
    if (dom.kafkaStatus) dom.kafkaStatus.textContent = '已连接';
  } else {
    if (dom.indKafka) dom.indKafka.className = 'indicator red';
    if (dom.kafkaStatus) dom.kafkaStatus.textContent = '未连接';
  }
  if (dom.dronesCount) dom.dronesCount.textContent = data.active_drones || 0;
  if (dom.kafkaTp) dom.kafkaTp.innerHTML = (data.kafka_msg_per_sec || 0) + ' <small>条/秒</small>';
  if (dom.uptime) dom.uptime.textContent = formatDuration(data.uptime_sec || 0);
  if (dom.errorCount) dom.errorCount.textContent = data.errors || 0;

  if (typeof addChartData === 'function') {
    addChartData('drones', data.active_drones || 0);
    addChartData('kafka', data.kafka_msg_per_sec || 0);
  }
}

// ── 日志（带类型标记） ───────────────────────────────────────────────
function addLog(msg, type) {
  type = type || 'other';
  var time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  var entry = { time: time, type: type, msg: msg };
  logs.push(entry);
  if (logs.length > 500) logs = logs.slice(-500);
  renderFilteredLogs();
}

function getActiveLogTypes() {
  var cbs = document.querySelectorAll('.run-log-type-cb');
  var types = [];
  for (var i = 0; i < cbs.length; i++) {
    if (cbs[i].checked) types.push(cbs[i].value);
  }
  return types;
}

function renderFilteredLogs() {
  if (!dom.logStream) return;
  var activeTypes = getActiveLogTypes();
  var filtered = logs.filter(function(l) { return activeTypes.indexOf(l.type) !== -1; });
  if (filtered.length === 0) {
    dom.logStream.innerHTML = '<div class="log-empty">无匹配日志</div>';
    return;
  }
  dom.logStream.innerHTML = filtered.map(function(l) {
    return '<div class="log-line">[' + l.time + '] ' + escHtml(l.msg) + '</div>';
  }).join('');
  dom.logStream.scrollTop = dom.logStream.scrollHeight;
}

// 日志类型过滤事件
document.addEventListener('DOMContentLoaded', function() {
  var cbs = document.querySelectorAll('.run-log-type-cb');
  for (var i = 0; i < cbs.length; i++) {
    cbs[i].addEventListener('change', renderFilteredLogs);
  }
});

// 导出日志
if (dom.btnExport) dom.btnExport.addEventListener('click', function() {
  var now = new Date().toISOString().replace(/[:.]/g, '-');
  var text = logs.map(function(l) { return '[' + l.time + '] ' + l.msg; }).join('\n');
  var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'sim-logs-' + now + '.txt';
  a.click();
  URL.revokeObjectURL(a.href);
});

// 清空日志
if (dom.btnClearLog) dom.btnClearLog.addEventListener('click', function() {
  logs = [];
  if (dom.logStream) dom.logStream.innerHTML = '<div class="log-empty">已清空</div>';
});

// ── 地图 ────────────────────────────────────────────────────────────
async function loadFlightPlans() {
  try {
    var data = await apiGet('/api/sim/plans?limit=200');
    if (data.error) { addLog('⚠️ 获取航线失败: ' + data.error, 'other'); return; }
    if (typeof drawPlansOnMap === 'function') drawPlansOnMap(data.plans || []);
    if (dom.mapStats) dom.mapStats.textContent = '航线: ' + (data.plans?data.plans.length:0) + ' | 总计: ' + (data.total||0);
    addLog('已加载 ' + (data.plans?data.plans.length:0) + '/' + (data.total||0) + ' 条航线', 'redis_route');
    if (typeof populatePlanRouteList === 'function') populatePlanRouteList(data.plans || []);
  } catch(e) { addLog('❌ 加载航线异常: ' + e.message, 'other'); }
}

async function loadNoFlyZones() {
  try {
    var data = await apiGet('/api/sim/nfzs');
    if (data.error) { addLog('⚠️ 获取禁飞区失败: ' + data.error, 'other'); return; }
    if (typeof drawNfzsOnMap === 'function') drawNfzsOnMap(data.nfzs || []);
    window._currentNfzCount = data.nfzs?data.nfzs.length:0;
    addLog('已加载 ' + (data.nfzs?data.nfzs.length:0) + ' 个禁飞区', 'redis_route');
  } catch(e) { addLog('❌ 加载禁飞区异常: ' + e.message, 'other'); }
}

function clearMap() {
  if (typeof clearMapLayers === 'function') clearMapLayers();
  if (dom.mapStats) dom.mapStats.textContent = '';
  addLog('地图已清除', 'other');
}

if (dom.btnPlans) dom.btnPlans.addEventListener('click', loadFlightPlans);
if (dom.btnNfzs) dom.btnNfzs.addEventListener('click', loadNoFlyZones);
if (dom.btnClear) dom.btnClear.addEventListener('click', clearMap);

// ── WebSocket 事件 ──────────────────────────────────────────────────
onWsEvent('status', function(data) {
  updateMonitor(data);
  if (data.running) setRunningState(true);
  else if (!data.running && isRunning) setRunningState(false);
});
onWsEvent('log', function(data) { addLog(data.message, 'sim_status'); });
onWsEvent('status_change', function(data) {
  addLog(data.message, 'sim_status');
  if (data.event === 'started') setRunningState(true);
  else if (data.event === 'stopped') setRunningState(false);
  else if (data.event === 'starting') {
    if (elBadge) { elBadge.textContent = '启动中'; elBadge.className = 'badge starting'; }
  }
});

// ── 定时状态轮询 ────────────────────────────────────────────────────
async function pollStatus() {
  try {
    var data = await fetchSimStatus();
    if (data && data.running) updateMonitor(data);
  } catch(e) {}
  setTimeout(pollStatus, 3000);
}

// ── 初始化 ──────────────────────────────────────────────────────────
async function initRun() {
  // 加载配置
  await fetchConfig();
  // 加载环境列表
  await loadEnvSelector();
  // 初始化图表和地图
  if (typeof initCharts === 'function') initCharts();
  if (typeof initMap === 'function') initMap();
  // 检查运行状态
  syncRunningState().then(function(running) {
    if (running) setRunningState(true);
  });
  // 开始轮询
  pollStatus();
  // 首次加载地图数据
  setTimeout(loadFlightPlans, 500);
  setTimeout(loadNoFlyZones, 800);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initRun);
} else {
  initRun();
}

})();
