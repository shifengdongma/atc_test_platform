/* -*- coding: utf-8 -*- */
/* 场景编排 — 三标签页 (单文件 / 多文件 / 任务列表) */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var jsonFileCache = [];
// 兼容 jQuery 风格 $(fn) 的简写：页面就绪后执行
window._$ready = function(fn) { if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', fn); } else { fn(); } };

// ── 标签页切换 ────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(function(btn) {
  btn.addEventListener('click', function() {
    document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
    document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
    btn.classList.add('active');
    var panel = document.getElementById(btn.dataset.tab);
    if (panel) panel.classList.add('active');
    if (btn.dataset.tab === 'tab-list') loadTaskList();
  });
});

// ── 公共：JSON文件列表 + 环境列表 ──────────────────────────────────
async function refreshJsonFiles() {
  try {
    var data = await apiGet('/api/data/db/files?page_size=200');
    if (data.files && data.files.length) {
      jsonFileCache = data.files;
      var opts = '<option value="">— 选择文件 —</option>' + data.files.map(function(f) { return '<option value="'+f.id+'">'+escHtml(f.name)+' ['+(f.category||'')+']</option>'; }).join('');
      var sel = $('#s-file');
      if (sel) sel.innerHTML = opts;
    }
  } catch(e) {}
}

function buildFileOpts(selId) {
  var opts = '<option value="">— 选择 —</option>';
  jsonFileCache.forEach(function(f) { opts += '<option value="'+f.id+'">'+escHtml(f.name)+'</option>'; });
  return opts;
}

async function refreshEnvList() {
  try {
    var data = await apiGet('/api/env/list');
    if (data.envs && data.envs.length) {
      var opts = '<option value="0">— 默认环境 —</option>' + data.envs.map(function(e) { return '<option value="'+e.id+'">'+escHtml(e.name||'')+'</option>'; }).join('');
      var s = $('#s-env'), m = $('#m-env');
      if (s) s.innerHTML = opts;
      if (m) m.innerHTML = opts;
    }
  } catch(e) {}
}

// ── 公共：cron 构建 ───────────────────────────────────────────────
function buildCron(dateEl, timeEl, repeatEl) {
  var d = $(dateEl).value, t = $(timeEl).value, r = $(repeatEl).value;
  if (!d || !t || r === 'once') return '';
  var dp = d.split('-'), tp = t.split(':');
  return tp[1] + ' ' + tp[0] + ' ' + dp[2] + ' ' + dp[1] + ' ' + (r==='daily'?'*':r==='weekly'?'*':dp[2]);
}

// ── 公共：显示历史 ─────────────────────────────────────────────────
async function showHistory(sceneId, elId) {
  var el = $(elId);
  if (!el) return;
  try {
    var data = await apiGet('/api/scenes/' + sceneId + '/history');
    if (!data.history || !data.history.length) { el.innerHTML = '<div class="empty-hint">—</div>'; return; }
    el.innerHTML = data.history.slice(0,12).map(function(h) {
      var c = h.status==='success'?'#2ecc71':h.status==='failed'?'#e74c3c':'#f39c12';
      return '<div style="padding:1px 0;"><span style="color:'+c+'">'+escHtml(h.status)+'</span> ['+escHtml((h.started_at||'').substring(5,16))+'] '+escHtml((h.message||'').substring(0,80))+'</div>';
    }).join('');
  } catch(e) {}
}

// ═══════════════════════════════════════════════════════════════════
// 标签页1: 单文件场景
// ═══════════════════════════════════════════════════════════════════

(function() { var d = new Date(Date.now()+86400000); var el = $('#s-date'); if (el) el.value = d.toISOString().substring(0,10); })();

$('#btn-s-refresh').addEventListener('click', refreshJsonFiles);

function resetSingleForm() {
  $('#single-form-title').textContent = '➕ 新建单文件场景';
  $('#s-name').value = '';
  $('#s-mode').value = 'scene';
  $('#s-interval').value = 30;
  $('#s-file').value = '';
  $('#s-date').value = '';
  $('#s-time').value = '09:00';
  $('#s-repeat').value = 'once';
  $('#s-enabled').checked = true;
  $('#s-edit-id').value = '';
  $('#btn-s-cancel').style.display = 'none';
}

$('#btn-s-cancel').addEventListener('click', resetSingleForm);

$('#btn-s-save').addEventListener('click', async function() {
  var name = $('#s-name').value.trim();
  if (!name) { showToast('请输入场景名称','error'); return; }
  var body = {
    name: name,
    env_id: parseInt($('#s-env').value)||0,
    scene_type: 'single',
    sim_mode: $('#s-mode').value,
    cron_expr: buildCron('#s-date','#s-time','#s-repeat'),
    enabled: $('#s-enabled').checked?1:0,
    file_id: $('#s-file').value||null,
    cycle_interval_sec: parseInt($('#s-interval').value)||30,
  };
  var editId = $('#s-edit-id').value;
  try {
    var r;
    if (editId) {
      var resp = await fetch('/api/scenes/'+editId, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      r = await resp.json();
    } else {
      r = await apiPost('/api/scenes', body);
    }
    if (r.success) { showToast(r.message||'已保存','success'); resetSingleForm(); loadTaskList(); }
    else { showToast(r.message||'保存失败','error'); }
  } catch(e) { showToast('请求异常: '+e.message,'error'); }
});

// ═══════════════════════════════════════════════════════════════════
// 标签页2: 多文件场景
// ═══════════════════════════════════════════════════════════════════

(function() { var d = new Date(Date.now()+86400000); var el = $('#m-date'); if (el) el.value = d.toISOString().substring(0,10); })();

var mTasks = [];
var mActiveTask = -1;

function resetMultiForm() {
  $('#multi-form-title').textContent = '➕ 新建多文件场景';
  $('#m-name').value = '';
  $('#m-edit-id').value = '';
  $('#m-enabled').checked = true;
  $('#m-date').value = '';
  $('#m-time').value = '09:00';
  $('#m-repeat').value = 'once';
  mTasks = [];
  mActiveTask = -1;
  $('#m-task-tabs').innerHTML = '';
  $('#m-task-editor').style.display = 'none';
  $('#btn-m-cancel').style.display = 'none';
}

$('#btn-m-cancel').addEventListener('click', resetMultiForm);

function saveMultiTaskEditor() {
  if (mActiveTask < 0 || mActiveTask >= mTasks.length) return;
  var t = mTasks[mActiveTask];
  t.name = $('#m-tk-name').value.trim() || ('任务'+(mActiveTask+1));
  t.task_type = $('#m-tk-type').value;
  t.cycle_interval_sec = parseInt($('#m-tk-interval').value)||0;
  t.repeat_count = parseInt($('#m-tk-repeat').value)||1;
  t.execution_timeout_sec = parseInt($('#m-tk-timeout').value)||300;
  renderMultiTabs();
}

function renderMultiTabs() {
  var c = $('#m-task-tabs');
  c.innerHTML = mTasks.map(function(t,i) {
    var cls = (i===mActiveTask)?'active':'';
    return '<span class="task-tab '+cls+'" onclick="window._selectMTask('+i+')">'+escHtml(t.name||'任务'+(i+1))+'<span class="tab-del" onclick="event.stopPropagation();window._delMTask('+i+')">×</span></span>';
  }).join('');
  if (mActiveTask>=0 && mActiveTask<mTasks.length) showMultiTaskEditor();
}

function showMultiTaskEditor() {
  var t = mTasks[mActiveTask];
  $('#m-task-editor').style.display = '';
  $('#m-tk-name').value = t.name||'';
  $('#m-tk-type').value = t.task_type||'sequential';
  $('#m-tk-interval').value = t.cycle_interval_sec||0;
  $('#m-tk-repeat').value = t.repeat_count||1;
  $('#m-tk-timeout').value = t.execution_timeout_sec||300;
  renderMultiFiles();
}

function renderMultiFiles() {
  var t = mTasks[mActiveTask], el = $('#m-task-file-list');
  if (!t.files||!t.files.length) { el.innerHTML = '<div style="font-size:11px;color:var(--text-dim);">暂无文件</div>'; return; }
  el.innerHTML = t.files.map(function(f,i) {
    var sel = buildFileOpts('mf'+i);
    return '<div class="file-row"><span>'+(i+1)+'.</span><select onchange="window._updateMFileId('+i+',this.value)">'+sel.replace('value="'+f.file_id+'"','value="'+f.file_id+'" selected')+'</select><span>间隔</span><input type="number" value="'+(f.interval_sec||0)+'" min="0" onchange="window._updateMFileInterval('+i+',this.value)">秒<button class="btn-tiny" onclick="window._delMFile('+i+')" style="color:var(--danger);">✕</button></div>';
  }).join('');
}

window._selectMTask = function(i) { saveMultiTaskEditor(); mActiveTask = i; renderMultiTabs(); };
window._delMTask = function(i) { if(!confirm('删除此任务？'))return; mTasks.splice(i,1); if(mActiveTask>=mTasks.length)mActiveTask=mTasks.length-1; renderMultiTabs(); };
window._updateMFileId = function(i,v) { mTasks[mActiveTask].files[i].file_id=parseInt(v)||0; };
window._updateMFileInterval = function(i,v) { mTasks[mActiveTask].files[i].interval_sec=parseInt(v)||0; };
window._delMFile = function(i) { mTasks[mActiveTask].files.splice(i,1); renderMultiFiles(); };

$('#btn-m-add-task').addEventListener('click', function() {
  saveMultiTaskEditor();
  mTasks.push({name:'任务'+(mTasks.length+1),task_type:'sequential',cycle_interval_sec:0,repeat_count:1,execution_timeout_sec:300,files:[]});
  mActiveTask = mTasks.length-1;
  renderMultiTabs();
});

$('#btn-m-add-file').addEventListener('click', function() {
  if (mActiveTask<0) return;
  if(!mTasks[mActiveTask].files)mTasks[mActiveTask].files=[];
  mTasks[mActiveTask].files.push({file_id:0,interval_sec:0});
  renderMultiFiles();
});

$('#btn-m-del-task').addEventListener('click', function() { if(mActiveTask>=0) _delMTask(mActiveTask); });

['m-tk-name','m-tk-type','m-tk-interval','m-tk-repeat','m-tk-timeout'].forEach(function(id) {
  var el = $('#'+id); if(!el) return;
  el.addEventListener('change', saveMultiTaskEditor);
  el.addEventListener('blur', saveMultiTaskEditor);
});

async function loadMultiSceneTasks(sceneId) {
  try {
    var resp = await apiGet('/api/scenes/'+sceneId+'/tasks');
    var tasks = resp.tasks||[];
    mTasks = [];
    for(var i=0;i<tasks.length;i++) {
      var t = tasks[i];
      var fr = await apiGet('/api/scenes/'+sceneId+'/tasks/'+t.id+'/files');
      mTasks.push({
        id: t.id, name: t.name, task_type: t.task_type||'sequential',
        cycle_interval_sec: t.cycle_interval_sec||0, repeat_count: t.repeat_count||1,
        execution_timeout_sec: t.execution_timeout_sec||300,
        files: (fr.files||[]).map(function(f){return{file_id:f.file_id,interval_sec:f.interval_sec||0};}),
      });
    }
    if(mTasks.length>0) mActiveTask=0; else mActiveTask=-1;
    renderMultiTabs();
  } catch(e) { console.error(e); }
}

$('#btn-m-save').addEventListener('click', async function() {
  var name = $('#m-name').value.trim();
  if (!name) { showToast('请输入场景名称','error'); return; }
  saveMultiTaskEditor();
  var body = {
    name: name, env_id: parseInt($('#m-env').value)||0, scene_type: 'multi',
    sim_mode: 'scene', cron_expr: buildCron('#m-date','#m-time','#m-repeat'),
    enabled: $('#m-enabled').checked?1:0,
    tasks: mTasks.map(function(t) {
      return { name: t.name||'未命名', task_type: t.task_type, cycle_interval_sec: t.cycle_interval_sec,
        repeat_count: t.repeat_count, execution_timeout_sec: t.execution_timeout_sec,
        files: (t.files||[]).map(function(f){return{file_id:f.file_id,interval_sec:f.interval_sec};}) };
    }),
  };
  var editId = $('#m-edit-id').value;
  try {
    var r;
    if (editId) {
      var resp = await fetch('/api/scenes/'+editId, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      r = await resp.json();
    } else {
      r = await apiPost('/api/scenes', body);
    }
    if (r.success) { showToast(r.message||'已保存','success'); resetMultiForm(); loadTaskList(); }
    else { showToast(r.message||'保存失败','error'); }
  } catch(e) { showToast('请求异常: '+e.message,'error'); }
});

// ═══════════════════════════════════════════════════════════════════
// 标签页3: 场景任务列表
// ═══════════════════════════════════════════════════════════════════

async function loadTaskList() {
  var el = $('#task-list-container');
  if (!el) return;
  try {
    var data = await apiGet('/api/scenes');
    if (!data.scenes||!data.scenes.length) { el.innerHTML = '<div class="empty-hint">暂无场景</div>'; return; }
    var html = '';
    for (var si=0; si<data.scenes.length; si++) {
      var s = data.scenes[si];
      var st = s.enabled ? '<span class="current-badge">启用</span>' : '<span style="color:var(--danger);font-size:10px;">暂停</span>';
      var typeLabel = s.scene_type==='multi'?'多文件':'单文件';
      html += '<div class="scene-card">'+
        '<h4>'+escHtml(s.name||'')+' '+st+' <span style="font-size:10px;color:var(--text-dim);">['+typeLabel+' | '+escHtml(s.sim_mode||'scene')+']</span></h4>'+
        '<div class="meta">调度: '+escHtml(s.cron_expr||'手动触发')+' | 环境: '+(s.env_id||'默认')+' | 上次: '+escHtml((s.last_run_at||'--').substring(0,16))+'</div>';
      // 如果是多文件，显示任务列表
      if (s.scene_type==='multi') {
        try {
          var tr = await apiGet('/api/scenes/'+s.id+'/tasks');
          if (tr.tasks && tr.tasks.length) {
            html += '<div style="margin:4px 0 0 8px;">';
            for (var ti=0; ti<tr.tasks.length; ti++) {
              var t = tr.tasks[ti];
              html += '<div class="task-info">📌 '+escHtml(t.name||'任务'+(ti+1))+
                ' <span style="color:var(--text-dim);">['+(t.task_type==='parallel'?'⚡并行':'📋顺序')+
                ' | 循环'+t.cycle_interval_sec+'s | ×'+t.repeat_count+' | 超时'+t.execution_timeout_sec+'s]</span></div>';
            }
            html += '</div>';
          }
        } catch(e) {}
      }
      html += '<div class="actions">'+
        '<button class="btn-tiny" onclick="window._toggleScene('+s.id+')">'+(s.enabled?'⏸暂停':'▶启用')+'</button>'+
        '<button class="btn-tiny" onclick="window._runScene('+s.id+')">⚡立即执行</button>'+
        '<button class="btn-tiny" onclick="window._editScene('+s.id+',\''+s.scene_type+'\')">✏️编辑</button>'+
        '<button class="btn-tiny" onclick="window._delScene('+s.id+')">🗑删除</button>'+
        '<button class="btn-tiny" onclick="window._viewHistory('+s.id+')">📜记录</button>'+
        '</div></div>';
    }
    el.innerHTML = html;
  } catch(e) { console.error(e); }
}

window._toggleScene = async function(id) { await apiPost('/api/scenes/'+id+'/toggle'); showToast('已切换','success'); loadTaskList(); };
window._runScene = async function(id) { var r = await apiPost('/api/scenes/'+id+'/run-now'); showToast(r.message||'已触发',r.success?'success':'error'); };
window._delScene = async function(id) { if(!confirm('确定删除此场景？'))return; await fetch('/api/scenes/'+id,{method:'DELETE'}); showToast('已删除','success'); loadTaskList(); };
window._viewHistory = async function(id) { showHistory(id, 'single-history'); };

window._editScene = async function(id, stype) {
  try {
    var data = await apiGet('/api/scenes');
    var s = (data.scenes||[]).find(function(x){return x.id===id;});
    if (!s) return;
    if (stype==='single') {
      // 切到单文件标签
      document.querySelector('.tab-btn[data-tab="tab-single"]').click();
      $('#single-form-title').textContent = '✏️ 编辑: '+escHtml(s.name||'');
      $('#s-name').value = s.name||'';
      $('#s-env').value = s.env_id||0;
      $('#s-mode').value = s.sim_mode||'scene';
      $('#s-edit-id').value = s.id;
      $('#s-enabled').checked = s.enabled===1;
      $('#btn-s-cancel').style.display = '';
      // 加载任务信息
      try {
        var tr = await apiGet('/api/scenes/'+id+'/tasks');
        if (tr.tasks&&tr.tasks[0]) {
          var t = tr.tasks[0];
          $('#s-interval').value = t.cycle_interval_sec||30;
          var fr = await apiGet('/api/scenes/'+id+'/tasks/'+t.id+'/files');
          if (fr.files&&fr.files[0]) $('#s-file').value = fr.files[0].file_id||'';
        }
      } catch(e) {}
      showHistory(id, 'single-history');
    } else {
      // 切到多文件标签
      document.querySelector('.tab-btn[data-tab="tab-multi"]').click();
      $('#multi-form-title').textContent = '✏️ 编辑: '+escHtml(s.name||'');
      $('#m-name').value = s.name||'';
      $('#m-env').value = s.env_id||0;
      $('#m-edit-id').value = s.id;
      $('#m-enabled').checked = s.enabled===1;
      $('#btn-m-cancel').style.display = '';
      loadMultiSceneTasks(id);
      showHistory(id, 'multi-history');
    }
  } catch(e) { console.error(e); }
};

$('#btn-list-refresh').addEventListener('click', loadTaskList);

// ── 初始化 ────────────────────────────────────────────────────────
function init() {
  refreshJsonFiles();
  refreshEnvList();
}
init();
})();
// defer 脚本在 DOM 解析后按序执行，此时 common.js 已就绪
initCommon('/scene');
