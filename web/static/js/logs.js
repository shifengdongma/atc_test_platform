/* -*- coding: utf-8 -*- */
/* 系统日志页 JS — Tab 分类展示 + 结构化详情卡片 + 导出 */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var $$ = function(sel) { return document.querySelectorAll(sel); };
var logs = [];          // {time, type, type_name, msg, detail}
var paused = false;
var activeTab = 'situation-uav';

// ── 数值格式化辅助（防御 toFixed 类型错误） ──────────────────────
function fmtNum(val, decimals, suffix) {
  if (typeof val === 'number' && isFinite(val)) return val.toFixed(decimals) + (suffix || '');
  return '-';
}

// ── 枚举标签 ─────────────────────────────────────────────────────
function statusLabel(s) {
  return {0:'未起飞',1:'起飞中',2:'飞行中',3:'悬停',4:'降落中',5:'已降落'}[s] || ('状态'+s);
}
function classLabel(c) {
  return {1:'C1-微型',2:'C2-轻型',3:'C3-小型',4:'C4-中型',5:'C5-大型'}[c] || ('分类'+c);
}

// ── Tab 切换 ──────────────────────────────────────────────────────
function initLogsTabs() {
  $$('.gen-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      $$('.gen-tab').forEach(function(t) { t.classList.remove('active'); });
      this.classList.add('active');
      $$('.gen-tab-content').forEach(function(c) { c.classList.remove('active'); });
      var target = document.getElementById('gentab-' + this.dataset.gentab);
      if (target) target.classList.add('active');
      activeTab = this.dataset.gentab;
      var title = $('#tab-title');
      if (title) title.textContent = this.textContent.trim();

      // "全部日志"tab 显示系统日志类型复选框，其他 tab 隐藏
      var sysTypes = document.querySelectorAll('.gentab-all-only');
      sysTypes.forEach(function(el) {
        el.style.display = (activeTab === 'all') ? '' : 'none';
      });
      renderActiveTab();
    });
  });
  // 初始状态：非"全部日志"tab 隐藏系统日志类型
  var sysTypes = document.querySelectorAll('.gentab-all-only');
  sysTypes.forEach(function(el) { el.style.display = 'none'; });
}

// ── 渲染调度 ──────────────────────────────────────────────────────
function renderActiveTab() {
  switch (activeTab) {
    case 'situation-uav': renderUavTab(); break;
    case 'situation-plan': renderPlanTab(); break;
    case 'situation-alarm': renderAlarmTab(); break;
    case 'all': renderAllTab(); break;
    default: renderAllTab(); break;
  }
  updateStats();
}

// ── 监视目标 Tab ─────────────────────────────────────────────────
function renderUavTab() {
  var el = $('#logs-stream-uav');
  if (!el) return;
  var filtered = getFilteredLogs('situation_uav');
  if (filtered.length === 0) {
    el.innerHTML = '<div class="log-empty">暂无监视目标日志，等待 ATC 态势数据...</div>';
    return;
  }

  var html = '';
  // 最新一条显示摘要卡片
  var latest = filtered[filtered.length - 1];
  if (latest.detail && latest.detail.uavs) {
    var uavs = latest.detail.uavs;
    html += '<div class="uav-summary-bar">';
    html += '<span class="uav-summary-count">🛸 当前监视目标: <strong>' + (latest.detail.count || uavs.length) + '</strong> 架</span>';
    html += '<span class="uav-summary-time">更新于 ' + escHtml(latest.time) + '</span>';
    html += '</div>';

    // UAV 卡片列表
    uavs.forEach(function(uav, i) {
      html += '<div class="uav-card">';
      html += '<div class="uav-card-header" onclick="this.parentNode.querySelector(\'.uav-card-body\').classList.toggle(\'open\')">';
      html += '<span class="uav-card-toggle">▶</span>';
      html += '<span class="uav-detail-code">' + escHtml(uav.uavIdentifyCode || '?') + '</span>';
      html += '<span style="font-size:11px;color:var(--text-dim);">' + escHtml(uav.realNameRegistrationSign || '') + '</span>';
      if (uav.operatingStatusLabel) {
        html += '<span class="uav-status-badge">' + escHtml(uav.operatingStatusLabel) + '</span>';
      }
      if (uav.classificationLabel) {
        html += '<span style="font-size:10px;color:var(--text-dim);">' + escHtml(uav.classificationLabel) + '</span>';
      }
      if (uav.warningCount) {
        html += '<span class="uav-warn-badge">⚠' + uav.warningCount + '</span>';
      }
      html += '</div>';
      html += '<div class="uav-card-body">';
      html += '<div class="uav-detail-grid">';
      html += '<div><span class="dim">经度:</span> ' + fmtNum(uav.longitude, 6) + '</div>';
      html += '<div><span class="dim">纬度:</span> ' + fmtNum(uav.latitude, 6) + '</div>';
      html += '<div><span class="dim">海拔高度:</span> ' + fmtNum(uav.geodeticAltitude, 1, ' m') + '</div>';
      html += '<div><span class="dim">地速:</span> ' + fmtNum(uav.speed, 1, ' m/s') + '</div>';
      html += '<div><span class="dim">航向角:</span> ' + fmtNum(uav.trackAngle, 1, '°') + '</div>';
      html += '<div><span class="dim">升降速:</span> ' + fmtNum(uav.verticalSpeed, 1, ' m/s') + '</div>';
      html += '</div></div>';
      html += '</div>';
    });
  } else {
    // 无 detail 的回退：显示纯文本
    html += '<div class="log-empty">当前日志无结构化详情，等待 flightTrack 数据...</div>';
    filtered.forEach(function(l) {
      html += '<div class="log-line"><span class="log-ts">[' + l.time + ']</span> ' + escHtml(l.msg) + '</div>';
    });
  }

  // 历史记录（折叠）
  if (filtered.length > 1) {
    html += '<div class="uav-card" style="margin-top:12px;">';
    html += '<div class="uav-card-header" onclick="this.parentNode.querySelector(\'.uav-card-body\').classList.toggle(\'open\')">';
    html += '<span class="uav-card-toggle">▶</span>';
    html += '<span class="uav-card-summary">📜 历史记录 (' + (filtered.length - 1) + ' 条)</span>';
    html += '</div>';
    html += '<div class="uav-card-body"><div class="log-stream" style="max-height:300px;background:var(--bg);border:none;">';
    for (var i = filtered.length - 2; i >= 0; i--) {
      html += '<div class="log-line"><span class="log-ts">[' + filtered[i].time + ']</span> ' + escHtml(filtered[i].msg) + '</div>';
    }
    html += '</div></div></div>';
  }
  el.innerHTML = html;
}

// ── 飞行计划 Tab ─────────────────────────────────────────────────
function renderPlanTab() {
  var el = $('#logs-stream-plan');
  if (!el) return;
  var filtered = getFilteredLogs('situation_plan');
  if (filtered.length === 0) {
    el.innerHTML = '<div class="log-empty">暂无飞行计划日志，等待 ATC 态势数据...</div>';
    return;
  }

  var latest = filtered[filtered.length - 1];
  var html = '';

  // 状态摘要条
  if (latest.detail && latest.detail.totalCount !== undefined) {
    var d = latest.detail;
    html += '<div class="plan-summary">';
    html += '<div class="plan-summary-item"><span style="color:var(--text-dim);">总计</span> <strong>' + d.totalCount + '</strong></div>';
    html += '<div class="plan-summary-item plan-waiting"><span style="color:var(--text-dim);">待处理</span> <strong>' + (d.waitingCount||0) + '</strong></div>';
    html += '<div class="plan-summary-item plan-active"><span style="color:var(--text-dim);">执行中</span> <strong>' + (d.activeCount||0) + '</strong></div>';
    html += '<div class="plan-summary-item plan-completed"><span style="color:var(--text-dim);">已完成</span> <strong>' + (d.completedCount||0) + '</strong></div>';
    html += '<div class="plan-summary-item plan-rejected"><span style="color:var(--text-dim);">已拒绝</span> <strong>' + (d.rejectedCount||0) + '</strong></div>';
    html += '<div class="plan-summary-item plan-cancelled"><span style="color:var(--text-dim);">已取消</span> <strong>' + (d.cancelledCount||0) + '</strong></div>';
    html += '</div>';
    html += '<div style="font-size:11px;color:var(--text-dim);margin-bottom:10px;">更新于 ' + escHtml(latest.time) + '</div>';
  }

  // 变更历史
  if (filtered.length > 0) {
    html += '<div style="font-size:12px;color:var(--accent-bright);margin-bottom:6px;">📜 变更历史</div>';
    for (var i = filtered.length - 1; i >= 0; i--) {
      var l = filtered[i];
      html += '<div class="plan-detail-row">';
      html += '<span class="log-ts">[' + l.time + ']</span> ';
      html += escHtml(l.msg);
      if (l.detail) {
        // 计数不匹配提示
        if (l.detail.countMismatch) {
          html += ' <span style="font-size:10px;color:var(--warning);">⚠️ 实际计划: ' + l.detail.redisCount + ' 条</span>';
        }
        // REST API 不可用提示
        if (l.detail.totalCount !== undefined && !l.detail.plans && !l.detail.countMismatch) {
          html += ' <span style="font-size:10px;color:var(--text-dim);">(计划列表 API 不可用)</span>';
        }
        html += ' <span style="font-size:10px;color:var(--text-dim);cursor:pointer;" onclick="var d=this.nextElementSibling;d.style.display=d.style.display===\'block\'?\'none\':\'block\'">📋 详情</span>';
        html += '<div class="plan-detail-sub"><code>' + escHtml(JSON.stringify(l.detail, null, 2)) + '</code></div>';
      }
      html += '</div>';
    }
  }
  el.innerHTML = html;
}

// ── 实时告警 Tab ─────────────────────────────────────────────────
function renderAlarmTab() {
  var el = $('#logs-stream-alarm');
  if (!el) return;
  var filtered = getFilteredLogs('situation_alarm');
  if (filtered.length === 0) {
    el.innerHTML = '<div class="log-empty">暂无实时告警日志，等待 ATC 态势数据...</div>';
    return;
  }

  var html = '';
  for (var i = filtered.length - 1; i >= 0; i--) {
    var l = filtered[i];
    html += '<div class="alarm-card">';
    html += '<div class="alarm-card-header">';
    html += '<span class="alarm-icon">⚠️</span>';
    html += '<span class="alarm-time">[' + l.time + ']</span>';
    html += '<span class="alarm-msg">' + escHtml(l.msg) + '</span>';
    html += '</div>';

    // 告警详情列表
    if (l.detail && l.detail.warnings && l.detail.warnings.length > 0) {
      l.detail.warnings.forEach(function(w) {
        html += '<div class="alarm-item">';
        html += '<span class="alarm-item-code">' + escHtml(w.uavCode || '-') + '</span>';
        html += '<span class="alarm-item-type">' + escHtml(w.warningType || '告警') + '</span>';
        html += '<span class="alarm-item-msg">' + escHtml(w.message || '') + '</span>';
        html += '</div>';
      });
    } else if (l.detail && l.detail.source === 'alarmStatistic') {
      // 来自 alarmStatistic 计数，区分有告警但详情未加载 / 无告警
      if (l.detail.total > 0) {
        html += '<div class="alarm-item"><span class="alarm-item-msg alarm-item-loading" style="grid-column:1/-1;">⏳ 告警详情获取中…（共 ' + l.detail.total + ' 条，REST API 请求）</span></div>';
      } else {
        html += '<div class="alarm-item"><span class="alarm-item-msg alarm-item-empty" style="grid-column:1/-1;">当前无告警 ✅</span></div>';
      }
    } else {
      html += '<div class="alarm-item"><span class="alarm-item-msg" style="grid-column:1/-1;">（无告警详情）</span></div>';
    }
    html += '</div>';
  }
  el.innerHTML = html;
}

// ── 全部日志 Tab ──────────────────────────────────────────────────
function renderAllTab() {
  var el = $('#logs-stream-all');
  if (!el) return;
  var types = getCheckedTypes();
  var filtered = logs.filter(function(l) { return types.indexOf(l.type) >= 0; });
  if (filtered.length === 0) {
    el.innerHTML = '<div class="log-empty">暂无日志，等待仿真事件...</div>';
    return;
  }
  el.innerHTML = filtered.map(function(l) {
    var line = '<span class="log-ts">[' + l.time + ']</span> <span class="log-type">[' + (l.type_name || l.type) + ']</span> ' + escHtml(l.msg);
    return '<div class="log-line">' + line + '</div>';
  }).join('');
  el.scrollTop = el.scrollHeight;
}

// ── 辅助 ──────────────────────────────────────────────────────────
function getFilteredLogs(typeFilter) {
  var search = ($('#logs-search').value || '').toLowerCase();
  return logs.filter(function(l) {
    if (l.type !== typeFilter) return false;
    if (search && l.msg.toLowerCase().indexOf(search) < 0) return false;
    return true;
  });
}

function getCheckedTypes() {
  var cbs = document.querySelectorAll('.log-type-cb:checked');
  var types = [];
  cbs.forEach(function(cb) { types.push(cb.value); });
  return types;
}

function updateStats() {
  var el = $('#logs-stats');
  if (!el) return;
  var filtered;
  if (activeTab === 'all') {
    var types = getCheckedTypes();
    filtered = logs.filter(function(l) { return types.indexOf(l.type) >= 0; });
  } else {
    var typeMap = {
      'situation-uav': 'situation_uav',
      'situation-plan': 'situation_plan',
      'situation-alarm': 'situation_alarm'
    };
    filtered = logs.filter(function(l) { return l.type === typeMap[activeTab]; });
  }
  el.textContent = '共 ' + filtered.length + ' 条' + (paused ? ' (已暂停)' : '');
}

// ── WebSocket 日志接收 ─────────────────────────────────────────────
onWsEvent('log', function(data) {
  if (paused) return;
  var msg = data.message || '';
  addLogEntry(msg, 'sim_status', '', null);
});

onWsEvent('log_entry', function(data) {
  if (paused) return;
  var msg = data.message || '';
  addLogEntry(msg, data.type || 'sim_status', data.type_name || '', data.detail || null);
});

// ── 添加日志条目 ───────────────────────────────────────────────────
function addLogEntry(msg, type, type_name, detail) {
  var search = ($('#logs-search').value || '').toLowerCase();
  if (search && msg.toLowerCase().indexOf(search) < 0) return;
  var time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  logs.push({ time: time, type: type, type_name: type_name || '', msg: msg, detail: detail || null });
  if (logs.length > 500) logs = logs.slice(-500);
  renderActiveTab();
}

// ── 初始加载：从 REST API 拉取已有日志 ──────────────────────────────
async function fetchInitialLogs() {
  try {
    var resp = await fetch('/api/logs?limit=200');
    if (!resp.ok) {
      console.error('[logs] API 返回错误:', resp.status, resp.statusText);
      showPlaceholder('日志服务暂不可用（HTTP ' + resp.status + '），3秒后重试...');
      return;
    }
    var data = await resp.json();
    if (data.logs && data.logs.length > 0) {
      data.logs.reverse().forEach(function(l) {
        logs.push({ time: l.time, type: l.type, type_name: l.type_name || '', msg: l.message, detail: l.detail || null });
      });
      renderActiveTab();
    } else {
      console.log('[logs] 日志缓冲区为空，等待新日志...');
    }
  } catch(e) {
    console.error('[logs] fetchInitialLogs 异常:', e);
    showPlaceholder('日志加载失败: ' + e.message + '，3秒后重试...');
  }
}

function showPlaceholder(msg) {
  // 在所有 tab 面板中显示占位提示（如果为空）
  ['logs-stream-uav', 'logs-stream-plan', 'logs-stream-alarm', 'logs-stream-all'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el && el.innerHTML === '') {
      el.innerHTML = '<div class="log-empty">' + escHtml(msg) + '</div>';
    }
  });
}

// ── 定时轮询兜底（每 10 秒拉一次新日志）─────────────────────────────
var _lastLogTime = '';
async function pollLogs() {
  if (paused) { setTimeout(pollLogs, 10000); return; }
  try {
    var url = '/api/logs?limit=50';
    if (_lastLogTime) url += '&since=' + encodeURIComponent(_lastLogTime);
    var resp = await fetch(url);
    if (!resp.ok) { setTimeout(pollLogs, 10000); return; }
    var data = await resp.json();
    if (data.logs && data.logs.length > 0) {
      var newCount = 0;
      data.logs.reverse().forEach(function(l) {
        if (l.time > _lastLogTime) {
          _lastLogTime = l.time;
          var dup = logs.some(function(existing) {
            return existing.time === l.time && existing.msg === l.message;
          });
          if (!dup) {
            logs.push({ time: l.time, type: l.type, type_name: l.type_name || '', msg: l.message, detail: l.detail || null });
            newCount++;
          }
        }
      });
      if (newCount > 0) {
        if (logs.length > 500) logs = logs.slice(-500);
        renderActiveTab();
      }
    }
  } catch(e) {
    console.error('[logs] pollLogs 异常:', e);
  }
  setTimeout(pollLogs, 10000);
}

// ── 暂停/恢复 ──────────────────────────────────────────────────────
$('#btn-logs-pause').addEventListener('click', function() {
  paused = !paused;
  this.textContent = paused ? '▶ 恢复' : '⏸ 暂停';
  updateStats();
});

// ── 清空 ───────────────────────────────────────────────────────────
$('#btn-logs-clear').addEventListener('click', function() {
  logs = [];
  var ids = ['logs-stream-uav', 'logs-stream-plan', 'logs-stream-alarm', 'logs-stream-all'];
  ids.forEach(function(id) { var el = document.getElementById(id); if (el) el.innerHTML = ''; });
  updateStats();
});

// ── 刷新 ───────────────────────────────────────────────────────────
$('#btn-logs-refresh').addEventListener('click', async function() {
  var btn = this;
  btn.disabled = true;
  btn.classList.add('refreshing');
  var origText = btn.textContent;
  btn.textContent = '⏳ 刷新中...';

  // 清空缓冲区并从 API 重新加载
  logs = [];
  _lastLogTime = '';
  await fetchInitialLogs();

  btn.disabled = false;
  btn.classList.remove('refreshing');
  btn.textContent = origText;
  showToast('日志已刷新', 'success');
});

// ── 关键字过滤 ─────────────────────────────────────────────────────
$('#logs-search').addEventListener('input', function() {
  renderActiveTab();
});

// ── 系统日志类型复选框（仅影响"全部日志"Tab） ─────────────────────
document.querySelectorAll('.log-type-cb').forEach(function(cb) {
  cb.addEventListener('change', function() {
    if (activeTab === 'all') renderAllTab();
  });
});

// ── 导出 ───────────────────────────────────────────────────────────
function exportLogs(format) {
  var exportList;
  if (activeTab === 'all') {
    var types = getCheckedTypes();
    exportList = logs.filter(function(l) { return types.indexOf(l.type) >= 0; });
  } else {
    var typeMap = {
      'situation-uav': 'situation_uav',
      'situation-plan': 'situation_plan',
      'situation-alarm': 'situation_alarm'
    };
    var typeFilter = typeMap[activeTab];
    exportList = logs.filter(function(l) { return l.type === typeFilter; });
  }

  if (exportList.length === 0) {
    showToast('当前 Tab 无日志可导出', 'info');
    return;
  }

  var now = new Date().toISOString().replace(/[:.]/g, '-');
  var content, mime, ext;

  if (format === 'csv') {
    content = 'time,type,type_name,message,detail\n';
    content += exportList.map(function(l) {
      var msg = (l.msg || '').replace(/"/g, '""');
      var typeName = (l.type_name || '').replace(/"/g, '""');
      var detailStr = l.detail ? JSON.stringify(l.detail).replace(/"/g, '""') : '';
      return '"' + l.time + '","' + l.type + '","' + typeName + '","' + msg + '","' + detailStr + '"';
    }).join('\n');
    mime = 'text/csv;charset=utf-8'; ext = 'csv';
  } else {
    content = JSON.stringify(exportList, null, 2);
    mime = 'application/json;charset=utf-8'; ext = 'json';
  }

  var blob = new Blob(['﻿' + content], { type: mime });  // BOM for Excel UTF-8
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'sim-logs-' + (activeTab === 'all' ? 'all' : activeTab) + '-' + now + '.' + ext;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast('日志已导出 (' + exportList.length + ' 条)', 'success');
}

$('#btn-logs-export-json').addEventListener('click', function() { exportLogs('json'); });
$('#btn-logs-export-csv').addEventListener('click', function() { exportLogs('csv'); });

// ── 初始化 ─────────────────────────────────────────────────────────
initLogsTabs();
fetchInitialLogs();
setTimeout(pollLogs, 3000);

})();
