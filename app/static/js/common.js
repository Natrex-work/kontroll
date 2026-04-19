(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/static/sw.js').catch(function () {});
    });
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function parseJson(value, fallback) {
    try { return JSON.parse(value || ''); } catch (e) { return fallback; }
  }


  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? String(meta.getAttribute('content') || '') : '';
  }

  function injectCsrfField(form) {
    if (!form || String(form.method || '').toLowerCase() !== 'post') return;
    var token = csrfToken();
    if (!token) return;
    var existing = form.querySelector('input[name="csrf_token"]');
    if (existing) {
      existing.value = token;
      return;
    }
    var input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'csrf_token';
    input.value = token;
    form.appendChild(input);
  }

  function appendCsrfToForms(scope) {
    Array.prototype.forEach.call((scope || document).querySelectorAll('form[method="post"], form[method="POST"]'), injectCsrfField);
  }

  function csrfHeaders(extraHeaders) {
    var headers = new Headers(extraHeaders || {});
    var token = csrfToken();
    if (token && !headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', token);
    return headers;
  }

  function secureFetchOptions(options) {
    var result = Object.assign({ credentials: 'same-origin' }, options || {});
    var method = String(result.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
      result.headers = csrfHeaders(result.headers);
    }
    return result;
  }

  function sourceChip(item) {
    var label = '<strong>' + escapeHtml(item.name || 'Kilde') + '</strong><span>' + escapeHtml(item.ref || '') + '</span>';
    if (item.url) return '<a class="source-chip" href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' + label + '</a>';
    return '<div class="source-chip">' + label + '</div>';
  }

  function findingSource(item) {
    var bits = [];
    if (item.source_name) bits.push(item.source_name);
    if (item.source_ref) bits.push(item.source_ref);
    return bits.join(' - ');
  }

  function lawHelpCard(item) {
    var lawName = escapeHtml(item.law_name || item.source_name || 'Regelverk');
    var section = escapeHtml(item.section || item.source_ref || '');
    var summary = escapeHtml(item.summary_text || item.label || '');
    var lawText = escapeHtml(item.law_text || item.help_text || '');
    return [
      '<div class="help-text hidden">',
      '<div class="law-help-head"><div class="law-help-kicker">' + lawName + '</div><div class="law-help-ref">' + section + '</div></div>',
      '<div class="law-help-summary">Kort forklart: ' + summary + '</div>',
      '<div class="law-help-body">' + lawText + '</div>',
      '</div>'
    ].join('');
  }

  function buildReadonlyFindingsHtml(items) {
    return (items || []).map(function (item, index) {
      return [
        '<article class="finding-card" data-index="' + index + '">',
        '<div class="finding-head">',
        '<div><strong>' + escapeHtml(item.label || item.key || ('Punkt ' + (index + 1))) + '</strong>',
        '<div class="muted small">' + escapeHtml(findingSource(item)) + '</div></div>',
        '<div class="finding-head-actions">',
        (item.help_text || item.law_text) ? '<button type="button" class="help-toggle" title="Vis hjemmel og paragraf">?</button>' : '',
        '</div>',
        '</div>',
        (item.help_text || item.law_text) ? lawHelpCard(item) : '',
        '<div class="finding-body">',
        '<div class="finding-status-row"><span class="pill">' + escapeHtml(item.status || 'ikke kontrollert') + '</span></div>',
        '<div class="finding-note">' + escapeHtml(item.notes || item.summary_text || '') + '</div>',
        '</div>',
        '</article>'
      ].join('');
    }).join('');
  }

  function normalizeFeatureCollection(data) {
    return data && data.type === 'FeatureCollection' ? data : { type: 'FeatureCollection', features: [] };
  }

  var portalFeatureCache = {};
  var portalFeatureInflight = {};
  var PORTAL_FEATURE_CACHE_MS = 45000;
  var PORTAL_FEATURE_CACHE_LIMIT = 240;
  var PORTAL_FETCH_CONCURRENCY = 2;

  function trimPortalFeatureCache() {
    var keys = Object.keys(portalFeatureCache);
    if (keys.length <= PORTAL_FEATURE_CACHE_LIMIT) return;
    keys.sort(function (a, b) { return (portalFeatureCache[a].ts || 0) - (portalFeatureCache[b].ts || 0); });
    while (keys.length > PORTAL_FEATURE_CACHE_LIMIT) {
      delete portalFeatureCache[keys.shift()];
    }
  }

  function fetchPortalFeatureCollection(viewKey, url) {
    var now = Date.now();
    var cached = portalFeatureCache[viewKey];
    if (cached && (now - cached.ts) < PORTAL_FEATURE_CACHE_MS) return Promise.resolve(cached.data);
    if (portalFeatureInflight[viewKey]) return portalFeatureInflight[viewKey];
    var request = fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var normalized = normalizeFeatureCollection(data);
        portalFeatureCache[viewKey] = { ts: Date.now(), data: normalized };
        trimPortalFeatureCache();
        return normalized;
      })
      .finally(function () { delete portalFeatureInflight[viewKey]; });
    portalFeatureInflight[viewKey] = request;
    return request;
  }

  function runLimited(tasks, limit) {
    limit = Math.max(1, Number(limit) || 1);
    return new Promise(function (resolve) {
      if (!tasks.length) { resolve(); return; }
      var index = 0;
      var active = 0;
      function launch() {
        if (index >= tasks.length && active === 0) { resolve(); return; }
        while (active < limit && index < tasks.length) {
          var task = tasks[index++];
          active += 1;
          Promise.resolve().then(task).catch(function () {}).then(function () {
            active -= 1;
            launch();
          });
        }
      }
      launch();
    });
  }

  function createPortalMap(el, layers, markerState) {
    if (!el || !window.L) return Promise.resolve(null);
    var storageKey = 'kv-map-view:' + (el.id || 'map');
    var savedView = null;
    try {
      savedView = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    } catch (e) { savedView = null; }

    function validLatLng(lat, lng) {
      return isFinite(lat) && isFinite(lng) && Math.abs(Number(lat)) <= 90 && Math.abs(Number(lng)) <= 180 && !(Math.abs(Number(lat)) < 0.000001 && Math.abs(Number(lng)) < 0.000001);
    }

    function caseIcon() {
      return L.divIcon({ className: 'kv-case-marker', html: '<div class="leaflet-case-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
    }

    function userIcon() {
      return L.divIcon({ className: 'kv-user-marker', html: '<div class="leaflet-user-dot"></div>', iconSize: [16, 16], iconAnchor: [8, 8] });
    }

    var state = el._kvPortalState;
    if (!state) {
      var initialView = (markerState && markerState.view) || savedView || ((markerState && validLatLng(markerState.lat, markerState.lng)) ? { lat: markerState.lat, lng: markerState.lng, zoom: markerState.defaultZoom || 11 } : ((markerState && validLatLng(markerState.deviceLat, markerState.deviceLng)) ? { lat: markerState.deviceLat, lng: markerState.deviceLng, zoom: markerState.defaultZoom || 13 } : null));
      var map = L.map(el, { zoomControl: true }).setView(initialView ? [initialView.lat, initialView.lng] : [63.5, 11], initialView ? initialView.zoom : 5);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap'
      }).addTo(map);
      state = {
        map: map,
        storageKey: storageKey,
        overlaysById: {},
        legendControl: null,
        markerState: markerState || {},
        clickBound: false,
        layerViewKeys: {},
        currentLayers: [],
        featureSummariesByLayer: {}
      };
      map.on('moveend zoomend', function () {
        try {
          var center = map.getCenter();
          sessionStorage.setItem(storageKey, JSON.stringify({ lat: center.lat, lng: center.lng, zoom: map.getZoom() }));
        } catch (e) {}
        if (typeof state.refreshLayers === 'function') {
          clearTimeout(state._refreshTimer);
          state._refreshTimer = setTimeout(function () { state.refreshLayers(); }, 220);
        }
      });
      el._kvPortalState = state;
      el._kvLeafletMap = map;
    }

    state.markerState = markerState || {};
    state.currentLayers = layers || [];
    state.refreshLayers = function () { createPortalMap(el, state.currentLayers, state.markerState || {}); };
    var map = state.map;
    var ms = state.markerState || {};
    var activeLayerIds = {};
    var bounds = map.getBounds ? map.getBounds() : null;
    var bbox = bounds ? [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()] : null;
    var bboxKey = bbox ? bbox.map(function (value) { return Number(value).toFixed(3); }).join(',') : '';

    var tasks = (layers || []).map(function (layer) {
      return function () {
        var cacheKey = String(layer.id);
        activeLayerIds[cacheKey] = true;
        var viewKey = cacheKey + ':' + bboxKey;
        if (state.overlaysById[cacheKey] && state.layerViewKeys[cacheKey] === viewKey) return Promise.resolve();
        var url = '/api/map/features?layer_id=' + encodeURIComponent(layer.id);
        if (bboxKey) url += '&bbox=' + encodeURIComponent(bbox.join(','));
        return fetchPortalFeatureCollection(viewKey, url)
          .then(function (data) {
            data = normalizeFeatureCollection(data);
            state.layerViewKeys[cacheKey] = viewKey;
            if (state.overlaysById[cacheKey]) {
              try { map.removeLayer(state.overlaysById[cacheKey]); } catch (e) {}
              delete state.overlaysById[cacheKey];
            }
            state.featureSummariesByLayer[cacheKey] = [];
            if (!data.features.length) return;
            var featureSummaries = [];
            var geo = L.geoJSON(data, {
              style: function (feature) {
                var geometryType = String((feature && feature.geometry && feature.geometry.type) || layer.geometry_type || '').toLowerCase();
                var isLine = geometryType.indexOf('line') !== -1;
                var isPoint = geometryType.indexOf('point') !== -1;
                return {
                  color: layer.color || '#c1121f',
                  weight: isLine ? 4 : 3,
                  opacity: isPoint ? 0.95 : 0.9,
                  fillColor: layer.color || '#c1121f',
                  fillOpacity: isPoint ? 0.8 : 0.28,
                  dashArray: isLine ? '8 6' : null
                };
              },
              pointToLayer: function (feature, latlng) {
                return L.circleMarker(latlng, {
                  radius: 7,
                  color: layer.color || '#c1121f',
                  weight: 2,
                  fillColor: layer.color || '#c1121f',
                  fillOpacity: 0.75
                });
              },
              onEachFeature: function (feature, lyr) {
                var props = feature && feature.properties ? feature.properties : {};
                var title = props.navn || props.omraade || props.område || props.name || layer.name;
                var desc = props.info || props.beskrivelse || props.informasjon || props.omraade_stengt_text || props.vurderes_aapnet_text || layer.description || layer.status || '';
                var law = props.jmelding_navn || props.url || '';
                var html = '<strong>' + escapeHtml(title || layer.name) + '</strong>';
                html += '<div class="small muted">' + escapeHtml(layer.status || '') + '</div>';
                if (desc) html += '<div class="small" style="margin-top:6px">' + escapeHtml(desc) + '</div>';
                if (law) html += '<div class="small muted" style="margin-top:6px">Kilde: ' + escapeHtml(law) + '</div>';
                if (props.url) html += '<div class="small" style="margin-top:6px"><a href="' + escapeHtml(props.url) + '" target="_blank" rel="noopener">Åpne regelgrunnlag</a></div>';
                lyr.bindPopup(html);
                featureSummaries.push({ layerId: layer.id, layer: layer.name, status: layer.status || '', name: title || layer.name, description: desc || '', url: props.url || '', source: law || '' });
              }
            }).addTo(map);
            state.overlaysById[cacheKey] = geo;
            state.featureSummariesByLayer[cacheKey] = featureSummaries;
          }).catch(function () { state.featureSummariesByLayer[cacheKey] = []; });
      };
    });

    return runLimited(tasks, PORTAL_FETCH_CONCURRENCY).then(function () {
      Object.keys(state.overlaysById).forEach(function (key) {
        if (activeLayerIds[key]) return;
        try { map.removeLayer(state.overlaysById[key]); } catch (e) {}
        delete state.overlaysById[key];
        delete state.layerViewKeys[key];
        delete state.featureSummariesByLayer[key];
      });

      var visibleFeatureSummaries = [];
      Object.keys(state.featureSummariesByLayer).forEach(function (key) {
        if (!activeLayerIds[key]) {
          delete state.featureSummariesByLayer[key];
          return;
        }
        visibleFeatureSummaries = visibleFeatureSummaries.concat(state.featureSummariesByLayer[key] || []);
      });
      if (typeof ms.onFeaturesRendered === 'function') {
        try { ms.onFeaturesRendered({ layers: layers || [], features: visibleFeatureSummaries, bbox: bbox || null }); } catch (e) {}
      }

      if (state.legendControl) {
        try { map.removeControl(state.legendControl); } catch (e) {}
        state.legendControl = null;
      }
      var legendLayers = (layers || []).filter(function (layer) {
        var key = String(layer.id);
        return (state.featureSummariesByLayer[key] || []).length > 0;
      });
      if (legendLayers.length) {
        var legendControl = L.control({ position: 'bottomleft' });
        legendControl.onAdd = function () {
          var div = L.DomUtil.create('div', 'leaflet-legend-control');
          div.innerHTML = '<div class="leaflet-legend-title">Kartlag</div>' + legendLayers.map(function (layer) {
            return '<div class="leaflet-legend-row"><span class="leaflet-legend-swatch" style="background:' + escapeHtml(layer.color || '#c1121f') + '"></span><span>' + escapeHtml(layer.name || '') + '</span></div>';
          }).join('');
          return div;
        };
        legendControl.addTo(map);
        state.legendControl = legendControl;
      }

      var hasCase = validLatLng(ms.lat, ms.lng);
      var hasDevice = validLatLng(ms.deviceLat, ms.deviceLng);

      if (hasCase) {
        if (!state.caseMarker) {
          state.caseMarker = L.marker([ms.lat, ms.lng], { draggable: !!ms.draggable, icon: caseIcon() }).addTo(map);
          state.caseMarker.on('dragend', function (event) {
            var currentState = el._kvPortalState && el._kvPortalState.markerState ? el._kvPortalState.markerState : {};
            var ll = event.target.getLatLng();
            if (typeof currentState.onManualMove === 'function') currentState.onManualMove(ll.lat, ll.lng);
            else if (typeof currentState.onMove === 'function') currentState.onMove(ll.lat, ll.lng);
          });
        }
        state.caseMarker.setLatLng([ms.lat, ms.lng]);
        state.caseMarker.setIcon(caseIcon());
        if (state.caseMarker.dragging) {
          if (ms.draggable) state.caseMarker.dragging.enable();
          else state.caseMarker.dragging.disable();
        }
        state.caseMarker.bindPopup('Kontrollposisjon');
        if (!state.caseRadius) {
          state.caseRadius = L.circle([ms.lat, ms.lng], {
            radius: (ms.radiusKm || 50) * 1000,
            color: '#24527b',
            weight: 1,
            fillColor: '#24527b',
            fillOpacity: 0.06
          }).addTo(map);
        } else {
          state.caseRadius.setLatLng([ms.lat, ms.lng]);
          state.caseRadius.setRadius((ms.radiusKm || 50) * 1000);
        }
      } else {
        if (state.caseMarker) { try { map.removeLayer(state.caseMarker); } catch (e) {} state.caseMarker = null; }
        if (state.caseRadius) { try { map.removeLayer(state.caseRadius); } catch (e) {} state.caseRadius = null; }
      }

      if (hasDevice) {
        if (!state.deviceMarker) {
          state.deviceMarker = L.marker([ms.deviceLat, ms.deviceLng], { icon: userIcon(), interactive: false }).addTo(map);
        }
        state.deviceMarker.setLatLng([ms.deviceLat, ms.deviceLng]);
        state.deviceMarker.setIcon(userIcon());
        state.deviceMarker.bindPopup('Enhetens posisjon');
        if (!state.deviceAccuracy) {
          state.deviceAccuracy = L.circle([ms.deviceLat, ms.deviceLng], {
            radius: Math.max(8, Number(ms.deviceAccuracy || 12)),
            color: '#1e7bff',
            weight: 1,
            fillColor: '#1e7bff',
            fillOpacity: 0.12,
            interactive: false
          }).addTo(map);
        } else {
          state.deviceAccuracy.setLatLng([ms.deviceLat, ms.deviceLng]);
          state.deviceAccuracy.setRadius(Math.max(8, Number(ms.deviceAccuracy || 12)));
        }
      } else {
        if (state.deviceMarker) { try { map.removeLayer(state.deviceMarker); } catch (e) {} state.deviceMarker = null; }
        if (state.deviceAccuracy) { try { map.removeLayer(state.deviceAccuracy); } catch (e) {} state.deviceAccuracy = null; }
      }

      if (!state.clickBound) {
        map.on('click', function (event) {
          var currentState = el._kvPortalState && el._kvPortalState.markerState ? el._kvPortalState.markerState : {};
          if (!currentState.allowMapMove) return;
          if (typeof currentState.onManualMove !== 'function' && typeof currentState.onMove !== 'function') return;
          if (!state.caseMarker) {
            state.caseMarker = L.marker(event.latlng, { draggable: !!currentState.draggable, icon: caseIcon() }).addTo(map);
            state.caseMarker.on('dragend', function (dragEvent) {
              var liveState = el._kvPortalState && el._kvPortalState.markerState ? el._kvPortalState.markerState : {};
              var ll = dragEvent.target.getLatLng();
              if (typeof liveState.onManualMove === 'function') liveState.onManualMove(ll.lat, ll.lng);
              else if (typeof liveState.onMove === 'function') liveState.onMove(ll.lat, ll.lng);
            });
          }
          state.caseMarker.setLatLng(event.latlng);
          if (typeof currentState.onManualMove === 'function') currentState.onManualMove(event.latlng.lat, event.latlng.lng);
          else currentState.onMove(event.latlng.lat, event.latlng.lng);
        });
        state.clickBound = true;
      }

      if (ms.recenterTo === 'device' && hasDevice) map.setView([ms.deviceLat, ms.deviceLng], ms.recenterZoom || Math.max(map.getZoom(), 15));
      else if (ms.recenterTo === 'case' && hasCase) map.setView([ms.lat, ms.lng], ms.recenterZoom || Math.max(map.getZoom(), 14));

      setTimeout(function () {
        try { map.invalidateSize(); } catch (e) {}
      }, 120);
      return { map: map, geoLayers: Object.keys(state.overlaysById).map(function (key) { return state.overlaysById[key]; }), marker: state.caseMarker || null, circle: state.caseRadius || null, deviceMarker: state.deviceMarker || null, accuracyCircle: state.deviceAccuracy || null };
    });
  }


  function setupSecurityInteractions() {
    appendCsrfToForms(document);
    document.addEventListener('submit', function (event) {
      var form = event.target;
      if (!form || form.tagName !== 'FORM') return;
      if (String(form.method || '').toLowerCase() === 'post') injectCsrfField(form);
      var message = form.getAttribute('data-confirm');
      if (message && !window.confirm(message)) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);
    document.addEventListener('click', function (event) {
      var trigger = event.target.closest('[data-confirm]:not(form)');
      if (!trigger) return;
      if (!window.confirm(trigger.getAttribute('data-confirm') || 'Er du sikker?')) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);
  }

  function setupSidebarToggle() {
    var sidebar = document.getElementById('app-sidebar');
    var toggle = document.getElementById('sidebar-toggle');
    if (!sidebar || !toggle) return;
    function isMobileSidebar() {
      return window.matchMedia('(max-width: 960px)').matches;
    }
    function closeMobileSidebar() {
      if (!isMobileSidebar()) return;
      sidebar.classList.remove('sidebar-open');
      toggle.setAttribute('aria-expanded', 'false');
    }
    toggle.addEventListener('click', function (event) {
      if (!isMobileSidebar()) return;
      event.preventDefault();
      event.stopPropagation();
      var willOpen = !sidebar.classList.contains('sidebar-open');
      sidebar.classList.toggle('sidebar-open', willOpen);
      toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    });
    Array.prototype.forEach.call(sidebar.querySelectorAll('.nav-link, .nav-link-button'), function (link) {
      link.addEventListener('click', closeMobileSidebar);
    });
    document.addEventListener('click', function (event) {
      if (!isMobileSidebar()) return;
      if (!sidebar.classList.contains('sidebar-open')) return;
      if (sidebar.contains(event.target)) return;
      closeMobileSidebar();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') closeMobileSidebar();
    });
    window.addEventListener('resize', function () {
      if (!isMobileSidebar()) {
        sidebar.classList.remove('sidebar-open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  ready(setupSecurityInteractions);
  ready(setupSidebarToggle);

  window.KVCommon = { ready: ready, escapeHtml: escapeHtml, parseJson: parseJson, csrfToken: csrfToken, injectCsrfField: injectCsrfField, appendCsrfToForms: appendCsrfToForms, csrfHeaders: csrfHeaders, secureFetchOptions: secureFetchOptions, sourceChip: sourceChip, findingSource: findingSource, lawHelpCard: lawHelpCard, buildReadonlyFindingsHtml: buildReadonlyFindingsHtml, normalizeFeatureCollection: normalizeFeatureCollection, createPortalMap: createPortalMap };
})();
