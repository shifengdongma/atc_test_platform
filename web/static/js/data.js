/* -*- coding: utf-8 -*- */
/* JSON 数据管理页 — v2: 路径存储 + 告警分类 + 分页预览 + 航线校验 */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var currentPage = 1;
var currentFileId = null;
var previewOffset = 0;
var previewTotalLines = 0;
var PREVIEW_PAGE_SIZE = 500;

// ── 加载文件列表（从数据库）──────────────────────────────────────────
window.loadFiles = async function(page) {
  page = page || 1;
  currentPage = page;
  var cat = $('#data-category').value;
  var alarmType = $('#data-alarm-type') ? $('#data-alarm-type').value : '';
  var kw = $('#data-search').value.trim();
  var tbody = $('#data-tbody');
  tbody.innerHTML = '<tr><td colspan="10" class="empty-hint">加载中...</td></tr>';

  try {
    var params = '?page=' + page + '&page_size=20';
    if (cat) params += '&category=' + encodeURIComponent(cat);
    if (alarmType) params += '&alarm_type=' + encodeURIComponent(alarmType);
    if (kw) params += '&keyword=' + encodeURIComponent(kw);
    var data = await apiGet('/api/data/db/files' + params);

    if (!data.files || !data.files.length) {
      tbody.innerHTML = '<tr><td colspan="10" class="empty-hint">暂无数据，点击"导入 mock/"或"新建"</td></tr>';
      $('#data-pagination').innerHTML = '';
      return;
    }

    tbody.innerHTML = data.files.map(function(f) {
      return renderFileRow(f);
    }).join('');

    // 分页
    renderPagination(data.total, data.page, data.page_size);
    // 重置批量选择状态
    var selAll = $('#data-select-all');
    if (selAll) selAll.checked = false;
    updateBatchUI();
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="10" class="empty-hint">加载失败: ' + escHtml(e.message) + '</td></tr>';
  }
};

function renderFileRow(f) {
  var modes = f.compatible_modes || [];
  var modeBadges = modes.length ? modes.map(function(m) {
    var labels = {scene:'🎬场景',plan:'📐计划'};
    return '<span class="mode-badge mode-' + m + '">' + (labels[m]||m) + '</span>';
  }).join(' ') : '<span class="mode-badge mode-unknown">通用</span>';

  var alarmHtml = getAlarmTypeBadge(f.alarm_type || '');
  var routeHtml = f.linked_route
    ? '<span class="route-cell">' + escHtml(f.linked_route) + '</span>'
    : '<span class="text-dim">-</span>';

  return '<tr>' +
    '<td><input type="checkbox" class="data-row-cb" data-id="' + f.id + '" onchange="updateBatchUI()"></td>' +
    '<td>' + f.id + '</td>' +
    '<td>' + alarmHtml + '</td>' +
    '<td class="action-cell">' +
      '<button class="btn-tiny" onclick="previewFile(' + f.id + ')" title="预览">👁</button>' +
      '<button class="btn-tiny" onclick="editFile(' + f.id + ')" title="编辑">✏️</button>' +
      '<button class="btn-tiny" onclick="executeFile(' + f.id + ')" title="导出并跳转到仿真执行">▶</button>' +
      '<button class="btn-tiny" onclick="downloadFile(' + f.id + ')" title="下载">⬇</button>' +
      '<button class="btn-tiny" onclick="deleteDbFile(' + f.id + ')" title="删除">🗑</button>' +
    '</td>' +
    '<td style="font-family:Consolas,monospace;font-size:10px;max-width:140px;overflow:hidden;text-overflow:ellipsis;" title="' + escHtml(f.simulator_id||'') + '">' + formatSimulatorId(f.simulator_id) + '</td>' +
    '<td>' + routeHtml + '</td>' +
    '<td style="font-family:Consolas,monospace;color:#4CAF50;cursor:pointer;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" onclick="previewFile(' + f.id + ')" title="' + escHtml(f.name||'') + '">' + escHtml(f.name||'') + '</td>' +
    '<td>' + (f.size_bytes ? formatSize(f.size_bytes) : '-') + '</td>' +
    '<td>' + getSourceLabel(f.source||f.created_by||'-') + '</td>' +
    '<td style="font-size:10px;">' + escHtml((f.updated_at||f.created_at||'').substring(0,10)) + '</td>' +
  '</tr>';
}

// ── 告警类型徽章 ─────────────────────────────────────────────────────
function getAlarmTypeBadge(type) {
  if (!type) return '<span class="alarm-badge" style="background:#95a5a620;color:#95a5a6;border-color:#95a5a640;">-</span>';
  var colors = {
    '碰撞预警': '#e74c3c',
    '偏航': '#f39c12',
    '最低安全高度': '#e67e22',
    '正常遥测': '#2ecc71',
    '飞行计划': '#3498db',
    '禁飞区': '#9b59b6',
  };
  var color = colors[type] || '#95a5a6';
  return '<span class="alarm-badge" style="background:' + color + '20;color:' + color + ';border:1px solid ' + color + '40;">' + escHtml(type) + '</span>';
}

function getSourceLabel(src) {
  var labels = {manual:'📝 手动',import:'📥 导入',upload:'📤 上传',generated:'🤖 生成'};
  var cls = {manual:'source-manual',import:'source-import',upload:'source-upload',generated:'source-generated'};
  var label = labels[src] || src || '-';
  var css = cls[src] || '';
  return '<span class="source-label ' + css + '">' + escHtml(label) + '</span>';
}

// ── 航线校验 ─────────────────────────────────────────────────────────
var _routeCache = {};
async function validateRouteCell(fileId, routeName) {
  if (_routeCache[routeName] !== undefined) {
    updateRouteIcon(fileId, _routeCache[routeName]);
    return;
  }
  try {
    var resp = await fetch('/api/data/db/files/' + fileId + '/validate-route');
    var result = await resp.json();
    _routeCache[routeName] = result.valid;
    updateRouteIcon(fileId, result.valid);
  } catch(e) {
    _routeCache[routeName] = null;
    updateRouteIcon(fileId, null);
  }
}

function updateRouteIcon(fileId, valid) {
  var el = document.getElementById('route-' + fileId);
  if (!el) return;
  var icon = el.querySelector('.route-check');
  if (!icon) return;
  if (valid === true) {
    icon.textContent = '✅';
    icon.title = '航线在数据库中存在';
  } else if (valid === false) {
    icon.textContent = '❌';
    icon.title = '航线在数据库中不存在';
    icon.style.color = '#e74c3c';
  } else {
    icon.textContent = '❓';
    icon.title = '无法验证（数据库不可用）';
  }
}

// ── 分页 ─────────────────────────────────────────────────────────────
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

// ── 预览（分页加载）───────────────────────────────────────────────────
window.previewFile = async function(id) {
  currentFileId = id;
  previewOffset = 0;
  try {
    var data = await apiGet('/api/data/db/files/' + id + '/preview?offset=0&limit=' + PREVIEW_PAGE_SIZE);
    if (data.error) { showToast(data.error, 'error'); return; }
    previewTotalLines = data.total_lines;
    renderPreviewLines(data.lines, data.has_more);
    $('#btn-preview-download').disabled = false;
    $('#btn-preview-export').disabled = false;
    if (data.has_more) {
      $('#btn-preview-load-more').style.display = '';
    } else {
      $('#btn-preview-load-more').style.display = 'none';
    }
    showToast(data.name + ' (' + formatSize(data.total_lines ? data.total_lines * 200 : 0) + ' 估, ' + data.total_lines + ' 行)', 'info');
  } catch(e) { showToast('加载预览失败: ' + e.message, 'error'); }
};

function renderPreviewLines(lines, hasMore) {
  var el = $('#data-preview');
  var html = '<pre class="preview-content">' +
    lines.map(function(l) { return escHtml(l); }).join('\n') +
    '</pre>';
  if (hasMore) {
    var remaining = previewTotalLines - previewOffset - PREVIEW_PAGE_SIZE;
    html += '<div class="preview-more-hint" id="preview-more-hint">... 已显示 ' + (previewOffset + PREVIEW_PAGE_SIZE) + ' / ' + previewTotalLines + ' 行，还有 ' + remaining + ' 行 ...</div>';
  }
  el.innerHTML = html;
}

async function loadMorePreview() {
  if (!currentFileId) return;
  previewOffset += PREVIEW_PAGE_SIZE;
  try {
    var data = await apiGet('/api/data/db/files/' + currentFileId + '/preview?offset=' + previewOffset + '&limit=' + PREVIEW_PAGE_SIZE);
    var el = $('#data-preview');
    var pre = el.querySelector('.preview-content');
    if (pre) {
      pre.textContent += '\n' + data.lines.join('\n');
    }
    var hint = $('#preview-more-hint');
    if (data.has_more) {
      var remaining = data.total_lines - previewOffset - PREVIEW_PAGE_SIZE;
      if (hint) {
        hint.textContent = '... 已显示 ' + Math.min(previewOffset + PREVIEW_PAGE_SIZE, data.total_lines) + ' / ' + data.total_lines + ' 行，还有 ' + remaining + ' 行 ...';
      }
    } else {
      if (hint) hint.remove();
      $('#btn-preview-load-more').style.display = 'none';
      $('#preview-more-hint') && $('#preview-more-hint').remove();
    }
  } catch(e) { showToast('加载更多失败: ' + e.message, 'error'); }
}

$('#btn-preview-load-more').addEventListener('click', loadMorePreview);

// 关闭预览
function closePreview() {
  currentFileId = null;
  previewOffset = 0;
  previewTotalLines = 0;
  $('#data-preview').innerHTML = '<div class="empty-hint">选择文件以预览内容</div>';
  $('#btn-preview-download').disabled = true;
  $('#btn-preview-export').disabled = true;
  $('#btn-preview-load-more').style.display = 'none';
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
    var fileData = await apiGet('/api/data/db/files/' + id);
    var fileName = fileData.name || ('file_' + id + '.json');
    showToast('正在导出文件并跳转...', 'info');
    var exportResult = await apiPost('/api/data/db/export/' + id);
    if (!exportResult.success) {
      showToast('导出失败: ' + (exportResult.message || ''), 'error');
      return;
    }
    var presetMode = (fileName.indexOf('route') >= 0) ? 'plan' : 'scene';
    var encodedName = encodeURIComponent(fileName);
    window.location.href = '/run?preset_file=' + encodedName + '&preset_mode=' + presetMode;
  } catch(e) {
    showToast('操作失败: ' + e.message, 'error');
  }
};

// ── 删除 ───────────────────────────────────────────────────────────
window.deleteDbFile = async function(id) {
  if (!(await showConfirm('确定删除该文件？此操作同时删除磁盘文件。', '删除文件'))) return;
  try {
    await fetch('/api/data/db/files/' + id, { method: 'DELETE' });
    showToast('已删除', 'success');
    loadFiles(currentPage);
    loadCategoryFilter();
    if (currentFileId === id) closePreview();
  } catch(e) { showToast('删除失败', 'error'); }
};

// ── 编辑/新建弹窗 ───────────────────────────────────────────────────
window.editFile = async function(id) {
  try {
    var data = await apiGet('/api/data/db/files/' + id + '?include_content=true');
    if (data.error) { showToast(data.error, 'error'); return; }
    $('#edit-modal-title').textContent = '编辑: ' + data.name;
    $('#edit-name').value = data.name || '';
    $('#edit-category').value = data.category || '';
    $('#edit-alarm-type').value = data.alarm_type || '';
    // 若 simulator_id 为空，尝试从 JSON 内容中提取 uniqueProductIdentificationCode
    var simId = data.simulator_id || '';
    if (!simId && data.content) {
      simId = extractSimulatorIdFromContent(data.content);
    }
    $('#edit-simulator-id').value = simId;
    $('#edit-linked-route').value = data.linked_route || '';
    $('#edit-desc').value = data.description || '';
    $('#edit-content').value = data.content || '';

    // 大文件警告
    var sizeMB = (data.size_bytes || 0) / 1048576;
    var truncated = data.content_truncated;
    if (sizeMB > 1 || truncated) {
      $('#edit-size-warning').style.display = '';
      if (truncated) {
        $('#edit-size-warning').textContent = '⚠ ' + (data.content_message || '文件较大，仅加载前100KB');
      }
    } else {
      $('#edit-size-warning').style.display = 'none';
    }

    $('#edit-modal').dataset.editId = id;
    // 标记文件内容是否被截断，保存时避免截断内容覆盖原文件
    $('#edit-modal').dataset.truncated = truncated ? '1' : '';
    $('#edit-content').dataset.originalSize = data.total_size || 0;
    loadAlarmTypeSelect();
  } catch(e) { showToast('加载失败: ' + e.message, 'error'); }
};

function showEditModal() {
  $('#edit-modal-title').textContent = '新建 JSON 文件';
  $('#edit-name').value = '';
  $('#edit-category').value = 'telemetry';
  $('#edit-alarm-type').value = '';
  $('#edit-simulator-id').value = '';
  $('#edit-linked-route').value = '';
  $('#edit-desc').value = '';
  $('#edit-content').value = '[]';
  $('#edit-size-warning').style.display = 'none';
  $('#edit-modal').style.display = 'flex';
  delete $('#edit-modal').dataset.editId;
  $('#edit-modal').dataset.truncated = '';
  $('#edit-content').dataset.originalSize = '0';
  loadAlarmTypeSelect();
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
  var wasTruncated = $('#edit-modal').dataset.truncated === '1';
  var originalSize = parseInt($('#edit-content').dataset.originalSize) || 0;
  var currentContent = $('#edit-content').value;
  var newContentLen = currentContent.length;

  var body = {
    name: $('#edit-name').value.trim(),
    category: $('#edit-category').value.trim(),
    alarm_type: $('#edit-alarm-type').value,
    simulator_id: $('#edit-simulator-id').value.trim(),
    linked_route: $('#edit-linked-route').value.trim(),
    description: $('#edit-desc').value.trim(),
  };

  // 保护：截断加载的大文件，除非用户明确修改了内容，否则不发送 content 字段
  // 防止 100KB 截断内容覆盖原始完整文件
  if (wasTruncated) {
    if (newContentLen > 0 && newContentLen < originalSize) {
      showToast('⚠ 文件过大仅加载了前100KB，保存将只保留元数据修改（文件内容不变）', 'info');
    }
    // 只有当用户特意删减内容且新内容确实小于原文件时才发送
    // 通常编辑大文件只修改元数据，不发送 content 保留原文件完整性
  } else {
    body.content = currentContent;
  }

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

// ── 批量操作 UI ─────────────────────────────────────────────────────
window.updateBatchUI = function() {
  var cbs = document.querySelectorAll('.data-row-cb:checked');
  var count = cbs.length;
  var btnDel = $('#btn-data-batch-delete');
  var selAll = $('#data-select-all');
  if (btnDel) btnDel.style.display = count > 0 ? '' : 'none';
  if (btnDel) btnDel.textContent = '🗑 批量删除 (' + count + ')';
  // 更新全选框状态
  if (selAll) {
    var total = document.querySelectorAll('.data-row-cb').length;
    selAll.checked = total > 0 && count === total;
    selAll.indeterminate = count > 0 && count < total;
  }
};

$('#data-select-all').addEventListener('change', function() {
  document.querySelectorAll('.data-row-cb').forEach(function(cb) { cb.checked = this.checked; }.bind(this));
  updateBatchUI();
});

// ── 批量删除 ─────────────────────────────────────────────────────────
$('#btn-data-batch-delete').addEventListener('click', async function() {
  var cbs = document.querySelectorAll('.data-row-cb:checked');
  var ids = Array.from(cbs).map(function(cb) { return parseInt(cb.dataset.id); });
  if (ids.length === 0) return;
  if (!(await showConfirm('确定删除选中的 ' + ids.length + ' 个文件？\n此操作同时删除磁盘文件，不可恢复。', '批量删除'))) return;
  try {
    var result = await apiPost('/api/data/db/files/batch-delete', {ids: ids});
    showToast(result.message || ('已删除 ' + (result.success||0) + '/' + result.total), 'success');
    loadFiles(currentPage);
    loadCategoryFilter();
    if (currentFileId && ids.indexOf(currentFileId) >= 0) closePreview();
  } catch(e) { showToast('批量删除失败: ' + (e.message || ''), 'error'); }
});

// ── 上传 ───────────────────────────────────────────────────────────
$('#btn-data-upload').addEventListener('click', function() {
  $('#file-upload-input').click();
});

$('#file-upload-input').addEventListener('change', async function() {
  var files = this.files;
  if (!files || files.length === 0) return;

  var total = files.length;
  var success = 0, fail = 0;

  for (var i = 0; i < total; i++) {
    var file = files[i];
    showToast('上传中 (' + (i + 1) + '/' + total + '): ' + file.name + '...', 'info');

    try {
      var content = await new Promise(function(resolve, reject) {
        var reader = new FileReader();
        reader.onload = function(e) { resolve(e.target.result); };
        reader.onerror = function(e) { reject(e); };
        reader.readAsText(file, 'UTF-8');
      });

      var body = {
        name: file.name,
        content: content,
        size_bytes: content.length,
        source: 'upload',
        description: '上传: ' + file.name,
      };
      var cat = file.name.indexOf('route') >= 0 ? 'route' : 'telemetry';
      body.category = cat;

      var result = await apiPost('/api/data/db/files', body);
      if (result.success) { success++; }
      else { fail++; }
    } catch(e) { fail++; }
  }

  showToast('上传完成: ' + success + ' 成功, ' + fail + ' 失败 (共 ' + total + ' 个)', success === total ? 'success' : 'error');
  loadFiles(currentPage);
  loadCategoryFilter();
  // 清空 input 以便重复选择相同文件
  this.value = '';
});

// ── 导入 mock/ ─────────────────────────────────────────────────────
$('#btn-data-import').addEventListener('click', async function() {
  showToast('正在从 mock/ 导入...', 'info');
  var result = await apiPost('/api/data/db/import');
  var msg = '导入完成: ' + (result.imported||0) + ' 新增, ' + (result.updated||0) + ' 更新, ' + (result.skipped||0) + ' 跳过';
  if (result.errors) msg += ', ' + result.errors + ' 个错误';
  showToast(msg, 'success');
  loadFiles(currentPage);
  loadCategoryFilter();
});

// ── 全部导出到磁盘（Docker 重建后恢复用）───────────────────────────────
$('#btn-data-export-all').addEventListener('click', async function() {
  if (!(await showConfirm('将数据库中所有文件导出到 data/mock/ 目录？\n已有同名文件将被跳过。', '全部导出'))) return;
  showToast('正在导出全部文件到磁盘...', 'info');
  try {
    var result = await apiPost('/api/data/db/export-all');
    var msg = result.message || ('导出完成: ' + result.success + '/' + result.total);
    showToast(msg, 'success');
    loadFiles(currentPage);
  } catch(e) {
    showToast('导出失败: ' + (e.message || ''), 'error');
  }
});

// ── 分类过滤下拉框加载 ──────────────────────────────────────────────
window.loadCategoryFilter = async function() {
  try {
    var data = await apiGet('/api/data/db/categories');
    var cats = data.categories || [];
    var alarmTypes = data.alarm_types || [];

    // 更新分类过滤下拉框
    var catSel = $('#data-category');
    var catVal = catSel.value;
    catSel.innerHTML = '<option value="">全部分类</option>' +
      cats.map(function(c) {
        return '<option value="' + escHtml(c) + '">' + escHtml(c) + '</option>';
      }).join('');
    catSel.value = catVal;

    // 更新告警类型过滤下拉框
    var alarmSel = $('#data-alarm-type');
    if (alarmSel) {
      var alarmVal = alarmSel.value;
      alarmSel.innerHTML = '<option value="">全部告警类型</option>' +
        alarmTypes.map(function(t) {
          return '<option value="' + escHtml(t) + '">' + escHtml(t) + '</option>';
        }).join('');
      alarmSel.value = alarmVal;
    }

    // 更新编辑弹窗的 datalist
    var dl = $('#category-datalist');
    if (dl) {
      dl.innerHTML = cats.map(function(c) {
        return '<option value="' + escHtml(c) + '">';
      }).join('');
    }
  } catch(e) {}
};

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
        if (!(await showConfirm('确定删除分类 "' + name + '"？\n关联文件的分类将被清空。', '删除分类'))) return;
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
  var sel = $('#data-category');
  var exists = false;
  for (var i = 0; i < sel.options.length; i++) {
    if (sel.options[i].value === name) { exists = true; break; }
  }
  if (!exists) {
    sel.appendChild(new Option(name, name));
    var dl = $('#category-datalist');
    if (dl) dl.appendChild(new Option(name, ''));
  }
  input.value = '';
  showToast('分类 "' + name + '" 已就绪，保存文件时即可使用', 'success');
  loadCategoryList();
});

$('#new-category-name').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') $('#btn-category-add').click();
});

// ── 告警类型管理弹窗 ──────────────────────────────────────────────
var alarmTypeModal = $('#alarm-type-modal');

function showAlarmTypeModal() {
  alarmTypeModal.style.display = 'flex';
  loadAlarmTypeList();
}
function hideAlarmTypeModal() {
  alarmTypeModal.style.display = 'none';
}

$('#btn-alarm-type-manage').addEventListener('click', showAlarmTypeModal);
$('#btn-alarm-type-modal-close').addEventListener('click', hideAlarmTypeModal);
alarmTypeModal.addEventListener('click', function(e) {
  if (e.target === this) hideAlarmTypeModal();
});

async function loadAlarmTypeList() {
  var el = $('#alarm-type-list');
  try {
    var data = await apiGet('/api/data/db/alarm-types');
    var types = data.alarm_types || [];
    if (!types.length) {
      el.innerHTML = '<div class="empty-hint">暂无告警类型</div>';
      return;
    }
    el.innerHTML = types.map(function(t) {
      var isBuiltin = t.is_builtin === 1;
      var badge = '<span class="alarm-badge" style="background:' + escHtml(t.color || '#64748b') + '20;color:' + escHtml(t.color || '#64748b') + ';border:1px solid ' + escHtml(t.color || '#64748b') + ';padding:2px 8px;border-radius:4px;font-size:12px;display:inline-block;min-width:60px;text-align:center;">' + escHtml(t.name) + '</span>';
      var lockIcon = isBuiltin ? ' 🔒' : '';
      var actions = isBuiltin
        ? '<span style="font-size:11px;color:var(--text-dim);">内置</span>'
        : ('<button class="btn-tiny alarm-btn-rename">✏️</button>' +
           '<button class="btn-tiny alarm-btn-delete">🗑</button>');
      return '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px;border-bottom:1px solid rgba(42,63,86,0.3);">' +
        '<div style="display:flex;align-items:center;gap:10px;">' +
          badge +
          '<span class="alarm-desc" style="font-size:12px;color:var(--text-dim);">' + escHtml(t.description || '') + '</span>' +
        '</div>' +
        '<span class="alarm-row-actions" style="display:flex;gap:4px;align-items:center;">' +
          '<input type="text" class="alarm-rename-input" value="' + escHtml(t.name) + '" style="display:none;width:120px;padding:2px 6px;background:#0d1b2a;border:1px solid var(--accent);color:var(--text);border-radius:3px;font-size:12px;">' +
          '<input type="color" class="alarm-color-input" value="' + escHtml(t.color || '#64748b') + '" style="display:none;width:30px;height:24px;padding:0;border:1px solid var(--accent);border-radius:3px;">' +
          '<button class="btn-tiny alarm-btn-save" style="display:none;color:#2ecc71;">✓</button>' +
          '<button class="btn-tiny alarm-btn-cancel" style="display:none;">✕</button>' +
          actions +
          lockIcon +
        '</span>' +
      '</div>';
    }).join('');

    // 编辑按钮
    el.querySelectorAll('.alarm-btn-rename').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('div');
        row.querySelector('.alarm-desc').style.display = 'none';
        row.querySelector('.alarm-row-actions').querySelector('.alarm-btn-rename').style.display = 'none';
        row.querySelector('.alarm-row-actions').querySelector('.alarm-btn-delete').style.display = 'none';
        row.querySelector('.alarm-rename-input').style.display = '';
        row.querySelector('.alarm-color-input').style.display = '';
        row.querySelector('.alarm-btn-save').style.display = '';
        row.querySelector('.alarm-btn-cancel').style.display = '';
        row.querySelector('.alarm-rename-input').focus();
      });
    });

    // 取消按钮
    el.querySelectorAll('.alarm-btn-cancel').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var row = btn.closest('div');
        row.querySelector('.alarm-desc').style.display = '';
        row.querySelector('.alarm-row-actions').querySelector('.alarm-btn-rename').style.display = '';
        row.querySelector('.alarm-row-actions').querySelector('.alarm-btn-delete').style.display = '';
        row.querySelector('.alarm-rename-input').style.display = 'none';
        row.querySelector('.alarm-color-input').style.display = 'none';
        row.querySelector('.alarm-btn-save').style.display = 'none';
        row.querySelector('.alarm-btn-cancel').style.display = 'none';
      });
    });

    // 保存按钮
    el.querySelectorAll('.alarm-btn-save').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        var row = btn.closest('div');
        var idx = Array.from(el.children).indexOf(row);
        var t = types[idx];
        if (!t) return;
        var newName = row.querySelector('.alarm-rename-input').value.trim();
        var newColor = row.querySelector('.alarm-color-input').value;
        if (!newName) { showToast('名称不能为空', 'error'); return; }
        var result = await apiPostWithMethod('/api/data/db/alarm-types/' + t.id, {
          name: newName,
          color: newColor,
        }, 'PUT');
        if (result.success) {
          showToast(result.message, 'success');
          loadAlarmTypeList();
          loadCategoryFilter();
        } else {
          showToast(result.message || '更新失败', 'error');
        }
      });
    });

    // 删除按钮
    el.querySelectorAll('.alarm-btn-delete').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        var row = btn.closest('div');
        var idx = Array.from(el.children).indexOf(row);
        var t = types[idx];
        if (!t) return;
        if (!(await showConfirm('确定删除告警类型 "' + t.name + '"？', '删除告警类型'))) return;
        var resp = await fetch('/api/data/db/alarm-types/' + t.id, { method: 'DELETE' });
        var result = await resp.json();
        showToast(result.message, result.success ? 'success' : 'error');
        loadAlarmTypeList();
        loadCategoryFilter();
      });
    });
  } catch(e) {
    el.innerHTML = '<div class="empty-hint">加载失败: ' + e.message + '</div>';
  }
}

// 添加新告警类型
$('#btn-alarm-type-add').addEventListener('click', async function() {
  var name = $('#new-alarm-type-name').value.trim();
  var color = $('#new-alarm-type-color').value;
  if (!name) { showToast('请输入告警类型名称', 'error'); return; }
  var result = await apiPostWithMethod('/api/data/db/alarm-types', {
    name: name,
    color: color,
    description: '',
  }, 'POST');
  if (result.success) {
    showToast(result.message, 'success');
    $('#new-alarm-type-name').value = '';
    loadAlarmTypeList();
    loadCategoryFilter();
  } else {
    showToast(result.message || '添加失败', 'error');
  }
});

$('#new-alarm-type-name').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') $('#btn-alarm-type-add').click();
});

// 动态填充编辑弹窗中的告警类型下拉框
async function loadAlarmTypeSelect() {
  var sel = $('#edit-alarm-type');
  if (!sel) return;
  var curVal = sel.value;
  try {
    var data = await apiGet('/api/data/db/alarm-types');
    var types = data.alarm_types || [];
    sel.innerHTML = '<option value="">自动检测</option>' +
      types.map(function(t) {
        return '<option value="' + escHtml(t.name) + '">' + escHtml(t.name) + '</option>';
      }).join('');
    sel.value = curVal;
  } catch(e) { /* keep defaults */ }
}

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

// ── 搜索/过滤 ──────────────────────────────────────────────────────
$('#data-search').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') loadFiles(1);
});
$('#data-category').addEventListener('change', function() { loadFiles(1); });
$('#data-alarm-type').addEventListener('change', function() { loadFiles(1); });
$('#btn-data-refresh').addEventListener('click', function() { loadFiles(currentPage); });

// ── 工具 ───────────────────────────────────────────────────────────
// ── 客户端提取模拟器ID（来自 uniqueProductIdentificationCode）───────
function extractSimulatorIdFromContent(content) {
  if (!content) return '';
  try {
    var data = JSON.parse(content);
    var seen = {};
    var ids = [];
    function add(uid) {
      if (uid && !seen[uid]) { seen[uid] = true; ids.push(uid); }
    }
    if (Array.isArray(data)) {
      for (var i = 0; i < data.length && ids.length < 10; i++) {
        var item = data[i];
        if (!item || typeof item !== 'object') continue;
        if (item.uniqueProductIdentificationCode) {
          add(String(item.uniqueProductIdentificationCode));
        } else if (item.key && item.value && typeof item.value === 'object') {
          add(String(item.value.uniqueProductIdentificationCode || item.key));
        } else if (item.key) {
          add(String(item.key));
        }
      }
    } else if (data && typeof data === 'object') {
      add(String(data.uniqueProductIdentificationCode || ''));
    }
    return ids.join(', ');
  } catch(e) { return ''; }
}

function formatSimulatorId(simId) {
  // 将逗号分隔的 UAV ID 列表格式化显示（最多展示前 2 个，超出显示 +N）
  if (!simId) return '-';
  var parts = simId.split(', ');
  // 检查末尾是否有 " 等 N 架" 后缀
  var last = parts[parts.length - 1];
  var totalSuffix = '';
  if (last && last.indexOf('等') === 0 && last.indexOf('架') > 0) {
    totalSuffix = last;
    parts.pop();
  }
  if (parts.length <= 2) {
    return escHtml(simId);
  }
  var shown = parts.slice(0, 2).join(', ');
  return escHtml(shown + ', ...' + (totalSuffix ? ' ' + totalSuffix : ' (+' + (parts.length - 2) + ')'));
}

function formatSize(bytes) {
  if (!bytes || bytes < 0) return '-';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1048576).toFixed(1) + ' MB';
}

// ── 初始化 ─────────────────────────────────────────────────────────
loadCategoryFilter();
loadFiles(1);
})();
initCommon('/data');
