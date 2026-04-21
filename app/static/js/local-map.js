(function () {
  var DB_NAME = 'kv-kontroll-local-map';
  var DB_VERSION = 3;
  var STORE = 'map_cache';
  var DEFAULT_MAX_PACKAGES = 8;
  var DEFAULT_STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000;
  var DEFAULT_PURGE_AFTER_MS = 30 * 24 * 60 * 60 * 1000;

  function supported() {
    return typeof indexedDB !== 'undefined';
  }

  function normalizeLayerIds(layerIds) {
    var seen = {};
    return (layerIds || []).map(function (value) { return Number(value); }).filter(function (value) {
      if (!isFinite(value)) return false;
      if (seen[value]) return false;
      seen[value] = true;
      return true;
    }).sort(function (a, b) { return a - b; });
  }

  function layerKey(layerIds) {
    return normalizeLayerIds(layerIds).join(',');
  }

  function normalizeBBox(bbox) {
    if (!Array.isArray(bbox) || bbox.length !== 4) return null;
    var values = bbox.map(function (value) { return Number(value); });
    if (values.some(function (value) { return !isFinite(value); })) return null;
    return values;
  }

  function bboxKey(bbox) {
    var normalized = normalizeBBox(bbox);
    if (!normalized) return '';
    return normalized.map(function (value) { return Number(value).toFixed(4); }).join(',');
  }

  function bboxArea(bbox) {
    bbox = normalizeBBox(bbox);
    if (!bbox) return 0;
    return Math.max(0, bbox[2] - bbox[0]) * Math.max(0, bbox[3] - bbox[1]);
  }

  function bboxContains(container, inner) {
    container = normalizeBBox(container);
    inner = normalizeBBox(inner);
    if (!container || !inner) return false;
    return container[0] <= inner[0] && container[1] <= inner[1] && container[2] >= inner[2] && container[3] >= inner[3];
  }

  function bboxOverlap(container, inner) {
    container = normalizeBBox(container);
    inner = normalizeBBox(inner);
    if (!container || !inner) return 0;
    var left = Math.max(container[0], inner[0]);
    var bottom = Math.max(container[1], inner[1]);
    var right = Math.min(container[2], inner[2]);
    var top = Math.min(container[3], inner[3]);
    if (right <= left || top <= bottom) return 0;
    var overlap = (right - left) * (top - bottom);
    var innerArea = bboxArea(inner);
    if (!innerArea) return 0;
    return overlap / innerArea;
  }

  function uniqueStrings(values) {
    var seen = {};
    return (values || []).map(function (value) { return String(value || '').trim(); }).filter(function (value) {
      if (!value) return false;
      if (seen[value]) return false;
      seen[value] = true;
      return true;
    });
  }

  function packageIdFor(layerIds, bbox) {
    return 'package:' + (layerKey(layerIds) || 'all') + ':' + (bboxKey(bbox) || '0,0,0,0');
  }

  function bundleIdFor(packageId) {
    return 'bundle:offline:' + String(packageId || '');
  }

  function buildPackageLabel(requestBBox, offlineBBox, layerIds) {
    var bbox = normalizeBBox(requestBBox) || normalizeBBox(offlineBBox) || [0, 0, 0, 0];
    var centerLat = ((bbox[1] + bbox[3]) / 2).toFixed(3);
    var centerLng = ((bbox[0] + bbox[2]) / 2).toFixed(3);
    var layerCount = normalizeLayerIds(layerIds).length;
    return 'Kartpakke ' + centerLat + ', ' + centerLng + (layerCount ? ' · ' + layerCount + ' lag' : '');
  }

  function openDb() {
    if (!supported()) return Promise.reject(new Error('IndexedDB er ikke tilgjengelig.'));
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onerror = function () { reject(request.error || new Error('Kunne ikke åpne lokalt kartlager.')); };
      request.onupgradeneeded = function () {
        var db = request.result;
        var store;
        if (db.objectStoreNames.contains(STORE)) {
          store = request.transaction.objectStore(STORE);
        } else {
          store = db.createObjectStore(STORE, { keyPath: 'id' });
        }
        if (!store.indexNames.contains('kind')) store.createIndex('kind', 'kind', { unique: false });
        if (!store.indexNames.contains('updated_at')) store.createIndex('updated_at', 'updated_at', { unique: false });
        if (!store.indexNames.contains('layer_key')) store.createIndex('layer_key', 'layer_key', { unique: false });
        if (!store.indexNames.contains('last_used_at')) store.createIndex('last_used_at', 'last_used_at', { unique: false });
      };
      request.onsuccess = function () { resolve(request.result); };
    });
  }

  function withStore(mode, runner) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, mode);
        var store = tx.objectStore(STORE);
        var done = false;
        function finishError(err) {
          if (done) return;
          done = true;
          reject(err);
          try { db.close(); } catch (e) {}
        }
        tx.onerror = function () { finishError(tx.error || new Error('Kartcache-transaksjon feilet.')); };
        tx.onabort = function () { finishError(tx.error || new Error('Kartcache-transaksjon ble avbrutt.')); };
        try {
          runner(store, tx, function (value) {
            if (done) return;
            done = true;
            resolve(value);
            try { db.close(); } catch (e) {}
          }, finishError);
        } catch (err) {
          try { tx.abort(); } catch (e) {}
          finishError(err);
        }
      });
    });
  }

  function requestToPromise(request) {
    return new Promise(function (resolve, reject) {
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error || new Error('Kartcache-forespørsel feilet.')); };
    });
  }

  function listByKind(kind) {
    return withStore('readonly', function (store, tx, resolve, reject) {
      var index;
      try {
        index = store.index('kind');
      } catch (e) {
        resolve([]);
        return;
      }
      if (typeof index.getAll === 'function' && typeof IDBKeyRange !== 'undefined' && IDBKeyRange.only) {
        requestToPromise(index.getAll(IDBKeyRange.only(String(kind || 'generic')))).then(resolve).catch(reject);
        return;
      }
      var rows = [];
      var request = index.openCursor();
      request.onerror = function () { reject(request.error || new Error('Kunne ikke lese kartcache.')); };
      request.onsuccess = function () {
        var cursor = request.result;
        if (!cursor) {
          resolve(rows.filter(function (row) { return String(row && row.kind || '') === String(kind || 'generic'); }));
          return;
        }
        rows.push(cursor.value);
        cursor.continue();
      };
    });
  }

  function listAllRows() {
    return withStore('readonly', function (store, tx, resolve, reject) {
      if (typeof store.getAll === 'function') {
        requestToPromise(store.getAll()).then(resolve).catch(reject);
        return;
      }
      var rows = [];
      var request = store.openCursor();
      request.onerror = function () { reject(request.error || new Error('Kunne ikke lese kartcache.')); };
      request.onsuccess = function () {
        var cursor = request.result;
        if (!cursor) {
          resolve(rows);
          return;
        }
        rows.push(cursor.value);
        cursor.continue();
      };
    });
  }

  function putRow(row) {
    return withStore('readwrite', function (store, tx, resolve, reject) {
      var request = store.put(row);
      request.onsuccess = function () { resolve(row); };
      request.onerror = function () { reject(request.error || new Error('Kunne ikke lagre kartcache.')); };
    });
  }

  function getRow(id) {
    return withStore('readonly', function (store, tx, resolve, reject) {
      requestToPromise(store.get(String(id))).then(resolve).catch(reject);
    });
  }

  function deleteRow(id) {
    return withStore('readwrite', function (store, tx, resolve, reject) {
      var request = store.delete(String(id));
      request.onsuccess = function () { resolve(true); };
      request.onerror = function () { reject(request.error || new Error('Kunne ikke slette kartcache-rad.')); };
    });
  }

  function makeBundleKey(layerIds, bbox) {
    return 'bundle:' + layerKey(layerIds) + ':' + bboxKey(bbox);
  }

  function cacheBundle(layerIds, bbox, payload, options) {
    options = options || {};
    var ids = normalizeLayerIds(layerIds);
    var normalizedBBox = normalizeBBox(bbox) || (payload && normalizeBBox(payload.bbox)) || null;
    var row = {
      id: String(options.id || makeBundleKey(ids, normalizedBBox || [0, 0, 0, 0])),
      kind: 'bundle',
      layer_key: layerKey(ids),
      layer_ids: ids,
      bbox: normalizedBBox,
      updated_at: Date.now(),
      last_used_at: Number(options.last_used_at || Date.now()),
      payload: payload,
      source: String(options.source || 'live'),
      offline: options.offline === true,
      package_id: options.package_id ? String(options.package_id) : ''
    };
    return putRow(row).then(function () { return payload; });
  }

  function readBundle(layerIds, bbox) {
    return getRow(makeBundleKey(layerIds, bbox)).then(function (row) {
      if (!row) return null;
      if (row.package_id) touchPackage(row.package_id).catch(function () {});
      return row.payload;
    });
  }

  function chooseBestBundle(rows, layerIds, bbox) {
    var wantedKey = layerKey(layerIds);
    var targetBBox = normalizeBBox(bbox);
    var best = null;
    (rows || []).forEach(function (row) {
      if (!row || String(row.kind || '') !== 'bundle') return;
      if (wantedKey && String(row.layer_key || '') !== wantedKey) return;
      if (!row.payload || !row.payload.features || !row.payload.features.length) return;
      var score = 0;
      if (targetBBox && row.bbox) {
        if (bboxContains(row.bbox, targetBBox)) {
          score = 1000 - Math.min(999, bboxArea(row.bbox) * 10);
        } else {
          score = Math.round(bboxOverlap(row.bbox, targetBBox) * 100);
        }
      } else {
        score = 10;
      }
      if (score <= 0) return;
      if (!best || score > best.score || (score === best.score && Number(row.updated_at || 0) > Number(best.row.updated_at || 0))) {
        best = { score: score, row: row };
      }
    });
    return best ? best.row : null;
  }

  function readBestBundle(layerIds, bbox) {
    return listByKind('bundle').then(function (rows) {
      var bestRow = chooseBestBundle(rows || [], layerIds, bbox);
      if (bestRow && bestRow.package_id) touchPackage(bestRow.package_id).catch(function () {});
      return bestRow ? bestRow.payload : null;
    });
  }

  function cacheCatalog(payload) {
    return putRow({ id: 'catalog:all', kind: 'catalog', layer_key: '', layer_ids: [], bbox: null, updated_at: Date.now(), last_used_at: Date.now(), payload: payload }).then(function () { return payload; });
  }

  function readCatalog() {
    return getRow('catalog:all').then(function (row) { return row ? row.payload : null; });
  }

  function listPackages() {
    return listByKind('package').then(function (rows) {
      return (rows || []).sort(function (a, b) {
        return Number(b.last_used_at || b.updated_at || 0) - Number(a.last_used_at || a.updated_at || 0);
      });
    });
  }

  function summarizePackage(row, now, options) {
    now = Number(now || Date.now());
    options = options || {};
    var staleAfterMs = Number(row && row.stale_after_ms || options.staleAfterMs || DEFAULT_STALE_AFTER_MS);
    var purgeAfterMs = Number(row && row.purge_after_ms || options.purgeAfterMs || DEFAULT_PURGE_AFTER_MS);
    var updatedAt = Number(row && row.updated_at || 0);
    var ageMs = updatedAt ? Math.max(0, now - updatedAt) : 0;
    var stale = !!updatedAt && ageMs >= staleAfterMs;
    var expired = !!updatedAt && ageMs >= purgeAfterMs;
    return {
      stale: stale,
      expired: expired,
      ageMs: ageMs,
      ageDays: ageMs / (24 * 60 * 60 * 1000)
    };
  }

  function touchPackage(packageId) {
    if (!packageId) return Promise.resolve(null);
    return withStore('readwrite', function (store, tx, resolve, reject) {
      requestToPromise(store.get(String(packageId))).then(function (row) {
        if (!row) {
          resolve(null);
          return;
        }
        row.last_used_at = Date.now();
        var request = store.put(row);
        request.onsuccess = function () { resolve(row); };
        request.onerror = function () { reject(request.error || new Error('Kunne ikke oppdatere kartpakke.')); };
      }).catch(reject);
    });
  }

  function cacheOfflinePackage(layerIds, requestBBox, payload, options) {
    options = options || {};
    var bundle = payload && payload.bundle ? payload.bundle : payload;
    var requestedBBox = normalizeBBox(requestBBox) || (payload && normalizeBBox(payload.requested_bbox)) || (payload && normalizeBBox(payload.offline_bbox)) || null;
    var offlineBBox = (payload && normalizeBBox(payload.offline_bbox)) || requestedBBox;
    var ids = normalizeLayerIds(layerIds && layerIds.length ? layerIds : (payload && payload.layer_ids) || []);
    var packageId = String(options.packageId || packageIdFor(ids, offlineBBox || requestedBBox || [0, 0, 0, 0]));
    var bundleId = bundleIdFor(packageId);
    var now = Date.now();
    var tileUrls = uniqueStrings(options.tile_urls || []);
    var featureCount = Array.isArray(bundle && bundle.features) ? bundle.features.length : 0;
    var layerCount = ids.length;
    var tileCount = isFinite(Number(options.tile_count)) ? Number(options.tile_count) : tileUrls.length;
    var label = String(options.label || buildPackageLabel(requestedBBox, offlineBBox, ids));
    var staleAfterMs = Number(options.staleAfterMs || DEFAULT_STALE_AFTER_MS);
    var purgeAfterMs = Number(options.purgeAfterMs || DEFAULT_PURGE_AFTER_MS);

    var bundleRow = {
      id: bundleId,
      kind: 'bundle',
      layer_key: layerKey(ids),
      layer_ids: ids,
      bbox: offlineBBox,
      updated_at: now,
      last_used_at: now,
      payload: bundle,
      source: 'offline-package',
      offline: true,
      package_id: packageId
    };
    var packageRow = {
      id: packageId,
      kind: 'package',
      label: label,
      layer_key: layerKey(ids),
      layer_ids: ids,
      requested_bbox: requestedBBox,
      bbox: offlineBBox,
      bundle_id: bundleId,
      feature_count: featureCount,
      layer_count: layerCount,
      tile_count: tileCount,
      tile_urls: tileUrls,
      created_at: Number(options.createdAt || now),
      updated_at: now,
      last_used_at: now,
      stale_after_ms: staleAfterMs,
      purge_after_ms: purgeAfterMs,
      expand_factor: Number(options.expandFactor || options.expand || 1.6),
      source: String(options.source || 'offline-package')
    };

    return withStore('readwrite', function (store, tx, resolve, reject) {
      var req1 = store.put(bundleRow);
      req1.onerror = function () { reject(req1.error || new Error('Kunne ikke lagre offline kartdata.')); };
      var req2 = store.put(packageRow);
      req2.onerror = function () { reject(req2.error || new Error('Kunne ikke lagre offline kartpakke.')); };
      tx.oncomplete = function () { resolve(packageRow); };
    });
  }

  function deletePackage(packageId) {
    if (!packageId) return Promise.resolve(null);
    return withStore('readwrite', function (store, tx, resolve, reject) {
      requestToPromise(store.get(String(packageId))).then(function (row) {
        if (!row) {
          resolve(null);
          return;
        }
        store.delete(String(packageId));
        if (row.bundle_id) store.delete(String(row.bundle_id));
        tx.oncomplete = function () { resolve(row); };
      }).catch(reject);
    });
  }

  function cleanupPackages(options) {
    options = options || {};
    var maxPackages = Math.max(1, Number(options.maxPackages || DEFAULT_MAX_PACKAGES));
    var purgeAfterMs = Math.max(0, Number(options.purgeAfterMs || DEFAULT_PURGE_AFTER_MS));
    var now = Date.now();
    return listPackages().then(function (rows) {
      var remove = [];
      var keep = [];
      (rows || []).forEach(function (row) {
        var summary = summarizePackage(row, now, { purgeAfterMs: purgeAfterMs });
        if (summary.expired) {
          remove.push(row);
        } else {
          keep.push(row);
        }
      });
      keep.sort(function (a, b) {
        return Number(b.last_used_at || b.updated_at || 0) - Number(a.last_used_at || a.updated_at || 0);
      });
      while (keep.length > maxPackages) {
        remove.push(keep.pop());
      }
      if (!remove.length) {
        return { removed: [], kept: keep };
      }
      return Promise.all(remove.map(function (row) { return deletePackage(row.id).catch(function () { return null; }); })).then(function () {
        return { removed: remove, kept: keep };
      });
    });
  }

  function cacheOfflinePackageLegacy(layerIds, requestBBox, payload) {
    return cacheOfflinePackage(layerIds, requestBBox, payload, {});
  }

  window.KVLocalMap = {
    supported: supported,
    cacheBundle: cacheBundle,
    readBundle: readBundle,
    readBestBundle: readBestBundle,
    cacheCatalog: cacheCatalog,
    readCatalog: readCatalog,
    cacheOfflinePackage: cacheOfflinePackageLegacy,
    saveOfflinePackage: cacheOfflinePackage,
    listPackages: listPackages,
    deletePackage: deletePackage,
    touchPackage: touchPackage,
    cleanupPackages: cleanupPackages,
    summarizePackage: summarizePackage,
    getPackage: getRow,
    makeBundleKey: makeBundleKey,
    layerKey: layerKey,
    bboxContains: bboxContains,
    bboxOverlap: bboxOverlap,
    normalizeBBox: normalizeBBox,
    buildPackageLabel: buildPackageLabel,
    uniqueStrings: uniqueStrings,
    uniqueLayerIds: normalizeLayerIds
  };
})();
