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

// ── 左侧面板 Tab 切换 ──────────────────────────────────────────────
document.querySelectorAll('.left-tab').forEach(function(tab) {
  tab.addEventListener('click', function() {
    document.querySelectorAll('.left-tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.left-tab-content').forEach(function(c) { c.classList.remove('active'); });
    this.classList.add('active');
    var target = document.getElementById('lefttab-' + this.dataset.lefttab);
    if (target) target.classList.add('active');
  });
});

// ── 定时任务 ───────────────────────────────────────────────────────
var editingTaskId = null;

async function loadScheduledTasks() {
  var el = document.getElementById('sched-list');
  if (!el) return;
  try {
    var data = await apiGet('/api/schedule/tasks');
    if (!data.tasks || !data.tasks.length) {
      el.innerHTML = '<div class="empty-hint">暂无定时任务，点击"新建任务"创建</div>';
      return;
    }
    el.innerHTML = data.tasks.map(function(t) {
      var statusBadge = t.enabled ? '<span class="current-badge">启用</span>' : '<span style="color:var(--danger);font-size:10px;">暂停</span>';
      var jsonInfo = '';
      try {
        var sp = JSON.parse(t.sim_params || '{}');
        jsonInfo = ' | ' + (sp.data_file || sp.json_file || '默认');
      } catch(e) {}
      return '<div class="sched-card">' +
        '<h4>' + escHtml(t.name||'') + '</h4>' +
        '<div class="meta">⏱ ' + escHtml(t.cron_expr||'单次') + ' | 模式: ' + escHtml(t.sim_mode||'') + jsonInfo + '</div>' +
        '<div class="meta">上次执行: ' + escHtml((t.last_run_at||'--').substring(0,16)) + ' | 下次: ' + escHtml((t.next_run_at||'--').substring(0,16)) + '</div>' +
        '<div class="actions">' +
          (t.enabled ?
            '<button class="btn-tiny" onclick="pauseTask(' + t.id + ')">⏸ 暂停</button>' :
            '<button class="btn-tiny" onclick="resumeTask(' + t.id + ')">▶ 启用</button>') +
          '<button class="btn-tiny" onclick="runTaskNow(' + t.id + ')">⚡ 立即执行</button>' +
          '<button class="btn-tiny" onclick="editTask(' + t.id + ')">✏️ 编辑</button>' +
          '<button class="btn-tiny" onclick="deleteTask(' + t.id + ')">🗑 删除</button>' +
        '</div>' +
        '<div style="display:flex;align-items:center;gap:8px;">' + statusBadge + '</div>' +
      '</div>';
    }).join('');
  } catch(e) {}
}

window.pauseTask = async function(id) { await apiPost('/api/schedule/tasks/' + id + '/pause'); showToast('已暂停','success'); loadScheduledTasks(); };
window.resumeTask = async function(id) { await apiPost('/api/schedule/tasks/' + id + '/resume'); showToast('已恢复','success'); loadScheduledTasks(); };
window.runTaskNow = async function(id) { var r = await apiPost('/api/schedule/tasks/' + id + '/run-now'); showToast(r.message||'已触发',r.success?'success':'error'); };
window.deleteTask = async function(id) { if (!confirm('确定删除？')) return; await fetch('/api/schedule/tasks/' + id, {method:'DELETE'}); showToast('已删除','success'); loadScheduledTasks(); };

// ── 弹窗控制 ───────────────────────────────────────────────────────
function showSchedModal(title, data) {
  editingTaskId = data ? data.id : null;
  document.getElementById('sched-modal-title').textContent = title;
  document.getElementById('sch-name').value = data ? (data.name||'') : '';
  document.getElementById('sch-mode').value = data ? (data.sim_mode||'replay') : 'replay';
  document.getElementById('sch-drones').value = 10;
  document.getElementById('sch-duration').value = 5;
  document.getElementById('sch-cron-expr').value = data ? (data.cron_expr||'*/30 * * * *') : '*/30 * * * *';
  document.getElementById('sch-enabled').checked = data ? (data.enabled === 1) : true;

  // 解析 sim_params
  if (data && data.sim_params) {
    try {
      var sp = JSON.parse(data.sim_params);
      document.getElementById('sch-drones').value = sp.target_drones || 10;
      document.getElementById('sch-duration').value = sp.duration_min || 5;
    } catch(e) {}
  }
  document.getElementById('sched-modal').classList.add('show');
  refreshJsonFileList();
}

function hideSchedModal() {
  document.getElementById('sched-modal').classList.remove('show');
}

document.getElementById('btn-sched-cancel').addEventListener('click', hideSchedModal);
document.getElementById('sched-modal').addEventListener('click', function(e) {
  if (e.target === this) hideSchedModal();
});

// ── JSON 文件列表加载 ──────────────────────────────────────────────
async function refreshJsonFileList() {
  var sel = document.getElementById('sch-json-file');
  try {
    var data = await apiGet('/api/data/db/files?page_size=100');
    if (data.files && data.files.length) {
      sel.innerHTML = '<option value="">— 使用默认文件 —</option>' +
        data.files.map(function(f) {
          return '<option value="' + f.id + '">' + escHtml(f.name) + ' [' + escHtml(f.category||'') + ', ' + (f.size_bytes? (f.size_bytes/1024).toFixed(1)+'KB' : '') + ']</option>';
        }).join('');
      document.getElementById('sch-file-info').textContent = '共 ' + data.total + ' 个文件';
    } else {
      sel.innerHTML = '<option value="">— 无可用文件，请先在"数据管理"页上传 —</option>';
    }
  } catch(e) { sel.innerHTML = '<option value="">加载失败</option>'; }
}

document.getElementById('btn-sch-refresh-files').addEventListener('click', refreshJsonFileList);

// ── 时间类型切换 ────────────────────────────────────────────────────
document.getElementById('sch-time-cron').addEventListener('change', function() {
  document.getElementById('sch-cron-area').style.display = '';
  document.getElementById('sch-once-area').style.display = 'none';
});
document.getElementById('sch-time-once').addEventListener('change', function() {
  document.getElementById('sch-cron-area').style.display = 'none';
  document.getElementById('sch-once-area').style.display = '';
  // 默认明天此时
  var d = new Date(Date.now() + 86400000);
  document.getElementById('sch-once-date').value = d.toISOString().substring(0,10);
});

// ── Cron 快捷按钮 ───────────────────────────────────────────────────
document.querySelectorAll('.cron-preset').forEach(function(btn) {
  btn.addEventListener('click', function() {
    document.getElementById('sch-cron-expr').value = this.dataset.cron;
    document.querySelectorAll('.cron-preset').forEach(function(b) { b.style.background = ''; b.style.color = ''; });
    this.style.background = 'var(--accent)'; this.style.color = '#fff';
  });
});

// ── 新建按钮 ───────────────────────────────────────────────────────
document.getElementById('btn-sched-new').addEventListener('click', function() {
  showSchedModal('新建定时任务', null);
});

// ── 编辑按钮 ───────────────────────────────────────────────────────
window.editTask = async function(id) {
  try {
    var data = await apiGet('/api/schedule/tasks');
    var task = (data.tasks||[]).find(function(t) { return t.id === id; });
    if (task) showSchedModal('编辑任务: ' + (task.name||''), task);
  } catch(e) { showToast('加载失败', 'error'); }
};

// ── 保存 ───────────────────────────────────────────────────────────
document.getElementById('btn-sched-save').addEventListener('click', async function() {
  var name = document.getElementById('sch-name').value.trim();
  if (!name) { showToast('请输入任务名称', 'error'); return; }

  var timeType = document.querySelector('input[name="sch-time-type"]:checked').value;
  var cronExpr = timeType === 'once'
    ? _onceToCron(document.getElementById('sch-once-date').value, document.getElementById('sch-once-time').value)
    : document.getElementById('sch-cron-expr').value.trim();

  // 收集 JSON 文件信息
  var jsonFileId = document.getElementById('sch-json-file').value;
  var jsonFileName = document.getElementById('sch-json-file').selectedOptions[0] ? document.getElementById('sch-json-file').selectedOptions[0].text : '';

  var simParams = {
    target_drones: parseInt(document.getElementById('sch-drones').value) || 10,
    duration_min: parseInt(document.getElementById('sch-duration').value) || 5,
    json_file_id: jsonFileId || '',
    json_file_name: jsonFileName || '',
  };

  var body = {
    name: name,
    cron_expr: cronExpr,
    sim_mode: document.getElementById('sch-mode').value,
    sim_params: JSON.stringify(simParams),
    enabled: document.getElementById('sch-enabled').checked ? 1 : 0,
  };
  if (editingTaskId) body.id = editingTaskId;

  var r = await apiPost('/api/schedule/tasks', body);
  if (r.success) {
    showToast(r.message||'已保存', 'success');
    hideSchedModal();
    loadScheduledTasks();
  } else {
    showToast(r.message||'保存失败', 'error');
  }
});

// ── 单次执行时间 → cron 转换 ──────────────────────────────────────
function _onceToCron(dateStr, timeStr) {
  if (!dateStr || !timeStr) return '';
  var parts = timeStr.split(':');
  return parts[1] + ' ' + parts[0] + ' ' + dateStr.substring(8) + ' ' + dateStr.substring(5,7) + ' *';
}

// 首次加载
setTimeout(loadScheduledTasks, 1500);

// 等待 Leaflet 等资源加载
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initRun);
} else {
  initRun();
}

})();
