/**
 * Sync orchestrator — kjøres på alle sider for innloggede brukere.
 *
 * Ansvar:
 *   - Be om persistent storage så IndexedDB ikke blir evictet på iOS/Safari
 *   - Synke alle pending lokale media på tvers av saker (ikke bare aktiv sak)
 *   - Re-prøve failed uploads med eksponentiell backoff
 *   - Oppdatere et globalt synkbadge i toppbaren
 *   - Reagere på "online"-event når nettverket kommer tilbake
 *   - Periodisk polling hver 60. sekund
 *
 * Ingen avhengigheter til case-app.js — bruker LocalMedia/LocalCases direkte
 * og POSTer til /api/cases/{id}/evidence-endepunktet.
 */
(function () {
  'use strict';

  if (!window.MKCurrentUser || !window.MKCurrentUser.id) return; // not logged in
  if (window.__MK_SYNC_ORCHESTRATOR_INSTALLED__) return;
  window.__MK_SYNC_ORCHESTRATOR_INSTALLED__ = true;

  var POLL_INTERVAL_MS = 60 * 1000;
  var MIN_RETRY_INTERVAL_MS = 30 * 1000;
  var MAX_RETRY_INTERVAL_MS = 10 * 60 * 1000;
  var STALE_UPLOADING_MS = 2 * 60 * 1000;

  var inFlight = false;
  var lastRunAt = 0;
  var failedBackoff = {}; // { recordId: { nextAttemptAt, attempts } }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? String(meta.getAttribute('content') || '') : '';
  }

  function ownerOptions() {
    return { owner_user_id: (window.MKCurrentUser && window.MKCurrentUser.id) || '' };
  }

  function localMediaSupported() {
    return !!(window.KVLocalMedia && typeof window.KVLocalMedia.supported === 'function' && window.KVLocalMedia.supported());
  }

  function getAllPendingAcrossCases() {
    if (!localMediaSupported()) return Promise.resolve([]);
    // Read everything for this owner across all cases. Then filter to needing-sync.
    return new Promise(function (resolve) {
      try {
        var req = indexedDB.open('kv-kontroll-local-media', 4);
        req.onsuccess = function () {
          var db = req.result;
          var tx = db.transaction('local_media', 'readonly');
          var store = tx.objectStore('local_media');
          var all = [];
          var cursor = store.openCursor();
          cursor.onsuccess = function (e) {
            var c = e.target.result;
            if (c) {
              var row = c.value;
              if (row && String(row.owner_user_id || '') === String((window.MKCurrentUser && window.MKCurrentUser.id) || '')) {
                all.push(row);
              }
              c.continue();
            } else {
              db.close();
              resolve(all);
            }
          };
          cursor.onerror = function () { db.close(); resolve([]); };
        };
        req.onerror = function () { resolve([]); };
      } catch (e) { resolve([]); }
    });
  }

  function recordsNeedingSync(rows) {
    var now = Date.now();
    return (rows || []).filter(function (row) {
      if (!row || !row.case_id) return false;
      var state = String(row.sync_state || 'pending');
      if (state === 'synced') return false;
      if (state === 'uploading') {
        // Treat as stale if updated_at is too old
        var updated = Number(row.updated_at || row.created_at || 0);
        return (now - updated) > STALE_UPLOADING_MS;
      }
      if (state === 'failed') {
        var entry = failedBackoff[row.id];
        if (entry && entry.nextAttemptAt > now) return false; // not yet
        return true;
      }
      return true; // pending
    });
  }

  function dataUrlToBlob(dataUrl, mimeFallback) {
    if (!dataUrl) return null;
    if (dataUrl instanceof Blob) return dataUrl;
    if (typeof dataUrl !== 'string') return null;
    var match = /^data:([^;]+);base64,(.*)$/.exec(dataUrl);
    if (!match) return null;
    var mime = match[1] || mimeFallback || 'application/octet-stream';
    var binary = atob(match[2]);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: mime });
  }

  function recordToBlob(record) {
    if (!record) return null;
    var f = record.file;
    if (f instanceof Blob) return f;
    if (typeof f === 'string') return dataUrlToBlob(f, record.mime_type);
    if (f && typeof f === 'object' && f.data) return dataUrlToBlob(f.data, record.mime_type);
    return null;
  }

  function uploadOne(record) {
    var caseId = String(record.case_id || '').trim();
    if (!caseId) return Promise.reject(new Error('Saks-ID mangler'));

    // Numeric server-side case_id only — local-only cases haven't been promoted yet
    if (!/^\d+$/.test(caseId)) return Promise.reject(new Error('Lokal sak (ikke synket til server enda)'));

    var blob = recordToBlob(record);
    if (!blob) return Promise.reject(new Error('Kunne ikke lese lokal fil'));

    var ext = String(record.mime_type || '').indexOf('audio/') === 0 ? '.webm' : '.jpg';
    var name = record.original_filename || ((record.kind === 'audio' ? 'avhor-' : 'bilde-') + Date.now() + ext);

    var fd = new FormData();
    fd.append('file', blob, name);
    fd.append('caption', record.caption || '');
    fd.append('finding_key', record.finding_key || '');
    fd.append('law_text', record.law_text || '');
    fd.append('violation_reason', record.violation_reason || '');
    fd.append('seizure_ref', record.seizure_ref || '');
    fd.append('display_order', String(record.display_order || ''));
    fd.append('local_media_id', String(record.id || ''));
    fd.append('csrf_token', csrfToken());

    // Mark uploading
    return window.KVLocalMedia.update(record.id, { sync_state: 'uploading', last_error: '' })
      .catch(function () { return null; })
      .then(function () {
        return fetch('/api/cases/' + encodeURIComponent(caseId) + '/evidence', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'X-CSRF-Token': csrfToken() },
          body: fd
        });
      })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.text().then(function (txt) {
            throw new Error('HTTP ' + resp.status + (txt ? ': ' + txt.slice(0, 100) : ''));
          });
        }
        return resp.json().catch(function () { return {}; });
      })
      .then(function (data) {
        var serverEv = (data && data.evidence) || {};
        delete failedBackoff[record.id];
        return window.KVLocalMedia.update(record.id, {
          sync_state: 'synced',
          last_error: '',
          server_evidence_id: serverEv.id || '',
          server_filename: serverEv.filename || '',
          server_received_at: new Date().toISOString()
        }).catch(function () { return null; });
      })
      .catch(function (err) {
        var attempts = (failedBackoff[record.id] && failedBackoff[record.id].attempts) || 0;
        attempts += 1;
        var delay = Math.min(MAX_RETRY_INTERVAL_MS, MIN_RETRY_INTERVAL_MS * Math.pow(2, attempts - 1));
        failedBackoff[record.id] = {
          attempts: attempts,
          nextAttemptAt: Date.now() + delay
        };
        return window.KVLocalMedia.update(record.id, {
          sync_state: 'failed',
          last_error: (err && err.message) || 'Ukjent synkfeil'
        }).catch(function () { return null; });
      });
  }

  function uploadAll(records) {
    // Sequential: don't hammer the server, especially over mobile network
    return records.reduce(function (p, rec) {
      return p.then(function () { return uploadOne(rec); });
    }, Promise.resolve());
  }

  function updateGlobalBadge(stats) {
    var badge = document.getElementById('mk-sync-badge');
    if (!badge) return;
    var pending = stats.pending || 0;
    var failed = stats.failed || 0;
    var total = pending + failed;

    if (!total) {
      badge.classList.remove('mk-sync-badge-active', 'mk-sync-badge-failed');
      badge.classList.add('mk-sync-badge-idle');
      badge.setAttribute('aria-label', 'Alle vedlegg er synket');
      var idleText = badge.querySelector('.mk-sync-text');
      if (idleText) idleText.textContent = 'Synket';
      var idleCount = badge.querySelector('.mk-sync-count');
      if (idleCount) idleCount.textContent = '';
      return;
    }
    badge.classList.remove('mk-sync-badge-idle');
    badge.classList.toggle('mk-sync-badge-failed', failed > 0 && pending === 0);
    badge.classList.toggle('mk-sync-badge-active', pending > 0);
    var label = failed > 0 ? (failed + ' vedlegg feilet, klikk for å prøve igjen') : (pending + ' vedlegg venter på synk');
    badge.setAttribute('aria-label', label);
    var text = badge.querySelector('.mk-sync-text');
    if (text) text.textContent = failed > 0 && pending === 0 ? 'Synk feilet' : 'Synker …';
    var count = badge.querySelector('.mk-sync-count');
    if (count) count.textContent = String(total);
  }

  function refreshStats() {
    return getAllPendingAcrossCases().then(function (rows) {
      var pending = 0, failed = 0;
      (rows || []).forEach(function (row) {
        var state = String(row.sync_state || 'pending');
        if (state === 'synced') return;
        if (state === 'failed') failed += 1;
        else pending += 1;
      });
      updateGlobalBadge({ pending: pending, failed: failed });
    });
  }

  function runOnce(opts) {
    opts = opts || {};
    if (inFlight && !opts.force) return Promise.resolve();
    if (!navigator.onLine) {
      // Offline — just refresh the badge so user sees pending count
      return refreshStats();
    }
    inFlight = true;
    lastRunAt = Date.now();
    return getAllPendingAcrossCases()
      .then(function (rows) {
        var queue = recordsNeedingSync(rows);
        if (!queue.length) return null;
        // Sort oldest first
        queue.sort(function (a, b) { return Number(a.created_at || 0) - Number(b.created_at || 0); });
        return uploadAll(queue);
      })
      .then(function () { return refreshStats(); })
      .catch(function () { return refreshStats(); })
      .then(function () { inFlight = false; });
  }

  // Force-run all failed (user clicked badge): reset backoff
  function retryAll() {
    failedBackoff = {};
    return runOnce({ force: true });
  }

  // ---- Triggers ----

  function attachOnlineListener() {
    window.addEventListener('online', function () {
      // Wait a beat for the network to actually be reachable
      setTimeout(function () { runOnce(); }, 1500);
    });
    window.addEventListener('offline', function () {
      refreshStats();
    });
  }

  function attachVisibilityListener() {
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') {
        if (Date.now() - lastRunAt > 30 * 1000) runOnce();
      }
    });
  }

  function startPolling() {
    setInterval(function () { runOnce(); }, POLL_INTERVAL_MS);
  }

  function attachBadgeClick() {
    // Badge is now a link to /synk; no click handler needed here.
  }

  function requestPersistentStorage() {
    if (!navigator.storage || typeof navigator.storage.persist !== 'function') return;
    // Best-effort, no UI noise. iOS will only grant if the site has been "added to home screen"
    // or used heavily — but asking is harmless and may help.
    navigator.storage.persist().catch(function () { /* ignore */ });
  }

  // ---- Boot ----

  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    requestPersistentStorage();
    attachOnlineListener();
    attachVisibilityListener();
    attachBadgeClick();
    startPolling();
    // Initial run after a short delay so the page can render first
    setTimeout(function () { runOnce(); }, 800);
    // Initial stats refresh ASAP
    setTimeout(function () { refreshStats(); }, 200);
  });

  // Public API for case-app.js to trigger a sync from a save action
  window.MKSyncOrchestrator = {
    runOnce: runOnce,
    retryAll: retryAll,
    refreshStats: refreshStats
  };
})();
