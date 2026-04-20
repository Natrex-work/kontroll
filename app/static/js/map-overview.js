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
    var filterWrap = document.getElementById('overview-layer-filters');
    var storageKey = 'kv-overview-layer-filter-v61';
    var defaultView = { lat: 64.8, lng: 14.5, zoom: 4 };
    var activeLayerStatuses = { 'fredningsområde': true, 'stengt område': true, 'maksimalmål område': true, 'regulert område': true, 'fiskeriområde': true };
    var state = {
      view: defaultView,
      persistView: false,
      fetchFeatureDetails: false,
      rasterOpacity: 0.9,
      enableAreaPopup: true,
      showLegend: false,
      mapServerUrl: el.dataset.portalMapserver || '',
      rasterLayerIds: (allLayers || []).map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); }),
      identifyLayerIds: (allLayers || []).map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); }),
      lat: null,
      lng: null,
      deviceLat: null,
      deviceLng: null,
      deviceAccuracy: null,
      recenterTo: ''
    };

    try {
      localStorage.removeItem('kv-overview-layer-filter');
    } catch (e) {}

    function filteredLayers() {
      return (allLayers || []).slice();
    }

    function syncFilterUi() {
      if (!filterWrap) return;
      filterWrap.style.display = 'none';
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
      redrawMap();
      if (statusEl) statusEl.innerHTML = 'Kartet viser alle fiskerirelaterte områder uavhengig av din posisjon. Trykk på et område i kartet for informasjon, eller bruk «Bruk min posisjon» for å kontrollere et bestemt punkt.';
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
          statusEl.innerHTML = zoneResultHtml(result);
        })
        .catch(function (err) {
          statusEl.innerHTML = 'Kunne ikke sjekke områdestatus akkurat nå: ' + escapeHtml(err && err.message ? err.message : 'ukjent feil');
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

    if (btnLocate) btnLocate.addEventListener('click', locateUser);
    if (btnNational) btnNational.addEventListener('click', function () {
      setNationalView();
    });

    if (statusEl) statusEl.innerHTML = 'Kartet viser alle fiskerirelaterte områder uavhengig av din posisjon. Trykk på et område i kartet for informasjon, eller bruk «Bruk min posisjon» for å kontrollere et bestemt punkt.';
    redrawMap();
    setTimeout(setNationalView, 50);
  }

  ready(initMapOverview);
})();
