/* -*- coding: utf-8 -*- */
/* utm_moc52 Web 可视化控制台 — 地图可视化模块 (Leaflet) */

'use strict';

// ── 坐标转换：WGS-84 → GCJ-02（火星坐标系）────────────────────
// 高德/腾讯/百度等国内瓦片使用 GCJ-02，我们的仿真数据是 WGS-84
// 需要转换后再叠加到地图上

function wgs84ToGcj02(lat, lon) {
  const A = 6378245.0;
  const EE = 0.00669342162296594323;

  function _transformLat(x, y) {
    let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin(y / 3.0 * Math.PI)) * 2.0 / 3.0;
    ret += (160.0 * Math.sin(y / 12.0 * Math.PI) + 320.0 * Math.sin(y * Math.PI / 30.0)) * 2.0 / 3.0;
    return ret;
  }

  function _transformLon(x, y) {
    let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin(x / 3.0 * Math.PI)) * 2.0 / 3.0;
    ret += (150.0 * Math.sin(x / 12.0 * Math.PI) + 300.0 * Math.sin(x / 30.0 * Math.PI)) * 2.0 / 3.0;
    return ret;
  }

  // 中国境外不转换
  if (lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271) {
    return [lat, lon];
  }

  const dLat = _transformLat(lon - 105.0, lat - 35.0);
  const dLon = _transformLon(lon - 105.0, lat - 35.0);
  const radLat = lat / 180.0 * Math.PI;
  let magic = Math.sin(radLat);
  magic = 1 - EE * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  const dLatFinal = (dLat * 180.0) / ((A * (1 - EE)) / (magic * sqrtMagic) * Math.PI);
  const dLonFinal = (dLon * 180.0) / (A / sqrtMagic * Math.cos(radLat) * Math.PI);
  return [lat + dLatFinal, lon + dLonFinal];
}

// ── 地图全局状态 ──────────────────────────────────────────────────
let map = null;
let planLayerGroup = null;
let nfzLayerGroup = null;
let legendEl = null;
let _tileErrorCount = 0;
let _mapInitAttempts = 0;
const MAX_INIT_ATTEMPTS = 50;  // 最多等 5 秒（50 × 100ms）

// 配色方案（用于区分不同航线）
const ROUTE_COLORS = [
  '#00b4d8', '#2ecc71', '#f39c12', '#e74c3c',
  '#9b59b6', '#1abc9c', '#3498db', '#e67e22',
  '#2c3e50', '#27ae60', '#8e44ad', '#16a085',
];

// ── 瓦片源配置（国内首选高德，备用 CartoDB/OSM）───────────────
const TILE_PROVIDERS = {
  gaode: {
    name: '高德地图',
    url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    options: { subdomains: '1234', maxZoom: 18, minZoom: 1 },
  },
  osm: {
    name: 'OpenStreetMap',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: { subdomains: 'abc', maxZoom: 19, minZoom: 1 },
  },
  cartodb: {
    name: 'CartoDB',
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
    options: { subdomains: 'abcd', maxZoom: 19, minZoom: 1 },
  },
};

let _currentTileLayer = null;
let _tileProviderKey = 'gaode';  // 默认高德

// ── 初始化地图 ────────────────────────────────────────────────────
function initMap() {
  if (map) return;  // 已初始化

  const container = document.getElementById('map-container');
  if (!container) return;

  // 等待容器有实际尺寸（flex 布局可能需要几个渲染帧才计算完毕）
  if (container.clientWidth === 0 || container.clientHeight === 0) {
    _mapInitAttempts++;
    if (_mapInitAttempts < MAX_INIT_ATTEMPTS) {
      setTimeout(initMap, 100);
    }
    return;
  }

  _mapInitAttempts = 0;

  // 苏州金鸡湖附近（仿真区域中心）
  const DEFAULT_CENTER = [31.315, 120.665];
  const DEFAULT_ZOOM = 13;

  map = L.map('map-container', {
    center: DEFAULT_CENTER,
    zoom: DEFAULT_ZOOM,
    zoomControl: true,
    attributionControl: false,
  });

  // 添加瓦片（高德为默认，国内秒加载）
  _addTileLayer(_tileProviderKey);

  // 瓦片加载失败提示（连续失败 ≥5 次后显示警告）
  _tileErrorCount = 0;
  map.on('tileerror', function(e) {
    _tileErrorCount++;
    if (_tileErrorCount === 5) {
      const loadingEl = document.getElementById('map-loading');
      if (loadingEl) {
        loadingEl.innerHTML = '⚠️ 地图瓦片加载失败，请检查网络连接<br><small>可尝试切换备用瓦片源</small>';
        loadingEl.style.display = '';
        loadingEl.style.color = '#f39c12';
        loadingEl.style.fontSize = '13px';
      }
    }
  });
  // 首次瓦片加载成功则清除错误提示
  map.on('tileload', function() {
    if (_tileErrorCount > 0) {
      _tileErrorCount = -999;  // 标记为已成功，不再提示
      const loadingEl = document.getElementById('map-loading');
      if (loadingEl) loadingEl.style.display = 'none';
    }
  });

  // 图层组
  planLayerGroup = L.layerGroup().addTo(map);
  nfzLayerGroup = L.layerGroup().addTo(map);

  // 图例容器
  legendEl = document.getElementById('map-legend');

  // 处理窗口大小变化
  window.addEventListener('resize', function() {
    if (map) map.invalidateSize();
  });

  // 隐藏加载提示（短暂延迟让用户看到地图已就绪）
  setTimeout(function() {
    const loadingEl = document.getElementById('map-loading');
    if (loadingEl) {
      loadingEl.style.opacity = '0';
      loadingEl.style.transition = 'opacity 0.3s';
      setTimeout(function() { loadingEl.style.display = 'none'; }, 300);
    }
  }, 300);
}

// ── 添加/切换瓦片层 ──────────────────────────────────────────────
function _addTileLayer(providerKey) {
  if (_currentTileLayer && map) {
    map.removeLayer(_currentTileLayer);
  }
  const provider = TILE_PROVIDERS[providerKey] || TILE_PROVIDERS['gaode'];
  _tileProviderKey = providerKey;

  _currentTileLayer = L.tileLayer(provider.url, Object.assign({
    maxZoom: 18,
    opacity: 0.85,
    // 瓦片加载失败时不再重试（避免浏览器卡在大量超时连接上）
    errorTileUrl: '',
  }, provider.options)).addTo(map);

  // 记录切换
  console.log('[map] 瓦片源: ' + provider.name);
}

// ── 切换瓦片源（供外部调用）─────────────────────────────────────
function switchTileProvider(providerKey) {
  if (TILE_PROVIDERS[providerKey]) {
    _addTileLayer(providerKey);
    // 重置瓦片错误计数并清除警告
    _tileErrorCount = 0;
    const loadingEl = document.getElementById('map-loading');
    if (loadingEl) {
      loadingEl.style.display = 'none';
      loadingEl.innerHTML = '';
    }
  }
}

// ── 获取颜色 ──────────────────────────────────────────────────────
function getRouteColor(index) {
  return ROUTE_COLORS[index % ROUTE_COLORS.length];
}

// ── 绘制飞行计划航线 ──────────────────────────────────────────────
function drawPlansOnMap(plans) {
  if (!map || !planLayerGroup) {
    initMap();
    // 延迟重试：initMap 可能因为容器无尺寸而延迟
    if (!map) {
      setTimeout(function() { drawPlansOnMap(plans); }, 200);
      return;
    }
  }

  // 清除旧图层
  planLayerGroup.clearLayers();
  let totalWaypoints = 0;

  if (!plans || plans.length === 0) {
    updateLegend(0, 0, nfzLayerGroup ? nfzLayerGroup.getLayers().length : 0);
    return;
  }

  const bounds = [];
  const allLayers = [];

  plans.forEach(function(plan, idx) {
    const color = getRouteColor(idx);
    const uid = plan.uniqueProductIdentificationCode || 'unknown';
    const routeList = (plan.flightPlanList && plan.flightPlanList[0]?.routeList) || [];

    if (routeList.length === 0) return;

    // 构建线段坐标（WGS-84 → GCJ-02 转换）
    const coords = [];
    routeList.forEach(function(seg, segIdx) {
      const startLat = parseFloat(seg.segmentStartLat);
      const startLon = parseFloat(seg.segmentStartLon);
      const endLat = parseFloat(seg.segmentEndLat);
      const endLon = parseFloat(seg.segmentEndLon);

      if (isNaN(startLat) || isNaN(startLon)) return;

      // 坐标转换
      const startGcj = wgs84ToGcj02(startLat, startLon);
      const endGcj = wgs84ToGcj02(endLat, endLon);

      if (segIdx === 0) coords.push(startGcj);
      coords.push(endGcj);
      totalWaypoints++;
    });

    if (coords.length < 2) return;

    // 构建图层（暂不添加到地图，最后批量添加）
    const polyline = L.polyline(coords, {
      color: color, weight: 2, opacity: 0.8,
    });
    polyline.bindPopup('<b>' + escHtml(uid) + '</b><br>航段数: ' + routeList.length);
    allLayers.push(polyline);

    const startMarker = L.circleMarker(coords[0], {
      radius: 4, fillColor: color, color: '#fff', weight: 1, fillOpacity: 0.9,
    });
    startMarker.bindPopup('起点: ' + escHtml(uid));
    allLayers.push(startMarker);

    const endMarker = L.circleMarker(coords[coords.length - 1], {
      radius: 4, fillColor: '#e74c3c', color: '#fff', weight: 1, fillOpacity: 0.9,
    });
    endMarker.bindPopup('终点: ' + escHtml(uid));
    allLayers.push(endMarker);

    // 收集边界
    coords.forEach(function(c) { bounds.push(c); });
  });

  // 使用 L.featureGroup 一次性批量添加到图层组（减少重绘）
  if (allLayers.length > 0) {
    const fg = L.featureGroup(allLayers);
    planLayerGroup.addLayer(fg);
  }

  // 自适应显示范围
  if (bounds.length > 0) {
    try {
      const latlngBounds = L.latLngBounds(bounds);
      if (latlngBounds.isValid()) {
        map.fitBounds(latlngBounds, { padding: [30, 30], maxZoom: 15 });
      }
    } catch (e) {
      // 忽略边界计算错误
    }
  }

  updateLegend(plans.length, totalWaypoints, nfzLayerGroup ? nfzLayerGroup.getLayers().length : 0);
}

// ── 绘制禁飞区多边形 ──────────────────────────────────────────────
function drawNfzsOnMap(nfzs) {
  if (!map || !nfzLayerGroup) {
    initMap();
    if (!map) {
      setTimeout(function() { drawNfzsOnMap(nfzs); }, 200);
      return;
    }
  }

  // 清除旧图层
  nfzLayerGroup.clearLayers();

  if (!nfzs || nfzs.length === 0) {
    const planLayers = planLayerGroup ? planLayerGroup.getLayers().length : 0;
    updateLegend(planLayers > 0 ? 1 : 0, 0, 0);
    return;
  }

  const allLayers = [];

  nfzs.forEach(function(nfz, idx) {
    const polygon = nfz.polygon;
    if (!polygon) return;

    // 支持 GeoJSON Polygon 格式
    let coords = null;
    if (polygon.type === 'Polygon' && polygon.coordinates?.[0]) {
      // GeoJSON: [lon, lat] → 转换并翻转为 [lat, lon]
      coords = polygon.coordinates[0].map(function(c) {
        return wgs84ToGcj02(c[1], c[0]);
      });
    } else if (Array.isArray(polygon)) {
      // 已经是 [lat, lon] 数组，转换每个点
      coords = polygon.map(function(c) {
        return wgs84ToGcj02(c[0], c[1]);
      });
    }

    if (!coords || coords.length < 3) return;

    const name = nfz.name || nfz.airspaceId || '禁飞区 ' + (idx + 1);
    const color = '#e74c3c';

    const poly = L.polygon(coords, {
      color: color,
      weight: 2,
      opacity: 0.8,
      fillColor: color,
      fillOpacity: 0.15,
    });
    allLayers.push(poly);

    poly.bindPopup(
      '<b>' + escHtml(name) + '</b><br>' +
      '类型: ' + (nfz.typeCode || '-') + '<br>' +
      '高度: ' + (nfz.lowestHeight || 0) + 'm ~ ' + (nfz.highestHeight || 0) + 'm'
    );

    // 标签
    if (coords.length > 0) {
      const center = poly.getBounds().getCenter();
      L.tooltip({
        permanent: true,
        direction: 'center',
        className: 'nfz-label',
      })
        .setContent(name)
        .setLatLng(center)
        .addTo(nfzLayerGroup);
    }
  });

  // 批量添加
  if (allLayers.length > 0) {
    allLayers.forEach(function(layer) { nfzLayerGroup.addLayer(layer); });
  }

  const planLayers = planLayerGroup ? planLayerGroup.getLayers().length : 0;
  updateLegend(planLayers > 0 ? 1 : 0, 0, nfzLayerGroup.getLayers().length);
}

// ── 清除地图图层 ──────────────────────────────────────────────────
function clearMapLayers() {
  if (planLayerGroup) planLayerGroup.clearLayers();
  if (nfzLayerGroup) nfzLayerGroup.clearLayers();
  updateLegend(0, 0, 0);
}

// ── 更新图例 ──────────────────────────────────────────────────────
function updateLegend(planCount, waypointCount, nfzCount) {
  if (!legendEl) return;

  let html = '';
  if (planCount > 0) {
    html += '<span style="color:#00b4d8">■</span> ' + planCount + ' 条航线 (' + waypointCount + ' 航点) ';
  }
  if (nfzCount > 0) {
    html += '<span style="color:#e74c3c">■</span> ' + nfzCount + ' 个禁飞区';
  }
  legendEl.innerHTML = html || '点击"加载航线"查看飞行计划';
}

// ── 辅助 ──────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// 导出
window.initMap = initMap;
window.drawPlansOnMap = drawPlansOnMap;
window.drawNfzsOnMap = drawNfzsOnMap;
window.clearMapLayers = clearMapLayers;
window.switchTileProvider = switchTileProvider;
