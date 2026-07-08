/* -*- coding: utf-8 -*- */
/* JSON 数据管理页 JS — 文件浏览/搜索/预览（完整功能在 Phase 3 实现） */

(function() {
'use strict';
var $ = function(sel) { return document.querySelector(sel); };

// ── 文件列表加载（当前使用 mock/ 目录 API，Phase 3 切换为数据库 API）──
async function loadFileList() {
  var tbody = $('#data-tbody');
  if (!tbody) return;
  try {
    var data = await apiGet('/api/data/files');
    if (!data.files || !data.files.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-hint">mock/ 目录为空</td></tr>';
      return;
    }
    tbody.innerHTML = data.files.map(function(f) {
      return '<tr data-file="' + escHtml(f.name) + '">' +
        '<td style="font-family:Consolas,monospace;color:#4CAF50;cursor:pointer;" onclick="previewFile(\'' + escHtml(f.name) + '\')">' + escHtml(f.name) + '</td>' +
        '<td>' + (f.type || '-') + '</td>' +
        '<td>' + (f.size_kb ? f.size_kb+' KB' : '-') + '</td>' +
        '<td>mock/</td>' +
        '<td>-</td>' +
        '<td><button class="btn-tiny" onclick="downloadFile(\'' + escHtml(f.name) + '\')">⬇</button></td>' +
      '</tr>';
    }).join('');
  } catch(e) { tbody.innerHTML = '<tr><td colspan="6" class="empty-hint">加载失败: ' + e.message + '</td></tr>'; }
}

// ── 文件预览 ───────────────────────────────────────────────────────
window.previewFile = async function(name) {
  var el = $('#data-preview');
  if (!el) return;
  try {
    var data = await apiGet('/api/data/files/' + encodeURIComponent(name));
    el.innerHTML = '<pre style="margin:0;">' + escHtml(JSON.stringify(data, null, 2)) + '</pre>';
  } catch(e) { el.innerHTML = '<div class="empty-hint">加载失败</div>'; }
};

// ── 文件下载 ───────────────────────────────────────────────────────
window.downloadFile = function(name) {
  window.open('/api/data/files/' + encodeURIComponent(name) + '?download=1', '_blank');
};

// ── 上传 ───────────────────────────────────────────────────────────
$('#btn-data-upload').addEventListener('click', function() {
  $('#data-upload-input').click();
});
$('#data-upload-input').addEventListener('change', async function() {
  var file = this.files[0];
  if (!file) return;
  var fd = new FormData();
  fd.append('file', file);
  try {
    var resp = await fetch('/api/data/files/upload', { method: 'POST', body: fd });
    var result = await resp.json();
    showToast(result.success ? '上传成功: ' + file.name : '上传失败', result.success ? 'success' : 'error');
    if (result.success) loadFileList();
  } catch(e) { showToast('上传异常: ' + e.message, 'error'); }
});

// ── 搜索过滤 ───────────────────────────────────────────────────────
$('#data-search').addEventListener('input', function() {
  var q = this.value.toLowerCase();
  document.querySelectorAll('#data-tbody tr').forEach(function(tr) {
    var name = (tr.dataset.file || '').toLowerCase();
    tr.style.display = q ? (name.indexOf(q) >= 0 ? '' : 'none') : '';
  });
});

// ── 刷新 ───────────────────────────────────────────────────────────
$('#btn-data-refresh').addEventListener('click', loadFileList);

// ── 初始化 ─────────────────────────────────────────────────────────
loadFileList();
})();
