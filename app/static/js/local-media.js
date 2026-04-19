(function () {
  var DB_NAME = 'kv-kontroll-local-media';
  var DB_VERSION = 1;
  var STORE = 'local_media';

  function supported() {
    return typeof indexedDB !== 'undefined';
  }

  function openDb() {
    if (!supported()) return Promise.reject(new Error('IndexedDB er ikke tilgjengelig.'));
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onerror = function () { reject(request.error || new Error('Kunne ikke åpne lokalt medielager.')); };
      request.onupgradeneeded = function () {
        var db = request.result;
        var store = db.objectStoreNames.contains(STORE) ? request.transaction.objectStore(STORE) : db.createObjectStore(STORE, { keyPath: 'id' });
        if (!store.indexNames.contains('case_id')) store.createIndex('case_id', 'case_id', { unique: false });
        if (!store.indexNames.contains('sync_state')) store.createIndex('sync_state', 'sync_state', { unique: false });
        if (!store.indexNames.contains('created_at')) store.createIndex('created_at', 'created_at', { unique: false });
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
        tx.onerror = function () { reject(tx.error || new Error('Lokal medietransaksjon feilet.')); db.close(); };
        tx.onabort = function () { reject(tx.error || new Error('Lokal medietransaksjon ble avbrutt.')); db.close(); };
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
      request.onerror = function () { reject(request.error || new Error('IndexedDB-forespørsel feilet.')); };
    });
  }

  function cloneRecord(record) {
    return Object.assign({}, record || {});
  }

  function put(record) {
    var entry = cloneRecord(record);
    if (!entry.id) entry.id = generateId();
    if (!entry.created_at) entry.created_at = Date.now();
    return withStore('readwrite', function (store) {
      store.put(entry);
      return entry;
    });
  }

  function get(id) {
    return withStore('readonly', function (store) {
      return requestToPromise(store.get(id));
    });
  }

  function remove(id) {
    return withStore('readwrite', function (store) {
      store.delete(id);
      return true;
    });
  }

  function getAllByCase(caseId) {
    return withStore('readonly', function (store) {
      var index = store.index('case_id');
      return requestToPromise(index.getAll(String(caseId)));
    }).then(function (rows) {
      return (rows || []).sort(function (a, b) { return Number(b.created_at || 0) - Number(a.created_at || 0); });
    });
  }

  function update(id, patch) {
    return get(id).then(function (current) {
      if (!current) return null;
      var next = Object.assign({}, current, patch || {}, { id: id });
      return put(next);
    });
  }

  function clearCase(caseId) {
    return getAllByCase(caseId).then(function (rows) {
      return Promise.all((rows || []).map(function (row) { return remove(row.id); }));
    });
  }

  function pendingByCase(caseId) {
    return getAllByCase(caseId).then(function (rows) {
      return (rows || []).filter(function (row) {
        return String(row.sync_state || 'pending') !== 'synced';
      });
    });
  }

  function generateId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    return 'local-' + Date.now() + '-' + Math.random().toString(16).slice(2);
  }

  window.KVLocalMedia = {
    supported: supported,
    put: put,
    get: get,
    remove: remove,
    update: update,
    getAllByCase: getAllByCase,
    getPendingByCase: pendingByCase,
    clearCase: clearCase,
    generateId: generateId
  };
})();
