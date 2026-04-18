(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }


  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? String(meta.getAttribute('content') || '') : '';
  }

  function ensureCsrfInputs() {
    var token = csrfToken();
    if (!token) return;
    Array.prototype.forEach.call(document.querySelectorAll('form[method], form:not([method])'), function (form) {
      var method = String(form.getAttribute('method') || 'get').toLowerCase();
      if (method !== 'post') return;
      var input = form.querySelector('input[name="_csrf"]');
      if (!input) {
        input = document.createElement('input');
        input.type = 'hidden';
        input.name = '_csrf';
        form.appendChild(input);
      }
      input.value = token;
    });
  }

  function installCsrfFetchHook() {
    if (!window.fetch || window.__kvCsrfHookInstalled) return;
    window.__kvCsrfHookInstalled = true;
    var originalFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      var reqInit = init || {};
      var method = String((reqInit && reqInit.method) || 'GET').toUpperCase();
      var token = csrfToken();
      var headers = new Headers(reqInit.headers || {});
      if (token && ['POST', 'PUT', 'PATCH', 'DELETE'].indexOf(method) !== -1 && !headers.has('X-CSRF-Token')) {
        headers.set('X-CSRF-Token', token);
      }
      reqInit.headers = headers;
      return originalFetch(input, reqInit);
    };
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

  function createPortalMap(el, layers, markerState) {
    if (!el || !window.L) return Promise.resolve(null);
    var storageKey = 'kv-map-view:' + (el.id || 'map');
    var savedView = null;
    try {
      savedView = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    } catch (e) { savedView = null; }
    if (el._kvLeafletMap) {
      try {
        var prevCenter = el._kvLeafletMap.getCenter();
        var prevZoom = el._kvLeafletMap.getZoom();
        savedView = { lat: prevCenter.lat, lng: prevCenter.lng, zoom: prevZoom };
        sessionStorage.setItem(storageKey, JSON.stringify(savedView));
      } catch (e) {}
      try { el._kvLeafletMap.remove(); } catch (e) {}
      el._kvLeafletMap = null;
    }
    el.innerHTML = '';
    var initialView = (markerState && markerState.view) || savedView || ((markerState && markerState.lat && markerState.lng) ? { lat: markerState.lat, lng: markerState.lng, zoom: markerState.defaultZoom || 8 } : null);
    var map = L.map(el, { zoomControl: true }).setView(initialView ? [initialView.lat, initialView.lng] : [63.5, 11], initialView ? initialView.zoom : 5);
    el._kvLeafletMap = map;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap'
    }).addTo(map);

    var geoLayers = [];
    var promises = (layers || []).map(function (layer) {
      var cacheKey = String(layer.id);
      var dataPromise = portalFeatureCache[cacheKey]
        ? Promise.resolve(portalFeatureCache[cacheKey])
        : fetch('/api/map/features?layer_id=' + encodeURIComponent(layer.id))
            .then(function (r) { return r.json(); })
            .then(function (data) {
              var normalized = normalizeFeatureCollection(data);
              if (normalized.features && normalized.features.length) portalFeatureCache[cacheKey] = normalized;
              return normalized;
            });

      return dataPromise.then(function (data) {
        data = normalizeFeatureCollection(data);
        if (!data.features.length) return;
        var geo = L.geoJSON(data, {
          style: function () {
            return { color: layer.color || '#c1121f', weight: 2.5, fillColor: layer.color || '#c1121f', fillOpacity: 0.2 };
          },
          onEachFeature: function (feature, lyr) {
            var props = feature && feature.properties ? feature.properties : {};
            var title = props.navn || props.omraade || layer.name;
            var desc = props.info || props.beskrivelse || props.informasjon || props.omraade_stengt_text || props.vurderes_aapnet_text || layer.description || layer.status || '';
            var law = props.jmelding_navn || props.url || '';
            var html = '<strong>' + escapeHtml(title || layer.name) + '</strong>';
            html += '<div class="small muted">' + escapeHtml(layer.status || '') + '</div>';
            if (desc) html += '<div class="small" style="margin-top:6px">' + escapeHtml(desc) + '</div>';
            if (law) html += '<div class="small muted" style="margin-top:6px">Kilde: ' + escapeHtml(law) + '</div>';
            if (props.url) html += '<div class="small" style="margin-top:6px"><a href="' + escapeHtml(props.url) + '" target="_blank" rel="noopener">Åpne regelgrunnlag</a></div>';
            lyr.bindPopup(html);
          }
        }).addTo(map);
        geoLayers.push(geo);
      }).catch(function () {});
    });

    return Promise.all(promises).then(function () {
      var circle = null;

      function ensureCircle(lat, lng) {
        if (!markerState) return;
        if (!circle) {
          circle = L.circle([lat, lng], {
            radius: (markerState.radiusKm || 50) * 1000,
            color: '#24527b',
            weight: 1,
            fillColor: '#24527b',
            fillOpacity: 0.06
          }).addTo(map);
          return;
        }
        circle.setLatLng([lat, lng]);
      }

      function syncMarker(lat, lng) {
        if (!markerState) return;
        if (!markerState.layer) {
          markerState.layer = L.marker([lat, lng], { draggable: !!markerState.draggable }).addTo(map);
          markerState.layer.bindPopup('Kontrollposisjon');
          if (markerState.draggable && (typeof markerState.onMove === 'function' || typeof markerState.onManualMove === 'function')) {
            markerState.layer.on('dragend', function (event) {
              var ll = event.target.getLatLng();
              if (typeof markerState.onManualMove === 'function') markerState.onManualMove(ll.lat, ll.lng);
              else markerState.onMove(ll.lat, ll.lng);
            });
          }
        } else {
          markerState.layer.setLatLng([lat, lng]);
        }
        ensureCircle(lat, lng);
      }

      if (markerState && markerState.lat && markerState.lng) {
        syncMarker(markerState.lat, markerState.lng);
      }
      if (markerState && markerState.allowMapMove && (typeof markerState.onMove === 'function' || typeof markerState.onManualMove === 'function')) {
        map.on('click', function (event) {
          syncMarker(event.latlng.lat, event.latlng.lng);
          if (typeof markerState.onManualMove === 'function') markerState.onManualMove(event.latlng.lat, event.latlng.lng);
          else markerState.onMove(event.latlng.lat, event.latlng.lng);
        });
      }
      var allLayers = geoLayers.concat(markerState && markerState.layer ? [markerState.layer] : []).concat(circle ? [circle] : []);
      var group = L.featureGroup(allLayers);
      if (!(markerState && markerState.view) && !(savedView && savedView.zoom) && !(markerState && markerState.lat && markerState.lng) && group.getLayers().length) {
        try { map.fitBounds(group.getBounds().pad(0.1)); } catch (e) {}
      }
      if (layers && layers.length) {
        var legendControl = L.control({ position: 'bottomleft' });
        legendControl.onAdd = function () {
          var div = L.DomUtil.create('div', 'leaflet-legend-control');
          div.innerHTML = '<div class="leaflet-legend-title">Kartlag</div>' + (layers || []).map(function (layer) {
            return '<div class="leaflet-legend-row"><span class="leaflet-legend-swatch" style="background:' + escapeHtml(layer.color || '#c1121f') + '"></span><span>' + escapeHtml(layer.name || '') + '</span></div>';
          }).join('');
          return div;
        };
        legendControl.addTo(map);
      }
      map.on('moveend zoomend', function () {
        try {
          var center = map.getCenter();
          sessionStorage.setItem(storageKey, JSON.stringify({ lat: center.lat, lng: center.lng, zoom: map.getZoom() }));
        } catch (e) {}
      });
      setTimeout(function () {
        try { map.invalidateSize(); } catch (e) {}
      }, 180);
      return { map: map, geoLayers: geoLayers, marker: markerState && markerState.layer ? markerState.layer : null, circle: circle };
    });
  }

  function setupSidebarToggle() {
    var sidebar = document.getElementById('app-sidebar');
    var toggle = document.getElementById('sidebar-toggle');
    if (!sidebar || !toggle) return;

    function closeMobileSidebar() {
      if (!window.matchMedia('(max-width: 960px)').matches) return;
      sidebar.classList.remove('sidebar-open');
      toggle.setAttribute('aria-expanded', 'false');
    }

    toggle.addEventListener('click', function () {
      var willOpen = !sidebar.classList.contains('sidebar-open');
      sidebar.classList.toggle('sidebar-open', willOpen);
      toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    });

    Array.prototype.forEach.call(sidebar.querySelectorAll('.nav-link'), function (link) {
      link.addEventListener('click', closeMobileSidebar);
    });

    window.addEventListener('resize', function () {
      if (!window.matchMedia('(max-width: 960px)').matches) {
        sidebar.classList.remove('sidebar-open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  ready(function () {
    ensureCsrfInputs();
    installCsrfFetchHook();
    setupSidebarToggle();
  });

  window.KVCommon = { ready: ready, escapeHtml: escapeHtml, parseJson: parseJson, sourceChip: sourceChip, findingSource: findingSource, lawHelpCard: lawHelpCard, buildReadonlyFindingsHtml: buildReadonlyFindingsHtml, normalizeFeatureCollection: normalizeFeatureCollection, createPortalMap: createPortalMap, csrfToken: csrfToken };
})();
