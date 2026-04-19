(function () {
  var Common = window.KVCommon || {};
  var ready = Common.ready || function (fn) { if (document.readyState !== 'loading') fn(); else document.addEventListener('DOMContentLoaded', fn); };
  var escapeHtml = Common.escapeHtml || function (value) { return String(value || ''); };
  var parseJson = Common.parseJson || function (value, fallback) { try { return JSON.parse(value || ''); } catch (e) { return fallback; } };
  var createPortalMap = Common.createPortalMap;
  var sourceChip = Common.sourceChip || function () { return ''; };

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
    if (result.hits && result.hits.length) {
      parts.push('<div class="source-list margin-top-s">' + result.hits.map(function (hit) {
        return sourceChip({ name: hit.source || hit.layer || 'Karttreff', ref: hit.name || hit.layer || '', url: hit.url || '' });
      }).join('') + '</div>');
    }
    return parts.join('');
  }

  function pillClass(status) {
    var normalized = String(status || '').toLowerCase();
    if (normalized.indexOf('stengt') !== -1 || normalized.indexOf('forbud') !== -1) return 'pill pill-danger';
    if (normalized.indexOf('fredning') !== -1) return 'pill';
    if (normalized.indexOf('maksimal') !== -1) return 'pill';
    if (normalized.indexOf('fiskeriomr') !== -1) return 'pill pill-info';
    return 'pill pill-success';
  }

  function zoneRow(item) {
    return [
      '<div class="zone-row">',
      '<span class="' + pillClass(item.status) + '">' + escapeHtml(item.status || 'Kartlag') + '</span>',
      '<div>',
      '<div><strong>' + escapeHtml(item.name || item.layer || 'Ukjent sone') + '</strong></div>',
      '<div class="small muted">' + escapeHtml(item.layer || '') + '</div>',
      item.description ? '<div class="small muted margin-top-s">' + escapeHtml(item.description) + '</div>' : '',
      item.url ? '<div class="small margin-top-s"><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">Åpne regelgrunnlag</a></div>' : '',
      '</div>',
      '</div>'
    ].join('');
  }

  function initMapOverview() {
    var el = document.getElementById('overview-map');
    if (!el || !createPortalMap) return;
    var allLayers = parseJson(el.dataset.portalCatalog, []);
    var statusEl = document.getElementById('overview-map-status');
    var btn = document.getElementById('btn-overview-location');
    var filterWrap = document.getElementById('overview-layer-filters');
    var storageKey = 'kv-overview-layer-filter';
    var activeLayerStatuses = { 'fredningsområde': true, 'stengt område': true, 'maksimalmål område': true, 'regulert område': true, 'fiskeriområde': true };
    var watchId = null;
    var lastZoneFetch = { lat: null, lng: null, ts: 0 };
    var state = {
      lat: null,
      lng: null,
      layer: null,
      deviceLat: null,
      deviceLng: null,
      deviceAccuracy: null,
      recenterTo: '',
      fetchFeatureDetails: false,
      enableAreaPopup: true,
      showLegend: false,
      mapServerUrl: el.dataset.portalMapserver || ''
    };

    try {
      var saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (saved && typeof saved === 'object') {
        Object.keys(activeLayerStatuses).forEach(function (key) {
          if (Object.prototype.hasOwnProperty.call(saved, key)) activeLayerStatuses[key] = !!saved[key];
        });
      }
    } catch (e) {}

    function distanceMeters(lat1, lng1, lat2, lng2) {
      if (!isFinite(lat1) || !isFinite(lng1) || !isFinite(lat2) || !isFinite(lng2)) return Infinity;
      var toRad = Math.PI / 180;
      var dLat = (lat2 - lat1) * toRad;
      var dLng = (lng2 - lng1) * toRad;
      var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
      return 6371000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function shouldRefreshZone(lat, lng, accuracy) {
      var now = Date.now();
      if (!isFinite(lastZoneFetch.lat) || !isFinite(lastZoneFetch.lng)) return true;
      if ((now - lastZoneFetch.ts) > 8000) return true;
      return distanceMeters(lastZoneFetch.lat, lastZoneFetch.lng, lat, lng) > Math.max(15, Number(accuracy || 0));
    }

    function filteredLayers() {
      return (allLayers || []).filter(function (layer) {
        var status = String(layer.status || '').trim().toLowerCase();
        if (!Object.prototype.hasOwnProperty.call(activeLayerStatuses, status)) return true;
        return !!activeLayerStatuses[status];
      });
    }

    function syncFilterUi() {
      if (!filterWrap) return;
      Array.prototype.forEach.call(filterWrap.querySelectorAll('input[data-layer-filter]'), function (input) {
        var key = String(input.getAttribute('data-layer-filter') || '').trim().toLowerCase();
        input.checked = activeLayerStatuses[key] !== false;
      });
    }

    function redrawMap() {
      return createPortalMap(el, filteredLayers(), state).then(function () {
        if (state.recenterTo) state.recenterTo = '';
      });
    }

    function refreshOverviewFromPosition(position) {
      var lat = Number(position.coords.latitude.toFixed(6));
      var lng = Number(position.coords.longitude.toFixed(6));
      var accuracy = Number(position.coords.accuracy || 12);
      state.lat = null;
      state.lng = null;
      state.deviceLat = lat;
      state.deviceLng = lng;
      state.deviceAccuracy = accuracy;
      state.recenterTo = 'device';
      if (!shouldRefreshZone(lat, lng, accuracy)) {
        redrawMap();
        return;
      }
      lastZoneFetch = { lat: lat, lng: lng, ts: Date.now() };
      fetch('/api/zones/check?lat=' + encodeURIComponent(lat) + '&lng=' + encodeURIComponent(lng))
        .then(function (r) { return r.json(); })
        .then(function (result) {
          statusEl.innerHTML = zoneResultHtml(result);
          redrawMap();
        })
        .catch(function () {
          statusEl.innerHTML = 'Kunne ikke sjekke områdestatus akkurat nå.';
          redrawMap();
        });
    }

    function startOverviewWatch() {
      if (!navigator.geolocation) {
        statusEl.innerHTML = 'Denne enheten støtter ikke geolokasjon i nettleseren.';
        return;
      }
      statusEl.innerHTML = 'Henter posisjon ...';
      if (watchId !== null) { try { navigator.geolocation.clearWatch(watchId); } catch (e) {} }
      watchId = navigator.geolocation.watchPosition(refreshOverviewFromPosition, function (err) {
        statusEl.innerHTML = 'Kunne ikke hente posisjon: ' + escapeHtml(err.message || err);
      }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
    }

    if (filterWrap) {
      syncFilterUi();
      Array.prototype.forEach.call(filterWrap.querySelectorAll('input[data-layer-filter]'), function (input) {
        input.addEventListener('change', function () {
          var key = String(input.getAttribute('data-layer-filter') || '').trim().toLowerCase();
          activeLayerStatuses[key] = !!input.checked;
          try { localStorage.setItem(storageKey, JSON.stringify(activeLayerStatuses)); } catch (e) {}
          redrawMap();
        });
      });
    }

    if (btn) btn.addEventListener('click', startOverviewWatch);
    redrawMap();
    startOverviewWatch();
  }

  ready(initMapOverview);
})();
