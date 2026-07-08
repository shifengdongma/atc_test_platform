/* -*- coding: utf-8 -*- */
/* utm_moc52 — 公共模块：导航栏、WebSocket、API封装、工具函数 */

(function() {
'use strict';

const API_BASE = '';

// ── 工具函数 ──────────────────────────────────────────────────────
window.escHtml = function(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
};

window.formatDuration = function(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

window.formatTime = function(ts) {
  var d = new Date(ts);
  return d.toLocaleTimeString('zh-CN', { hour12: false });
};

// ── API 封装 ──────────────────────────────────────────────────────
window.apiGet = async function(path) {
  const resp = await fetch(API_BASE + path);
  return resp.json();
};

window.apiPost = async function(path, body) {
  const resp = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return resp.json();
};

// ── WebSocket（单例，所有页面共享）─────────────────────────────────
var _socket = null;
var _wsCallbacks = { status: [], status_change: [], log: [], log_entry: [] };

window.getSocket = function() {
  if (_socket) return _socket;
  _socket = io({ transports: ['websocket', 'polling'] });
  _socket.on('connect', function() {
    var dot = document.getElementById('connection-dot');
    var txt = document.getElementById('connection-text');
    if (dot) { dot.className = 'dot green'; }
    if (txt) { txt.textContent = '已连接'; }
  });
  _socket.on('disconnect', function() {
    var dot = document.getElementById('connection-dot');
    var txt = document.getElementById('connection-text');
    if (dot) { dot.className = 'dot red'; }
    if (txt) { txt.textContent = '已断开'; }
  });
  _socket.on('status', function(data) {
    _wsCallbacks.status.forEach(function(fn) { fn(data); });
  });
  _socket.on('status_change', function(data) {
    _wsCallbacks.status_change.forEach(function(fn) { fn(data); });
  });
  _socket.on('log', function(data) {
    _wsCallbacks.log.forEach(function(fn) { fn(data); });
  });
  _socket.on('log_entry', function(data) {
    _wsCallbacks.log_entry.forEach(function(fn) { fn(data); });
  });
  return _socket;
};

window.onWsEvent = function(event, callback) {
  if (_wsCallbacks[event]) {
    _wsCallbacks[event].push(callback);
  }
};

window.offWsEvent = function(event, callback) {
  if (_wsCallbacks[event]) {
    _wsCallbacks[event] = _wsCallbacks[event].filter(function(fn) { return fn !== callback; });
  }
};

// ── 导航栏渲染 ────────────────────────────────────────────────────
var NAV_PAGES = [
  { href: '/config',    icon: '⚙️', label: '仿真配置' },
  { href: '/run',       icon: '▶️', label: '仿真执行' },
  { href: '/generate',  icon: '📊', label: '数据生成' },
  { href: '/data',      icon: '📁', label: '数据管理' },
  { href: '/env',       icon: '🔧', label: '环境管理' },
  { href: '/logs',      icon: '📋', label: '系统日志' },
];

window.renderNavbar = function(activePath) {
  var nav = document.getElementById('top-nav');
  if (!nav) return;
  var html = '';
  for (var i = 0; i < NAV_PAGES.length; i++) {
    var p = NAV_PAGES[i];
    var cls = (p.href === activePath) ? 'nav-item active' : 'nav-item';
    html += '<a class="' + cls + '" href="' + p.href + '">' + p.icon + ' ' + p.label + '</a>';
  }
  nav.innerHTML = html;
};

// ── 连接状态检查 ──────────────────────────────────────────────────
window.checkConnection = async function() {
  try {
    var data = await window.apiGet('/api/sim/test-connection');
    return data;
  } catch(e) {
    return { redis: false, kafka: false };
  }
};

// ── 仿真状态查询 ──────────────────────────────────────────────────
window.fetchSimStatus = async function() {
  try {
    var data = await window.apiGet('/api/sim/status');
    return data;
  } catch(e) {
    return { running: false, mode: '', active_drones: 0 };
  }
};

// ── Toast 通知 ────────────────────────────────────────────────────
window.showToast = function(msg, type) {
  type = type || 'info';  // info / success / error
  var el = document.getElementById('toast-container');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast-container';
    el.style.cssText = 'position:fixed;top:50px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(el);
  }
  var colors = { info: '#00b4d8', success: '#2ecc71', error: '#e74c3c' };
  var t = document.createElement('div');
  t.className = 'toast';
  t.style.cssText = 'background:#1a2736;color:' + (colors[type]||colors.info) +
    ';padding:10px 18px;border-radius:6px;border:1px solid #2a3f56;font-size:13px;' +
    'animation:fadeIn 0.3s ease;min-width:200px;';
  t.textContent = msg;
  el.appendChild(t);
  setTimeout(function() { t.style.opacity = '0'; t.style.transition = 'opacity 0.3s'; }, 3000);
  setTimeout(function() { t.remove(); }, 3300);
};

// ── 初始化 WebSocket 连接 ─────────────────────────────────────────
// ── Plan 模式：航线选择列表（跨页面共享）────────────────────────
window.populatePlanRouteList = function(plans) {
  var list = document.getElementById('plan-route-list');
  var summary = document.getElementById('plan-route-summary');
  if (!list) return;
  if (!plans || plans.length === 0) {
    list.innerHTML = '<div class="empty-hint">Redis 中暂无航线数据</div>';
    if (summary) summary.textContent = '';
    return;
  }
  var html = '';
  for (var i = 0; i < plans.length; i++) {
    var p = plans[i];
    var uid = p._uid || p.uniqueProductIdentificationCode || '未知';
    var fpCount = p._fpCount || 0;
    html += '<label class="plan-route-item">' +
      '<input type="checkbox" class="plan-route-cb" value="' + window.escHtml(uid) + '">' +
      '<span class="plan-route-uid">' + window.escHtml(uid) + '</span>' +
      '<span class="plan-route-info">' + fpCount + ' 个计划</span>' +
    '</label>';
  }
  list.innerHTML = html;
  window.updatePlanRouteSummary();
};

window.getSelectedPlanUids = function() {
  var cbs = document.querySelectorAll('.plan-route-cb:checked');
  var uids = [];
  for (var i = 0; i < cbs.length; i++) { uids.push(cbs[i].value); }
  return uids;
};

window.updatePlanRouteSummary = function() {
  var el = document.getElementById('plan-route-summary');
  if (!el) return;
  var total = document.querySelectorAll('.plan-route-cb').length;
  var sel = document.querySelectorAll('.plan-route-cb:checked').length;
  el.textContent = '已选 ' + sel + ' / ' + total + ' 条航线';
};

// ── 全选/取消全选事件绑定 ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  var btnAll = document.getElementById('btn-plan-select-all');
  var btnNone = document.getElementById('btn-plan-deselect-all');
  if (btnAll) btnAll.addEventListener('click', function() {
    document.querySelectorAll('.plan-route-cb').forEach(function(cb) { cb.checked = true; });
    if (window.updatePlanRouteSummary) window.updatePlanRouteSummary();
  });
  if (btnNone) btnNone.addEventListener('click', function() {
    document.querySelectorAll('.plan-route-cb').forEach(function(cb) { cb.checked = false; });
    if (window.updatePlanRouteSummary) window.updatePlanRouteSummary();
  });
});

// ── 跨页面仿真状态同步 ─────────────────────────────────────────────
window._simRunningCache = false;
window.syncRunningState = async function() {
  try {
    var data = await window.apiGet('/api/sim/status');
    window._simRunningCache = data.running === true;
    return window._simRunningCache;
  } catch(e) { return false; }
};

window.initCommon = function(activePath) {
  window.renderNavbar(activePath);
  window.getSocket();
  window.syncRunningState();
};

})();
