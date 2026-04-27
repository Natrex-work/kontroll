(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/static/sw.js?v=V1.1').catch(function () {});
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
  var portalBundleCache = {};
  var portalBundleInflight = {};
  var PORTAL_FEATURE_CACHE_MS = 900000;
  var PORTAL_FEATURE_CACHE_LIMIT = 240;
  var PORTAL_FETCH_CONCURRENCY = 2;
  var PORTAL_FETCH_TIMEOUT_MS = 8500;

  function trimPortalFeatureCache() {
    var keys = Object.keys(portalFeatureCache);
    if (keys.length <= PORTAL_FEATURE_CACHE_LIMIT) return;
    keys.sort(function (a, b) { return (portalFeatureCache[a].ts || 0) - (portalFeatureCache[b].ts || 0); });
    while (keys.length > PORTAL_FEATURE_CACHE_LIMIT) {
      delete portalFeatureCache[keys.shift()];
    }
  }

  function fetchPortalFeatureCollection(viewKey, url, directUrl) {
    var now = Date.now();
    var cached = portalFeatureCache[viewKey];
    if (cached && (now - cached.ts) < PORTAL_FEATURE_CACHE_MS) return Promise.resolve(cached.data);
    if (portalFeatureInflight[viewKey]) return portalFeatureInflight[viewKey];
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { try { controller.abort(); } catch (e) {} }, PORTAL_FETCH_TIMEOUT_MS) : null;
    var request = fetch(url, controller ? { signal: controller.signal, credentials: 'same-origin' } : { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var normalized = normalizeFeatureCollection(data);
        if (normalized.features && normalized.features.length) {
          portalFeatureCache[viewKey] = { ts: Date.now(), data: normalized };
          trimPortalFeatureCache();
          return normalized;
        }
        if (directUrl) {
          return fetch(directUrl, { credentials: 'omit' }).then(function (r) { return r.json(); }).then(normalizeFeatureCollection).catch(function () { return normalized; });
        }
        return normalized;
      })
      .then(function (normalized) {
        if (normalized.features && normalized.features.length) {
          portalFeatureCache[viewKey] = { ts: Date.now(), data: normalized };
          trimPortalFeatureCache();
        }
        return normalized;
      })
      .catch(function () {
        return cached && cached.data ? cached.data : { type: 'FeatureCollection', features: [] };
      })
      .finally(function () {
        if (timer) clearTimeout(timer);
        delete portalFeatureInflight[viewKey];
      });
    portalFeatureInflight[viewKey] = request;
    return request;
  }



  function trimPortalBundleCache() {
    var keys = Object.keys(portalBundleCache);
    if (keys.length <= PORTAL_FEATURE_CACHE_LIMIT) return;
    keys.sort(function (a, b) { return (portalBundleCache[a].ts || 0) - (portalBundleCache[b].ts || 0); });
    while (keys.length > PORTAL_FEATURE_CACHE_LIMIT) {
      delete portalBundleCache[keys.shift()];
    }
  }

  function fetchPortalBundle(viewKey, url, layerIds, bbox) {
    var now = Date.now();
    var cached = portalBundleCache[viewKey];
    if (cached && (now - cached.ts) < PORTAL_FEATURE_CACHE_MS) return Promise.resolve(cached.data);
    if (portalBundleInflight[viewKey]) return portalBundleInflight[viewKey];
    var localMap = window.KVLocalMap;
    var exactRead = localMap && typeof localMap.readBundle === 'function' ? localMap.readBundle(layerIds, bbox).catch(function () { return null; }) : Promise.resolve(null);
    var bestRead = localMap && typeof localMap.readBestBundle === 'function' ? localMap.readBestBundle(layerIds, bbox).catch(function () { return null; }) : Promise.resolve(null);

    function finalizeBundle(data, layerIds, bbox) {
      var normalized = normalizeFeatureCollection(data);
      normalized.layers = Array.isArray(data && data.layers) ? data.layers : (Array.isArray(normalized.layers) ? normalized.layers : []);
      if (normalized.features && normalized.features.length) {
        portalBundleCache[viewKey] = { ts: Date.now(), data: normalized };
        trimPortalBundleCache();
        if (localMap && typeof localMap.cacheBundle === 'function') localMap.cacheBundle(layerIds, normalized.bbox || bbox, normalized).catch(function () {});
      }
      return normalized;
    }

    function fetchNetwork(fallbackData) {
      var controller = typeof AbortController === 'function' ? new AbortController() : null;
      var timer = controller ? setTimeout(function () { try { controller.abort(); } catch (e) {} }, PORTAL_FETCH_TIMEOUT_MS + 3000) : null;
      return fetch(url, controller ? { signal: controller.signal, credentials: 'same-origin' } : { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var normalized = finalizeBundle(data, layerIds, bbox);
          if (normalized.features && normalized.features.length) return normalized;
          return fallbackData || normalized;
        })
        .catch(function () {
          return fallbackData || (cached && cached.data ? cached.data : { type: 'FeatureCollection', features: [], layers: [] });
        })
        .finally(function () {
          if (timer) clearTimeout(timer);
          delete portalBundleInflight[viewKey];
        });
    }

    var request = Promise.all([exactRead, bestRead]).then(function (results) {
      var exact = results[0];
      var best = results[1];
      var offline = (exact && exact.features && exact.features.length) ? exact : ((best && best.features && best.features.length) ? best : null);
      if (offline) {
        portalBundleCache[viewKey] = { ts: Date.now(), data: offline };
        trimPortalBundleCache();
        fetchNetwork(offline).catch(function () {});
        return offline;
      }
      return fetchNetwork(null);
    });
    portalBundleInflight[viewKey] = request;
    return request;
  }

  function directMapFeatureUrl(serviceBase, layerId, bbox) {
    serviceBase = String(serviceBase || '').replace(/\/+$/g, '');
    if (!serviceBase) return '';
    var params = { where: '1=1', outFields: '*', returnGeometry: 'true', f: 'geojson', outSR: '4326' };
    if (bbox && bbox.length === 4) {
      params.geometry = bbox.join(',');
      params.geometryType = 'esriGeometryEnvelope';
      params.inSR = '4326';
      params.spatialRel = 'esriSpatialRelIntersects';
    }
    var base = serviceBase + '/' + encodeURIComponent(String(layerId)) + '/query';
    return base + L.Util.getParamString(params, base, true);
  }

  function directIdentifyRequest(serviceBase, layerId, lat, lng) {
    serviceBase = String(serviceBase || '').replace(/\/+$/g, '');
    if (!serviceBase) return Promise.resolve([]);
    var params = { f: 'json', geometry: String(lng) + ',' + String(lat), geometryType: 'esriGeometryPoint', inSR: '4326', spatialRel: 'esriSpatialRelIntersects', returnGeometry: 'false', outFields: '*' };
    var base = serviceBase + '/' + encodeURIComponent(String(layerId)) + '/query';
    var url = base + L.Util.getParamString(params, base, true);
    return fetch(url, { credentials: 'omit' }).then(function (r) { return r.json(); }).then(function (payload) { return Array.isArray(payload && payload.features) ? payload.features : []; }).catch(function () { return []; });
  }

  function normalizeDirectIdentifyHits(features, layer) {
    return (features || []).map(function (feature) {
      var props = feature && feature.attributes ? feature.attributes : (feature && feature.properties ? feature.properties : {});
      return {
        layer_id: Number(layer && layer.id || 0),
        layer: layer && layer.name || '',
        status: layer && layer.status || '',
        name: props.navn || props.omraade || props.område || props.name || (layer && layer.name) || 'Område',
        description: props.info || props.beskrivelse || props.informasjon || props.omraade_stengt_text || props.vurderes_aapnet_text || props.regelverk || (layer && layer.description) || '',
        url: props.url || props.url_lovtekst || props.lenke || (layer && layer.service_url) || '',
        source: 'Fiskeridirektoratets kartdatabase',
        database: 'Fiskeridirektoratets kartdatabase'
      };
    });
  }

  function browserIdentifyFallback(serviceBase, layers, lat, lng) {
    var collected = [];
    var tasks = (layers || []).map(function (layer) {
      return function () {
        return directIdentifyRequest(serviceBase, layer.id, lat, lng).then(function (features) {
          if (features && features.length) collected = collected.concat(normalizeDirectIdentifyHits(features, layer));
        });
      };
    });
    return runLimited(tasks, 2).then(function () { return { match: collected.length > 0, lat: Number(lat), lng: Number(lng), hits: collected }; });
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


  function identifyPopupHtml(payload) {
    var hits = payload && Array.isArray(payload.hits) ? payload.hits : [];
    if (!hits.length) {
      return '<div class="map-popup"><div class="map-popup-title">Ingen områdetreff</div><div class="small muted">Ingen aktive fiskerilag traff i dette punktet.</div></div>';
    }
    var primary = hits[0] || {};
    return '<div class="map-popup">'
      + '<div class="map-popup-title">' + escapeHtml(primary.name || primary.layer || 'Områdetreff') + '</div>'
      + (primary.status ? '<div class="pill ' + (String(primary.status || '').toLowerCase().indexOf('stengt') !== -1 || String(primary.status || '').toLowerCase().indexOf('forbud') !== -1 ? 'pill-danger' : (String(primary.status || '').toLowerCase().indexOf('fiskeri') !== -1 ? 'pill-info' : '')) + '">' + escapeHtml(primary.status) + '</div>' : '')
      + '<div class="small muted" style="margin-top:6px">Trykkpunkt: ' + escapeHtml(Number(payload.lat || 0).toFixed(6)) + ', ' + escapeHtml(Number(payload.lng || 0).toFixed(6)) + '</div>'
      + hits.slice(0, 8).map(function (item) {
          return '<div class="map-popup-hit">'
            + '<div><strong>' + escapeHtml(item.name || item.layer || 'Område') + '</strong></div>'
            + (item.layer ? '<div class="small muted">Lag: ' + escapeHtml(item.layer) + '</div>' : '')
            + (item.description ? '<div class="small" style="margin-top:4px">' + escapeHtml(item.description) + '</div>' : '')
            + '<div class="small muted" style="margin-top:4px">Datakilde: ' + escapeHtml(item.source || item.database || 'Fiskeridirektoratets kartdatabase') + '</div>'
            + (item.url ? '<div class="small" style="margin-top:4px"><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">Åpne regelgrunnlag</a></div>' : '')
            + '</div>';
        }).join('')
      + (hits.length > 8 ? '<div class="small muted" style="margin-top:8px">Viser de første 8 treffene.</div>' : '')
      + '</div>';
  }


  var LAYER_PANEL_PREFS_VERSION = 'V1.1';

  function layerPanelStorageKey(el, markerState) {
    return 'kv-temalag:' + LAYER_PANEL_PREFS_VERSION + ':' + String((markerState && markerState.layerPanelKey) || (el && el.id) || 'map');
  }

  function loadLayerPanelPrefs(key) {
    try {
      var data = JSON.parse(localStorage.getItem(key) || '{}');
      if (!data || typeof data !== 'object') return {};
      if (String(data.version || '') !== LAYER_PANEL_PREFS_VERSION) return {};
      return data;
    } catch (e) {
      return {};
    }
  }

  function saveLayerPanelPrefs(key, prefs) {
    try {
      var payload = Object.assign({}, prefs || {}, { version: LAYER_PANEL_PREFS_VERSION });
      localStorage.setItem(key, JSON.stringify(payload));
    } catch (e) {}
  }

  function layerPanelGroup(layer) {
    if (layer && layer.panel_group) {
      return {
        label: String(layer.panel_group || 'Andre temalag'),
        key: String(layer.panel_group_key || layer.panel_group || 'andre_temalag'),
        order: Number(layer.panel_group_order || 999)
      };
    }
    var name = String(layer && layer.name || '').toLowerCase();
    var desc = String(layer && layer.description || '').toLowerCase();
    var status = String(layer && layer.status || '').toLowerCase();
    var blob = [name, desc, status].join(' ');
    if (blob.indexOf('administrasjon') !== -1 || blob.indexOf('kontor') !== -1) return { label: 'Administrasjon', key: 'administrasjon', order: 10 };
    if (blob.indexOf('korall') !== -1) return { label: 'Korallrev', key: 'korallrev', order: 30 };
    if (blob.indexOf('verne') !== -1 || blob.indexOf('nasjonalpark') !== -1 || blob.indexOf('bunnhabitat') !== -1 || blob.indexOf('sårbar') !== -1 || blob.indexOf('saarbar') !== -1 || blob.indexOf('laksefjord') !== -1) return { label: 'Verneområder', key: 'verneomrader', order: 40 };
    if (blob.indexOf('tare') !== -1) return { label: 'Tare', key: 'tare', order: 50 };
    if (status.indexOf('fiskeriområde') !== -1 || status.indexOf('fiskeriomrade') !== -1 || blob.indexOf('gyte') !== -1 || blob.indexOf('oppvekst') !== -1 || blob.indexOf('fiskeplass') !== -1 || blob.indexOf('rekefelt') !== -1 || blob.indexOf('skjellforekomst') !== -1 || blob.indexOf('låssettings') !== -1 || blob.indexOf('lasettings') !== -1 || blob.indexOf('havbeitelokalitet') !== -1) {
      return { label: 'Kystnære fiskeridata', key: 'kystnaere_fiskeridata', order: 60 };
    }
    if (blob.indexOf('tapte redskap') !== -1) return { label: 'Tapte redskap', key: 'tapte_redskap', order: 70 };
    if (blob.indexOf('hovedomraader') !== -1 || blob.indexOf('hovedområder') !== -1 || blob.indexOf('lokasjoner') !== -1 || blob.indexOf('statistikkområde') !== -1 || blob.indexOf('statistikkomrade') !== -1) return { label: 'Statistikkområder', key: 'statistikkomrader', order: 80 };
    if (blob.indexOf('dybde') !== -1 || blob.indexOf('sjø') !== -1 || blob.indexOf('sjo') !== -1) return { label: 'Sjø- og dybdedata', key: 'sjo_dybdedata', order: 90 };
    return { label: 'Fiskerireguleringer', key: 'fiskerireguleringer', order: 20 };
  }

  function layerStatusClass(status) {
    return String(status || 'ukjent').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  }

  function layerStatusLabel(status) {
    var value = String(status || '').trim();
    if (!value) return 'Kartlag';
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  function geometryLabel(value) {
    var text = String(value || '').toLowerCase();
    if (text.indexOf('point') !== -1) return 'Punkt';
    if (text.indexOf('line') !== -1) return 'Linje';
    return 'Flate';
  }

  function buildLayerPanelGroups(layers, query) {
    var groupsByKey = {};
    var search = String(query || '').trim().toLowerCase();
    (layers || []).forEach(function (layer) {
      if (!layer || !isFinite(Number(layer.id))) return;
      var haystack = [layer.name, layer.description, layer.status, layer.panel_group].join(' ').toLowerCase();
      if (search && haystack.indexOf(search) === -1) return;
      var group = layerPanelGroup(layer);
      if (!groupsByKey[group.key]) groupsByKey[group.key] = { key: group.key, label: group.label, order: group.order, layers: [] };
      groupsByKey[group.key].layers.push(layer);
    });
    return Object.keys(groupsByKey).map(function (key) { return groupsByKey[key]; }).sort(function (a, b) {
      var diff = Number(a.order || 999) - Number(b.order || 999);
      if (diff) return diff;
      return String(a.label || '').localeCompare(String(b.label || ''), 'nb');
    }).map(function (group) {
      group.layers.sort(function (a, b) { return String(a.name || '').localeCompare(String(b.name || ''), 'nb'); });
      return group;
    });
  }

  function visibleLayersFromPrefs(layers, prefs, markerState) {
    var hidden = {};
    var initialized = !!(prefs && prefs.initialized);
    var presetVisible = {};
    (prefs && Array.isArray(prefs.hidden_ids) ? prefs.hidden_ids : []).forEach(function (value) {
      hidden[String(value)] = true;
    });
    if (!initialized && markerState && Array.isArray(markerState.defaultVisibleLayerIds) && markerState.defaultVisibleLayerIds.length) {
      markerState.defaultVisibleLayerIds.forEach(function (value) {
        var numericId = Number(value);
        if (isFinite(numericId)) presetVisible[String(numericId)] = true;
      });
    }
    var usePreset = !initialized && Object.keys(presetVisible).length > 0;
    return (layers || []).filter(function (layer) {
      var id = String(layer && layer.id);
      if (hidden[id]) return false;
      if (usePreset) return !!presetVisible[id];
      if (!initialized && layer && layer.default_visible === false) return false;
      return true;
    });
  }

  function resolveLayerPanelMount(state, map) {
    var markerState = state && state.markerState ? state.markerState : {};
    var target = markerState.layerPanelTargetEl || null;
    if (!target && markerState.layerPanelTargetSelector) {
      try {
        target = document.querySelector(String(markerState.layerPanelTargetSelector || ''));
      } catch (e) {
        target = null;
      }
    }
    if (target && target.nodeType === 1) {
      return { element: target, external: true };
    }
    var container = map && typeof map.getContainer === 'function' ? map.getContainer() : null;
    return { element: container, external: false };
  }

  function ensureLayerPanelRoot(state, mountInfo) {
    var root = state.layerPanelRoot;
    if (!root) {
      root = document.createElement('div');
      root.className = 'kv-temalag-panel';
      root.innerHTML = [
        '<button type="button" class="kv-temalag-handle" aria-expanded="false"><span>Velg kartlag</span><span class="kv-temalag-handle-icon">▾</span></button>',
        '<div class="kv-temalag-card">',
        '<div class="kv-temalag-head">',
        '<div><strong>Velg kartlag i kartet</strong><div class="small muted kv-temalag-summary"></div></div>',
        '<div class="kv-temalag-panel-actions"><button type="button" class="btn btn-secondary btn-small kv-temalag-expand-all">Utvid alle</button><button type="button" class="btn btn-secondary btn-small kv-temalag-collapse-all">Legg sammen</button><button type="button" class="kv-temalag-close" aria-label="Skjul temalag">×</button></div>',
        '</div>',
        '<div class="kv-temalag-search-wrap"><input type="search" class="kv-temalag-search" placeholder="Søk i lag" /></div>',
        '<div class="kv-temalag-groups"></div>',
        '</div>'
      ].join('');
      state.layerPanelRoot = root;
      root.querySelector('.kv-temalag-handle').addEventListener('click', function (event) {
        event.preventDefault();
        state.layerPanelPrefs = state.layerPanelPrefs || {};
        state.layerPanelPrefs.open = !root.classList.contains('is-open');
        saveLayerPanelPrefs(state.layerPanelStorageKey, state.layerPanelPrefs);
        syncLayerPanel(state, state.map, state.currentLayers || [], state.visibleLayers || []);
      });
      root.querySelector('.kv-temalag-close').addEventListener('click', function (event) {
        event.preventDefault();
        state.layerPanelPrefs = state.layerPanelPrefs || {};
        state.layerPanelPrefs.open = false;
        saveLayerPanelPrefs(state.layerPanelStorageKey, state.layerPanelPrefs);
        syncLayerPanel(state, state.map, state.currentLayers || [], state.visibleLayers || []);
      });
      root.querySelector('.kv-temalag-expand-all').addEventListener('click', function (event) {
        event.preventDefault();
        state.layerPanelPrefs = state.layerPanelPrefs || {};
        state.layerPanelPrefs.collapsed_groups = [];
        state.layerPanelPrefs.groups_initialized = true;
        saveLayerPanelPrefs(state.layerPanelStorageKey, state.layerPanelPrefs);
        syncLayerPanel(state, state.map, state.currentLayers || [], state.visibleLayers || []);
      });
      root.querySelector('.kv-temalag-collapse-all').addEventListener('click', function (event) {
        event.preventDefault();
        state.layerPanelPrefs = state.layerPanelPrefs || {};
        state.layerPanelPrefs.collapsed_groups = (state._lastLayerPanelGroupKeys || []).slice();
        state.layerPanelPrefs.groups_initialized = true;
        saveLayerPanelPrefs(state.layerPanelStorageKey, state.layerPanelPrefs);
        syncLayerPanel(state, state.map, state.currentLayers || [], state.visibleLayers || []);
      });
      root.querySelector('.kv-temalag-search').addEventListener('input', function (event) {
        state.layerPanelSearch = String(event.target.value || '');
        syncLayerPanel(state, state.map, state.currentLayers || [], state.visibleLayers || []);
      });
    }
    if (mountInfo && mountInfo.element && root.parentNode !== mountInfo.element) {
      mountInfo.element.appendChild(root);
    }
    root.classList.toggle('kv-temalag-panel-external', !!(mountInfo && mountInfo.external));
    if (window.L && L.DomEvent && !(mountInfo && mountInfo.external)) {
      L.DomEvent.disableClickPropagation(root);
      if (L.DomEvent.disableScrollPropagation) L.DomEvent.disableScrollPropagation(root);
    }
    return root;
  }

  function syncLayerPanel(state, map, allLayers, visibleLayers) {
    if (!map || !state) return;
    if (state.markerState && state.markerState.showLayerPanel === false) {
      if (state.layerPanelRoot && state.layerPanelRoot.parentNode) state.layerPanelRoot.parentNode.removeChild(state.layerPanelRoot);
      state.layerPanelRoot = null;
      return;
    }
    var mountInfo = resolveLayerPanelMount(state, map);
    if (!mountInfo.element) return;
    var root = ensureLayerPanelRoot(state, mountInfo);

    var prefs = state.layerPanelPrefs || {};
    var defaultOpen = !window.matchMedia('(max-width: 960px)').matches;
    if (state.markerState && typeof state.markerState.layerPanelDefaultOpen === 'boolean') defaultOpen = state.markerState.layerPanelDefaultOpen;
    if (typeof prefs.open !== 'boolean') prefs.open = defaultOpen;
    state.layerPanelPrefs = prefs;
    saveLayerPanelPrefs(state.layerPanelStorageKey, prefs);

    root.classList.toggle('is-open', prefs.open !== false);
    var handle = root.querySelector('.kv-temalag-handle');
    var card = root.querySelector('.kv-temalag-card');
    if (handle) handle.setAttribute('aria-expanded', root.classList.contains('is-open') ? 'true' : 'false');
    if (card) card.hidden = !root.classList.contains('is-open');
    var searchInput = root.querySelector('.kv-temalag-search');
    if (searchInput && searchInput.value !== String(state.layerPanelSearch || '')) searchInput.value = String(state.layerPanelSearch || '');

    var summary = root.querySelector('.kv-temalag-summary');
    if (summary) summary.textContent = String((visibleLayers || []).length) + ' av ' + String((allLayers || []).length) + ' lag vises';

    var visibleLookup = {};
    (visibleLayers || []).forEach(function (layer) { visibleLookup[String(layer && layer.id)] = true; });
    var groups = buildLayerPanelGroups(allLayers, state.layerPanelSearch || '');
    state._lastLayerPanelGroupKeys = groups.map(function (group) { return String(group.key); });
    var isExternalMobilePanel = root.classList.contains('kv-temalag-panel-external') && window.matchMedia('(max-width: 720px)').matches;
    if (isExternalMobilePanel && !prefs.groups_initialized && !String(state.layerPanelSearch || '').trim() && groups.length > 1) {
      prefs.collapsed_groups = groups.slice(1).map(function (group) { return String(group.key); });
      prefs.groups_initialized = true;
      saveLayerPanelPrefs(state.layerPanelStorageKey, prefs);
    }
    var collapsedLookup = {};
    (Array.isArray(prefs.collapsed_groups) ? prefs.collapsed_groups : []).forEach(function (key) { collapsedLookup[String(key)] = true; });
    var groupsWrap = root.querySelector('.kv-temalag-groups');
    if (!groupsWrap) return;
    groupsWrap.innerHTML = groups.length ? groups.map(function (group) {
      var visibleCount = group.layers.filter(function (layer) { return visibleLookup[String(layer && layer.id)]; }).length;
      var itemsHtml = group.layers.map(function (layer) {
        var layerId = Number(layer && layer.id);
        var checked = visibleLookup[String(layerId)];
        return [
          '<label class="kv-temalag-item">',
          '<input class="kv-temalag-item-check" type="checkbox" data-layer-id="' + escapeHtml(layerId) + '" ' + (checked ? 'checked' : '') + ' />',
          '<span class="kv-temalag-swatch" style="background:' + escapeHtml(layer.color || '#1f4f82') + '"></span>',
          '<span class="kv-temalag-item-body">',
          '<span class="kv-temalag-item-title">' + escapeHtml(layer.name || ('Lag ' + layerId)) + '</span>',
          '<span class="kv-temalag-item-meta"><span class="kv-status-chip ' + escapeHtml(layerStatusClass(layer.status)) + '">' + escapeHtml(layerStatusLabel(layer.status)) + '</span><span class="kv-geom-chip">' + escapeHtml(geometryLabel(layer.geometry_type)) + '</span>' + (layer.selection_summary ? '<span class="kv-selection-chip">' + escapeHtml(layer.selection_summary) + '</span>' : '') + '</span>',
          '</span>',
          '</label>'
        ].join('');
      }).join('');
      var collapsed = !!collapsedLookup[group.key];
      return [
        '<section class="kv-temalag-group ' + (collapsed ? 'is-collapsed' : 'is-open') + '" data-group-key="' + escapeHtml(group.key) + '">',
        '<button type="button" class="kv-temalag-group-toggle" data-group-key="' + escapeHtml(group.key) + '" aria-expanded="' + (collapsed ? 'false' : 'true') + '"><span class="kv-temalag-group-title">' + escapeHtml(group.label) + '</span><span class="kv-temalag-group-count">' + visibleCount + '/' + group.layers.length + '</span></button>',
        '<div class="kv-temalag-group-body" ' + (collapsed ? 'hidden' : '') + '>',
        '<div class="kv-temalag-group-actions"><button type="button" class="btn btn-secondary btn-small kv-temalag-show-all" data-group-key="' + escapeHtml(group.key) + '">Vis alle i gruppen</button><button type="button" class="btn btn-secondary btn-small kv-temalag-hide-all" data-group-key="' + escapeHtml(group.key) + '">Skjul alle i gruppen</button></div>',
        '<div class="kv-temalag-items">' + itemsHtml + '</div>',
        '</div>',
        '</section>'
      ].join('');
    }).join('') : '<div class="offline-package-empty">Ingen lag matcher søket.</div>';

    Array.prototype.forEach.call(groupsWrap.querySelectorAll('.kv-temalag-item-check'), function (input) {
      input.addEventListener('change', function (event) {
        var layerId = String(event.target.getAttribute('data-layer-id') || '');
        state.layerPanelPrefs = state.layerPanelPrefs || {};
        var hiddenIds = Array.isArray(state.layerPanelPrefs.hidden_ids) ? state.layerPanelPrefs.hidden_ids.slice() : [];
        var hiddenLookup = {};
        hiddenIds.forEach(function (value) { hiddenLookup[String(value)] = true; });
        if (event.target.checked) delete hiddenLookup[layerId];
        else hiddenLookup[layerId] = true;
        state.layerPanelPrefs.hidden_ids = Object.keys(hiddenLookup);
        state.layerPanelPrefs.initialized = true;
        saveLayerPanelPrefs(state.layerPanelStorageKey, state.layerPanelPrefs);
        if (typeof state.refreshLayers === 'function') state.refreshLayers();
      });
    });

    Array.prototype.forEach.call(groupsWrap.querySelectorAll('.kv-temalag-show-all, .kv-temalag-hide-all'), function (button) {
      button.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        var groupKey = String(event.currentTarget.getAttribute('data-group-key') || '');
        var group = groups.filter(function (row) { return row.key === groupKey; })[0];
        if (!group) return;
        state.layerPanelPrefs = state.layerPanelPrefs || {};
        var hiddenLookup = {};
        (Array.isArray(state.layerPanelPrefs.hidden_ids) ? state.layerPanelPrefs.hidden_ids : []).forEach(function (value) { hiddenLookup[String(value)] = true; });
        var showAll = event.currentTarget.classList.contains('kv-temalag-show-all');
        group.layers.forEach(function (layer) {
          var key = String(layer && layer.id);
          if (showAll) delete hiddenLookup[key];
          else hiddenLookup[key] = true;
        });
        state.layerPanelPrefs.hidden_ids = Object.keys(hiddenLookup);
        state.layerPanelPrefs.initialized = true;
        saveLayerPanelPrefs(state.layerPanelStorageKey, state.layerPanelPrefs);
        if (typeof state.refreshLayers === 'function') state.refreshLayers();
      });
    });

    Array.prototype.forEach.call(groupsWrap.querySelectorAll('.kv-temalag-group-toggle'), function (button) {
      button.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        var groupKey = String(event.currentTarget.getAttribute('data-group-key') || '');
        if (!groupKey) return;
        state.layerPanelPrefs = state.layerPanelPrefs || {};
        var collapsed = Array.isArray(state.layerPanelPrefs.collapsed_groups) ? state.layerPanelPrefs.collapsed_groups.slice() : [];
        var lookup = {};
        collapsed.forEach(function (value) { lookup[String(value)] = true; });
        var section = event.currentTarget.closest ? event.currentTarget.closest('.kv-temalag-group') : null;
        var body = section && section.querySelector ? section.querySelector('.kv-temalag-group-body') : null;
        var willCollapse = !lookup[groupKey];
        if (lookup[groupKey]) delete lookup[groupKey];
        else lookup[groupKey] = true;
        state.layerPanelPrefs.collapsed_groups = Object.keys(lookup);
        state.layerPanelPrefs.initialized = true;
        saveLayerPanelPrefs(state.layerPanelStorageKey, state.layerPanelPrefs);
        // Update the touched group immediately. This makes Safari/iPhone feel
        // responsive even if the map layer refresh takes a moment.
        if (section) {
          section.classList.toggle('is-collapsed', willCollapse);
          section.classList.toggle('is-open', !willCollapse);
        }
        if (body) body.hidden = willCollapse;
        event.currentTarget.setAttribute('aria-expanded', willCollapse ? 'false' : 'true');
      });
    });
  }


  function createPortalMap(el, layers, markerState) {
    if (!el || !window.L) return Promise.resolve(null);
    var storageKey = 'kv-map-view:' + (el.id || 'map');
    var persistView = !(markerState && markerState.persistView === false);
    var savedView = null;
    if (persistView) {
      try {
        savedView = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
      } catch (e) { savedView = null; }
    }

    function validLatLng(lat, lng) {
      return isFinite(lat) && isFinite(lng) && Math.abs(Number(lat)) <= 90 && Math.abs(Number(lng)) <= 180 && !(Math.abs(Number(lat)) < 0.000001 && Math.abs(Number(lng)) < 0.000001);
    }

    function caseIcon() {
      return L.divIcon({ className: 'kv-case-marker', html: '<div class="leaflet-case-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
    }

    function userIcon() {
      return L.divIcon({ className: 'kv-user-marker', html: '<div class="leaflet-user-dot"></div>', iconSize: [16, 16], iconAnchor: [8, 8] });
    }

    function uniqueLayerIds(rows) {
      var seen = {};
      return (rows || []).map(function (layer) { return Number(layer && layer.id); }).filter(function (value) {
        if (!isFinite(value)) return false;
        if (seen[value]) return false;
        seen[value] = true;
        return true;
      });
    }

    function deriveMapServerUrl(targetEl, rows, ms) {
      if (ms && ms.mapServerUrl) return String(ms.mapServerUrl || '').replace(/\/+$|\/export$/g, '');
      if (targetEl && targetEl.dataset && targetEl.dataset.portalMapserver) return String(targetEl.dataset.portalMapserver || '').replace(/\/+$|\/export$/g, '');
      for (var i = 0; i < (rows || []).length; i += 1) {
        var serviceUrl = String(rows[i] && rows[i].service_url || '').trim();
        if (!serviceUrl) continue;
        return serviceUrl.replace(/\/\d+$/g, '').replace(/\/+$|\/export$/g, '');
      }
      return '';
    }

    function ensureArcGisExportLayerClass() {
      if (!window.L) return null;
      if (L.TileLayer.ArcGISExportKV) return L.TileLayer.ArcGISExportKV;
      L.TileLayer.ArcGISExportKV = L.TileLayer.extend({
        initialize: function (serviceUrl, options) {
          this._serviceUrl = String(serviceUrl || '').replace(/\/+$|\/export$/g, '');
          L.TileLayer.prototype.initialize.call(this, '', Object.assign({
            tileSize: 256,
            opacity: 0.78,
            updateWhenIdle: true,
            updateWhenZooming: false,
            keepBuffer: 3,
            className: 'kv-arcgis-export-layer'
          }, options || {}));
        },
        getTileUrl: function (coords) {
          var tileBounds = this._tileCoordsToBounds(coords);
          var nw = this._map.options.crs.project(tileBounds.getNorthWest());
          var se = this._map.options.crs.project(tileBounds.getSouthEast());
          var bbox = [nw.x, se.y, se.x, nw.y].join(',');
          var size = this.getTileSize();
          var params = {
            bbox: bbox,
            bboxSR: 3857,
            imageSR: 3857,
            size: size.x + ',' + size.y,
            format: 'png32',
            transparent: true,
            dpi: 96,
            f: 'image'
          };
          var layerIds = uniqueLayerIds(this.options.layerDefs || []);
          if (layerIds.length) params.layers = 'show:' + layerIds.join(',');
          var exportUrl = this._serviceUrl + '/export';
          return exportUrl + L.Util.getParamString(params, exportUrl, true);
        }
      });
      return L.TileLayer.ArcGISExportKV;
    }

    function createArcGisExportLayer(serviceUrl, options) {
      var Klass = ensureArcGisExportLayerClass();
      return Klass ? new Klass(serviceUrl, options || {}) : null;
    }

    function chunkLayerIds(ids, size) {
      size = Math.max(1, Number(size || 20));
      var values = uniqueLayerIds(ids || []);
      var chunks = [];
      for (var i = 0; i < values.length; i += size) chunks.push(values.slice(i, i + size));
      return chunks;
    }

    function portalVernIdLookup() {
      return { '0': true, '1': true, '2': true, '3': true, '6': true, '23': true, '34': true, '35': true, '37': true };
    }

    function normalizedServiceUrl(value) {
      return String(value || '').replace(/\/\d+$/g, '').replace(/\/+$/g, '').replace(/\/export$/g, '');
    }

    function layerServiceMeta(layer, fisheryServiceUrl, vernServiceUrl) {
      var meta = { url: '', layerId: null };
      if (!layer) return meta;
      var rawId = Number(layer.id);
      var legacyIds = Array.isArray(layer.legacy_ids) ? layer.legacy_ids.map(function (value) { return Number(value); }).filter(function (value) { return isFinite(value); }) : [];
      var serviceUrl = normalizedServiceUrl(layer.service_url || '');
      var knownVernIds = portalVernIdLookup();
      var isVernService = serviceUrl && serviceUrl.toLowerCase().indexOf('fiskeridir_vern') !== -1;
      if (isVernService) {
        meta.url = normalizedServiceUrl(vernServiceUrl || serviceUrl);
        if (knownVernIds[String(rawId)]) meta.layerId = rawId;
        else if (legacyIds.length) meta.layerId = legacyIds[0];
        return meta;
      }
      if (legacyIds.some(function (value) { return knownVernIds[String(value)]; })) {
        meta.url = normalizedServiceUrl(vernServiceUrl);
        meta.layerId = legacyIds.filter(function (value) { return knownVernIds[String(value)]; })[0];
        return meta;
      }
      meta.url = normalizedServiceUrl(fisheryServiceUrl || serviceUrl);
      if (isFinite(rawId)) meta.layerId = rawId;
      return meta;
    }

    function buildPortalRasterServicesFromLayers(layers, fisheryServiceUrl, vernServiceUrl, options) {
      options = options || {};
      var byService = {};
      (layers || []).forEach(function (layer) {
        var meta = layerServiceMeta(layer, fisheryServiceUrl, vernServiceUrl);
        var layerId = Number(meta.layerId);
        if (!meta.url || !isFinite(layerId)) return;
        if (!byService[meta.url]) byService[meta.url] = [];
        byService[meta.url].push(layerId);
      });
      var services = [];
      Object.keys(byService).forEach(function (serviceUrl) {
        chunkLayerIds(byService[serviceUrl], options.chunkSize || 20).forEach(function (chunk, index) {
          services.push({
            url: serviceUrl,
            layerIds: chunk,
            opacity: isFinite(Number(options.opacity)) ? Number(options.opacity) : 0.88,
            respectVisibility: false,
            key: serviceUrl + '|chunk:' + String(index) + '|' + chunk.join(',')
          });
        });
      });
      return services;
    }

    function rasterServiceList(ms, defaultUrl, renderLayers, visibleLayerLookup) {
      var services = [];
      if (ms && ms.rasterServicesAuto) {
        services = buildPortalRasterServicesFromLayers(
          renderLayers,
          (ms && ms.portalFisheryService) || defaultUrl,
          ms && ms.portalVernService,
          { opacity: ms && isFinite(Number(ms.rasterOpacity)) ? Number(ms.rasterOpacity) : 0.88, chunkSize: ms && ms.rasterChunkSize }
        );
      } else if (ms && Array.isArray(ms.rasterServices) && ms.rasterServices.length) {
        services = ms.rasterServices.slice();
      } else {
        services = [{ url: defaultUrl, layerIds: (Array.isArray(ms.rasterLayerIds) && ms.rasterLayerIds.length ? ms.rasterLayerIds.slice() : uniqueLayerIds(renderLayers)), opacity: ms && isFinite(Number(ms.rasterOpacity)) ? Number(ms.rasterOpacity) : 0.8, respectVisibility: true }];
      }
      return services.map(function (svc) {
        var ids = Array.isArray(svc.layerIds) ? svc.layerIds.map(function (value) { return Number(value); }).filter(function (value) { return isFinite(value); }) : [];
        if (svc.respectVisibility !== false) {
          ids = ids.filter(function (value) { return visibleLayerLookup[String(value)]; });
        }
        return {
          url: String((svc && svc.url) || defaultUrl || '').replace(/\/+$/g, '').replace(/\/export$/g, ''),
          layerIds: ids,
          opacity: isFinite(Number(svc && svc.opacity)) ? Number(svc.opacity) : (ms && isFinite(Number(ms.rasterOpacity)) ? Number(ms.rasterOpacity) : 0.8),
          key: String((svc && svc.key) || ((svc && svc.url) || defaultUrl || '').replace(/\/+$/g, '').replace(/\/export$/g, '') + '|' + ids.join(','))
        };
      }).filter(function (svc) { return svc.url && svc.layerIds.length; });
    }
    function clearFeatureOverlays(state, map) {
      Object.keys(state.overlaysById || {}).forEach(function (key) {
        try { map.removeLayer(state.overlaysById[key]); } catch (e) {}
      });
      state.overlaysById = {};
      state.layerViewKeys = {};
      state.featureSummariesByLayer = {};
    }

    function layerSummaryFromDef(layer) {
      return {
        layerId: layer.id,
        layer: layer.name,
        status: layer.status || '',
        name: layer.name || 'Kartlag',
        description: layer.description || '',
        url: layer.service_url || '',
        source: 'Fiskeridirektoratet kartlag'
      };
    }

    function legendSort(a, b) {
      var order = { 'stengt område': 0, 'fredningsområde': 1, 'maksimalmål område': 2, 'fiskeriområde': 3, 'regulert område': 4 };
      var aStatus = String(a && a.status || '').toLowerCase();
      var bStatus = String(b && b.status || '').toLowerCase();
      var diff = (order[aStatus] != null ? order[aStatus] : 99) - (order[bStatus] != null ? order[bStatus] : 99);
      if (diff) return diff;
      return String(a && a.name || '').localeCompare(String(b && b.name || ''), 'nb');
    }

    var state = el._kvPortalState;
    if (!state) {
      var initialView = (markerState && markerState.view) || savedView || ((markerState && validLatLng(markerState.lat, markerState.lng)) ? { lat: markerState.lat, lng: markerState.lng, zoom: markerState.defaultZoom || 11 } : ((markerState && validLatLng(markerState.deviceLat, markerState.deviceLng)) ? { lat: markerState.deviceLat, lng: markerState.deviceLng, zoom: markerState.defaultZoom || 13 } : null));
      var map = L.map(el, { zoomControl: true }).setView(initialView ? [initialView.lat, initialView.lng] : [63.5, 11], initialView ? initialView.zoom : 5);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap',
        updateWhenIdle: true,
        updateWhenZooming: false,
        keepBuffer: 4,
        crossOrigin: true
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
        featureSummariesByLayer: {},
        rasterOverlay: null,
        rasterKey: ''
      };
      map.on('moveend zoomend', function () {
        var liveMarkerState = state.markerState || {};
        if (liveMarkerState.persistView !== false) {
          try {
            var center = map.getCenter();
            sessionStorage.setItem(storageKey, JSON.stringify({ lat: center.lat, lng: center.lng, zoom: map.getZoom() }));
          } catch (e) {}
        }
        var liveMarkerState = state.markerState || {};
        if (typeof state.refreshLayers === 'function' && liveMarkerState.fetchFeatureDetails === true) {
          clearTimeout(state._refreshTimer);
          state._refreshTimer = setTimeout(function () { state.refreshLayers(); }, 850);
        }
      });
      el._kvPortalState = state;
      el._kvLeafletMap = map;
    }

    state.markerState = markerState || {};
    state.layerPanelStorageKey = layerPanelStorageKey(el, state.markerState || {});
    state.layerPanelPrefs = loadLayerPanelPrefs(state.layerPanelStorageKey);
    state.currentLayers = Array.isArray(layers) ? layers.slice() : [];
    state.visibleLayers = visibleLayersFromPrefs(state.currentLayers, state.layerPanelPrefs, state.markerState || {});
    state.refreshLayers = function () { createPortalMap(el, state.currentLayers, state.markerState || {}); };
    var map = state.map;
    var ms = state.markerState || {};
    var highlightLayerLookup = {};
    (Array.isArray(ms.highlightLayerIds) ? ms.highlightLayerIds : []).forEach(function (value) {
      var numericId = Number(value);
      if (isFinite(numericId)) highlightLayerLookup[String(numericId)] = true;
    });
    var renderLayers = state.visibleLayers.slice();
    ms.visibleLayerCount = renderLayers.length;
    syncLayerPanel(state, map, state.currentLayers, renderLayers);
    var mapServerUrl = deriveMapServerUrl(el, state.currentLayers, ms);
    var visibleLayerLookup = {};
    renderLayers.forEach(function (layer) { visibleLayerLookup[String(Number(layer && layer.id))] = true; });
    var rasterServices = rasterServiceList(ms, mapServerUrl, renderLayers, visibleLayerLookup);
    state.rasterOverlays = state.rasterOverlays || {};
    var activeRasterKeys = {};
    Object.keys(state.rasterOverlays).forEach(function (key) {
      activeRasterKeys[key] = false;
    });
    rasterServices.forEach(function (svc) {
      activeRasterKeys[svc.key] = true;
      if (!state.rasterOverlays[svc.key]) {
        var overlay = createArcGisExportLayer(svc.url, { layerDefs: svc.layerIds.slice(), opacity: svc.opacity });
        if (overlay) { overlay.addTo(map); state.rasterOverlays[svc.key] = overlay; }
      } else {
        state.rasterOverlays[svc.key].options.layerDefs = svc.layerIds.slice();
        if (state.rasterOverlays[svc.key].setOpacity) state.rasterOverlays[svc.key].setOpacity(svc.opacity);
        if (state.rasterOverlays[svc.key].redraw) state.rasterOverlays[svc.key].redraw();
      }
    });
    Object.keys(state.rasterOverlays).forEach(function (key) {
      if (activeRasterKeys[key]) return;
      try { map.removeLayer(state.rasterOverlays[key]); } catch (e) {}
      delete state.rasterOverlays[key];
    });
    state.rasterOverlay = rasterServices.length ? state.rasterOverlays[rasterServices[0].key] || null : null;
    state.rasterKey = rasterServices.length ? rasterServices.map(function (svc) { return svc.key; }).join('||') : '';

    var shouldFetchFeatureDetails = ms.fetchFeatureDetails === true;
    var detailFetchThresholdZoom = Number(ms.detailFetchThresholdZoom || 0);
    if (shouldFetchFeatureDetails && detailFetchThresholdZoom && map.getZoom && map.getZoom() < detailFetchThresholdZoom) {
      shouldFetchFeatureDetails = false;
    }
    var bounds = map.getBounds ? map.getBounds() : null;
    var bbox = bounds ? [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()] : null;
    var bboxKey = bbox ? bbox.map(function (value) { return Number(value).toFixed(2); }).join(',') : '';
    var activeLayerIds = {};
    var featurePromise = Promise.resolve();
    var featureLayers = renderLayers.slice();
    var detailIds = Array.isArray(ms.featureDetailLayerIds) ? ms.featureDetailLayerIds.map(function (value) { return String(value); }) : [];
    if (detailIds.length) {
      featureLayers = featureLayers.filter(function (layer) { return detailIds.indexOf(String(layer && layer.id)) !== -1; });
    }

    function clearBundleOverlay() {
      if (state.bundleOverlay) {
        try { map.removeLayer(state.bundleOverlay); } catch (e) {}
        state.bundleOverlay = null;
      }
      state.bundleViewKey = '';
      state.featureSummariesByLayer = {};
    }

    if (!shouldFetchFeatureDetails) {
      clearFeatureOverlays(state, map);
      clearBundleOverlay();
    } else {
      var bundleLayerIds = featureLayers.map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); });
      bundleLayerIds.forEach(function (value) { activeLayerIds[String(value)] = true; });
      var bundleViewKey = 'bundle:' + bundleLayerIds.join(',') + ':' + bboxKey;
      if (state.bundleOverlay && state.bundleViewKey === bundleViewKey) {
        featurePromise = Promise.resolve();
      } else {
        var bundleUrl = '/api/map/bundle';
        var params = [];
        if (bboxKey) params.push('bbox=' + encodeURIComponent(bbox.join(',')));
        if (bundleLayerIds.length) params.push('layer_ids=' + encodeURIComponent(bundleLayerIds.join(',')));
        if (params.length) bundleUrl += '?' + params.join('&');
        featurePromise = fetchPortalBundle(bundleViewKey, bundleUrl, bundleLayerIds, bbox).then(function (data) {
          data = normalizeFeatureCollection(data);
          data.layers = Array.isArray(data.layers) ? data.layers : [];
          clearFeatureOverlays(state, map);
          clearBundleOverlay();
          state.featureSummariesByLayer = {};
          if (!data.features.length) {
            state.bundleViewKey = bundleViewKey;
            return;
          }
          var featureSummaries = [];
          var geo = L.geoJSON(data, {
            interactive: false,
            style: function (feature) {
              var props = feature && feature.properties ? feature.properties : {};
              var geometryType = String((feature && feature.geometry && feature.geometry.type) || '').toLowerCase();
              var isLine = geometryType.indexOf('line') !== -1;
              var isPoint = geometryType.indexOf('point') !== -1;
              var color = props.__layer_color || '#c1121f';
              var isHighlight = !!highlightLayerLookup[String(Number(props.__layer_id || props.layer_id || 0))];
              return {
                color: color,
                weight: isLine ? (isHighlight ? 6 : 4) : (isHighlight ? 4 : 3),
                opacity: isPoint ? 0.99 : 0.98,
                fillColor: color,
                fillOpacity: isPoint ? (isHighlight ? 0.95 : 0.85) : (isHighlight ? 0.42 : 0.28),
                dashArray: isLine ? (isHighlight ? '10 5' : '8 6') : null
              };
            },
            pointToLayer: function (feature, latlng) {
              var props = feature && feature.properties ? feature.properties : {};
              var color = props.__layer_color || '#c1121f';
              var isHighlight = !!highlightLayerLookup[String(Number(props.__layer_id || props.layer_id || 0))];
              return L.circleMarker(latlng, {
                interactive: false,
                radius: isHighlight ? 9 : 7,
                color: color,
                weight: isHighlight ? 3 : 2,
                fillColor: color,
                fillOpacity: isHighlight ? 0.92 : 0.75
              });
            },
            bubblingMouseEvents: false,
            onEachFeature: function (feature, lyr) {
              var props = feature && feature.properties ? feature.properties : {};
              var title = props.navn || props.omraade || props.område || props.name || props.__layer_name || 'Område';
              var desc = props.info || props.beskrivelse || props.informasjon || props.omraade_stengt_text || props.vurderes_aapnet_text || props.regelverk || props.forskrift || props.__layer_description || '';
              var sourceUrl = props.url || props.url_lovtekst || props.lenke || props.__layer_url || '';
              var html = '<strong>' + escapeHtml(title) + '</strong>';
              if (props.__layer_status) html += '<div class="small muted">' + escapeHtml(props.__layer_status) + '</div>';
              if (desc) html += '<div class="small" style="margin-top:6px">' + escapeHtml(desc) + '</div>';
              html += '<div class="small muted" style="margin-top:6px">Datakilde: ' + escapeHtml(props.__layer_source || 'Fiskeridirektoratets kartdatabase') + '</div>';
              if (sourceUrl) html += '<div class="small" style="margin-top:6px"><a href="' + escapeHtml(sourceUrl) + '" target="_blank" rel="noopener">Åpne regelgrunnlag</a></div>';
              lyr.bindPopup(html);
              featureSummaries.push({
                layerId: Number(props.__layer_id || 0),
                layer: props.__layer_name || '',
                status: props.__layer_status || '',
                name: title,
                description: desc || '',
                url: sourceUrl || '',
                source: props.__layer_source || 'Fiskeridirektoratets kartdatabase'
              });
            }
          }).addTo(map);
          if (geo && typeof geo.bringToFront === 'function') geo.bringToFront();
          state.bundleOverlay = geo;
          state.bundleViewKey = bundleViewKey;
          state.featureSummariesByLayer.__bundle = featureSummaries;
        }).catch(function () {
          clearBundleOverlay();
        });
      }
    }

    return featurePromise.then(function () {
      if (shouldFetchFeatureDetails) {
        Object.keys(state.overlaysById).forEach(function (key) {
          if (activeLayerIds[key]) return;
          try { map.removeLayer(state.overlaysById[key]); } catch (e) {}
          delete state.overlaysById[key];
          delete state.layerViewKeys[key];
          delete state.featureSummariesByLayer[key];
        });
      }

      var visibleFeatureSummaries = [];
      if (shouldFetchFeatureDetails) {
        Object.keys(state.featureSummariesByLayer).forEach(function (key) {
          visibleFeatureSummaries = visibleFeatureSummaries.concat(state.featureSummariesByLayer[key] || []);
        });
      } else {
        visibleFeatureSummaries = renderLayers.map(layerSummaryFromDef);
      }

      if (typeof ms.onFeaturesRendered === 'function') {
        try { ms.onFeaturesRendered({ layers: renderLayers, features: visibleFeatureSummaries, bbox: bbox || null, synthetic: !shouldFetchFeatureDetails }); } catch (e) {}
      }

      if (state.legendControl) {
        try { map.removeControl(state.legendControl); } catch (e) {}
        state.legendControl = null;
      }
      var showLegend = ms.showLegend === true;
      var legendLayers = (shouldFetchFeatureDetails ? renderLayers.filter(function (layer) {
        var key = String(layer.id);
        return (state.featureSummariesByLayer[key] || []).length > 0;
      }) : renderLayers.slice()).sort(legendSort);
      var extraLegendCount = legendLayers.length > 12 ? (legendLayers.length - 12) : 0;
      legendLayers = legendLayers.slice(0, 12);
      if (showLegend && legendLayers.length) {
        var legendControl = L.control({ position: 'bottomleft' });
        legendControl.onAdd = function () {
          var div = L.DomUtil.create('div', 'leaflet-legend-control');
          div.innerHTML = '<div class="leaflet-legend-title">Kartlag</div>' + legendLayers.map(function (layer) {
            return '<div class="leaflet-legend-row"><span class="leaflet-legend-swatch" style="background:' + escapeHtml(layer.color || '#c1121f') + '"></span><span>' + escapeHtml(layer.name || '') + '</span></div>';
          }).join('') + (extraLegendCount ? '<div class="small muted" style="margin-top:8px">+' + extraLegendCount + ' flere lag i visningen</div>' : '');
          return div;
        };
        legendControl.addTo(map);
        state.legendControl = legendControl;
      }

      var hasCase = validLatLng(ms.lat, ms.lng);
      var hasDevice = ms.showDeviceMarker !== false && validLatLng(ms.deviceLat, ms.deviceLng);

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
          if (currentState.allowMapMove) {
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
            return;
          }
          if (currentState.enableAreaPopup === false) return;
          var activeLayers = (el._kvPortalState && Array.isArray(el._kvPortalState.visibleLayers)) ? el._kvPortalState.visibleLayers : renderLayers;
          var layerIds = (Array.isArray(currentState.identifyLayerIds) && currentState.identifyLayerIds.length ? currentState.identifyLayerIds : activeLayers.map(function (layer) { return Number(layer && layer.id); })).map(function (value) { return Number(value); }).filter(function (value) { return isFinite(value); });
          var url = '/api/map/identify?lat=' + encodeURIComponent(event.latlng.lat.toFixed(6)) + '&lng=' + encodeURIComponent(event.latlng.lng.toFixed(6));
          if (layerIds.length) url += '&layer_ids=' + encodeURIComponent(layerIds.join(','));
          state._identifyToken = (state._identifyToken || 0) + 1;
          var token = state._identifyToken;
          var loadingPopup = L.popup({ maxWidth: 320 }).setLatLng(event.latlng).setContent('<div class="map-popup"><div class="map-popup-title">Laster områdedata …</div><div class="small muted">Henter treff fra kartdatabasen.</div></div>').openOn(map);
          var activeRows = activeLayers || [];
          fetch(url)
            .then(function (response) { return response.json(); })
            .then(function (payload) {
              if (token !== state._identifyToken) return;
              if (payload && payload.hits && payload.hits.length) {
                loadingPopup.setContent(identifyPopupHtml(payload));
                return;
              }
              if (!mapServerUrl || !activeRows.length) {
                loadingPopup.setContent(identifyPopupHtml(payload || { lat: event.latlng.lat, lng: event.latlng.lng, hits: [] }));
                return;
              }
              browserIdentifyFallback(mapServerUrl, activeRows, event.latlng.lat.toFixed(6), event.latlng.lng.toFixed(6)).then(function (fallbackPayload) {
                if (token !== state._identifyToken) return;
                loadingPopup.setContent(identifyPopupHtml((fallbackPayload && fallbackPayload.hits && fallbackPayload.hits.length) ? fallbackPayload : (payload || { lat: event.latlng.lat, lng: event.latlng.lng, hits: [] })));
              }).catch(function () {
                if (token !== state._identifyToken) return;
                loadingPopup.setContent(identifyPopupHtml(payload || { lat: event.latlng.lat, lng: event.latlng.lng, hits: [] }));
              });
            })
            .catch(function () {
              if (token !== state._identifyToken) return;
              if (!mapServerUrl || !activeRows.length) {
                loadingPopup.setContent('<div class="map-popup"><div class="map-popup-title">Kunne ikke hente områdedata</div><div class="small muted">Prøv igjen om et øyeblikk.</div></div>');
                return;
              }
              browserIdentifyFallback(mapServerUrl, activeRows, event.latlng.lat.toFixed(6), event.latlng.lng.toFixed(6)).then(function (fallbackPayload) {
                if (token !== state._identifyToken) return;
                loadingPopup.setContent(identifyPopupHtml(fallbackPayload || { lat: event.latlng.lat, lng: event.latlng.lng, hits: [] }));
              }).catch(function () {
                if (token !== state._identifyToken) return;
                loadingPopup.setContent('<div class="map-popup"><div class="map-popup-title">Kunne ikke hente områdedata</div><div class="small muted">Prøv igjen om et øyeblikk.</div></div>');
              });
            });
        });
        state.clickBound = true;
      }

      if (ms.recenterTo === 'device' && hasDevice) map.setView([ms.deviceLat, ms.deviceLng], ms.recenterZoom || Math.max(map.getZoom(), 15));
      else if (ms.recenterTo === 'case' && hasCase) map.setView([ms.lat, ms.lng], ms.recenterZoom || Math.max(map.getZoom(), 14));

      setTimeout(function () {
        try { map.invalidateSize(); } catch (e) {}
      }, 120);
      return { map: map, marker: state.caseMarker || null, circle: state.caseRadius || null, deviceMarker: state.deviceMarker || null, accuracyCircle: state.deviceAccuracy || null, rasterOverlay: state.rasterOverlay || null };
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

  function setupHistoryControls() {
    var backButton = document.getElementById('history-back-btn');
    var forwardButton = document.getElementById('history-forward-btn');
    if (backButton) {
      backButton.addEventListener('click', function () {
        var fallbackUrl = backButton.getAttribute('data-home-url') || '/dashboard';
        try {
          if (window.history.length > 1) {
            window.history.back();
            return;
          }
        } catch (e) {}
        window.location.href = fallbackUrl;
      });
    }
    if (forwardButton) {
      forwardButton.addEventListener('click', function () {
        try {
          window.history.forward();
        } catch (e) {}
      });
    }
  }


  function setupLogoutClearLocal() {
    var btn = document.getElementById('logout-clear-local-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var form = document.getElementById('logout-form') || btn.closest('form');
      var owner = '';
      try { owner = String((window.MKCurrentUser && window.MKCurrentUser.id) || ''); } catch (e) { owner = ''; }
      btn.disabled = true;
      btn.textContent = 'Sletter lokalt...';
      var jobs = [];
      try {
        if (window.KVLocalCases && typeof window.KVLocalCases.clearOwner === 'function') {
          jobs.push(window.KVLocalCases.clearOwner(owner));
        }
      } catch (e) {}
      try {
        if (window.KVLocalMedia && typeof window.KVLocalMedia.clearOwner === 'function') {
          jobs.push(window.KVLocalMedia.clearOwner(owner));
        }
      } catch (e) {}
      Promise.all(jobs).catch(function () {}).then(function () {
        try {
          localStorage.removeItem('kv-case-draft-dismissed');
        } catch (e) {}
        if (form) form.submit();
        else window.location.href = '/logout';
      });
    });
  }

  ready(setupSecurityInteractions);
  ready(setupSidebarToggle);
  ready(setupHistoryControls);
  ready(setupLogoutClearLocal);

  window.csrfHeaders = csrfHeaders;
  window.secureFetchOptions = secureFetchOptions;
  window.KVCommon = { ready: ready, escapeHtml: escapeHtml, parseJson: parseJson, csrfToken: csrfToken, injectCsrfField: injectCsrfField, appendCsrfToForms: appendCsrfToForms, csrfHeaders: csrfHeaders, secureFetchOptions: secureFetchOptions, sourceChip: sourceChip, findingSource: findingSource, lawHelpCard: lawHelpCard, buildReadonlyFindingsHtml: buildReadonlyFindingsHtml, normalizeFeatureCollection: normalizeFeatureCollection, createPortalMap: createPortalMap };
})();
