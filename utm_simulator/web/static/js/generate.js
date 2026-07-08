/* -*- coding: utf-8 -*- */
/* 数据生成页 JS */

(function() {
'use strict';

var $ = function(sel) { return document.querySelector(sel); };

// ── Tab 切换 ───────────────────────────────────────────────────────
function initGenTabs() {
  document.querySelectorAll('.gen-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      document.querySelectorAll('.gen-tab').forEach(function(t) { t.classList.remove('active'); });
      this.classList.add('active');
      document.querySelectorAll('.gen-tab-content').forEach(function(c) { c.classList.remove('active'); });
      var target = document.getElementById('gentab-' + this.dataset.gentab);
      if (target) target.classList.add('active');
      if (this.dataset.gentab === 'batch') loadBatchPresets();
    });
  });
  document.querySelectorAll('.sub-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      var parent = this.closest('.gen-tab-content');
      if (!parent) return;
      parent.querySelectorAll('.sub-tab').forEach(function(t) { t.classList.remove('active'); });
      this.classList.add('active');
      parent.querySelectorAll('.sub-tab-content').forEach(function(c) { c.classList.remove('active'); });
      var target = document.getElementById('subtab-' + this.dataset.subtab);
      if (target) target.classList.add('active');
    });
  });
}

// ── 基础生成 ───────────────────────────────────────────────────────
$('#btn-generate').addEventListener('click', async function() {
  var body = {
    count: parseInt($('#gen-count').value) || 10,
    center_lat: parseFloat($('#gen-lat').value) || 31.315,
    center_lon: parseFloat($('#gen-lon').value) || 120.665,
    radius: parseInt($('#gen-radius').value) || 800,
    pattern: $('#gen-pattern').value,
    duration_min: parseInt($('#gen-duration').value) || 10
  };
  var el = $('#gen-result');
  el.textContent = '生成中...';
  var result = await apiPost('/api/data/files/generate', body);
  el.textContent = result.success ? '✅ ' + (result.message||'生成成功') + ' → ' + (result.file||'') : '❌ ' + (result.message||'失败');
  el.style.color = result.success ? '#2ecc71' : '#e74c3c';
});

// ── 单机航线 ───────────────────────────────────────────────────────
$('#btn-gen-single-route').addEventListener('click', async function() {
  var body = {
    uid: $('#s-uid').value, speed: parseFloat($('#s-speed').value)||15,
    altitude: parseFloat($('#s-altitude').value)||30, interval: parseInt($('#s-interval').value)||1000
  };
  var pts = $('#s-points').value.trim();
  if (pts) body.points = pts;
  else {
    body.start_lon = parseFloat($('#s-start-lon').value); body.start_lat = parseFloat($('#s-start-lat').value);
    body.end_lon = parseFloat($('#s-end-lon').value); body.end_lat = parseFloat($('#s-end-lat').value);
  }
  var el = $('#gen-single-result'); el.textContent = '生成中...';
  var result = await apiPost('/api/data/scene/single', body);
  el.textContent = result.success ? '✅ ' + (result.message||'成功') : '❌ ' + (result.error||'失败');
  el.style.color = result.success ? '#2ecc71' : '#e74c3c';
});

// ── 单机偏离 ───────────────────────────────────────────────────────
$('#btn-gen-single-deviate').addEventListener('click', async function() {
  var body = {
    uid: $('#sd-uid').value, deviate_offset: parseFloat($('#sd-deviate-offset').value)||0.001,
    deviate_start_index: parseInt($('#sd-deviate-start').value)||5,
    deviate: true, speed: parseFloat($('#sd-speed').value)||15, altitude: parseFloat($('#sd-altitude').value)||30
  };
  var pts = $('#sd-points').value.trim();
  if (pts) body.points = pts;
  else {
    body.start_lon = parseFloat($('#sd-start-lon').value); body.start_lat = parseFloat($('#sd-start-lat').value);
    body.end_lon = parseFloat($('#sd-end-lon').value); body.end_lat = parseFloat($('#sd-end-lat').value);
  }
  var el = $('#gen-deviate-result'); el.textContent = '生成中...';
  var result = await apiPost('/api/data/scene/deviate', body);
  el.textContent = result.success ? '✅ ' + (result.message||'成功') : '❌ ' + (result.error||'失败');
  el.style.color = result.success ? '#2ecc71' : '#e74c3c';
});

// ── 状态变更 ───────────────────────────────────────────────────────
$('#btn-gen-status-change').addEventListener('click', async function() {
  var body = {
    uid: $('#ss-uid').value, operating_status: parseInt($('#ss-oper-status').value)||2,
    operating_status_change_time: parseInt($('#ss-change-time').value)||5000,
    operating_status_changed: parseInt($('#ss-oper-status-changed').value)||1
  };
  var el = $('#gen-status-result'); el.textContent = '生成中...';
  var result = await apiPost('/api/data/scene/single', body);
  el.textContent = result.success ? '✅ ' + (result.message||'成功') : '❌ ' + (result.error||'失败');
  el.style.color = result.success ? '#2ecc71' : '#e74c3c';
});

// ── 平行飞行 ───────────────────────────────────────────────────────
$('#btn-gen-parallel').addEventListener('click', async function() {
  var body = {
    count: parseInt($('#mp-count').value)||30, center_lat: parseFloat($('#mp-center-lat').value)||40.818724,
    center_lng: parseFloat($('#mp-center-lng').value)||85.070136, altitude: parseInt($('#mp-altitude').value)||50,
    speed: parseFloat($('#mp-speed').value)||15, heading: parseInt($('#mp-heading').value)||90,
    spacing: parseInt($('#mp-spacing').value)||2000, layout: $('#mp-layout').value
  };
  var el = $('#gen-parallel-result'); el.textContent = '生成中...';
  var result = await apiPost('/api/data/scene/parallel', body);
  el.textContent = result.success ? '✅ ' + (result.message||'成功') : '❌ ' + (result.error||'失败');
  el.style.color = result.success ? '#2ecc71' : '#e74c3c';
});

// ── 高级偏离 ───────────────────────────────────────────────────────
$('#btn-gen-deviate-adv').addEventListener('click', async function() {
  var body = {
    route_name: $('#da-route-name').value, deviate_offset: parseInt($('#da-deviate-offset').value)||3000,
    deviate_start: parseInt($('#da-deviate-start').value)||20, deviate_mode: $('#da-deviate-mode').value
  };
  var el = $('#gen-deviate-adv-result'); el.textContent = '生成中...';
  var result = await apiPost('/api/data/scene/deviate-adv', body);
  el.textContent = result.success ? '✅ ' + (result.message||'成功') : '❌ ' + (result.error||'失败');
  el.style.color = result.success ? '#2ecc71' : '#e74c3c';
});

// ── 碰撞 ───────────────────────────────────────────────────────────
$('#btn-gen-collision').addEventListener('click', async function() {
  var body = {
    route_names: $('#col-route-names').value, uids: $('#col-uids').value,
    meeting_threshold: parseInt($('#col-meeting-threshold').value)||10,
    collision_time: parseInt($('#col-collision-time').value)||300
  };
  var el = $('#gen-collision-result'); el.textContent = '生成中...';
  var result = await apiPost('/api/data/scene/collision', body);
  el.textContent = result.success ? '✅ ' + (result.message||'成功') : '❌ ' + (result.error||'失败');
  el.style.color = result.success ? '#2ecc71' : '#e74c3c';
});

// ── 状态告警 ───────────────────────────────────────────────────────
$('#btn-gen-status-alert').addEventListener('click', async function() {
  var body = {
    count: parseInt($('#sa-count').value)||1, flight_minutes: parseInt($('#sa-flight-min').value)||1,
    scene3: $('#sa-scene3').checked, scene5: $('#sa-scene5').checked, scene3_5: $('#sa-scene35').checked
  };
  var el = $('#gen-status-alert-result'); el.textContent = '生成中...';
  var result = await apiPost('/api/data/scene/status', body);
  el.textContent = result.success ? '✅ ' + (result.message||'成功') : '❌ ' + (result.error||'失败');
  el.style.color = result.success ? '#2ecc71' : '#e74c3c';
});

// ── 批量预设 ───────────────────────────────────────────────────────
async function loadBatchPresets() {
  var el = $('#batch-preset-list');
  try {
    var data = await apiGet('/api/data/batch/presets');
    if (data.presets && data.presets.length) {
      el.innerHTML = data.presets.map(function(p) {
        return '<button class="btn-batch-preset" data-index="' + p.index + '">' + p.name + '<br><small>' + (p.desc||'') + '</small></button>';
      }).join('');
      el.querySelectorAll('.btn-batch-preset').forEach(function(btn) {
        btn.addEventListener('click', async function() {
          var idx = parseInt(this.dataset.index);
          var result = await apiPost('/api/data/batch', { config_index: idx });
          var r = $('#gen-batch-result');
          r.textContent = result.success ? '✅ ' + (result.message||'生成成功') : '❌ ' + (result.error||'失败');
          r.style.color = result.success ? '#2ecc71' : '#e74c3c';
        });
      });
    }
  } catch(e) { el.innerHTML = '<div class="empty-hint">加载失败</div>'; }
}

$('#btn-gen-batch-all').addEventListener('click', async function() {
  var r = $('#gen-batch-result'); r.textContent = '批量生成中...';
  var result = await apiPost('/api/data/batch', {});
  r.textContent = result.success ? '✅ 全部预设生成完成' : '❌ ' + (result.error||'失败');
  r.style.color = result.success ? '#2ecc71' : '#e74c3c';
});

// ── 初始化 ─────────────────────────────────────────────────────────
initGenTabs();
})();
