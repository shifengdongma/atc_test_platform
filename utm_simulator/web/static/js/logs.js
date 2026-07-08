/* -*- coding: utf-8 -*- */
/* 系统日志页 JS — 完整功能在 Phase 6 实现，当前展示仿真运行日志 */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var logs = [];
var paused = false;

// ── WebSocket 日志接收 ─────────────────────────────────────────────
onWsEvent('log', function(data) {
  if (paused) return;
  var types = getCheckedTypes();
  if (types.length === 0) return;
  var msg = data.message || '';
  var search = ($('#logs-search').value || '').toLowerCase();
  if (search && msg.toLowerCase().indexOf(search) < 0) return;
  addLogEntry(msg, 'sim_status');
});

// ── 添加日志条目 ───────────────────────────────────────────────────
function addLogEntry(msg, type) {
  var time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  logs.push({ time: time, type: type, msg: msg });
  if (logs.length > 500) logs = logs.slice(-500);
  renderLogs();
}

function renderLogs() {
  var el = $('#logs-stream');
  if (!el) return;
  el.innerHTML = logs.map(function(l) {
    return '<div class="log-line"><span class="log-ts">[' + l.time + ']</span> <span class="log-type">[' + l.type + ']</span> ' + escHtml(l.msg) + '</div>';
  }).join('');
  el.scrollTop = el.scrollHeight;
  updateStats();
}

function updateStats() {
  var el = $('#logs-stats');
  if (el) el.textContent = '共 ' + logs.length + ' 条' + (paused ? ' (已暂停)' : '');
}

// ── 日志类型过滤 ───────────────────────────────────────────────────
function getCheckedTypes() {
  var cbs = document.querySelectorAll('.log-type-cb:checked');
  var types = [];
  cbs.forEach(function(cb) { types.push(cb.value); });
  return types;
}

document.querySelectorAll('.log-type-cb').forEach(function(cb) {
  cb.addEventListener('change', function() { renderLogs(); });
});

// ── 暂停/恢复 ──────────────────────────────────────────────────────
$('#btn-logs-pause').addEventListener('click', function() {
  paused = !paused;
  this.textContent = paused ? '▶ 恢复' : '⏸ 暂停';
  updateStats();
});

// ── 清空 ───────────────────────────────────────────────────────────
$('#btn-logs-clear').addEventListener('click', function() {
  logs = [];
  renderLogs();
});

// ── 关键字过滤 ─────────────────────────────────────────────────────
$('#logs-search').addEventListener('input', function() {
  renderLogs();
});

// ── 导出 ───────────────────────────────────────────────────────────
function exportLogs(format) {
  var now = new Date().toISOString().replace(/[:.]/g, '-');
  var content, mime, ext;
  if (format === 'csv') {
    content = 'time,type,message\n' + logs.map(function(l) { return '"' + l.time + '","' + l.type + '","' + l.msg.replace(/"/g,'""') + '"'; }).join('\n');
    mime = 'text/csv;charset=utf-8'; ext = 'csv';
  } else {
    content = JSON.stringify(logs, null, 2);
    mime = 'application/json;charset=utf-8'; ext = 'json';
  }
  var blob = new Blob([content], { type: mime });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'sim-logs-' + now + '.' + ext;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast('日志已导出 (' + logs.length + ' 条)', 'success');
}

$('#btn-logs-export-json').addEventListener('click', function() { exportLogs('json'); });
$('#btn-logs-export-csv').addEventListener('click', function() { exportLogs('csv'); });

})();
