/* -*- coding: utf-8 -*- */
/* 仿真执行页 JS — 监控面板 + 地图 + 日志流 */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var logs = [];

// ── DOM ───────────────────────────────────────────────────────────
var dom = {
  indRedis: $('#ind-redis'), redisStatus: $('#redis-status'),
  indKafka: $('#ind-kafka'), kafkaStatus: $('#kafka-status'),
  dronesCount: $('#drones-count'), kafkaTp: $('#kafka-tp'),
  uptime: $('#uptime'), errorCount: $('#error-count'),
  logStream: $('#log-stream'), btnExport: $('#btn-export-log'),
  btnPlans: $('#btn-load-plans'), btnNfzs: $('#btn-load-nfzs'), btnClear: $('#btn-clear-map'),
  mapStats: $('#map-stats'),
};

// ── 监控更新 ───────────────────────────────────────────────────────
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

// ── 日志 ───────────────────────────────────────────────────────────
function addLog(msg) {
  var time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  var entry = '[' + time + '] ' + msg;
  logs.push(entry);
  if (logs.length > 200) logs = logs.slice(-200);
  if (dom.logStream) {
    dom.logStream.innerHTML = logs.map(function(l) { return '<div class="log-line">' + escHtml(l) + '</div>'; }).join('');
    dom.logStream.scrollTop = dom.logStream.scrollHeight;
  }
}

if (dom.btnExport) dom.btnExport.addEventListener('click', function() {
  var now = new Date().toISOString().replace(/[:.]/g, '-');
  var blob = new Blob([logs.join('\n')], { type: 'text/plain;charset=utf-8' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'sim-logs-' + now + '.txt';
  a.click();
  URL.revokeObjectURL(a.href);
});

// ── 地图 ───────────────────────────────────────────────────────────
async function loadFlightPlans() {
  try {
    var data = await apiGet('/api/sim/plans?limit=200');
    if (data.error) { addLog('⚠️ 获取航线失败: ' + data.error); return; }
    if (typeof drawPlansOnMap === 'function') drawPlansOnMap(data.plans || []);
    if (dom.mapStats) dom.mapStats.textContent = '航线: ' + (data.plans?data.plans.length:0) + ' | 总计: ' + (data.total||0);
    addLog('已加载 ' + (data.plans?data.plans.length:0) + '/' + (data.total||0) + ' 条航线');
    if (typeof populatePlanRouteList === 'function') populatePlanRouteList(data.plans || []);
  } catch(e) { addLog('❌ 加载航线异常: ' + e.message); }
}

async function loadNoFlyZones() {
  try {
    var data = await apiGet('/api/sim/nfzs');
    if (data.error) { addLog('⚠️ 获取禁飞区失败: ' + data.error); return; }
    if (typeof drawNfzsOnMap === 'function') drawNfzsOnMap(data.nfzs || []);
    window._currentNfzCount = data.nfzs?data.nfzs.length:0;
    addLog('已加载 ' + (data.nfzs?data.nfzs.length:0) + ' 个禁飞区');
  } catch(e) { addLog('❌ 加载禁飞区异常: ' + e.message); }
}

function clearMap() {
  if (typeof clearMapLayers === 'function') clearMapLayers();
  if (dom.mapStats) dom.mapStats.textContent = '';
  addLog('地图已清除');
}

if (dom.btnPlans) dom.btnPlans.addEventListener('click', loadFlightPlans);
if (dom.btnNfzs) dom.btnNfzs.addEventListener('click', loadNoFlyZones);
if (dom.btnClear) dom.btnClear.addEventListener('click', clearMap);

// ── WebSocket 事件 ─────────────────────────────────────────────────
onWsEvent('status', updateMonitor);
onWsEvent('log', function(data) { addLog(data.message); });
onWsEvent('status_change', function(data) { addLog(data.message); });

// ── 定时状态轮询 ───────────────────────────────────────────────────
async function pollStatus() {
  try {
    var data = await fetchSimStatus();
    if (data && data.running) updateMonitor(data);
  } catch(e) {}
  setTimeout(pollStatus, 3000);
}

// ── 初始化 ─────────────────────────────────────────────────────────
function initRun() {
  if (typeof initCharts === 'function') initCharts();
  if (typeof initMap === 'function') initMap();
  pollStatus();
  // 首次加载
  setTimeout(loadFlightPlans, 500);
  setTimeout(loadNoFlyZones, 800);
}

// ── 定时任务 ───────────────────────────────────────────────────────
async function loadScheduledTasks() {
  var el = $('#sched-list');
  if (!el) return;
  try {
    var data = await apiGet('/api/schedule/tasks');
    if (!data.tasks || !data.tasks.length) {
      el.innerHTML = '<div class="empty-hint">暂无定时任务</div>';
      return;
    }
    el.innerHTML = data.tasks.map(function(t) {
      var status = t.enabled ? '<span class="current-badge">启用</span>' : '<span style="color:var(--danger);font-size:10px;">暂停</span>';
      return '<div style="padding:4px 0;border-bottom:1px solid #1a2740;font-size:11px;">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;">' +
          '<span style="color:#82aaff;">' + escHtml(t.name||'') + '</span>' + status +
        '</div>' +
        '<div style="color:var(--text-dim);">' + escHtml(t.cron_expr||'') + ' | ' + escHtml(t.sim_mode||'') +
          ' | 上次: ' + escHtml((t.last_run_at||'--').substring(0,16)) + '</div>' +
        '<div style="margin-top:2px;">' +
          (t.enabled ?
            '<button class="btn-tiny" onclick="pauseTask(' + t.id + ')">⏸</button>' :
            '<button class="btn-tiny" onclick="resumeTask(' + t.id + ')">▶</button>') +
          '<button class="btn-tiny" onclick="runTaskNow(' + t.id + ')">⚡立即</button>' +
          '<button class="btn-tiny" onclick="deleteTask(' + t.id + ')">🗑</button>' +
        '</div>' +
      '</div>';
    }).join('');
  } catch(e) {}
}

window.pauseTask = async function(id) {
  await apiPost('/api/schedule/tasks/' + id + '/pause');
  showToast('已暂停', 'success'); loadScheduledTasks();
};
window.resumeTask = async function(id) {
  await apiPost('/api/schedule/tasks/' + id + '/resume');
  showToast('已恢复', 'success'); loadScheduledTasks();
};
window.runTaskNow = async function(id) {
  var r = await apiPost('/api/schedule/tasks/' + id + '/run-now');
  showToast(r.message||'已触发', r.success?'success':'error');
};
window.deleteTask = async function(id) {
  if (!confirm('确定删除？')) return;
  await fetch('/api/schedule/tasks/' + id, {method:'DELETE'});
  showToast('已删除', 'success'); loadScheduledTasks();
};

// 新建任务弹窗（简化版：快捷 cron 选择器）
$('#btn-sched-new').addEventListener('click', async function() {
  var name = prompt('任务名称：', '自动仿真-' + new Date().toLocaleTimeString('zh-CN',{hour12:false}));
  if (!name) return;
  var cronOpts = ['*/30 * * * * (每30分钟)', '0 * * * * (每小时)', '0 */2 * * * (每2小时)', '0 9 * * * (每天9点)'];
  var cronChoice = prompt('选择执行频率：\n1. 每30分钟\n2. 每小时\n3. 每2小时\n4. 每天9:00\n或输入自定义 cron 表达式', '1');
  if (!cronChoice) return;
  var cronMap = {'1':'*/30 * * * *','2':'0 * * * *','3':'0 */2 * * *','4':'0 9 * * *'};
  var cronExpr = cronMap[cronChoice] || cronChoice;

  var body = {
    name: name,
    cron_expr: cronExpr,
    sim_mode: 'replay',
    sim_params: JSON.stringify({target_drones:10, duration_min:5}),
    enabled: 1,
  };
  var r = await apiPost('/api/schedule/tasks', body);
  showToast(r.message||'已创建', r.success?'success':'error');
  loadScheduledTasks();
});

// 首次加载
setTimeout(loadScheduledTasks, 1500);

// 等待 Leaflet 等资源加载
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initRun);
} else {
  initRun();
}

})();
