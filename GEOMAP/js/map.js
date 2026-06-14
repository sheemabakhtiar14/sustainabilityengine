// Leaflet map — India-only, state-level semantic segmentation, impact zones, routes, markers

const GeoMap = (() => {
  let _map, _heat, _routeGroup, _markerGroup, _clusterGroup, _segmentGroup;
  let _heatOn = true, _routesOn = false, _clustersOn = false, _segmentsOn = false, _lulcOn = false;
  let _currentView = 'impact';
  let _data = null;
  const _markers = {};

  // Real simplified polygon boundaries for India's major mining states.
  // Coordinates are [lng, lat] in GeoJSON order, tracing actual state shapes.
  const INDIA_STATE_POLYGONS = {
    'Rajasthan': [
      [72.03,29.97],[72.94,30.18],[74.05,30.41],[74.89,30.07],[75.30,30.05],
      [76.03,29.97],[76.96,29.62],[77.42,28.95],[77.42,28.28],[77.09,27.60],
      [76.90,26.99],[77.01,26.57],[76.48,26.20],[75.72,25.62],[75.09,25.09],
      [74.67,24.65],[74.04,24.13],[73.70,24.03],[73.00,23.86],[72.56,23.45],
      [72.00,23.28],[71.00,23.07],[70.63,23.39],[70.24,23.99],[70.03,24.56],
      [69.86,25.41],[69.61,26.41],[69.72,27.05],[70.38,27.99],[70.65,28.94],
      [71.03,29.59],[72.03,29.97]
    ],
    'Madhya Pradesh': [
      [74.04,26.87],[75.62,26.99],[76.91,26.90],[78.24,26.98],[79.28,26.86],
      [80.07,26.48],[80.61,25.98],[81.44,25.52],[82.83,24.35],[82.64,23.45],
      [82.23,22.97],[81.82,22.55],[81.12,22.07],[80.48,21.95],[79.90,21.59],
      [79.09,21.22],[78.18,21.14],[77.23,21.43],[76.48,21.66],[75.62,21.88],
      [74.51,22.07],[74.11,23.20],[74.04,24.21],[74.04,26.87]
    ],
    'Chhattisgarh': [
      [80.48,23.90],[82.07,24.19],[82.35,23.54],[83.85,22.75],[84.38,22.00],
      [84.25,21.05],[83.84,20.12],[83.22,19.28],[82.59,18.57],[81.27,18.07],
      [80.65,18.22],[80.02,18.94],[80.05,19.97],[80.20,20.87],[80.48,21.75],
      [80.48,23.90]
    ],
    'Jharkhand': [
      [83.33,24.29],[84.44,25.00],[85.44,25.31],[86.50,25.30],[87.40,24.98],
      [87.55,24.15],[87.24,23.23],[86.79,22.55],[85.82,22.07],[84.89,21.97],
      [84.07,22.12],[83.61,22.55],[83.33,23.20],[83.33,24.29]
    ],
    'Odisha': [
      [83.33,22.58],[85.15,22.77],[86.59,22.10],[87.42,21.54],[87.47,20.83],
      [86.83,20.22],[86.55,19.25],[85.62,18.42],[84.68,17.89],[83.85,17.90],
      [83.05,18.54],[82.22,18.87],[81.41,19.37],[81.56,20.34],[82.10,21.28],
      [82.56,22.03],[83.33,22.58]
    ],
    'Karnataka': [
      [74.04,15.70],[74.43,17.07],[74.91,18.03],[75.44,18.41],[76.33,18.35],
      [77.28,18.00],[78.25,17.19],[78.55,16.38],[78.34,15.52],[77.86,14.18],
      [77.63,13.10],[77.44,12.49],[76.94,11.75],[76.61,11.56],[76.22,11.72],
      [75.57,11.92],[74.86,12.38],[74.26,13.46],[73.98,14.52],[74.04,15.70]
    ],
    'Goa': [
      [73.69,15.70],[73.91,15.75],[74.05,15.68],[74.22,15.52],[74.32,15.34],
      [74.22,15.09],[73.93,14.90],[73.70,14.92],[73.66,15.12],[73.69,15.42],
      [73.69,15.70]
    ],
    'Tamil Nadu': [
      [76.23,12.79],[77.46,13.57],[78.93,13.58],[80.07,13.35],[80.29,12.56],
      [80.28,11.55],[79.92,10.73],[79.55,9.94],[79.19,9.02],[78.48,8.44],
      [77.55,8.09],[76.83,8.42],[76.44,9.52],[76.24,11.09],[76.23,12.79]
    ]
  };

  // Centroid labels for each state polygon
  const STATE_LABEL_CENTERS = {
    'Rajasthan':      [26.5, 73.5],
    'Madhya Pradesh': [23.5, 78.5],
    'Chhattisgarh':   [21.2, 81.8],
    'Jharkhand':      [23.5, 85.5],
    'Odisha':         [20.5, 84.5],
    'Karnataka':      [14.5, 76.2],
    'Goa':            [15.3, 74.0],
    'Tamil Nadu':     [11.1, 78.5]
  };

  function init(analyticsData) {
    _data = analyticsData;

    _map = L.map('map', {
      center: [22.5, 80.0], zoom: 5,
      zoomControl: false, minZoom: 4, maxZoom: 14,
      maxBounds: [[6.5, 67.5], [37.5, 98.5]],
      maxBoundsViscosity: 0.85
    });

    L.control.zoom({ position: 'topright' }).addTo(_map);

    // ESRI World Imagery — satellite base matching Google Earth Engine visual style
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics',
      maxZoom: 18
    }).addTo(_map);

    // CartoDB labels-only pane on top so place names stay readable over imagery
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd', maxZoom: 19, opacity: 0.72,
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>'
    }).addTo(_map);

    _buildHeatmap();
    _buildRegionalSegments();
    _buildRoutes();
    _buildMarkers();
    _buildClusters();
  }

  // ── Heatmap ───────────────────────────────────────────────────────────────────
  function _buildHeatmap() {
    const pts = _data.facilities.map(f => [f.lat, f.lng, _heatVal(f)]);
    // GEE-style heatmap — viridis-inspired gradient, vivid against satellite
    _heat = L.heatLayer(pts, {
      radius: 42, blur: 32, maxZoom: 7, max: 1.0,
      gradient: {
        0.00: 'rgba(0,0,0,0)',
        0.25: 'rgba(45,88,117,0.28)',
        0.50: 'rgba(42,126,125,0.34)',
        0.75: 'rgba(107,151,83,0.40)',
        1.00: 'rgba(214,169,67,0.52)'
      }
    }).addTo(_map);
  }

  function _heatVal(f) {
    if (_currentView === 'recovery')    return f.ros / 100;
    if (_currentView === 'circularity') return f.cs  / 100;
    return f.eis / 100;
  }

  function _rebuildHeatmap() {
    if (_heat) _map.removeLayer(_heat);
    _buildHeatmap();
    if (!_heatOn) _map.removeLayer(_heat);
  }

  // ── Regional Segmentation (real state GeoJSON polygons) ───────────────────────
  function _buildRegionalSegments() {
    _segmentGroup = L.layerGroup();

    _data.regional.forEach(region => {
      const coords = INDIA_STATE_POLYGONS[region.name];
      if (!coords) return;

      const color = _eisColor(region.avgEIS);
      const cls   = Analytics.eisClass(region.avgEIS);

      // Render actual state boundary polygon using GeoJSON coordinates
      const geojsonFeature = {
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [coords] },
        properties: {}
      };

      // GEE-style polygon: vivid fill, bright white border, no dash — crisp classified-map look
      const poly = L.geoJSON(geojsonFeature, {
        style: {
          color: '#f7fff3',
          fillColor: color,
          fillOpacity: 0.34,
          weight: 2.4,
          opacity: 0.95,
          dashArray: null
        }
      });

      poly.bindTooltip(_regionTip(region, color), { sticky: true, className: 'geo-tooltip geo-tooltip-region' });
      poly.on('click', () => { if (window.UI) UI.showRegionalView(); });
      _segmentGroup.addLayer(poly);

      // State label badge at pre-computed centroid
      const center = STATE_LABEL_CENTERS[region.name];
      if (center) {
        const labelIcon = L.divIcon({
          className: '',
          html: `<div class="region-label region-label-${cls}">
                   <div class="rl-name">${region.name}</div>
                   <div class="rl-meta">EIS&nbsp;${region.avgEIS}&nbsp;·&nbsp;${region.facilities.length}&nbsp;sites</div>
                 </div>`,
          iconSize: [150, 42], iconAnchor: [75, 21]
        });
        _segmentGroup.addLayer(
          L.marker(center, { icon: labelIcon, interactive: false, zIndexOffset: -2000 })
        );
      }

      // GEE-style impact-zone rings — solid bright ring, no fill (keeps satellite visible)
      region.facilities.forEach(f => {
        const r = (35 + (f.eis / 100) * 110) * 1000;
        L.circle([f.lat, f.lng], {
          radius: r,
          color: _eisColor(f.eis), fillColor: 'transparent',
          fillOpacity: 0, weight: 2.2, opacity: 0.68,
          dashArray: '7 7'
        }).addTo(_segmentGroup);
      });
    });

    if (_segmentsOn) _segmentGroup.addTo(_map);
  }

  function _regionTip(r, color) {
    return `
      <div style="min-width:200px">
        <div style="font-size:13px;font-weight:700;margin-bottom:8px;color:#d0ecd6">${r.name} — India</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 14px;font-size:11.5px">
          <div><div style="color:#6a9a74">Avg. Impact</div><div style="font-weight:700;color:${color}">${r.avgEIS}</div></div>
          <div><div style="color:#6a9a74">Avg. Circularity</div><div style="font-weight:700;color:#14b8a6">${r.avgCS}</div></div>
          <div><div style="color:#6a9a74">Avg. Recovery</div><div style="font-weight:700;color:#a855f7">${r.avgROS}</div></div>
          <div><div style="color:#6a9a74">Facilities</div><div style="font-weight:700;color:#d0ecd6">${r.facilities.length}</div></div>
        </div>
        <div style="margin-top:8px;padding-top:7px;border-top:1px solid #1c3c24;font-size:10.5px;color:#6a9a74">
          <span style="color:#ef4444;font-weight:600">${(r.totalCO2/1e6).toFixed(1)}M t CO₂/yr</span>
          &nbsp;·&nbsp;${r.co2Share}% of portfolio total
        </div>
        <div style="margin-top:4px;font-size:10px;color:#3e6848">Click to open Regional Analysis</div>
      </div>`;
  }

  // GEE spectral palette — vivid, high-contrast against satellite imagery
  function _eisColor(eis) {
    if (eis >= 70) return '#c2410c';
    if (eis >= 50) return '#d97706';
    if (eis >= 30) return '#a3a34b';
    return '#2f8f6b';
  }

  // ── Transport Routes ──────────────────────────────────────────────────────────
  function _buildRoutes() {
    _routeGroup = L.layerGroup();
    _data.facilities.forEach(f => {
      const color  = _routeColor(f.normTrans);
      const weight = Math.max(3.2, Math.min(7, f.productionVolume / 180000 * 6));

      L.polyline([[f.lat, f.lng], [f.transportRoute.destLat, f.transportRoute.destLng]], {
        color: '#101410', weight: weight + 3, opacity: 0.42,
        dashArray: f.normTrans > 0.7 ? '9 6' : null
      }).addTo(_routeGroup);

      L.polyline([[f.lat, f.lng], [f.transportRoute.destLat, f.transportRoute.destLng]], {
        color, weight, opacity: 0.92,
        dashArray: f.normTrans > 0.7 ? '9 6' : null
      }).bindTooltip(
        `<strong>${f.shortName} → ${f.transportRoute.destination}</strong><br>
         ${f.transportRoute.mode} · ${f.transportRoute.distanceKm.toLocaleString()} km<br>
         Transport CO₂: ${_fmtSmall(f.transportCO2)}`,
        { sticky: true, className: 'geo-tooltip' }
      ).addTo(_routeGroup);

      L.circleMarker([f.transportRoute.destLat, f.transportRoute.destLng], {
        radius: 6, color: '#ffffff', fillColor: '#64748b', fillOpacity: 1, weight: 2
      }).bindTooltip(f.transportRoute.destination, { className: 'geo-tooltip' }).addTo(_routeGroup);
    });
    if (_routesOn) _routeGroup.addTo(_map);
  }

  function _routeColor(n) {
    if (n > 0.70) return '#c2410c';
    if (n > 0.40) return '#d97706';
    if (n > 0.15) return '#a3a34b';
    return '#2f8f6b';
  }

  // ── Individual Markers ────────────────────────────────────────────────────────
  function _buildMarkers() {
    _markerGroup = L.layerGroup();
    _data.facilities.forEach(f => {
      const m = _createMarker(f);
      _markers[f.id] = m;
      _markerGroup.addLayer(m);
    });
    _markerGroup.addTo(_map);
  }

  function _createMarker(f) {
    const score = _currentView === 'recovery' ? f.ros : _currentView === 'circularity' ? f.cs : f.eis;
    const cls   = Analytics.eisClass(score);
    const size  = Math.round(22 + (f.productionVolume / Math.max(..._data.facilities.map(x => x.productionVolume))) * 22);

    const html = `
      <div class="fmarker fmarker-${cls}" style="width:${size}px;height:${size}px;line-height:${size}px;font-size:${Math.max(9,size/3.1)}px">
        ${f.metalType[0]}
        ${f.priorityRank === 1 ? '<span class="fmarker-badge">!</span>' : ''}
      </div>`;

    const icon = L.divIcon({ className: '', html, iconSize: [size, size], iconAnchor: [size/2, size/2] });
    const mk = L.marker([f.lat, f.lng], { icon, zIndexOffset: Math.round(score) });

    mk.bindTooltip(`
      <div class="tip-header">${f.flag} <strong>${f.name}</strong></div>
      <div class="tip-row"><span>State</span><span style="color:#d0ecd6">${f.region}</span></div>
      <div class="tip-row"><span>Impact Score</span><span class="${Analytics.eisClass(f.eis)}-text">${f.eis}</span></div>
      <div class="tip-row"><span>Recovery</span><span class="recovery-text">${f.ros}</span></div>
      <div class="tip-row"><span>Circularity</span><span class="circularity-text">${f.cs}</span></div>
      <div class="tip-hint">Click for full decision analysis</div>`,
      { sticky: false, className: 'geo-tooltip', offset: [0, -size/2] }
    );
    mk.on('click', () => { if (window.UI) UI.showFacilityDetail(f.id); });
    return mk;
  }

  // ── Cluster Group ─────────────────────────────────────────────────────────────
  function _buildClusters() {
    _clusterGroup = L.markerClusterGroup({
      chunkedLoading: true, maxClusterRadius: 70,
      iconCreateFunction(cluster) {
        const children = cluster.getAllChildMarkers();
        const ids = children.map(m => m._fid).filter(Boolean);
        const avg = ids.length ? ids.reduce((s, id) => s + (_data.facilityMap[id]?.eis || 0), 0) / ids.length : 0;
        const cls = Analytics.eisClass(avg);
        return L.divIcon({
          html: `<div class="cluster-icon cluster-${cls}"><span>${cluster.getChildCount()}</span></div>`,
          className: '', iconSize: [46, 46], iconAnchor: [23, 23]
        });
      }
    });
    _data.facilities.forEach(f => {
      const icon = L.divIcon({
        className: '',
        html: `<div class="fmarker fmarker-${Analytics.eisClass(f.eis)}" style="width:30px;height:30px;line-height:30px;font-size:11px">${f.metalType[0]}</div>`,
        iconSize: [30, 30], iconAnchor: [15, 15]
      });
      const m = L.marker([f.lat, f.lng], { icon });
      m._fid = f.id;
      m.on('click', () => { if (window.UI) UI.showFacilityDetail(f.id); });
      _clusterGroup.addLayer(m);
    });
  }

  // ── Public API ────────────────────────────────────────────────────────────────
  function toggleHeatmap() {
    _heatOn = !_heatOn;
    _heatOn ? _map.addLayer(_heat) : _map.removeLayer(_heat);
    document.getElementById('btn-heatmap').classList.toggle('active', _heatOn);
  }

  function toggleLULC() {
    _lulcOn = !_lulcOn;
    const legend = document.getElementById('lulc-legend');
    if (legend) legend.classList.toggle('visible', _lulcOn);
    document.getElementById('btn-lulc').classList.toggle('active', _lulcOn);
  }

  function toggleRoutes() {
    _routesOn = !_routesOn;
    _routesOn ? _map.addLayer(_routeGroup) : _map.removeLayer(_routeGroup);
    document.getElementById('btn-routes').classList.toggle('active', _routesOn);
  }

  function toggleClusters() {
    _clustersOn = !_clustersOn;
    document.getElementById('btn-clusters').classList.toggle('active', _clustersOn);
    if (_clustersOn) { _map.removeLayer(_markerGroup); _map.addLayer(_clusterGroup); }
    else             { _map.removeLayer(_clusterGroup); _map.addLayer(_markerGroup); }
  }

  function toggleSegments() {
    _segmentsOn = !_segmentsOn;
    _segmentsOn ? _map.addLayer(_segmentGroup) : _map.removeLayer(_segmentGroup);
    document.getElementById('btn-segments').classList.toggle('active', _segmentsOn);
  }

  function setView(view) {
    _currentView = view;
    document.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
    _markerGroup.clearLayers();
    Object.keys(_markers).forEach(id => delete _markers[id]);
    _data.facilities.forEach(f => {
      const m = _createMarker(f);
      _markers[f.id] = m;
      _markerGroup.addLayer(m);
    });
    _rebuildHeatmap();
    _updateLegend(view);
  }

  function _updateLegend(view) {
    const cfg = {
      impact:      ['Environmental Impact Score', ['Critical (70–100)', 'High (50–70)', 'Moderate (30–50)', 'Low (0–30)']],
      recovery:    ['Recovery Opportunity Score', ['Excellent (75–100)', 'Good (55–75)', 'Moderate (35–55)', 'Low (0–35)']],
      circularity: ['Circularity Score',          ['Excellent (75–100)', 'Good (55–75)', 'Moderate (35–55)', 'Poor (0–35)']]
    };
    const [title, labels] = cfg[view] || cfg.impact;
    const el = document.getElementById('map-legend');
    if (!el) return;
    el.querySelector('.legend-title').textContent = title;
    el.querySelectorAll('.legend-label').forEach((s, i) => { s.textContent = labels[i]; });
  }

  function focusFacility(id) {
    const f = _data.facilityMap[id];
    if (!f) return;
    _map.flyTo([f.lat, f.lng], 8, { duration: 1.2 });
    setTimeout(() => { _markers[id]?.openTooltip(); }, 1300);
    document.querySelectorAll('.fmarker-active').forEach(el => el.classList.remove('fmarker-active'));
    setTimeout(() => {
      const el = _markers[id]?.getElement();
      if (el) el.querySelector('.fmarker')?.classList.add('fmarker-active');
    }, 200);
  }

  function _fmtSmall(n) {
    if (n >= 1000) return `${Math.round(n/1000).toLocaleString()}k t/yr`;
    return `${n.toLocaleString()} t/yr`;
  }

  function getMap() { return _map; }

  return { init, toggleLULC, toggleHeatmap, toggleRoutes, toggleClusters, toggleSegments, setView, focusFacility, getMap };
})();
