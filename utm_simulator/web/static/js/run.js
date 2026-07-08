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

// 等待 Leaflet 等资源加载
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initRun);
} else {
  initRun();
}

})();
