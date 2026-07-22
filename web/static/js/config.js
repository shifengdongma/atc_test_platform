/* -*- coding: utf-8 -*- */
/* 仿真配置页 JS */

(function() {
'use strict';

var isRunning = false;
var history = [];
var modeDescriptions = {
  scene: '🎬 场景文件注入：选择JSON按间隔发射，支持3种时间戳模式。适合特定场景精确回放。',
  plan: '📐 Redis计划插值：从Redis读飞行计划，沿航段插值生成遥测。实时监听Redis变更。'
};

// 每种仿真模式对应的工具脚本
var modeScriptTags = {
  scene: 'tools/run_kafka_scene.py (SceneEmitter 场景注入)',
  plan: 'tools/run_plan.py (PlanRunner Redis插值)'
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
  ['scene-params','plan-params'].forEach(function(id) {
    var p = document.getElementById(id);
    if (p) p.querySelectorAll('input,select,button').forEach(function(e) { e.disabled = running; });
  });
  elBadge.textContent = running ? '运行中' : '已停止';
  elBadge.className = 'badge ' + (running ? 'running' : 'stopped');
}

// ── 更新模式描述 ───────────────────────────────────────────────────
function updateMode() {
  elDesc.textContent = modeDescriptions[elMode.value] || '';
  // 更新调用脚本标注
  var scriptTag = document.getElementById('mode-script-tag');
  if (scriptTag) scriptTag.textContent = modeScriptTags[elMode.value] || '';
  ['scene-params','plan-params'].forEach(function(id) {
    var p = document.getElementById(id);
    if (p) p.style.display = 'none';
  });
  if (elMode.value === 'scene') {
    var sp = document.getElementById('scene-params');
    if (sp) sp.style.display = '';
    refreshSceneFileList();
  } else if (elMode.value === 'plan') {
    var pp = document.getElementById('plan-params');
    if (pp) pp.style.display = '';
    loadPlanRouteList();
  }
}

// ── Plan 模式：加载航线列表 ─────────────────────────────────────────
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

// ── 场景文件列表 ─────────────────────────────────────────────────
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
  } catch (e) { sel.innerHTML = '<option>加载失败</option>'; }
}

// Plan 模式刷新按钮
var btnPlanRefresh = document.getElementById('btn-plan-refresh-routes');
if (btnPlanRefresh) btnPlanRefresh.addEventListener('click', loadPlanRouteList);

// Scene 模式刷新按钮
var btnRefScene = document.getElementById('btn-refresh-scene-files');
if (btnRefScene) btnRefScene.addEventListener('click', refreshSceneFileList);

// ── 加载配置 ───────────────────────────────────────────────────────
async function fetchConfig() {
  try {
    var data = await apiGet('/api/sim/config');
    elMode.value = data.mode || 'scene';
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
  if (mode === 'plan') {
    // 仅当航线列表已渲染时才发送选择；未渲染时发送 null（后端视为"全部航线"）
    var hasCheckboxes = document.querySelectorAll('.plan-route-cb').length > 0;
    if (hasCheckboxes && typeof window.getSelectedPlanUids === 'function') {
      body.plan_selected_uids = window.getSelectedPlanUids();
    }
    // 无 checkbox 时不发送 plan_selected_uids，后端保持 None（全部航线）
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

// ── 定时任务管理 ─────────────────────────────────────────────────────

async function loadTaskList() {
  var el = document.getElementById('task-list');
  if (!el) return;
  try {
    var data = await apiGet('/api/schedule/tasks');
    if (!data.tasks || !data.tasks.length) {
      el.innerHTML = '<div class="empty-hint">暂无定时任务</div>';
      loadTaskHistory();
      return;
    }
    el.innerHTML = data.tasks.map(function(t) {
      var status = t.enabled ? '<span class="current-badge">启用</span>' : '<span style="color:var(--danger);font-size:10px;">暂停</span>';
      var jsonInfo = '';
      try { var sp = JSON.parse(t.sim_params||'{}'); jsonInfo = sp.json_file_name || ''; } catch(e) {}
      return '<div class="task-card">' +
        '<h4>' + escHtml(t.name||'') + ' ' + status + '</h4>' +
        '<div class="meta">模式: ' + escHtml(t.sim_mode||'') + (jsonInfo?' | 文件: ' + escHtml(jsonInfo):'') + '</div>' +
        '<div class="meta">⏱ 执行时间: ' + escHtml(t.cron_expr||'--') + '</div>' +
        '<div class="meta">上次: ' + escHtml((t.last_run_at||'--').substring(0,16)) + '</div>' +
        '<div class="actions">' +
          (t.enabled ? '<button class="btn-tiny" onclick="pauseTask(' + t.id + ')">⏸</button>' : '<button class="btn-tiny" onclick="resumeTask(' + t.id + ')">▶</button>') +
          '<button class="btn-tiny" onclick="runTaskNow(' + t.id + ')">⚡立即</button>' +
          '<button class="btn-tiny" onclick="editTask(' + t.id + ')">✏️</button>' +
          '<button class="btn-tiny" onclick="deleteTask(' + t.id + ')">🗑</button>' +
        '</div>' +
      '</div>';
    }).join('');
  } catch(e) {}
}

async function loadTaskHistory(taskId) {
  var el = document.getElementById('task-history');
  if (!el) return;
  try {
    var url = '/api/schedule/tasks/' + (taskId||'0') + '/history';
    var data = await apiGet(url);
    if (!data.history || !data.history.length) { el.innerHTML = '<div class="empty-hint">—</div>'; return; }
    el.innerHTML = data.history.slice(0,10).map(function(h) {
      var color = h.status==='success'?'#2ecc71':h.status==='failed'?'#e74c3c':'#f39c12';
      return '<div style="padding:2px 0;"><span style="color:'+color+'">' + escHtml(h.status) + '</span> [' + escHtml((h.started_at||'').substring(5,16)) + '] ' + escHtml((h.message||'').substring(0,80)) + '</div>';
    }).join('');
  } catch(e) {}
}

window.pauseTask = async function(id) { await apiPost('/api/schedule/tasks/'+id+'/pause'); showToast('已暂停','success'); loadTaskList(); };
window.resumeTask = async function(id) { await apiPost('/api/schedule/tasks/'+id+'/resume'); showToast('已恢复','success'); loadTaskList(); };
window.runTaskNow = async function(id) { var r=await apiPost('/api/schedule/tasks/'+id+'/run-now'); showToast(r.message||'已触发',r.success?'success':'error'); };
window.deleteTask = async function(id) { if(!confirm('确定删除？'))return; await fetch('/api/schedule/tasks/'+id,{method:'DELETE'}); showToast('已删除','success'); loadTaskList(); };

window.editTask = async function(id) {
  try {
    var resp = await apiGet('/api/schedule/tasks');
    var t = (resp.tasks||[]).find(function(x){return x.id===id;});
    if (!t) return;
    // 填充内联表单
    editingTaskId = t.id;
    document.getElementById('task-form-title').textContent = '✏️ 编辑定时任务: ' + (t.name||'');
    document.getElementById('tk-name').value = t.name||'';
    document.getElementById('tk-mode').value = t.sim_mode||'scene';
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

// ── 内联表单逻辑 ──────────────────────────────────────────────────
var editingTaskId = null;

function resetTaskForm() {
  document.getElementById('task-form-title').textContent = '➕ 新建定时任务';
  document.getElementById('tk-name').value = '';
  document.getElementById('tk-mode').value = 'scene';
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

document.getElementById('btn-task-cancel-edit').addEventListener('click', resetTaskForm);

// 默认日期设为明天
(function() {
  var d = new Date(Date.now() + 86400000);
  var el = document.getElementById('tk-date');
  if (el) el.value = d.toISOString().substring(0, 10);
})();

// ── JSON 文件列表 ────────────────────────────────────────────────
async function refreshTaskJsonFiles() {
  var sel = document.getElementById('tk-json-file');
  try {
    var data = await apiGet('/api/data/db/files?page_size=100');
    if (data.files && data.files.length) {
      sel.innerHTML = '<option value="">— 使用默认文件 —</option>' +
        data.files.map(function(f) { return '<option value="'+f.id+'">'+escHtml(f.name)+' ['+(f.category||'')+']</option>'; }).join('');
    }
  } catch(e) {}
}
document.getElementById('btn-tk-refresh-files').addEventListener('click', refreshTaskJsonFiles);

// ── 新建/保存 ────────────────────────────────────────────────────
// 内联表单 — 用户直接在右上角表单填写即可创建新任务
var btnNew = document.getElementById('btn-task-new');
if (btnNew) btnNew.addEventListener('click', resetTaskForm);

document.getElementById('btn-task-save').addEventListener('click', async function() {
  var name = document.getElementById('tk-name').value.trim();
  if (!name) { showToast('请输入任务名称','error'); return; }
  var dateVal = document.getElementById('tk-date').value;
  var timeVal = document.getElementById('tk-time').value;
  if (!dateVal || !timeVal) { showToast('请选择执行日期和时间','error'); return; }

  var repeat = document.getElementById('tk-repeat').value;
  var dateParts = dateVal.split('-'); var timeParts = timeVal.split(':');
  var cronExpr = timeParts[1] + ' ' + timeParts[0] + ' ' + dateParts[2] + ' ' + dateParts[1] + ' '
    + (repeat==='daily'?'*':repeat==='weekly'?'*':repeat==='monthly'?dateParts[2]:'*');
  // 格式: 分 时 日 月 周

  var sel = document.getElementById('tk-json-file');
  var body = {
    name: name,
    cron_expr: cronExpr,
    sim_mode: document.getElementById('tk-mode').value,
    sim_params: JSON.stringify({
      target_drones: parseInt(document.getElementById('tk-drones').value)||10,
      duration_min: 5,
      json_file_id: sel.value||'',
      json_file_name: sel.selectedOptions[0]?sel.selectedOptions[0].text:'',
      repeat: repeat,
    }),
    enabled: document.getElementById('tk-enabled').checked?1:0,
  };
  var editId = document.getElementById('tk-edit-id').value;
  if (editId) body.id = parseInt(editId);

  var r = await apiPost('/api/schedule/tasks', body);
  if (r.success) { showToast(r.message||'已保存','success'); resetTaskForm(); loadTaskList(); }
  else { showToast(r.message||'保存失败','error'); }
});

// ── 初始化：加载配置 + 同步运行状态 ──────────────────────────────────
async function initConfig() {
  await fetchConfig();
  loadTaskList();
  // 检查服务器当前是否在运行中
  syncRunningState().then(function(running) {
    if (running) setRunningState(true);
  });
  // WebSocket 持续同步状态
  onWsEvent('status', function(data) {
    if (data.running) setRunningState(true);
    else if (!data.running && isRunning) setRunningState(false);
  });
  onWsEvent('status_change', function(data) {
    if (data.event === 'started') setRunningState(true);
    else if (data.event === 'stopped') setRunningState(false);
  });
}
initConfig();
})();
