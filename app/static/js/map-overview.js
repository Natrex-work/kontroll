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

  function initMapOverview() {
    var el = document.getElementById('overview-map');
    if (!el || !createPortalMap) return;
    var layers = parseJson(el.dataset.portalCatalog, []);
    var statusEl = document.getElementById('overview-map-status');
    var btn = document.getElementById('btn-overview-location');
    var state = { lat: null, lng: null, layer: null };
    var watchId = null;
    createPortalMap(el, layers, state);

    function refreshOverviewFromPosition(position) {
      state.lat = Number(position.coords.latitude.toFixed(6));
      state.lng = Number(position.coords.longitude.toFixed(6));
      fetch('/api/zones/check?lat=' + encodeURIComponent(state.lat) + '&lng=' + encodeURIComponent(state.lng))
        .then(function (r) { return r.json(); })
        .then(function (result) {
          statusEl.innerHTML = zoneResultHtml(result);
          createPortalMap(el, layers, state);
        })
        .catch(function () {
          statusEl.innerHTML = 'Kunne ikke sjekke områdestatus akkurat nå.';
          createPortalMap(el, layers, state);
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

    if (btn) btn.addEventListener('click', startOverviewWatch);
    startOverviewWatch();
  }

  ready(initMapOverview);
})();
