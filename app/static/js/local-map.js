(function () {
  var DB_NAME = 'kv-kontroll-local-map';
  var DB_VERSION = 2;
  var STORE = 'map_cache';

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
      payload: payload,
      source: String(options.source || 'live'),
      offline: options.offline === true
    };
    return putRow(row).then(function () { return payload; });
  }

  function readBundle(layerIds, bbox) {
    return getRow(makeBundleKey(layerIds, bbox)).then(function (row) { return row ? row.payload : null; });
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
    return best ? best.row.payload : null;
  }

  function readBestBundle(layerIds, bbox) {
    return listByKind('bundle').then(function (rows) {
      return chooseBestBundle(rows || [], layerIds, bbox);
    });
  }

  function cacheCatalog(payload) {
    return putRow({ id: 'catalog:all', kind: 'catalog', layer_key: '', layer_ids: [], bbox: null, updated_at: Date.now(), payload: payload }).then(function () { return payload; });
  }

  function readCatalog() {
    return getRow('catalog:all').then(function (row) { return row ? row.payload : null; });
  }

  function cacheOfflinePackage(layerIds, requestBBox, payload) {
    var bundle = payload && payload.bundle ? payload.bundle : payload;
    var offlineBBox = payload && normalizeBBox(payload.offline_bbox) ? payload.offline_bbox : requestBBox;
    return cacheBundle(layerIds, offlineBBox, bundle, { source: 'offline-package', offline: true, id: 'bundle:' + layerKey(layerIds) + ':' + bboxKey(offlineBBox) });
  }

  window.KVLocalMap = {
    supported: supported,
    cacheBundle: cacheBundle,
    readBundle: readBundle,
    readBestBundle: readBestBundle,
    cacheCatalog: cacheCatalog,
    readCatalog: readCatalog,
    cacheOfflinePackage: cacheOfflinePackage,
    makeBundleKey: makeBundleKey,
    layerKey: layerKey,
    bboxContains: bboxContains,
    bboxOverlap: bboxOverlap
  };
})();
