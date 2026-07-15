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

// ── 批量模式切换 ──────────────────────────────────────────────────────
var batchMode = false;
var batchRowCounter = 0;

document.getElementById('btn-mode-single').addEventListener('click', function() {
  batchMode = false;
  document.getElementById('btn-mode-single').style.background = 'var(--accent)';
  document.getElementById('btn-mode-single').style.color = '#fff';
  document.getElementById('btn-mode-batch').style.background = 'var(--bg-card)';
  document.getElementById('btn-mode-batch').style.color = 'var(--text-dim)';
  document.getElementById('task-inline-form').style.display = '';
  document.getElementById('batch-form-area').style.display = 'none';
  document.getElementById('task-form-title').textContent = editingTaskId ? document.getElementById('task-form-title').textContent : '➕ 新建定时任务';
});

document.getElementById('btn-mode-batch').addEventListener('click', function() {
  batchMode = true;
  document.getElementById('btn-mode-batch').style.background = 'var(--accent)';
  document.getElementById('btn-mode-batch').style.color = '#fff';
  document.getElementById('btn-mode-single').style.background = 'var(--bg-card)';
  document.getElementById('btn-mode-single').style.color = 'var(--text-dim)';
  document.getElementById('task-inline-form').style.display = 'none';
  document.getElementById('batch-form-area').style.display = '';
  document.getElementById('task-form-title').textContent = '📑 批量添加定时任务';
  resetTaskForm();
  if (document.getElementById('batch-tbody').children.length === 0) {
    addBatchRow();
  }
});

// ── 批量行操作 ────────────────────────────────────────────────────────
function buildJsonFileOptions() {
  var sel = document.getElementById('tk-json-file');
  var opts = '<option value="">— 默认 —</option>';
  if (sel) {
    for (var i = 0; i < sel.options.length; i++) {
      if (sel.options[i].value) {
        opts += '<option value="'+sel.options[i].value+'">'+escHtml(sel.options[i].text)+'</option>';
      }
    }
  }
  return opts;
}

function buildModeOptions() {
  return '<option value="replay">🔁 回放(循环)</option>' +
    '<option value="replay_once">▶️ 回放(单次)</option>' +
    '<option value="plan">📐 Redis插值</option>' +
    '<option value="dynamic">🎮 动态仿真</option>' +
    '<option value="scene">🎬 场景注入</option>';
}

window.addBatchRow = function() {
  batchRowCounter++;
  var tbody = document.getElementById('batch-tbody');
  var tr = document.createElement('tr');
  tr.id = 'batch-row-' + batchRowCounter;
  var tomorrow = new Date(Date.now() + 86400000).toISOString().substring(0, 10);
  tr.innerHTML =
    '<td style="padding:2px;text-align:center;">' + batchRowCounter + '</td>' +
    '<td style="padding:2px;"><input type="text" class="batch-name" placeholder="任务名" style="width:95%;font-size:11px;"></td>' +
    '<td style="padding:2px;"><select class="batch-file" style="width:95%;font-size:11px;">' + buildJsonFileOptions() + '</select></td>' +
    '<td style="padding:2px;"><select class="batch-mode" style="width:95%;font-size:11px;">' + buildModeOptions() + '</select></td>' +
    '<td style="padding:2px;"><input type="date" class="batch-date" value="' + tomorrow + '" style="width:95%;font-size:11px;"></td>' +
    '<td style="padding:2px;"><input type="time" class="batch-time" value="09:00" style="width:90%;font-size:11px;"></td>' +
    '<td style="padding:2px;"><select class="batch-repeat" style="width:90%;font-size:11px;"><option value="once">仅一次</option><option value="daily">每天</option><option value="weekly">每周</option><option value="monthly">每月</option></select></td>' +
    '<td style="padding:2px;text-align:center;"><button class="btn-tiny" onclick="removeBatchRow(\'batch-row-' + batchRowCounter + '\')" style="color:var(--danger);">✕</button></td>';
  tbody.appendChild(tr);
};

window.removeBatchRow = function(rowId) {
  var tr = document.getElementById(rowId);
  if (tr) tr.remove();
  // 重新编号
  var rows = document.querySelectorAll('#batch-tbody tr');
  rows.forEach(function(r, i) { r.cells[0].textContent = (i+1); });
};

document.getElementById('btn-batch-add-row').addEventListener('click', function() { addBatchRow(); });

// ── 批量保存 ──────────────────────────────────────────────────────────
document.getElementById('btn-batch-save').addEventListener('click', async function() {
  var rows = document.querySelectorAll('#batch-tbody tr');
  if (!rows.length) { showToast('请至少添加一行任务','error'); return; }
  var items = [];
  var valid = true;
  rows.forEach(function(tr) {
    var nameEl = tr.querySelector('.batch-name');
    var fileEl = tr.querySelector('.batch-file');
    var modeEl = tr.querySelector('.batch-mode');
    var dateEl = tr.querySelector('.batch-date');
    var timeEl = tr.querySelector('.batch-time');
    var repeatEl = tr.querySelector('.batch-repeat');
    var name = (nameEl.value||'').trim();
    if (!name) { valid = false; showToast('请填写所有任务名称','error'); return; }
    var dateVal = dateEl.value;
    var timeVal = timeEl.value;
    if (!dateVal || !timeVal) { valid = false; showToast('请选择执行日期和时间','error'); return; }
    var repeat = repeatEl.value;
    var dateParts = dateVal.split('-'); var timeParts = timeVal.split(':');
    var cronExpr = timeParts[1] + ' ' + timeParts[0] + ' ' + dateParts[2] + ' ' + dateParts[1] + ' '
      + (repeat==='daily'?'*':repeat==='weekly'?'*':repeat==='monthly'?dateParts[2]:'*');
    var fileSel = fileEl.options[fileEl.selectedIndex];
    items.push({
      name: name,
      cron_expr: cronExpr,
      sim_mode: modeEl.value,
      sim_params: JSON.stringify({
        target_drones: 10,
        duration_min: 5,
        json_file_id: fileEl.value||'',
        json_file_name: fileSel?fileSel.text:'',
        repeat: repeat,
      }),
      enabled: 1,
    });
  });
  if (!valid) return;
  try {
    var r = await apiPost('/api/schedule/tasks/batch', {items:items});
    if (r.success) {
      showToast('已批量创建 ' + r.count + ' 个任务','success');
      // 清空表格
      document.getElementById('batch-tbody').innerHTML = '';
      batchRowCounter = 0;
      loadTaskList();
    } else {
      showToast('批量创建失败','error');
    }
  } catch(e) { showToast('请求异常','error'); }
});

// ── 初始化 ──────────────────────────────────────────────────────────
function initSchedule() {
  refreshTaskJsonFiles();
  loadTaskList();
}
initSchedule();
})();
