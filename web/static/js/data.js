/* -*- coding: utf-8 -*- */
/* JSON 数据管理页 — 数据库 CRUD + 预览 + 导入导出 + 分类管理 + 执行跳转 */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var currentPage = 1;
var currentFileId = null;
var _pendingPresetFile = null; // 待预选的导出文件名

// ── 加载文件列表（从数据库）──────────────────────────────────────────
async function loadFiles(page) {
  page = page || 1;
  currentPage = page;
  var cat = $('#data-category').value;
  var kw = $('#data-search').value.trim();
  var tbody = $('#data-tbody');
  tbody.innerHTML = '<tr><td colspan="8" class="empty-hint">加载中...</td></tr>';

  try {
    var params = '?page=' + page + '&page_size=20';
    if (cat) params += '&category=' + encodeURIComponent(cat);
    if (kw) params += '&keyword=' + encodeURIComponent(kw);
    var data = await apiGet('/api/data/db/files' + params);

    if (!data.files || !data.files.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-hint">暂无数据，点击"导入 mock/"或"新建"</td></tr>';
      $('#data-pagination').innerHTML = '';
      return;
    }

    tbody.innerHTML = data.files.map(function(f) {
      var modes = f.compatible_modes || [];
      var modeBadges = modes.length ? modes.map(function(m) {
        var labels = {scene:'🎬场景',replay:'🔁回放',replay_once:'▶️单次',plan:'📐计划'};
        return '<span class="mode-badge mode-' + m + '">' + (labels[m]||m) + '</span>';
      }).join(' ') : '<span class="mode-badge mode-unknown">通用</span>';
      return '<tr>' +
        '<td>' + f.id + '</td>' +
        '<td style="font-family:Consolas,monospace;color:#4CAF50;cursor:pointer;" onclick="previewFile(' + f.id + ')">' + escHtml(f.name||'') + '</td>' +
        '<td>' + escHtml(f.category||'-') + '</td>' +
        '<td style="font-size:10px;">' + modeBadges + '</td>' +
        '<td>' + (f.size_bytes ? formatSize(f.size_bytes) : '-') + '</td>' +
        '<td>' + escHtml(f.created_by||'-') + '</td>' +
        '<td style="font-size:10px;">' + escHtml((f.updated_at||f.created_at||'').substring(0,10)) + '</td>' +
        '<td>' +
          '<button class="btn-tiny" onclick="previewFile(' + f.id + ')">👁</button>' +
          '<button class="btn-tiny" onclick="editFile(' + f.id + ')">✏️</button>' +
          '<button class="btn-tiny" onclick="executeFile(' + f.id + ')" title="导出并跳转到仿真执行">▶</button>' +
          '<button class="btn-tiny" onclick="downloadFile(' + f.id + ')">⬇</button>' +
          '<button class="btn-tiny" onclick="deleteDbFile(' + f.id + ')">🗑</button>' +
        '</td>' +
      '</tr>';
    }).join('');

    // 分页
    renderPagination(data.total, data.page, data.page_size);
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-hint">加载失败: ' + e.message + '</td></tr>';
  }
}

function renderPagination(total, page, pageSize) {
  var totalPages = Math.ceil(total / pageSize);
  var el = $('#data-pagination');
  if (totalPages <= 1) { el.innerHTML = ''; return; }
  var html = '';
  for (var i = 1; i <= totalPages; i++) {
    html += '<button class="btn-tiny' + (i === page ? ' active' : '') + '" onclick="loadFiles(' + i + ')">' + i + '</button>';
  }
  el.innerHTML = html;
}

// ── 预览 ───────────────────────────────────────────────────────────
window.previewFile = async function(id) {
  currentFileId = id;
  try {
    var data = await apiGet('/api/data/db/files/' + id);
    if (data.error) { showToast(data.error, 'error'); return; }
    var el = $('#data-preview');
    var content = data.content || '{}';
    try {
      var obj = JSON.parse(content);
      el.innerHTML = '<pre style="margin:0;white-space:pre-wrap;">' + escHtml(JSON.stringify(obj, null, 2)) + '</pre>';
    } catch(e) {
      el.innerHTML = '<pre style="margin:0;color:var(--danger);">[非JSON内容] ' + escHtml(content.substring(0, 2000)) + '</pre>';
    }
    $('#btn-preview-download').disabled = false;
    $('#btn-preview-export').disabled = false;
    showToast((data.name||'文件') + ' (' + (data.category||'?') + ', ' + formatSize(data.size_bytes||0) + ')', 'info');
  } catch(e) { showToast('加载预览失败', 'error'); }
};

// ── 关闭预览 ───────────────────────────────────────────────────────
function closePreview() {
  currentFileId = null;
  $('#data-preview').innerHTML = '<div class="empty-hint">选择文件以预览内容</div>';
  $('#btn-preview-download').disabled = true;
  $('#btn-preview-export').disabled = true;
}

// ── 下载 ───────────────────────────────────────────────────────────
window.downloadFile = function(id) {
  window.open('/api/data/db/files/' + id + '/download', '_blank');
};

$('#btn-preview-download').addEventListener('click', function() {
  if (currentFileId) window.downloadFile(currentFileId);
});

$('#btn-preview-export').addEventListener('click', async function() {
  if (!currentFileId) return;
  var result = await apiPost('/api/data/db/export/' + currentFileId);
  showToast(result.message || (result.success ? '导出成功' : '导出失败'), result.success ? 'success' : 'error');
});

$('#btn-preview-close').addEventListener('click', closePreview);

// ── 执行按钮 — 导出文件并跳转到仿真执行页 ─────────────────────────────
window.executeFile = async function(id) {
  try {
    // 先获取文件名
    var fileData = await apiGet('/api/data/db/files/' + id);
    var fileName = fileData.name || ('file_' + id + '.json');
    showToast('正在导出文件并跳转...', 'info');
    // 导出到 mock/
    var exportResult = await apiPost('/api/data/db/export/' + id);
    if (!exportResult.success) {
      showToast('导出失败: ' + (exportResult.message || ''), 'error');
      return;
    }
    // 根据文件名判断预设模式：含 route 用 plan，否则用 replay
    var presetMode = (fileName.indexOf('route') >= 0) ? 'plan' : 'replay';
    // 跳转到仿真执行页，携带文件参数
    var encodedName = encodeURIComponent(fileName);
    window.location.href = '/run?preset_file=' + encodedName + '&preset_mode=' + presetMode;
  } catch(e) {
    showToast('操作失败: ' + e.message, 'error');
  }
};

// ── 删除 ───────────────────────────────────────────────────────────
window.deleteDbFile = async function(id) {
  if (!confirm('确定删除该文件？')) return;
  try {
    await fetch('/api/data/db/files/' + id, { method: 'DELETE' });
    showToast('已删除', 'success');
    loadFiles(currentPage);
    loadCategoryFilter();
    // 如果删除的是当前预览的文件，关闭预览
    if (currentFileId === id) closePreview();
  } catch(e) { showToast('删除失败', 'error'); }
};

// ── 编辑/新建弹窗 ───────────────────────────────────────────────────
window.editFile = async function(id) {
  try {
    var data = await apiGet('/api/data/db/files/' + id);
    if (data.error) { showToast(data.error, 'error'); return; }
    $('#edit-modal-title').textContent = '编辑: ' + data.name;
    $('#edit-name').value = data.name || '';
    $('#edit-category').value = data.category || '';
    $('#edit-desc').value = data.description || '';
    $('#edit-content').value = data.content || '';
    $('#edit-modal').style.display = 'flex';
    $('#edit-modal').dataset.editId = id;
  } catch(e) { showToast('加载失败', 'error'); }
};

function showEditModal() {
  $('#edit-modal-title').textContent = '新建 JSON 文件';
  $('#edit-name').value = '';
  $('#edit-category').value = 'telemetry';
  $('#edit-desc').value = '';
  $('#edit-content').value = '[]';
  $('#edit-modal').style.display = 'flex';
  delete $('#edit-modal').dataset.editId;
}

function hideEditModal() {
  $('#edit-modal').style.display = 'none';
}

$('#btn-data-new').addEventListener('click', showEditModal);
$('#btn-edit-cancel').addEventListener('click', hideEditModal);
$('#edit-modal').addEventListener('click', function(e) {
  if (e.target === this) hideEditModal();
});

$('#btn-edit-save').addEventListener('click', async function() {
  var body = {
    name: $('#edit-name').value.trim(),
    category: $('#edit-category').value.trim(),
    description: $('#edit-desc').value.trim(),
    content: $('#edit-content').value,
  };
  if (!body.name) { showToast('请输入文件名', 'error'); return; }
  var editId = $('#edit-modal').dataset.editId;
  if (editId) body.id = parseInt(editId);

  var result = await apiPost('/api/data/db/files', body);
  if (result.success) {
    showToast(result.message || '已保存', 'success');
    hideEditModal();
    loadFiles(currentPage);
    loadCategoryFilter();
  } else {
    showToast(result.message || '保存失败', 'error');
  }
});

// ── 上传 ───────────────────────────────────────────────────────────
$('#btn-data-upload').addEventListener('click', function() {
  $('#file-upload-input').click();
});

$('#file-upload-input').addEventListener('change', async function() {
  var file = this.files[0];
  if (!file) return;
  var reader = new FileReader();
  reader.onload = async function(e) {
    var content = e.target.result;
    var body = {
      name: file.name,
      category: file.name.indexOf('route')>=0 ? 'route' : 'telemetry',
      content: content,
      size_bytes: content.length,
      description: '上传: ' + file.name,
      created_by: 'upload',
    };
    var result = await apiPost('/api/data/db/files', body);
    if (result.success) {
      showToast('上传成功: ' + file.name, 'success');
      loadFiles(currentPage);
      loadCategoryFilter();
    } else {
      showToast('上传失败: ' + (result.message||''), 'error');
    }
  };
  reader.readAsText(file, 'UTF-8');
});

// ── 导入 mock/ ─────────────────────────────────────────────────────
$('#btn-data-import').addEventListener('click', async function() {
  showToast('正在从 mock/ 导入...', 'info');
  var result = await apiPost('/api/data/db/import');
  showToast('导入完成: ' + (result.imported||0) + ' 个文件, ' + (result.errors||0) + ' 个错误', 'success');
  loadFiles(currentPage);
  loadCategoryFilter();
});

// ── 分类过滤下拉框加载 ──────────────────────────────────────────────
async function loadCategoryFilter() {
  try {
    var data = await apiGet('/api/data/db/categories');
    var cats = data.categories || [];
    // 更新过滤下拉框
    var sel = $('#data-category');
    var currentVal = sel.value;
    sel.innerHTML = '<option value="">全部分类</option>' +
      cats.map(function(c) {
        return '<option value="' + escHtml(c) + '">' + escHtml(c) + '</option>';
      }).join('');
    sel.value = currentVal; // 保持选中值（如果还存在）
    // 更新编辑弹窗的 datalist
    var dl = $('#category-datalist');
    if (dl) {
      dl.innerHTML = cats.map(function(c) {
        return '<option value="' + escHtml(c) + '">';
      }).join('');
    }
  } catch(e) {}
}

// ── 分类管理弹窗 ──────────────────────────────────────────────────
var categoryModal = $('#category-modal');

function showCategoryModal() {
  categoryModal.style.display = 'flex';
  loadCategoryList();
}

function hideCategoryModal() {
  categoryModal.style.display = 'none';
}

$('#btn-category-manage').addEventListener('click', showCategoryModal);
$('#btn-category-modal-close').addEventListener('click', hideCategoryModal);
categoryModal.addEventListener('click', function(e) {
  if (e.target === this) hideCategoryModal();
});

async function loadCategoryList() {
  var el = $('#category-list');
  try {
    var data = await apiGet('/api/data/db/categories');
    var cats = data.categories || [];
    if (!cats.length) {
      el.innerHTML = '<div class="empty-hint">暂无分类，使用下方输入框添加</div>';
      return;
    }
    el.innerHTML = cats.map(function(c) {
      return '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-bottom:1px solid rgba(42,63,86,0.3);">' +
        '<span class="cat-name" style="font-size:13px;color:var(--text);">' + escHtml(c) + '</span>' +
        '<span class="cat-actions" style="display:flex;gap:4px;">' +
          '<input type="text" class="cat-rename-input" value="' + escHtml(c) + '" style="display:none;width:120px;padding:2px 6px;background:#0d1b2a;border:1px solid var(--accent);color:var(--text);border-radius:3px;font-size:12px;">' +
          '<button class="btn-tiny cat-btn-rename">✏️</button>' +
          '<button class="btn-tiny cat-btn-save" style="display:none;color:#2ecc71;">✓</button>' +
          '<button class="btn-tiny cat-btn-cancel" style="display:none;">✕</button>' +
          '<button class="btn-tiny cat-btn-delete">🗑</button>' +
        '</span>' +
      '</div>';
    }).join('');

    // 绑定事件
    el.querySelectorAll('.cat-btn-rename').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('div');
        var nameEl = row.querySelector('.cat-name');
        var inputEl = row.querySelector('.cat-rename-input');
        var renameBtn = row.querySelector('.cat-btn-rename');
        var saveBtn = row.querySelector('.cat-btn-save');
        var cancelBtn = row.querySelector('.cat-btn-cancel');
        nameEl.style.display = 'none';
        inputEl.style.display = '';
        renameBtn.style.display = 'none';
        saveBtn.style.display = '';
        cancelBtn.style.display = '';
        inputEl.focus();
        inputEl.select();
      });
    });

    el.querySelectorAll('.cat-btn-save').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        var row = btn.closest('div');
        var nameEl = row.querySelector('.cat-name');
        var inputEl = row.querySelector('.cat-rename-input');
        var oldName = nameEl.textContent.trim();
        var newName = inputEl.value.trim();
        if (!newName || newName === oldName) {
          cancelEdit(row); return;
        }
        var result = await apiPostWithMethod('/api/data/db/categories', { old_name: oldName, new_name: newName }, 'PUT');
        if (result.success) {
          showToast(result.message, 'success');
          loadCategoryList();
          loadCategoryFilter();
          loadFiles(currentPage);
        } else {
          showToast(result.message || '重命名失败', 'error');
        }
      });
    });

    el.querySelectorAll('.cat-btn-cancel').forEach(function(btn) {
      btn.addEventListener('click', function() {
        cancelEdit(btn.closest('div'));
      });
    });

    el.querySelectorAll('.cat-btn-delete').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        var row = btn.closest('div');
        var name = row.querySelector('.cat-name').textContent.trim();
        if (!confirm('确定删除分类 "' + name + '"？\n关联文件的分类将被清空。')) return;
        try {
          var resp = await fetch('/api/data/db/categories/' + encodeURIComponent(name), { method: 'DELETE' });
          var result = await resp.json();
          showToast(result.message, 'success');
          loadCategoryList();
          loadCategoryFilter();
          loadFiles(currentPage);
        } catch(e) { showToast('删除失败', 'error'); }
      });
    });
  } catch(e) {
    el.innerHTML = '<div class="empty-hint">加载失败: ' + e.message + '</div>';
  }
}

function cancelEdit(row) {
  var nameEl = row.querySelector('.cat-name');
  var inputEl = row.querySelector('.cat-rename-input');
  var renameBtn = row.querySelector('.cat-btn-rename');
  var saveBtn = row.querySelector('.cat-btn-save');
  var cancelBtn = row.querySelector('.cat-btn-cancel');
  nameEl.style.display = '';
  inputEl.style.display = 'none';
  renameBtn.style.display = '';
  saveBtn.style.display = 'none';
  cancelBtn.style.display = 'none';
}

// 添加新分类
$('#btn-category-add').addEventListener('click', async function() {
  var input = $('#new-category-name');
  var name = input.value.trim();
  if (!name) { showToast('请输入分类名称', 'error'); return; }
  // 通过保存一个临时文件来创建分类（实际使用中，保存任务时会自然创建）
  // 这里直接更新 datalist + 过滤下拉框的选项
  var sel = $('#data-category');
  var exists = false;
  for (var i = 0; i < sel.options.length; i++) {
    if (sel.options[i].value === name) { exists = true; break; }
  }
  if (!exists) {
    // 将新分类添加到下拉框和 datalist
    sel.appendChild(new Option(name, name));
    var dl = $('#category-datalist');
    if (dl) dl.appendChild(new Option(name, ''));
  }
  input.value = '';
  showToast('分类 "' + name + '" 已就绪，保存文件时即可使用', 'success');
  loadCategoryList();
});

// 回车键添加分类
$('#new-category-name').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') $('#btn-category-add').click();
});

// ── apiPostWithMethod — 支持 PUT/DELETE ─────────────────────────────
async function apiPostWithMethod(url, body, method) {
  method = method || 'POST';
  var resp = await fetch(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return resp.json();
}

// ── 搜索/分类过滤 ──────────────────────────────────────────────────
$('#data-search').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') loadFiles(1);
});
$('#data-category').addEventListener('change', function() { loadFiles(1); });
$('#btn-data-refresh').addEventListener('click', function() { loadFiles(currentPage); });

// ── 工具 ───────────────────────────────────────────────────────────
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1048576).toFixed(1) + ' MB';
}

// ── 初始化 ─────────────────────────────────────────────────────────
loadCategoryFilter();
loadFiles(1);
})();
