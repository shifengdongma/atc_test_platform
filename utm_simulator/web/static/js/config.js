/* -*- coding: utf-8 -*- */
/* 仿真配置页 JS */

(function() {
'use strict';

var isRunning = false;
var history = [];
var modeDescriptions = {
  dynamic: '🎮 动态仿真：实时生成飞行计划，Simulator引擎计算遥测，持续运行。适合开发调试和实时测试。',
  replay: '🔁 预生成回放(循环)：读取mock目录JSON循环发射，每轮刷新Redis航线，永不停止。适合长期稳定注入。',
  replay_once: '▶️ 预生成回放(单次)：JSON回放一次，耗尽自动停止并输出精度报告。适合单次回归测试。',
  scene: '🎬 场景文件注入：选择JSON按间隔发射，支持3种时间戳模式。适合特定场景精确回放。',
  plan: '📐 Redis计划插值：从Redis读飞行计划，沿航段插值生成遥测。实时监听Redis变更。'
};

var $ = function(sel) { return document.querySelector(sel); };

// ── DOM ───────────────────────────────────────────────────────────
var elMode = $('#mode-select');
var elDesc = $('#mode-description');
var elDrones = $('#target-drones');
var elDronesVal = $('#drones-value');
var elNfzOn = $('#nfz-enabled');
var elNfzCnt = $('#nfz-count');
var elRedisHost = $('#cfg-redis-host');
var elRedisPort = $('#cfg-redis-port');
var elKafkaUrl = $('#cfg-kafka-url');
var elBtnStart = $('#btn-start');
var elBtnStop = $('#btn-stop');
var elBtnTest = $('#btn-test-conn');
var elConnTest = $('#conn-test-result');
var elBadge = $('#sim-status-badge');
var elHistory = $('#history-list');
var elSaveConn = $('#btn-save-conn');
var elSaveResult = $('#conn-save-result');

// ── 设置运行状态 ───────────────────────────────────────────────────
function setRunningState(running) {
  isRunning = running;
  elBtnStart.disabled = running;
  elBtnStop.disabled = !running;
  elMode.disabled = running;
  elDrones.disabled = running;
  if (elNfzOn) elNfzOn.disabled = running;
  if (elNfzCnt) elNfzCnt.disabled = running || !elNfzOn.checked;
  // 禁用特定模式参数
  ['scene-params','replay-params','plan-params'].forEach(function(id) {
    var p = document.getElementById(id);
    if (p) p.querySelectorAll('input,select,button').forEach(function(e) { e.disabled = running; });
  });
  elBadge.textContent = running ? '运行中' : '已停止';
  elBadge.className = 'badge ' + (running ? 'running' : 'stopped');
}

// ── 更新模式描述 ───────────────────────────────────────────────────
function updateMode() {
  elDesc.textContent = modeDescriptions[elMode.value] || '';
  ['scene-params','replay-params','plan-params'].forEach(function(id) {
    var p = document.getElementById(id);
    if (p) p.style.display = 'none';
  });
  if (elMode.value === 'scene') {
    var sp = document.getElementById('scene-params');
    if (sp) sp.style.display = '';
  } else if (elMode.value === 'replay' || elMode.value === 'replay_once') {
    var rp = document.getElementById('replay-params');
    if (rp) rp.style.display = '';
  } else if (elMode.value === 'plan') {
    var pp = document.getElementById('plan-params');
    if (pp) pp.style.display = '';
  }
}

// ── 加载配置 ───────────────────────────────────────────────────────
async function fetchConfig() {
  try {
    var data = await apiGet('/api/sim/config');
    elMode.value = data.mode || 'dynamic';
    elDrones.value = data.target_drones || 1;
    elDronesVal.textContent = data.target_drones || 1;
    elRedisHost.value = data.redis_ip || '127.0.0.1';
    elRedisPort.value = data.redis_port || '6379';
    elKafkaUrl.value = data.kafka_url || '127.0.0.1:9092';
    if (elNfzOn) elNfzOn.checked = data.nfz_enabled !== false;
    if (elNfzCnt) { elNfzCnt.value = data.nfz_count || 3; elNfzCnt.disabled = !elNfzOn.checked; }
    updateMode();
  } catch(e) {}
}

// ── 事件绑定 ───────────────────────────────────────────────────────
elMode.addEventListener('change', updateMode);
elDrones.addEventListener('input', function() { elDronesVal.textContent = elDrones.value; });
if (elNfzOn) elNfzOn.addEventListener('change', function() { if (elNfzCnt) elNfzCnt.disabled = !elNfzOn.checked || isRunning; });

// WebSocket 事件
onWsEvent('status_change', function(data) {
  if (data.event === 'started') setRunningState(true);
  else if (data.event === 'stopped') setRunningState(false);
  else if (data.event === 'starting') { elBadge.textContent = '启动中'; elBadge.className = 'badge starting'; }
});

// 启动仿真
elBtnStart.addEventListener('click', async function() {
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
    body.plan_selected_uids = (typeof getSelectedPlanUids === 'function') ? getSelectedPlanUids() : [];
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

// 停止仿真
elBtnStop.addEventListener('click', async function() {
  var result = await apiPost('/api/sim/stop');
  if (result.success) {
    setRunningState(false);
    showToast('仿真已停止', 'success');
  } else {
    showToast(result.message || '停止失败', 'error');
  }
});

// 测试连接
elBtnTest.addEventListener('click', async function() {
  elConnTest.textContent = '测试中...';
  var result = await apiGet('/api/sim/test-connection');
  elConnTest.textContent = 'Redis: ' + (result.redis?'OK':'FAIL') + ' | Kafka: ' + (result.kafka?'OK':'FAIL');
});

// 保存连接配置
if (elSaveConn) elSaveConn.addEventListener('click', async function() {
  var body = { redis_ip: elRedisHost.value, redis_port: elRedisPort.value, kafka_url: elKafkaUrl.value };
  var result = await apiPost('/api/sim/config/save', body);
  elSaveResult.textContent = result.success ? '已保存' : '保存失败';
  setTimeout(function() { elSaveResult.textContent = ''; }, 3000);
});

// 历史记录
function renderHistory() {
  if (!elHistory) return;
  if (history.length === 0) { elHistory.innerHTML = '<li class="empty-hint">暂无运行记录</li>'; return; }
  elHistory.innerHTML = history.map(function(h) {
    return '<li class="' + (h.success?'success':'error') + '">[' + h.time + '] ' + h.detail + '</li>';
  }).join('');
}

// ── 初始化 ─────────────────────────────────────────────────────────
fetchConfig();
})();
