(function () {
  var Common = window.KVCommon || {};
  var ready = Common.ready || function (fn) { if (document.readyState !== 'loading') fn(); else document.addEventListener('DOMContentLoaded', fn); };
  var escapeHtml = Common.escapeHtml || function (value) { return String(value || ''); };
  var parseJson = Common.parseJson || function (value, fallback) { try { return JSON.parse(value || ''); } catch (e) { return fallback; } };
  var createPortalMap = Common.createPortalMap;

  function zoneResultHtml(result) {
    if (!result || !result.match || String(result.status || '').toLowerCase() === 'ingen treff') {
      return '<strong>ingen treff</strong><div class="small muted">Ingen treff i kartlagene for fredningsområder, stengte områder eller tilsvarende regulerte områder.</div>' + (result && (result.location_name || result.nearest_place) ? '<div class="small muted">Nærmeste sted: ' + escapeHtml(result.location_name || result.nearest_place) + '</div>' : '');
    }
    var parts = ['<strong>' + escapeHtml(result.status || '') + '</strong>'];
    if (result.name) parts.push('<div>' + escapeHtml(result.name) + '</div>');
    if (result.location_name || result.nearest_place) parts.push('<div class="small muted">Nærmeste sted: ' + escapeHtml(result.location_name || result.nearest_place) + (result.distance_to_place_km ? ' (' + escapeHtml(result.distance_to_place_km + ' km') + ')' : '') + '</div>');
    if (result.notes) parts.push('<div class="small muted">' + escapeHtml(result.notes) + '</div>');
    if (result.recommended_violation && result.recommended_violation.message) {
      parts.push('<div class="callout area-warning"><strong>Områdevarsel</strong><div>' + escapeHtml(result.recommended_violation.message) + '</div></div>');
    }
    return parts.join('');
  }

  function initMapOverview() {
    var el = document.getElementById('overview-map');
    if (!el || !createPortalMap) return;
    var allLayers = parseJson(el.dataset.portalCatalog, []);
    var statusEl = document.getElementById('overview-map-status');
    var btnLocate = document.getElementById('btn-overview-location');
    var btnNational = document.getElementById('btn-overview-national');
    var btnDownloadOffline = document.getElementById('btn-overview-download-offline');
    var btnRefreshPackages = document.getElementById('btn-overview-refresh-packages');
    var packagesSummary = document.getElementById('overview-offline-packages-summary');
    var packagesList = document.getElementById('overview-offline-packages-list');
    var relevantAreasList = document.getElementById('overview-relevant-areas-list');
    var filterWrap = document.getElementById('overview-layer-filters');
    var storageKey = 'kv-overview-layer-filter-v1-1';
    var defaultView = { lat: 64.8, lng: 14.5, zoom: 4 };
    var activeLayerStatuses = { 'fredningsområde': true, 'stengt område': true, 'maksimalmål område': true, 'regulert område': true, 'fiskeriområde': true };
    var fisheryPortalService = el.dataset.portalMapserver || 'https://portal.fiskeridir.no/server/rest/services/fiskeridirWMS_fiskeri/MapServer';
    var vernPortalService = el.dataset.portalVernMapserver || 'https://portal.fiskeridir.no/server/rest/services/Fiskeridir_vern/MapServer';
    var state = {
      view: defaultView,
      persistView: false,
      fetchFeatureDetails: false,
      rasterOpacity: 0.9,
      enableAreaPopup: true,
      showLegend: false,
      showLayerPanel: false,
      mapServerUrl: fisheryPortalService,
      portalFisheryService: fisheryPortalService,
      portalVernService: vernPortalService,
      rasterServicesAuto: true,
      rasterChunkSize: 18,
      rasterLayerIds: (allLayers || []).map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); }),
      rasterServices: null,
      identifyLayerIds: (allLayers || []).map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); }),
      lat: null,
      lng: null,
      deviceLat: null,
      deviceLng: null,
      deviceAccuracy: null,
      recenterTo: '',
      latestZoneResult: null,
      onFeaturesRendered: function () { renderRelevantAreas(state.latestZoneResult || null); }
    };

    function currentMapBbox() {
      if (!el._kvLeafletMap || typeof el._kvLeafletMap.getBounds !== 'function') return null;
      var bounds = el._kvLeafletMap.getBounds();
      return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()];
    }

    function collectTileUrls(layer, map, padding) {
      if (!layer || !map || typeof layer.getTileUrl !== 'function' || typeof map.getZoom !== 'function') return [];
      var pixelBounds = typeof map.getPixelBounds === 'function' ? map.getPixelBounds() : null;
      if (!pixelBounds || typeof layer._pxBoundsToTileRange !== 'function') return [];
      var range = layer._pxBoundsToTileRange(pixelBounds);
      if (!range || !range.min || !range.max) return [];
      padding = Math.max(0, Number(padding || 0));
      var urls = [];
      var zoom = map.getZoom();
      for (var x = range.min.x - padding; x <= range.max.x + padding; x += 1) {
        for (var y = range.min.y - padding; y <= range.max.y + padding; y += 1) {
          try {
            var url = layer.getTileUrl({ x: x, y: y, z: zoom });
            if (url) urls.push(url);
          } catch (e) {}
        }
      }
      return urls;
    }

    function uniqueUrls(urls) {
      var seen = {};
      return (urls || []).filter(function (url) {
        var key = String(url || '');
        if (!key || seen[key]) return false;
        seen[key] = true;
        return true;
      });
    }

    function prefetchUrlsToCache(urls, cacheName) {
      if (!('caches' in window) || !Array.isArray(urls) || !urls.length) return Promise.resolve(0);
      return caches.open(cacheName).then(function (cache) {
        var index = 0;
        var stored = 0;
        var concurrency = 4;
        return new Promise(function (resolve) {
          function next() {
            if (index >= urls.length && concurrency <= 0) {
              resolve(stored);
              return;
            }
            while (concurrency > 0 && index < urls.length) {
              var url = urls[index++];
              concurrency -= 1;
              fetch(url, { mode: 'no-cors', credentials: 'omit' })
                .then(function (response) {
                  if (response && (response.ok || response.type === 'opaque')) {
                    stored += 1;
                    return cache.put(url, response.clone()).catch(function () {});
                  }
                })
                .catch(function () {})
                .finally(function () {
                  concurrency += 1;
                  next();
                });
            }
          }
          next();
        });
      }).catch(function () { return 0; });
    }

    function prefetchVisibleMapTiles() {
      if (!el._kvLeafletMap) return Promise.resolve({ count: 0, urls: [] });
      var map = el._kvLeafletMap;
      var urls = [];
      map.eachLayer(function (layer) {
        if (typeof layer.getTileUrl !== 'function') return;
        urls = urls.concat(collectTileUrls(layer, map, 2));
      });
      urls = uniqueUrls(urls);
      return prefetchUrlsToCache(urls, 'kv-kontroll-v1-1-map-tiles').then(function (count) {
        return { count: count, urls: urls };
      });
    }

    function deleteUrlsFromTileCaches(urls) {
      if (!('caches' in window) || !Array.isArray(urls) || !urls.length) return Promise.resolve(0);
      return caches.keys().then(function (keys) {
        var targetKeys = keys.filter(function (key) { return String(key || '').indexOf('map-tiles') !== -1; });
        return Promise.all(targetKeys.map(function (key) {
          return caches.open(key).then(function (cache) {
            return Promise.all(urls.map(function (url) { return cache.delete(url).catch(function () { return false; }); }));
          });
        })).then(function (results) {
          var removed = 0;
          (results || []).forEach(function (row) { (row || []).forEach(function (value) { if (value) removed += 1; }); });
          return removed;
        });
      }).catch(function () { return 0; });
    }

    function filteredLayers() {
      var rows = (allLayers || []).filter(function (layer) {
        var status = String(layer && layer.status || '').trim().toLowerCase();
        return !Object.prototype.hasOwnProperty.call(activeLayerStatuses, status) || activeLayerStatuses[status] !== false;
      });
      return rows.slice().sort(function (a, b) {
        return String(a && a.name || '').localeCompare(String(b && b.name || ''), 'nb');
      });
    }

    function toneClass(status) {
      var key = String(status || '').trim().toLowerCase();
      if (key === 'stengt område' || key === 'nullfiskeområde') return 'stengt';
      if (key === 'fredningsområde') return 'fredning';
      if (key === 'maksimalmål område') return 'maksimal';
      if (key === 'regulert område') return 'regulert';
      if (key === 'fiskeriområde') return 'fiskeri';
      return 'annet';
    }

    function renderRelevantAreas(result) {
      if (!relevantAreasList) return;
      var items = [];
      var seen = {};
      var hits = result && result.match && Array.isArray(result.hits) ? result.hits.slice(0, 4) : [];
      hits.forEach(function (hit) {
        var key = 'zone:' + String(hit.zone_id || hit.name || hit.layer || '');
        if (!key || seen[key]) return;
        seen[key] = true;
        items.push({
          title: hit.name || hit.layer || hit.status || 'Område',
          status: hit.status || 'regulert område',
          summary: hit.notes || 'Treff for valgt punkt i kartet.',
          meta: [hit.source || '', hit.layer || ''].filter(Boolean)
        });
      });
      filteredLayers().slice(0, 8).forEach(function (layer) {
        var key = 'layer:' + String(layer && (layer.id || layer.name) || '');
        if (!key || seen[key]) return;
        seen[key] = true;
        var meta = [];
        if (Array.isArray(layer.control_tags) && layer.control_tags.length) meta.push('Kontroll: ' + layer.control_tags.join(', '));
        if (Array.isArray(layer.fishery_tags) && layer.fishery_tags.length) meta.push('Fiskeri: ' + layer.fishery_tags.join(', '));
        if (Array.isArray(layer.gear_tags) && layer.gear_tags.length) meta.push('Redskap: ' + layer.gear_tags.join(', '));
        items.push({
          title: layer.name || ('Lag ' + String(layer.id || '')),
          status: layer.status || 'annet lag',
          summary: layer.selection_summary || layer.description || 'Synlig temalag i oversiktskartet.',
          meta: meta
        });
      });
      if (!items.length) {
        relevantAreasList.innerHTML = '<div class="muted small">Ingen temalag er valgt akkurat nå. Slå på flere filtre over kartet.</div>';
        return;
      }
      relevantAreasList.innerHTML = items.map(function (item) {
        return [
          '<article class="map-relevant-item">',
          '<div class="map-relevant-meta"><span class="map-tone ' + escapeHtml(toneClass(item.status)) + '">' + escapeHtml(item.status || 'Temalag') + '</span></div>',
          '<strong>' + escapeHtml(item.title || 'Område') + '</strong>',
          item.summary ? '<div class="muted small">' + escapeHtml(item.summary) + '</div>' : '',
          item.meta && item.meta.length ? '<div class="map-quick-tags">' + item.meta.map(function (meta) { return '<span class="map-quick-tag">' + escapeHtml(meta) + '</span>'; }).join('') + '</div>' : '',
          '</article>'
        ].join('');
      }).join('');
    }

    function syncFilterUi() {
      if (!filterWrap) return;
      filterWrap.style.display = '';
      Array.prototype.forEach.call(filterWrap.querySelectorAll('input[data-layer-filter]'), function (input) {
        var key = String(input.getAttribute('data-layer-filter') || '').trim().toLowerCase();
        input.checked = activeLayerStatuses[key] !== false;
      });
    }

    function redrawMap() {
      return createPortalMap(el, filteredLayers(), state).then(function () {
        if (state.recenterTo) state.recenterTo = '';
        renderRelevantAreas(state.latestZoneResult || null);
      });
    }

    function setNationalView() {
      state.deviceLat = null;
      state.deviceLng = null;
      state.deviceAccuracy = null;
      state.view = defaultView;
      state.recenterTo = '';
      var map = el._kvLeafletMap;
      if (map && typeof map.setView === 'function') {
        map.setView([defaultView.lat, defaultView.lng], defaultView.zoom);
      }
      state.latestZoneResult = null;
      redrawMap();
      renderRelevantAreas(null);
      if (statusEl) statusEl.innerHTML = 'Kartet viser nasjonalt utvalg av temalag direkte i kartet. Lagpanelet i selve kartet er skjult på mobil, så bruk filtrene over kartet og listen under for å se aktuelle områder.';
    }

    function applyPosition(position) {
      var lat = Number(position.coords.latitude.toFixed(6));
      var lng = Number(position.coords.longitude.toFixed(6));
      state.deviceLat = lat;
      state.deviceLng = lng;
      state.deviceAccuracy = Number(position.coords.accuracy || 12);
      state.recenterTo = 'device';
      redrawMap();
      fetch('/api/zones/check?lat=' + encodeURIComponent(lat) + '&lng=' + encodeURIComponent(lng))
        .then(function (r) { return r.json(); })
        .then(function (result) {
          state.latestZoneResult = result || null;
          statusEl.innerHTML = zoneResultHtml(result);
          renderRelevantAreas(result || null);
        })
        .catch(function (err) {
          state.latestZoneResult = null;
          statusEl.innerHTML = 'Kunne ikke sjekke områdestatus akkurat nå: ' + escapeHtml(err && err.message ? err.message : 'ukjent feil');
          renderRelevantAreas(null);
        });
    }

    function locateUser() {
      if (!navigator.geolocation) {
        statusEl.innerHTML = 'Denne enheten støtter ikke geolokasjon i nettleseren.';
        return;
      }
      statusEl.innerHTML = 'Henter posisjon ...';
      navigator.geolocation.getCurrentPosition(applyPosition, function (err) {
        statusEl.innerHTML = 'Kunne ikke hente posisjon: ' + escapeHtml(err.message || err);
      }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
    }

    function packageStatus(row) {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.summarizePackage === 'function')) return { stale: false, expired: false };
      return window.KVLocalMap.summarizePackage(row);
    }

    function formatTimestamp(ts) {
      var value = Number(ts || 0);
      if (!value) return 'ukjent';
      try {
        return new Date(value).toLocaleString('nb-NO', { dateStyle: 'short', timeStyle: 'short' });
      } catch (e) {
        return new Date(value).toISOString();
      }
    }

    function formatBBoxSummary(bbox) {
      if (!Array.isArray(bbox) || bbox.length !== 4) return '';
      var west = Number(bbox[0]);
      var south = Number(bbox[1]);
      var east = Number(bbox[2]);
      var north = Number(bbox[3]);
      if (!isFinite(west) || !isFinite(south) || !isFinite(east) || !isFinite(north)) return '';
      var centerLat = ((south + north) / 2).toFixed(3);
      var centerLng = ((west + east) / 2).toFixed(3);
      return centerLat + ', ' + centerLng;
    }

    function renderOfflinePackages(rows) {
      if (!packagesList) return;
      var items = Array.isArray(rows) ? rows.slice() : [];
      if (!items.length) {
        packagesList.innerHTML = '<div class="offline-package-empty">Ingen offline-kartpakker er lagret på denne enheten ennå.</div>';
        if (packagesSummary) packagesSummary.textContent = 'Ingen offline-kartpakker er lagret på denne enheten ennå.';
        return;
      }
      var totalFeatures = 0;
      var totalTiles = 0;
      packagesList.innerHTML = items.map(function (row) {
        var stateInfo = packageStatus(row);
        var featureCount = Number(row && row.feature_count || 0);
        var tileCount = Number(row && row.tile_count || 0);
        totalFeatures += isFinite(featureCount) ? featureCount : 0;
        totalTiles += isFinite(tileCount) ? tileCount : 0;
        var badgeClass = stateInfo.expired ? 'expired' : (stateInfo.stale ? 'stale' : '');
        var badgeText = stateInfo.expired ? 'Utløpt' : (stateInfo.stale ? 'Bør oppdateres' : 'Oppdatert');
        return '<div class="offline-package-card ' + badgeClass + '" data-package-id="' + escapeHtml(row.id || '') + '">' +
          '<div class="split-row"><strong>' + escapeHtml(row.label || ('Kartpakke ' + formatBBoxSummary(row.requested_bbox))) + '</strong><span class="offline-package-badge ' + badgeClass + '">' + escapeHtml(badgeText) + '</span></div>' +
          '<div class="offline-package-meta">' +
            '<span>Område: ' + escapeHtml(formatBBoxSummary(row.requested_bbox)) + '</span>' +
            '<span>Lag: ' + escapeHtml(String((row.layer_ids || []).length)) + '</span>' +
            '<span>Objekter: ' + escapeHtml(String(featureCount || 0)) + '</span>' +
            '<span>Kartbilder: ' + escapeHtml(String(tileCount || 0)) + '</span>' +
            '<span>Sist oppdatert: ' + escapeHtml(formatTimestamp(row.updated_at)) + '</span>' +
          '</div>' +
          '<div class="offline-package-actions">' +
            '<button type="button" class="btn btn-secondary btn-small" data-offline-package-action="open">Vis område</button>' +
            '<button type="button" class="btn btn-secondary btn-small" data-offline-package-action="refresh">Oppdater</button>' +
            '<button type="button" class="btn btn-secondary btn-small" data-offline-package-action="delete">Slett</button>' +
          '</div>' +
        '</div>';
      }).join('');
      if (packagesSummary) packagesSummary.textContent = items.length + ' offline-kartpakker er lagret på enheten. ' + totalFeatures + ' kartobjekter og ' + totalTiles + ' kartbilder er tilgjengelige lokalt.';
    }

    function refreshOfflinePackageList() {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.listPackages === 'function')) {
        renderOfflinePackages([]);
        return Promise.resolve([]);
      }
      return window.KVLocalMap.listPackages().then(function (rows) {
        renderOfflinePackages(rows || []);
        return rows || [];
      }).catch(function () {
        renderOfflinePackages([]);
        return [];
      });
    }

    function maintainOfflinePackages(backgroundOnly) {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.cleanupPackages === 'function')) return Promise.resolve();
      return window.KVLocalMap.cleanupPackages({ maxPackages: 8, purgeAfterMs: 30 * 24 * 60 * 60 * 1000 }).then(function (result) {
        var removedRows = result && Array.isArray(result.removed) ? result.removed : [];
        return Promise.all(removedRows.map(function (row) { return deleteUrlsFromTileCaches(row && row.tile_urls || []); })).then(function () {
          if (!backgroundOnly && statusEl && removedRows.length) {
            statusEl.innerHTML = 'Gamle offline-kartpakker ble ryddet bort automatisk (' + escapeHtml(removedRows.length) + ' fjernet).';
          }
          return refreshOfflinePackageList();
        });
      }).catch(function () { return refreshOfflinePackageList(); });
    }

    function focusOfflinePackage(row) {
      if (!row || !Array.isArray(row.bbox) || row.bbox.length !== 4 || !el._kvLeafletMap) return;
      el._kvLeafletMap.fitBounds([[row.bbox[1], row.bbox[0]], [row.bbox[3], row.bbox[2]]], { padding: [18, 18] });
      if (window.KVLocalMap && typeof window.KVLocalMap.touchPackage === 'function') window.KVLocalMap.touchPackage(row.id).catch(function () {});
      if (statusEl) statusEl.innerHTML = 'Viser offline-kartpakke: <strong>' + escapeHtml(row.label || formatBBoxSummary(row.requested_bbox)) + '</strong>.';
      refreshOfflinePackageList();
    }

    function deleteOfflinePackage(packageId) {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.deletePackage === 'function')) return Promise.resolve();
      return window.KVLocalMap.deletePackage(packageId).then(function (row) {
        if (!row) return null;
        return deleteUrlsFromTileCaches(row.tile_urls || []).then(function () { return row; });
      }).then(function () {
        return maintainOfflinePackages(true);
      });
    }

    function downloadCurrentMapToDevice(options) {
      options = options || {};
      var bbox = Array.isArray(options.requestBBox) ? options.requestBBox : currentMapBbox();
      var layerIds = Array.isArray(options.layerIds) && options.layerIds.length ? options.layerIds : (allLayers || []).map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); });
      if (!bbox || !layerIds.length) {
        if (statusEl && !options.silent) statusEl.innerHTML = 'Zoom inn til et område og prøv igjen for å lagre offline-kart.';
        return Promise.resolve();
      }
      if (statusEl && !options.silent) statusEl.innerHTML = options.packageId ? 'Oppdaterer offline-kartpakke ...' : 'Lagrer offline-kartpakke på enheten ...';
      var expandFactor = Number(options.expandFactor || 1.8);
      var url = '/api/map/offline-package?bbox=' + encodeURIComponent(bbox.join(',')) + '&layer_ids=' + encodeURIComponent(layerIds.join(',')) + '&expand=' + encodeURIComponent(String(expandFactor));
      return fetch(url, { credentials: 'same-origin' })
        .then(function (response) { return response.json(); })
        .then(function (payload) {
          var tilePromise = options.packageRow ? Promise.resolve({ count: Number(options.packageRow.tile_count || 0), urls: Array.isArray(options.packageRow.tile_urls) ? options.packageRow.tile_urls : [] }) : prefetchVisibleMapTiles();
          return tilePromise.then(function (tileInfo) {
            if (window.KVLocalMap && typeof window.KVLocalMap.saveOfflinePackage === 'function') {
              return window.KVLocalMap.saveOfflinePackage(layerIds, bbox, payload, {
                packageId: options.packageId,
                label: options.label || '',
                tile_urls: tileInfo.urls,
                tile_count: tileInfo.count,
                expandFactor: expandFactor,
                createdAt: options.packageRow && options.packageRow.created_at ? options.packageRow.created_at : undefined
              }).then(function (row) {
                return { row: row, bundle: payload && payload.bundle ? payload.bundle : { type: 'FeatureCollection', features: [] }, tileInfo: tileInfo };
              });
            }
            return { row: null, bundle: payload && payload.bundle ? payload.bundle : { type: 'FeatureCollection', features: [] }, tileInfo: tileInfo };
          });
        })
        .then(function (result) {
          var featureCount = Array.isArray(result && result.bundle && result.bundle.features) ? result.bundle.features.length : 0;
          if (statusEl && !options.silent) statusEl.innerHTML = (options.packageId ? 'Offline-kartpakke oppdatert.' : 'Offline-kart lagret på enheten.') + ' ' + escapeHtml(featureCount) + ' kartobjekter og ' + escapeHtml(result && result.tileInfo ? result.tileInfo.count : 0) + ' kartbilder er tilgjengelige lokalt.';
          return maintainOfflinePackages(true);
        });
    }

    function refreshOfflinePackage(packageId, silent) {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.getPackage === 'function')) return Promise.resolve();
      return window.KVLocalMap.getPackage(packageId).then(function (row) {
        if (!row) return null;
        return downloadCurrentMapToDevice({
          packageId: row.id,
          packageRow: row,
          requestBBox: row.requested_bbox || row.bbox,
          layerIds: row.layer_ids || [],
          label: row.label || '',
          expandFactor: row.expand_factor || 1.8,
          silent: silent === true
        });
      });
    }

    function autoRefreshStalePackages() {
      if (!navigator.onLine || !(window.KVLocalMap && typeof window.KVLocalMap.listPackages === 'function')) return Promise.resolve();
      return window.KVLocalMap.listPackages().then(function (rows) {
        var staleRows = (rows || []).filter(function (row) {
          var info = packageStatus(row);
          return info && info.stale && !info.expired;
        }).slice(0, 2);
        if (!staleRows.length) return rows || [];
        return staleRows.reduce(function (promise, row) {
          return promise.then(function () { return refreshOfflinePackage(row.id, true); });
        }, Promise.resolve()).then(function () { return refreshOfflinePackageList(); });
      }).catch(function () { return []; });
    }

    if (filterWrap) {
      syncFilterUi();
      Array.prototype.forEach.call(filterWrap.querySelectorAll('input[data-layer-filter]'), function (input) {
        input.addEventListener('change', function () {
          var key = String(input.getAttribute('data-layer-filter') || '').trim().toLowerCase();
          activeLayerStatuses[key] = !!input.checked;
          try { localStorage.setItem(storageKey, JSON.stringify(activeLayerStatuses)); } catch (e) {}
          renderRelevantAreas(state.latestZoneResult || null);
          redrawMap();
        });
      });
    }

    if (btnLocate) btnLocate.addEventListener('click', locateUser);
    if (btnNational) btnNational.addEventListener('click', function () { setNationalView(); });
    if (btnDownloadOffline) btnDownloadOffline.addEventListener('click', function () { downloadCurrentMapToDevice(); });
    if (btnRefreshPackages) btnRefreshPackages.addEventListener('click', function () {
      if (statusEl) statusEl.innerHTML = 'Oppdaterer lagrede offline-kartpakker ...';
      maintainOfflinePackages(true).then(function () { return autoRefreshStalePackages(); }).then(function () {
        if (statusEl) statusEl.innerHTML = 'Lagrede offline-kartpakker er kontrollert og oppdatert der det var behov.';
      });
    });
    if (packagesList) packagesList.addEventListener('click', function (event) {
      var button = event.target.closest('[data-offline-package-action]');
      if (!button || !(window.KVLocalMap && typeof window.KVLocalMap.getPackage === 'function')) return;
      var card = button.closest('[data-package-id]');
      var packageId = card ? String(card.getAttribute('data-package-id') || '') : '';
      if (!packageId) return;
      var action = String(button.getAttribute('data-offline-package-action') || '');
      if (action === 'delete') {
        deleteOfflinePackage(packageId);
        return;
      }
      if (action === 'refresh') {
        refreshOfflinePackage(packageId);
        return;
      }
      window.KVLocalMap.getPackage(packageId).then(function (row) { focusOfflinePackage(row); });
    });

    if (statusEl) statusEl.innerHTML = 'Kartet viser nasjonalt utvalg av temalag direkte i kartet. Lagpanelet i selve kartet er skjult på mobil, så bruk filtrene over kartet og listen under for å se aktuelle områder.';
    renderRelevantAreas(null);
    redrawMap();
    setTimeout(setNationalView, 50);
    maintainOfflinePackages(true).then(function () { return refreshOfflinePackageList(); }).then(function () { return autoRefreshStalePackages(); });
    window.addEventListener('online', function () { autoRefreshStalePackages(); });
  }

  ready(initMapOverview);
})();
