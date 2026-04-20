(function () {
  var DB_NAME = 'kv-kontroll-local-map';
  var DB_VERSION = 1;
  var STORE = 'map_cache';

  function supported() {
    return typeof indexedDB !== 'undefined';
  }

  function openDb() {
    if (!supported()) return Promise.reject(new Error('IndexedDB er ikke tilgjengelig.'));
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onerror = function () { reject(request.error || new Error('Kunne ikke åpne lokalt kartlager.')); };
      request.onupgradeneeded = function () {
        var db = request.result;
        var store = db.objectStoreNames.contains(STORE) ? request.transaction.objectStore(STORE) : db.createObjectStore(STORE, { keyPath: 'id' });
        if (!store.indexNames.contains('kind')) store.createIndex('kind', 'kind', { unique: false });
        if (!store.indexNames.contains('updated_at')) store.createIndex('updated_at', 'updated_at', { unique: false });
      };
      request.onsuccess = function () { resolve(request.result); };
    });
  }

  function withStore(mode, runner) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, mode);
        var store = tx.objectStore(STORE);
        var result;
        tx.oncomplete = function () { resolve(result); db.close(); };
        tx.onerror = function () { reject(tx.error || new Error('Kartcache-transaksjon feilet.')); db.close(); };
        tx.onabort = function () { reject(tx.error || new Error('Kartcache-transaksjon ble avbrutt.')); db.close(); };
        try {
          result = runner(store, tx);
        } catch (err) {
          try { tx.abort(); } catch (e) {}
          reject(err);
          db.close();
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

  function put(id, kind, payload) {
    return withStore('readwrite', function (store) {
      var row = { id: String(id), kind: String(kind || 'generic'), updated_at: Date.now(), payload: payload };
      store.put(row);
      return row;
    });
  }

  function get(id) {
    return withStore('readonly', function (store) {
      return requestToPromise(store.get(String(id)));
    }).then(function (row) { return row ? row.payload : null; });
  }

  function makeBundleKey(layerIds, bbox) {
    var ids = (layerIds || []).map(function (value) { return Number(value); }).filter(function (value) { return isFinite(value); }).sort(function (a, b) { return a - b; });
    var bboxKey = (bbox || []).map(function (value) { return Number(value).toFixed(4); }).join(',');
    return 'bundle:' + ids.join('-') + ':' + bboxKey;
  }

  function cacheBundle(layerIds, bbox, payload) {
    return put(makeBundleKey(layerIds, bbox), 'bundle', payload).then(function () { return payload; });
  }

  function readBundle(layerIds, bbox) {
    return get(makeBundleKey(layerIds, bbox));
  }

  function cacheCatalog(payload) {
    return put('catalog:all', 'catalog', payload).then(function () { return payload; });
  }

  function readCatalog() {
    return get('catalog:all');
  }

  window.KVLocalMap = {
    supported: supported,
    cacheBundle: cacheBundle,
    readBundle: readBundle,
    cacheCatalog: cacheCatalog,
    readCatalog: readCatalog,
    makeBundleKey: makeBundleKey
  };
})();
