/* -*- coding: utf-8 -*- */
/* 定时任务管理页 JS */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var editingTaskId = null;

// ── 加载任务列表 ─────────────────────────────────────────────────────
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

// ── 执行历史 ────────────────────────────────────────────────────────
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

// ── 任务操作 ────────────────────────────────────────────────────────
window.pauseTask = async function(id) { await apiPost('/api/schedule/tasks/'+id+'/pause'); showToast('已暂停','success'); loadTaskList(); };
window.resumeTask = async function(id) { await apiPost('/api/schedule/tasks/'+id+'/resume'); showToast('已恢复','success'); loadTaskList(); };
window.runTaskNow = async function(id) { var r=await apiPost('/api/schedule/tasks/'+id+'/run-now'); showToast(r.message||'已触发',r.success?'success':'error'); };
window.deleteTask = async function(id) { if(!confirm('确定删除？'))return; await fetch('/api/schedule/tasks/'+id,{method:'DELETE'}); showToast('已删除','success'); loadTaskList(); };

window.editTask = async function(id) {
  try {
    var resp = await apiGet('/api/schedule/tasks');
    var t = (resp.tasks||[]).find(function(x){return x.id===id;});
    if (!t) return;
    editingTaskId = t.id;
    document.getElementById('task-form-title').textContent = '✏️ 编辑定时任务: ' + (t.name||'');
    document.getElementById('tk-name').value = t.name||'';
    document.getElementById('tk-mode').value = t.sim_mode||'replay';
    document.getElementById('tk-edit-id').value = t.id;
    document.getElementById('tk-enabled').checked = (t.enabled===1);
    document.getElementById('btn-task-cancel-edit').style.display = '';
    try {
      var sp = JSON.parse(t.sim_params||'{}');
      document.getElementById('tk-drones').value = sp.target_drones||10;
    } catch(e) {}
    var parts = (t.cron_expr||'').split(' ');
    if (parts.length >= 4) {
      document.getElementById('tk-time').value = parts[1]+':'+parts[0];
      document.getElementById('tk-date').value = '2026-'+parts[3]+'-'+parts[2];
    }
    refreshTaskJsonFiles();
    document.getElementById('task-inline-form').scrollIntoView({ behavior: 'smooth' });
  } catch(e) {}
};

// ── 表单重置 ────────────────────────────────────────────────────────
function resetTaskForm() {
  document.getElementById('task-form-title').textContent = '➕ 新建定时任务';
  document.getElementById('tk-name').value = '';
  document.getElementById('tk-mode').value = 'replay';
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

// ── 默认日期设为明天 ──────────────────────────────────────────────────
(function() {
  var d = new Date(Date.now() + 86400000);
  var el = document.getElementById('tk-date');
  if (el) el.value = d.toISOString().substring(0, 10);
})();

// ── JSON 文件列表刷新 ───────────────────────────────────────────────
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

// ── 保存任务 ────────────────────────────────────────────────────────
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

// ── 初始化 ──────────────────────────────────────────────────────────
function initSchedule() {
  refreshTaskJsonFiles();
  loadTaskList();
}
initSchedule();
})();
