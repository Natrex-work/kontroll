(function () {
  var DB_NAME = 'kv-kontroll-local-cases';
  var DB_VERSION = 2;
  var STORE = 'case_drafts';

  function currentDeviceId() {
    try {
      var key = 'mk-device-id';
      var existing = localStorage.getItem(key);
      if (existing) return existing;
      var value = (window.crypto && typeof window.crypto.randomUUID === 'function') ? window.crypto.randomUUID() : ('device-' + Date.now() + '-' + Math.random().toString(16).slice(2));
      localStorage.setItem(key, value);
      return value;
    } catch (e) {
      return 'device-unknown';
    }
  }

  function ownerFromOptions(options) {
    options = options || {};
    return String(options.owner_user_id || (window.MKCurrentUser && window.MKCurrentUser.id) || '').trim();
  }

  function rowAllowedForOwner(row, ownerUserId) {
    if (!row) return false;
    ownerUserId = String(ownerUserId || '').trim();
    if (!ownerUserId) return true;
    var rowOwner = String(row.owner_user_id || '').trim();
    return rowOwner === ownerUserId;
  }

  function supported() {
    return typeof indexedDB !== 'undefined';
  }

  function openDb() {
    if (!supported()) return Promise.reject(new Error('IndexedDB er ikke tilgjengelig.'));
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onerror = function () { reject(request.error || new Error('Kunne ikke åpne lokalt sakslager.')); };
      request.onupgradeneeded = function () {
        var db = request.result;
        var store = db.objectStoreNames.contains(STORE) ? request.transaction.objectStore(STORE) : db.createObjectStore(STORE, { keyPath: 'case_id' });
        if (!store.indexNames.contains('updated_at')) store.createIndex('updated_at', 'updated_at', { unique: false });
        if (!store.indexNames.contains('sync_state')) store.createIndex('sync_state', 'sync_state', { unique: false });
        if (!store.indexNames.contains('case_number')) store.createIndex('case_number', 'case_number', { unique: false });
        if (!store.indexNames.contains('last_server_sync_at')) store.createIndex('last_server_sync_at', 'last_server_sync_at', { unique: false });
        if (!store.indexNames.contains('owner_user_id')) store.createIndex('owner_user_id', 'owner_user_id', { unique: false });
        if (!store.indexNames.contains('device_id')) store.createIndex('device_id', 'device_id', { unique: false });
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
        tx.onerror = function () { reject(tx.error || new Error('Lokal sakstransaksjon feilet.')); db.close(); };
        tx.onabort = function () { reject(tx.error || new Error('Lokal sakstransaksjon ble avbrutt.')); db.close(); };
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
      request.onerror = function () { reject(request.error || new Error('Lokal sakforespørsel feilet.')); };
    });
  }


  function isLocalCaseId(caseId) {
    return String(caseId || '').indexOf('local-') === 0;
  }

  function generateLocalCaseId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return 'local-' + window.crypto.randomUUID();
    return 'local-' + Date.now() + '-' + Math.random().toString(16).slice(2);
  }

  function buildCaseUrl(caseId) {
    var value = String(caseId || '');
    if (!value) return '/cases/offline/new';
    if (isLocalCaseId(value)) return '/cases/offline/new?local_id=' + encodeURIComponent(value);
    return '/cases/' + encodeURIComponent(value) + '/edit';
  }

  function normalizeDraft(draft, current) {
    var now = Date.now();
    var base = Object.assign({}, current || {}, draft || {});
    base.case_id = String(base.case_id || '');
    if (!base.case_id) throw new Error('case_id mangler for lokal sakslagring.');
    base.case_number = String(base.case_number || (current && current.case_number) || '');
    base.owner_user_id = String(base.owner_user_id || (current && current.owner_user_id) || ownerFromOptions() || '');
    base.device_id = String(base.device_id || (current && current.device_id) || currentDeviceId());
    base.local_schema_version = 2;
    base.case_url = String(base.case_url || (current && current.case_url) || buildCaseUrl(base.case_id));
    base.updated_at = Number(base.updated_at || now);
    base.sync_state = String(base.sync_state || 'pending');
    base.last_server_sync_at = base.last_server_sync_at || (current && current.last_server_sync_at) || '';
    base.server_updated_at = base.server_updated_at || (current && current.server_updated_at) || '';
    base.restore_count = Number(base.restore_count || (current && current.restore_count) || 0);
    base.form_values = Array.isArray(base.form_values) ? base.form_values : [];
    base.findings = Array.isArray(base.findings) ? base.findings : [];
    base.sources = Array.isArray(base.sources) ? base.sources : [];
    base.crew = Array.isArray(base.crew) ? base.crew : [];
    base.external_actors = Array.isArray(base.external_actors) ? base.external_actors : [];
    base.interviews = Array.isArray(base.interviews) ? base.interviews : [];
    base.map_view = base.map_view || null;
    base.current_step = Number(base.current_step || 1);
    base.position_mode = String(base.position_mode || 'auto');
    base.summary_cache = base.summary_cache || {};
    base.meta = Object.assign({}, current && current.meta || {}, draft && draft.meta || {});
    return base;
  }

  function getDraft(caseId, options) {
    var ownerUserId = ownerFromOptions(options);
    return withStore('readonly', function (store) {
      return requestToPromise(store.get(String(caseId)));
    }).then(function (row) {
      return rowAllowedForOwner(row, ownerUserId) ? row : null;
    });
  }

  function putDraft(draft, options) {
    return Promise.resolve().then(function () {
      if (!draft || !draft.case_id) throw new Error('Lokal sak mangler case_id.');
      options = options || {};
      if (!draft.owner_user_id) draft.owner_user_id = ownerFromOptions(options);
      if (!draft.device_id) draft.device_id = currentDeviceId();
      return getDraft(draft.case_id, options).catch(function () { return null; }).then(function (current) {
        return withStore('readwrite', function (store) {
          var row = normalizeDraft(draft, current);
          store.put(row);
          return row;
        });
      });
    });
  }

  function removeDraft(caseId, options) {
    var ownerUserId = ownerFromOptions(options);
    return getDraft(caseId, options).then(function (row) {
      if (!rowAllowedForOwner(row, ownerUserId)) return false;
      return withStore('readwrite', function (store) {
        store.delete(String(caseId));
        return true;
      });
    });
  }

  function listDrafts(options) {
    options = options || {};
    return withStore('readonly', function (store) {
      return requestToPromise(store.getAll());
    }).then(function (rows) {
      rows = Array.isArray(rows) ? rows : [];
      var ownerUserId = ownerFromOptions(options);
      if (ownerUserId) rows = rows.filter(function (row) { return rowAllowedForOwner(row, ownerUserId); });
      if (options.unsyncedOnly) rows = rows.filter(function (row) { return String(row.sync_state || 'pending') !== 'synced'; });
      return rows.sort(function (a, b) { return Number(b.updated_at || 0) - Number(a.updated_at || 0); });
    });
  }

  function markSynced(caseId, meta) {
    meta = meta || {};
    return getDraft(caseId).then(function (row) {
      if (!row) return null;
      return putDraft(Object.assign({}, row, {
        case_id: String(caseId),
        sync_state: 'synced',
        last_server_sync_at: meta.last_server_sync_at || meta.server_updated_at || new Date().toISOString(),
        server_updated_at: meta.server_updated_at || meta.last_server_sync_at || row.server_updated_at || ''
      }));
    });
  }

  function markPending(caseId, meta) {
    meta = meta || {};
    return getDraft(caseId).then(function (row) {
      if (!row) return null;
      return putDraft(Object.assign({}, row, {
        case_id: String(caseId),
        sync_state: 'pending',
        updated_at: Number(meta.updated_at || Date.now())
      }));
    });
  }

  function incrementRestoreCount(caseId) {
    return getDraft(caseId).then(function (row) {
      if (!row) return null;
      return putDraft(Object.assign({}, row, {
        case_id: String(caseId),
        restore_count: Number(row.restore_count || 0) + 1
      }));
    });
  }


  function reassignDraft(oldCaseId, newCaseId, patch) {
    oldCaseId = String(oldCaseId || '');
    newCaseId = String(newCaseId || '');
    patch = patch || {};
    if (!oldCaseId || !newCaseId) return Promise.resolve(null);
    return Promise.all([
      getDraft(oldCaseId).catch(function () { return null; }),
      getDraft(newCaseId).catch(function () { return null; })
    ]).then(function (rows) {
      var current = rows[0];
      var existingTarget = rows[1];
      if (!current && !existingTarget) return null;
      var merged = normalizeDraft(Object.assign({}, existingTarget || {}, current || {}, patch || {}, {
        case_id: newCaseId,
        case_url: patch.case_url || buildCaseUrl(newCaseId)
      }), existingTarget || current || {});
      return withStore('readwrite', function (store) {
        store.put(merged);
        if (oldCaseId !== newCaseId) store.delete(oldCaseId);
        return merged;
      });
    });
  }

  function clearOwner(ownerUserId) {
    ownerUserId = String(ownerUserId || '').trim();
    return listDrafts({ owner_user_id: ownerUserId }).then(function (rows) {
      return Promise.all((rows || []).map(function (row) { return removeDraft(row.case_id, { owner_user_id: ownerUserId }); }));
    });
  }

  function clearAll() {
    return withStore('readwrite', function (store) {
      store.clear();
      return true;
    });
  }

  function requestPersistence() {
    if (!navigator.storage || typeof navigator.storage.persist !== 'function') return Promise.resolve(false);
    return navigator.storage.persist().catch(function () { return false; });
  }

  function storageInfo() {
    if (!navigator.storage || typeof navigator.storage.estimate !== 'function') return Promise.resolve(null);
    return navigator.storage.estimate().then(function (estimate) {
      return {
        quota: Number(estimate && estimate.quota || 0),
        usage: Number(estimate && estimate.usage || 0)
      };
    }).catch(function () { return null; });
  }

  window.KVLocalCases = {
    supported: supported,
    getDraft: getDraft,
    putDraft: putDraft,
    removeDraft: removeDraft,
    listDrafts: listDrafts,
    markSynced: markSynced,
    markPending: markPending,
    incrementRestoreCount: incrementRestoreCount,
    reassignDraft: reassignDraft,
    generateLocalCaseId: generateLocalCaseId,
    buildCaseUrl: buildCaseUrl,
    isLocalCaseId: isLocalCaseId,
    requestPersistence: requestPersistence,
    storageInfo: storageInfo,
    currentDeviceId: currentDeviceId,
    clearOwner: clearOwner,
    clearAll: clearAll
  };
})();
