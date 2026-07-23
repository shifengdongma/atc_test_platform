/* -*- coding: utf-8 -*- */
/* 趋势图表模块 */

'use strict';

// ── 图表实例 ──────────────────────────────────────────────────────
let chartDrones = null;
let chartRedis = null;

// ── 数据缓冲区（最多保留 60 个采样点 = 1 分钟） ─────────────────
const MAX_POINTS = 60;
const dronesData = [];
const redisData = [];
const timeLabels = [];

// ── 初始化图表 ────────────────────────────────────────────────────
function initCharts() {
  const commonOpts = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 200 },
    scales: {
      x: {
        display: true,
        ticks: { color: '#7a93a8', font: { size: 9 }, maxTicksLimit: 6 },
        grid: { color: 'rgba(42,63,86,0.5)' },
      },
      y: {
        display: true,
        beginAtZero: true,
        ticks: { color: '#7a93a8', font: { size: 9 } },
        grid: { color: 'rgba(42,63,86,0.5)' },
      },
    },
    plugins: {
      legend: { display: false },
    },
  };

  // 活跃无人机数量图表
  const ctx1 = document.getElementById('chart-drones');
  if (ctx1) {
    chartDrones = new Chart(ctx1, {
      type: 'line',
      data: {
        labels: timeLabels,
        datasets: [{
          label: '活跃无人机',
          data: dronesData,
          borderColor: '#00b4d8',
          backgroundColor: 'rgba(0,180,216,0.1)',
          fill: true,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
        }],
      },
      options: {
        ...commonOpts,
        plugins: {
          ...commonOpts.plugins,
          title: {
            display: true,
            text: '活跃无人机数量',
            color: '#7a93a8',
            font: { size: 11 },
          },
        },
      },
    });
  }

  // Redis 吞吐量图表
  const ctx2 = document.getElementById('chart-redis');
  if (ctx2) {
    chartRedis = new Chart(ctx2, {
      type: 'line',
      data: {
        labels: timeLabels,
        datasets: [{
          label: 'Redis 吞吐 (条/秒)',
          data: redisData,
          borderColor: '#2ecc71',
          backgroundColor: 'rgba(46,204,113,0.1)',
          fill: true,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
        }],
      },
      options: {
        ...commonOpts,
        plugins: {
          ...commonOpts.plugins,
          title: {
            display: true,
            text: 'Redis 消息吞吐量',
            color: '#7a93a8',
            font: { size: 11 },
          },
        },
      },
    });
  }
}

// ── 添加数据点 ────────────────────────────────────────────────────
function addChartData(type, value) {
  const now = new Date();
  const label = now.toLocaleTimeString('zh-CN', {
    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

  if (type === 'drones') {
    dronesData.push(value);
    if (dronesData.length > MAX_POINTS) dronesData.shift();
    if (chartDrones) {
      chartDrones.data.labels.push(label);
      if (chartDrones.data.labels.length > MAX_POINTS) chartDrones.data.labels.shift();
      chartDrones.update('none');
    }
  } else if (type === 'redis') {
    redisData.push(value);
    if (redisData.length > MAX_POINTS) redisData.shift();
    if (chartRedis) {
      chartRedis.data.labels.push(label);
      if (chartRedis.data.labels.length > MAX_POINTS) chartRedis.data.labels.shift();
      chartRedis.update('none');
    }
  }

  // 同步时间轴
  if (timeLabels.length < MAX_POINTS) {
    if (timeLabels.length === 0 || timeLabels[timeLabels.length - 1] !== label) {
      timeLabels.push(label);
    }
  } else {
    timeLabels.shift();
    timeLabels.push(label);
  }
}

// 导出给 app.js 调用
window.initCharts = initCharts;
window.addChartData = addChartData;