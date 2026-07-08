/* -*- coding: utf-8 -*- */
/* JSON 数据管理页 — 数据库 CRUD + 预览 + 导入导出 */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var currentPage = 1;
var currentFileId = null;

// ── 加载文件列表（从数据库）──────────────────────────────────────────
async function loadFiles(page) {
  page = page || 1;
  currentPage = page;
  var cat = $('#data-category').value;
  var kw = $('#data-search').value.trim();
  var tbody = $('#data-tbody');
  tbody.innerHTML = '<tr><td colspan="7" class="empty-hint">加载中...</td></tr>';

  try {
    var params = '?page=' + page + '&page_size=20';
    if (cat) params += '&category=' + encodeURIComponent(cat);
    if (kw) params += '&keyword=' + encodeURIComponent(kw);
    var data = await apiGet('/api/data/db/files' + params);

    if (!data.files || !data.files.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-hint">暂无数据，点击"导入 mock/"或"新建"</td></tr>';
      $('#data-pagination').innerHTML = '';
      return;
    }

    tbody.innerHTML = data.files.map(function(f) {
      return '<tr>' +
        '<td>' + f.id + '</td>' +
        '<td style="font-family:Consolas,monospace;color:#4CAF50;cursor:pointer;" onclick="previewFile(' + f.id + ')">' + escHtml(f.name||'') + '</td>' +
        '<td>' + escHtml(f.category||'-') + '</td>' +
        '<td>' + (f.size_bytes ? formatSize(f.size_bytes) : '-') + '</td>' +
        '<td>' + escHtml(f.created_by||'-') + '</td>' +
        '<td style="font-size:10px;">' + escHtml((f.updated_at||f.created_at||'').substring(0,10)) + '</td>' +
        '<td>' +
          '<button class="btn-tiny" onclick="previewFile(' + f.id + ')">👁</button>' +
          '<button class="btn-tiny" onclick="editFile(' + f.id + ')">✏️</button>' +
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

// ── 删除 ───────────────────────────────────────────────────────────
window.deleteDbFile = async function(id) {
  if (!confirm('确定删除该文件？')) return;
  try {
    await fetch('/api/data/db/files/' + id, { method: 'DELETE' });
    showToast('已删除', 'success');
    loadFiles(currentPage);
  } catch(e) { showToast('删除失败', 'error'); }
};

// ── 编辑/新建弹窗 ───────────────────────────────────────────────────
window.editFile = async function(id) {
  try {
    var data = await apiGet('/api/data/db/files/' + id);
    if (data.error) { showToast(data.error, 'error'); return; }
    $('#edit-modal-title').textContent = '编辑: ' + data.name;
    $('#edit-name').value = data.name || '';
    $('#edit-category').value = data.category || 'telemetry';
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
    category: $('#edit-category').value,
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
});

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
loadFiles(1);
})();
