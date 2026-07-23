/* -*- coding: utf-8 -*- */
/* 环境管理页 JS — Redis/Kafka 连接配置管理 */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };
var currentEnvId = null;
var editingId = null;

// ── 加载列表 ───────────────────────────────────────────────────────
async function loadEnvList() {
  var tbody = $('#env-tbody');
  var info = $('#current-info');
  try {
    var data = await apiGet('/api/env/list');
    if (!data.envs || !data.envs.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-hint">暂无环境配置，点击"新建环境"或"从 env.py 导入"</td></tr>';
    } else {
      tbody.innerHTML = data.envs.map(function(e) {
        var isCurrent = e.is_default ? ' <span class="current-badge">当前</span>' : '';
        return '<tr>' +
          '<td>' + escHtml(e.name || '') + '</td>' +
          '<td style="font-family:Consolas,monospace;font-size:11px;">' + escHtml(e.redis_ip||'') + ':' + escHtml(e.redis_port||'') + '</td>' +
          '<td style="font-family:Consolas,monospace;font-size:11px;">' + escHtml(e.kafka_url||'') + '</td>' +
          '<td>' + isCurrent + '</td>' +
          '<td>' +
            '<button class="btn-tiny" onclick="editEnv(' + e.id + ')">✏️</button>' +
            '<button class="btn-tiny" onclick="activateEnv(' + e.id + ')">🔘 切换</button>' +
            '<button class="btn-tiny" onclick="deleteEnv(' + e.id + ')">🗑</button>' +
          '</td>' +
        '</tr>';
      }).join('');
    }
    // 显示当前激活信息
    var cur = data.current || {};
    info.innerHTML = '<strong>当前激活：</strong>Redis <code>' + (cur.redis_ip||'?') + ':' + (cur.redis_port||'?') +
      '</code> | Kafka <code>' + (cur.kafka_url||'?') + '</code>' +
      (cur.kafka_url2 ? ' (地址2: ' + cur.kafka_url2 + ')' : '') +
      ' | 达梦 <code>' + (cur.dm_host||'?') + (cur.dm_schema ? '/' + cur.dm_schema : '') + '</code>' +
      ' | MySQL <code>' + (cur.mysql_host||'?') + (cur.mysql_database ? '/' + cur.mysql_database : '') + '</code>';
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-hint">加载失败: ' + e.message + '</td></tr>';
  }
}

// ── 弹窗 ───────────────────────────────────────────────────────────
function showModal(title, data) {
  $('#modal-title').textContent = title;
  editingId = data ? data.id : null;
  $('#ev-name').value = data ? (data.name||'') : '';
  // Redis
  $('#ev-redis-ip').value = data ? (data.redis_ip||'127.0.0.1') : '127.0.0.1';
  $('#ev-redis-port').value = data ? (data.redis_port||'6379') : '6379';
  $('#ev-redis-pwd').value = data ? (data.redis_pwd||'') : '';
  // Kafka
  $('#ev-kafka-url').value = data ? (data.kafka_url||'127.0.0.1:9092') : '127.0.0.1:9092';
  $('#ev-kafka-url2').value = data ? (data.kafka_url2||'') : '';
  // 达梦
  $('#ev-dm-host').value = data ? (data.dm_host||'') : '';
  $('#ev-dm-port').value = data ? (data.dm_port||5236) : 5236;
  $('#ev-dm-user').value = data ? (data.dm_user||'SYSDBA') : 'SYSDBA';
  $('#ev-dm-pwd').value = data ? (data.dm_password||'') : '';
  $('#ev-dm-schema').value = data ? (data.dm_schema||'') : '';
  // MySQL
  $('#ev-mysql-host').value = data ? (data.mysql_host||'') : '';
  $('#ev-mysql-port').value = data ? (data.mysql_port||3306) : 3306;
  $('#ev-mysql-user').value = data ? (data.mysql_user||'') : '';
  $('#ev-mysql-pwd').value = data ? (data.mysql_password||'') : '';
  $('#ev-mysql-database').value = data ? (data.mysql_database||'') : '';
  // ATC 集群
  $('#ev-atc-cluster-api').value = data ? (data.atc_cluster_api||'') : '';
  $('#ev-atc-vip').value = data ? (data.atc_vip||'') : '';
  $('#ev-atc-node-a').value = data ? (data.atc_node_a||'') : '';
  $('#ev-atc-node-b').value = data ? (data.atc_node_b||'') : '';
  // ES
  $('#ev-es-hosts').value = data ? (data.es_hosts||'') : '';
  $('#env-modal').classList.add('show');
}

function hideModal() {
  $('#env-modal').classList.remove('show');
}

$('#btn-modal-cancel').addEventListener('click', hideModal);
$('#env-modal').addEventListener('click', function(e) {
  if (e.target === this) hideModal();
});

// ── 保存 ───────────────────────────────────────────────────────────
$('#btn-modal-save').addEventListener('click', async function() {
  var name = $('#ev-name').value.trim();
  if (!name) { showToast('请输入环境名称', 'error'); return; }
  var body = {
    name: name,
    redis_ip: $('#ev-redis-ip').value.trim(),
    redis_port: $('#ev-redis-port').value.trim(),
    redis_pwd: $('#ev-redis-pwd').value,
    kafka_url: $('#ev-kafka-url').value.trim(),
    kafka_url2: $('#ev-kafka-url2').value.trim(),
    // 达梦
    dm_host: $('#ev-dm-host').value.trim(),
    dm_port: parseInt($('#ev-dm-port').value) || 5236,
    dm_user: $('#ev-dm-user').value.trim(),
    dm_password: $('#ev-dm-pwd').value,
    dm_schema: $('#ev-dm-schema').value.trim(),
    // MySQL
    mysql_host: $('#ev-mysql-host').value.trim(),
    mysql_port: parseInt($('#ev-mysql-port').value) || 3306,
    mysql_user: $('#ev-mysql-user').value.trim(),
    mysql_password: $('#ev-mysql-pwd').value,
    mysql_database: $('#ev-mysql-database').value.trim(),
    // ATC 集群
    atc_cluster_api: $('#ev-atc-cluster-api').value.trim(),
    atc_vip: $('#ev-atc-vip').value.trim(),
    atc_node_a: $('#ev-atc-node-a').value.trim(),
    atc_node_b: $('#ev-atc-node-b').value.trim(),
    // ES
    es_hosts: $('#ev-es-hosts').value.trim(),
  };
  if (editingId) body.id = editingId;
  var result = await apiPost('/api/env/save', body);
  if (result.success) {
    showToast('已保存', 'success');
    hideModal();
    loadEnvList();
  } else {
    showToast(result.message || '保存失败', 'error');
  }
});

// ── 编辑 ───────────────────────────────────────────────────────────
window.editEnv = async function(id) {
  try {
    var data = await apiGet('/api/env/' + id);
    if (data.success && data.env) {
      showModal('编辑环境', data.env);
    }
  } catch(e) { showToast('获取环境信息失败', 'error'); }
};

// ── 激活 ───────────────────────────────────────────────────────────
window.activateEnv = async function(id) {
  var result = await apiPost('/api/env/' + id + '/activate');
  if (result.success) {
    showToast(result.message, 'success');
    loadEnvList();
  } else {
    showToast(result.message || '切换失败', 'error');
  }
};

// ── 删除 ───────────────────────────────────────────────────────────
window.deleteEnv = async function(id) {
  if (!(await showConfirm('确定删除该环境配置？', '删除环境'))) return;
  try {
    var resp = await fetch('/api/env/' + id, { method: 'DELETE' });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var result = await resp.json();
    if (result.success) {
      showToast('已删除', 'success');
      loadEnvList();
    } else {
      showToast(result.message || '删除失败', 'error');
    }
  } catch(e) { showToast('删除失败: ' + (e.message || '网络错误'), 'error'); }
};

// ── 新建 ───────────────────────────────────────────────────────────
$('#btn-env-new').addEventListener('click', function() {
  showModal('新建环境', null);
});

// ── 从 env.py 导入 ─────────────────────────────────────────────────
$('#btn-env-import').addEventListener('click', async function() {
  var result = await apiPost('/api/env/import');
  if (result.success) {
    showToast(result.message, 'success');
    loadEnvList();
  } else {
    showToast(result.message || '导入失败', 'error');
  }
});

// ── 初始化 ─────────────────────────────────────────────────────────
loadEnvList();
})();
