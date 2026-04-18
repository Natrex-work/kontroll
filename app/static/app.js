(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/static/sw.js').catch(function () {});
    });
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function parseJson(value, fallback) {
    try { return JSON.parse(value || ''); } catch (e) { return fallback; }
  }

  function normalizeHummerParticipantNo(value) {
    var raw = String(value || '').trim().toUpperCase().replace(/\s+/g, '').replace(/[–—]/g, '-');
    if (!raw) return '';
    if (/^20\d{5}$/.test(raw)) return 'H-' + raw.slice(0, 4) + '-' + raw.slice(4);
    if (/^H\d{4}-?\d{3}$/.test(raw)) {
      var compactH = raw.replace(/-/g, '');
      return 'H-' + compactH.slice(1, 5) + '-' + compactH.slice(5);
    }
    if (/^[A-ZÆØÅ]{3,4}-[A-ZÆØÅ]{3,4}-\d{3}(?:-\d{3})?$/.test(raw)) return raw;
    return '';
  }

  function classifyLookupIdentifier(identifier) {
    var value = String(identifier || '').trim();
    var compact = value.replace(/\s+/g, '');
    var normalizedHummer = normalizeHummerParticipantNo(value);
    if (!value) return { phone: '', vessel_reg: '', radio_call_sign: '', hummer_participant_no: '' };
    if (/^(?:\+?47)?\d{8}$/.test(compact)) return { phone: compact.slice(-8), vessel_reg: '', radio_call_sign: '', hummer_participant_no: '' };
    if (normalizedHummer || /deltak/i.test(value)) return { phone: '', vessel_reg: '', radio_call_sign: '', hummer_participant_no: normalizedHummer || value.toUpperCase().replace(/\s+/g, '') };
    if (/^[A-ZÆØÅ]{1,3}[- ]?[A-ZÆØÅ]{1,3}[- ]?\d{1,4}$/i.test(value)) return { phone: '', vessel_reg: value.toUpperCase().replace(/\s+/g, ''), radio_call_sign: '', hummer_participant_no: '' };
    if (/^[A-ZÆØÅ]{1,3}[- ]?\d{1,4}(?:[- ]?[A-ZÆØÅ]{1,2})?$/i.test(value)) return { phone: '', vessel_reg: value.toUpperCase().replace(/\s+/g, ''), radio_call_sign: '', hummer_participant_no: '' };
    if (/^[A-ZÆØÅ]{2,5}[- ]?\d{0,3}$/i.test(value)) return { phone: '', vessel_reg: '', radio_call_sign: compact.toUpperCase(), hummer_participant_no: '' };
    return { phone: '', vessel_reg: '', radio_call_sign: '', hummer_participant_no: '' };
  }


  function sourceChip(item) {
    var label = '<strong>' + escapeHtml(item.name || 'Kilde') + '</strong><span>' + escapeHtml(item.ref || '') + '</span>';
    if (item.url) return '<a class="source-chip" href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' + label + '</a>';
    return '<div class="source-chip">' + label + '</div>';
  }

  function findingSource(item) {
    var bits = [];
    if (item.source_name) bits.push(item.source_name);
    if (item.source_ref) bits.push(item.source_ref);
    return bits.join(' - ');
  }

  function zoneHasRelevantRestriction(result) {
    return Boolean(result && result.match && result.recommended_violation && result.recommended_violation.item);
  }

  function areaContextForNarrative() {
    if (zoneHasRelevantRestriction(latestZoneResult)) {
      return String((latestZoneResult && (latestZoneResult.name || latestZoneResult.status)) || '').trim();
    }
    return '';
  }

  function zoneResultHtml(result) {
    var manualNote = manualPositionText ? manualPositionText() : '';
    if (!result || !result.match || String(result.status || '').toLowerCase() === 'ingen treff') {
      return '<strong>ingen treff</strong><div class="small muted">Ingen treff i kartlagene for fredningsområder, stengte områder eller tilsvarende regulerte områder.</div>' + (result && (result.location_name || result.nearest_place) ? '<div class="small muted">Nærmeste sted: ' + escapeHtml(result.location_name || result.nearest_place) + '</div>' : '') + (manualNote ? '<div class="small muted">' + escapeHtml(manualNote) + '</div>' : '');
    }
    var parts = ['<strong>' + escapeHtml(result.status || '') + '</strong>'];
    if (result.name) parts.push('<div>' + escapeHtml(result.name) + '</div>');
    if (result.location_name || result.nearest_place) parts.push('<div class="small muted">Nærmeste sted: ' + escapeHtml(result.location_name || result.nearest_place) + (result.distance_to_place_km ? ' (' + escapeHtml(result.distance_to_place_km + ' km') + ')' : '') + '</div>');
    if (result.notes) parts.push('<div class="small muted">' + escapeHtml(result.notes) + '</div>');
    if (manualNote) parts.push('<div class="small muted">' + escapeHtml(manualNote) + '</div>');
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

  function lawHelpCard(item) {
    var lawName = escapeHtml(item.law_name || item.source_name || 'Regelverk');
    var section = escapeHtml(item.section || item.source_ref || '');
    var summary = escapeHtml(item.summary_text || item.label || '');
    var lawText = escapeHtml(item.law_text || item.help_text || '');
    return [
      '<div class="help-text hidden">',
      '<div class="law-help-head"><div class="law-help-kicker">' + lawName + '</div><div class="law-help-ref">' + section + '</div></div>',
      '<div class="law-help-summary">Kort forklart: ' + summary + '</div>',
      '<div class="law-help-body">' + lawText + '</div>',
      '</div>'
    ].join('');
  }

  function itemSupportsMeasurements(item) {
    var key = String(item && item.key || '').toLowerCase();
    return Boolean(item && item.supports_measurements) || key.indexOf('minstemal') !== -1 || key.indexOf('maksimalmal') !== -1;
  }

  function itemSupportsMarkerPositions(item) {
    var key = String(item && item.key || '').toLowerCase();
    return ['vak_merking', 'hummer_merking'].indexOf(key) !== -1;
  }

  function itemSupportsMarkerCounts(item) {
    var key = String(item && item.key || '').toLowerCase();
    return ['vak_merking', 'hummer_merking'].indexOf(key) !== -1;
  }

  function ensureMeasurementState(item) {
    if (!item.measurements || !Array.isArray(item.measurements)) item.measurements = [];
    return item.measurements;
  }

  function ensureMarkerState(item) {
    if (!item.marker_positions || typeof item.marker_positions !== 'object') item.marker_positions = { current: '', start: '', end: '', total: '', approved: '', deviations: '' };
    if (item.marker_positions.total === undefined) item.marker_positions.total = '';
    if (item.marker_positions.approved === undefined) item.marker_positions.approved = '';
    if (item.marker_positions.deviations === undefined) item.marker_positions.deviations = '';
    return item.marker_positions;
  }

  function ensureDeviationState(item) {
    if (!item.deviation_units || !Array.isArray(item.deviation_units)) item.deviation_units = [];
    return item.deviation_units;
  }

  function deviationSummaryText(item) {
    var rows = ensureDeviationState(item);
    if (!rows.length) return '';
    return rows.map(function (row, idx) {
      var ref = row.seizure_ref || ('Beslag ' + (idx + 1));
      var gearKind = row.gear_kind ? (' / type ' + row.gear_kind) : '';
      var gearRef = row.gear_ref ? (' / ID ' + row.gear_ref) : '';
      var qty = row.quantity ? (' / antall ' + row.quantity) : '';
      var violation = row.violation || 'ikke spesifisert avvik';
      var note = row.note ? (' / ' + row.note) : '';
      return ref + gearKind + gearRef + qty + ': ' + violation + note;
    }).join('; ');
  }


  function seizureBaseCaseNumber() {
    return String((document.getElementById('case-app') || {}).dataset.caseNumber || '').trim();
  }

  function deviationGearOptions() {
    return ['Hummerteine', 'Sanketeine', 'Samleteine', 'Krabbeteine', 'Teine', 'Ruse', 'Garn', 'Garnlenke', 'Teinelenke', 'Annet'];
  }

  function suggestedDeviationText(item) {
    return String(item.label || item.summary_text || item.key || 'Registrert avvik').trim();
  }

  function normalizedGearSignature(row) {
    return [String(row.gear_kind || '').trim().toLowerCase(), String(row.gear_ref || '').trim().toLowerCase()].join('|');
  }

  function nextSeizureSequence() {
    var maxSeq = 0;
    findingsState.forEach(function (finding) {
      ensureDeviationState(finding).forEach(function (row) {
        var match = /-(\d{3})\s*$/.exec(String(row.seizure_ref || ''));
        if (match) {
          var seq = Number(match[1] || 0);
          if (seq > maxSeq) maxSeq = seq;
        }
      });
    });
    return maxSeq + 1;
  }

  function reusedSeizureRefForRow(targetItem, row) {
    var signature = normalizedGearSignature(row);
    if (!signature || signature === '|') return '';
    var found = '';
    findingsState.forEach(function (item) {
      ensureDeviationState(item).forEach(function (candidate) {
        if (candidate === row) return;
        if (normalizedGearSignature(candidate) === signature && candidate.seizure_ref) found = candidate.seizure_ref;
      });
    });
    return found;
  }

  function syncDeviationDefaults(item) {
    ensureDeviationState(item).forEach(function (row) {
      if (!row.gear_kind) row.gear_kind = String((document.getElementById('gear_type') || {}).value || 'Teine').trim() || 'Teine';
      if (!row.quantity) row.quantity = '1';
      if (!row.violation) row.violation = suggestedDeviationText(item);
      var reused = reusedSeizureRefForRow(item, row);
      if (reused) row.seizure_ref = reused;
      if (!row.seizure_ref) row.seizure_ref = seizureBaseCaseNumber() + '-' + String(nextSeizureSequence()).padStart(3, '0');
    });
    item.deviation_summary = deviationSummaryText(item);
  }

  function measurementSummaryText(item) {
    var rows = ensureMeasurementState(item);
    if (!rows.length) return '';
    return rows.map(function (row, idx) {
      var ref = row.reference || ('Måling ' + (idx + 1));
      var length = row.length_cm ? (String(row.length_cm).replace('.', ',') + ' cm') : 'ukjent lengde';
      var photo = row.photo_ref ? (' foto: ' + row.photo_ref) : '';
      var note = row.note ? (' (' + row.note + ')') : '';
      return ref + ': ' + length + photo + note;
    }).join('; ');
  }

  function markerSummaryText(item) {
    var pos = ensureMarkerState(item);
    var parts = [];
    if (pos.current) parts.push('Kontrollørposisjon: ' + pos.current);
    if (pos.start) parts.push('Startposisjon: ' + pos.start);
    if (pos.end) parts.push('Sluttposisjon: ' + pos.end);
    if (pos.total) parts.push('Kontrollerte teiner: ' + pos.total);
    if (pos.approved) parts.push('Godkjente: ' + pos.approved);
    if (pos.deviations) parts.push('Med avvik: ' + pos.deviations);
    return parts.join(' | ');
  }

  function measurementSectionHtml(item, index) {
    if (!itemSupportsMeasurements(item)) return '';
    var rows = ensureMeasurementState(item);
    var minLabel = item.min_size_cm ? ('Minstekrav: ' + escapeHtml(String(item.min_size_cm)) + ' cm') : '';
    var maxLabel = item.max_size_cm ? (' / Maks: ' + escapeHtml(String(item.max_size_cm)) + ' cm') : '';
    return [
      '<div class="finding-extra finding-measurements">',
      '<div class="subhead">Lengdemålinger' + (minLabel || maxLabel ? ' <span class="muted small">' + minLabel + maxLabel + '</span>' : '') + '</div>',
      '<div class="measurement-list">' + rows.map(function (row, mIndex) {
        return [
          '<div class="measurement-row" data-measure-index="' + mIndex + '">',
          '<input class="measurement-reference" placeholder="Ref / ID" value="' + escapeHtml(row.reference || '') + '" />',
          '<input class="measurement-length" type="number" step="0.1" placeholder="cm" value="' + escapeHtml(row.length_cm || '') + '" />',
          '<input class="measurement-photo" placeholder="Bildereferanse" value="' + escapeHtml(row.photo_ref || '') + '" />',
          '<input class="measurement-note" placeholder="Kort merknad" value="' + escapeHtml(row.note || '') + '" />',
          '<button type="button" class="btn btn-danger btn-small measurement-remove">Fjern</button>',
          '</div>'
        ].join('');
      }).join('') + '</div>',
      '<div class="actions-row wrap"><button type="button" class="btn btn-secondary btn-small measurement-add">Legg til måling</button></div>',
      '<div class="small muted structured-preview">' + escapeHtml(measurementSummaryText(item)) + '</div>',
      '</div>'
    ].join('');
  }

  function markerSectionHtml(item) {
    if (!itemSupportsMarkerPositions(item) && !itemSupportsMarkerCounts(item)) return '';
    var pos = ensureMarkerState(item);
    var showPositions = itemSupportsMarkerPositions(item);
    var showCounts = itemSupportsMarkerCounts(item);
    var parts = ['<div class="finding-extra finding-marker-positions">'];
    parts.push('<div class="subhead">Merking av vak / kontrollposisjon</div>');
    if (showPositions) {
      parts.push('<div class="grid-two compact-grid-form">');
      parts.push('<label><span>Kontrollørposisjon</span><input class="marker-current" value="' + escapeHtml(pos.current || '') + '" /></label>');
      parts.push('<div class="actions-row wrap align-end"><button type="button" class="btn btn-secondary btn-small marker-current-fill">Bruk nåværende posisjon</button><button type="button" class="btn btn-secondary btn-small marker-current-refresh">Oppdater</button></div>');
      parts.push('<label><span>Startposisjon (lenke/garn)</span><input class="marker-start" value="' + escapeHtml(pos.start || '') + '" /></label>');
      parts.push('<div class="actions-row wrap align-end"><button type="button" class="btn btn-secondary btn-small marker-start-fill">Sett start = nåværende</button></div>');
      parts.push('<label><span>Sluttposisjon (lenke/garn)</span><input class="marker-end" value="' + escapeHtml(pos.end || '') + '" /></label>');
      parts.push('<div class="actions-row wrap align-end"><button type="button" class="btn btn-secondary btn-small marker-end-fill">Sett slutt = nåværende</button></div>');
      parts.push('</div>');
    }
    if (showCounts) {
      parts.push('<div class="grid-three compact-grid-form margin-top-s">');
      parts.push('<label><span>Antall teiner kontrollert</span><input class="marker-total" type="number" min="0" value="' + escapeHtml(pos.total || '') + '" /></label>');
      parts.push('<label><span>Antall godkjente</span><input class="marker-approved" type="number" min="0" value="' + escapeHtml(pos.approved || '') + '" /></label>');
      parts.push('<label><span>Antall med avvik</span><input class="marker-deviations" type="number" min="0" value="' + escapeHtml(pos.deviations || '') + '" /></label>');
      parts.push('</div>');
      parts.push('<div class="small muted">Bruk avviksradene under til å registrere konkrete teiner / redskap med lovbrudd.</div>');
    }
    parts.push('<div class="small muted structured-preview">' + escapeHtml(markerSummaryText(item)) + '</div>');
    parts.push('</div>');
    return parts.join('');
  }

  function deviationSectionHtml(item) {
    var rows = ensureDeviationState(item);
    syncDeviationDefaults(item);
    var isAvvik = String(item.status || '').toLowerCase() === 'avvik';
    return [
      '<div class="finding-extra finding-deviations ' + (isAvvik ? '' : 'hidden') + '">',
      '<div class="subhead">Teiner / redskap med avvik</div>',
      '<div class="deviation-list">' + rows.map(function (row, dIndex) {
        return [
          '<div class="deviation-row" data-dev-index="' + dIndex + '">',
          '<input class="deviation-seizure-ref" placeholder="Beslag nr." value="' + escapeHtml(row.seizure_ref || '') + '" readonly />',
          '<select class="deviation-gear-kind">' + deviationGearOptions().map(function (opt) { return '<option value="' + escapeHtml(opt) + '" ' + (String(row.gear_kind || '') === opt ? 'selected' : '') + '>' + escapeHtml(opt) + '</option>'; }).join('') + '</select>',
          '<input class="deviation-gear-ref" placeholder="Teine / redskap-ID" value="' + escapeHtml(row.gear_ref || '') + '" />',
          '<input class="deviation-quantity" type="number" min="1" placeholder="Antall" value="' + escapeHtml(row.quantity || '') + '" />',
          '<input class="deviation-violation" placeholder="Hva er avviket" value="' + escapeHtml(row.violation || '') + '" />',
          '<input class="deviation-note" placeholder="Merknad" value="' + escapeHtml(row.note || '') + '" />',
          '<button type="button" class="btn btn-secondary btn-small deviation-evidence-link ' + (isAvvik ? '' : 'hidden') + '">Koble bildebevis</button>',
          '<button type="button" class="btn btn-danger btn-small deviation-remove">Fjern</button>',
          '</div>'
        ].join('');
      }).join('') + '</div>',
      '<div class="actions-row wrap"><button type="button" class="btn btn-secondary btn-small deviation-add">Legg til teine / redskap med avvik</button></div>',
      '<div class="small muted structured-preview">' + escapeHtml(deviationSummaryText(item)) + '</div>',
      '</div>'
    ].join('');
  }

  function buildReadonlyFindingsHtml(items) {
    if (!items || !items.length) return '<div class="callout">Ingen kontrollpunkter tilgjengelig for dette valget.</div>';
    return items.map(function (item, index) {
      return [
        '<article class="finding-card readonly-card" data-index="' + index + '">',
        '<div class="finding-head">',
        '<div><strong>' + escapeHtml(item.label || item.key || ('Punkt ' + (index + 1))) + '</strong>',
        '<div class="muted small">' + escapeHtml(findingSource(item)) + '</div></div>',
        item.help_text || item.law_text ? '<button type="button" class="help-toggle" title="Vis hjemmel og paragraf">?</button>' : '',
        '</div>',
        (item.help_text || item.law_text) ? lawHelpCard(item) : '',
        '</article>'
      ].join('');
    }).join('');
  }

  function buildEditableFindingHtml(item, index) {
    var isAvvik = String(item.status || '').toLowerCase() === 'avvik';
    ensureMeasurementState(item);
    ensureMarkerState(item);
    return [
      '<article class="finding-card" data-index="' + index + '">',
      '<div class="finding-head">',
      '<div><strong>' + escapeHtml(item.label || item.key || ('Punkt ' + (index + 1))) + '</strong>',
      '<div class="muted small">' + escapeHtml(findingSource(item)) + '</div></div>',
      '<div class="finding-head-actions">',
      (item.help_text || item.law_text) ? '<button type="button" class="help-toggle" title="Vis hjemmel og paragraf">?</button>' : '',
      '</div>',
      '</div>',
      (item.help_text || item.law_text) ? lawHelpCard(item) : '',
      '<div class="finding-body">',
      '<label><span>Status</span>',
      '<select class="finding-status">',
      '<option value="ikke kontrollert" ' + (item.status === 'ikke kontrollert' ? 'selected' : '') + '>ikke kontrollert</option>',
      '<option value="godkjent" ' + (item.status === 'godkjent' ? 'selected' : '') + '>godkjent</option>',
      '<option value="avvik" ' + (isAvvik ? 'selected' : '') + '>avvik</option>',
      '<option value="ikke relevant" ' + (item.status === 'ikke relevant' ? 'selected' : '') + '>ikke relevant</option>',
      '</select></label>',
      '<label><span>Notat / begrunnelse</span><textarea class="finding-notes" rows="3" placeholder="Skriv kort hva som ble observert">' + escapeHtml(item.notes || '') + '</textarea></label>',
      measurementSectionHtml(item, index),
      markerSectionHtml(item),
      deviationSectionHtml(item),
      (item.auto_note ? '<div class="callout area-warning margin-top-s"><strong>Automatisk varsel</strong><div>' + escapeHtml(item.auto_note) + '</div></div>' : ''),
      '<div class="actions-row wrap">',
      '<button type="button" class="btn btn-secondary btn-small finding-evidence-btn ' + (isAvvik ? '' : 'hidden') + '">Koble bildebevis</button>',
      '</div>',
      '</div>',
      '</article>'
    ].join('');
  }

  function normalizeFeatureCollection(data) {
    return data && data.type === 'FeatureCollection' ? data : { type: 'FeatureCollection', features: [] };
  }

  var portalFeatureCache = {};

  function createPortalMap(el, layers, markerState) {
    if (!el || !window.L) return Promise.resolve(null);
    var storageKey = 'kv-map-view:' + (el.id || 'map');
    var savedView = null;
    try {
      savedView = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    } catch (e) { savedView = null; }
    if (el._kvLeafletMap) {
      try {
        var prevCenter = el._kvLeafletMap.getCenter();
        var prevZoom = el._kvLeafletMap.getZoom();
        savedView = { lat: prevCenter.lat, lng: prevCenter.lng, zoom: prevZoom };
        sessionStorage.setItem(storageKey, JSON.stringify(savedView));
      } catch (e) {}
      try { el._kvLeafletMap.remove(); } catch (e) {}
      el._kvLeafletMap = null;
    }
    el.innerHTML = '';
    var initialView = (markerState && markerState.view) || savedView;
    var map = L.map(el, { zoomControl: true }).setView(initialView ? [initialView.lat, initialView.lng] : [63.5, 11], initialView ? initialView.zoom : 5);
    el._kvLeafletMap = map;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap'
    }).addTo(map);

    var geoLayers = [];
    var promises = (layers || []).map(function (layer) {
      var cacheKey = String(layer.id);
      var dataPromise = portalFeatureCache[cacheKey]
        ? Promise.resolve(portalFeatureCache[cacheKey])
        : fetch('/api/map/features?layer_id=' + encodeURIComponent(layer.id))
            .then(function (r) { return r.json(); })
            .then(function (data) {
              portalFeatureCache[cacheKey] = normalizeFeatureCollection(data);
              return portalFeatureCache[cacheKey];
            });

      return dataPromise.then(function (data) {
        data = normalizeFeatureCollection(data);
        if (!data.features.length) return;
        var geo = L.geoJSON(data, {
          style: function () {
            return { color: layer.color || '#c1121f', weight: 2, fillColor: layer.color || '#c1121f', fillOpacity: 0.12 };
          },
          onEachFeature: function (feature, lyr) {
            var props = feature && feature.properties ? feature.properties : {};
            var title = props.navn || props.omraade || layer.name;
            var desc = props.info || props.beskrivelse || props.informasjon || props.omraade_stengt_text || props.vurderes_aapnet_text || layer.description || layer.status || '';
            var law = props.jmelding_navn || props.url || '';
            var html = '<strong>' + escapeHtml(title || layer.name) + '</strong>';
            html += '<div class="small muted">' + escapeHtml(layer.status || '') + '</div>';
            if (desc) html += '<div class="small" style="margin-top:6px">' + escapeHtml(desc) + '</div>';
            if (law) html += '<div class="small muted" style="margin-top:6px">Kilde: ' + escapeHtml(law) + '</div>';
            if (props.url) html += '<div class="small" style="margin-top:6px"><a href="' + escapeHtml(props.url) + '" target="_blank" rel="noopener">Åpne regelgrunnlag</a></div>';
            lyr.bindPopup(html);
          }
        }).addTo(map);
        geoLayers.push(geo);
      }).catch(function () {});
    });

    return Promise.all(promises).then(function () {
      var circle = null;
      if (markerState && markerState.lat && markerState.lng) {
        markerState.layer = L.marker([markerState.lat, markerState.lng], { draggable: !!markerState.draggable }).addTo(map);
        markerState.layer.bindPopup('Kontrollposisjon');
        if (markerState.draggable && (typeof markerState.onMove === 'function' || typeof markerState.onManualMove === 'function')) {
          markerState.layer.on('dragend', function (event) {
            var ll = event.target.getLatLng();
            if (typeof markerState.onManualMove === 'function') markerState.onManualMove(ll.lat, ll.lng);
            else markerState.onMove(ll.lat, ll.lng);
          });
          if (markerState.allowMapMove) {
            map.on('click', function (event) {
              markerState.layer.setLatLng(event.latlng);
              if (typeof markerState.onManualMove === 'function') markerState.onManualMove(event.latlng.lat, event.latlng.lng);
              else markerState.onMove(event.latlng.lat, event.latlng.lng);
            });
          }
        }
        circle = L.circle([markerState.lat, markerState.lng], {
          radius: (markerState.radiusKm || 50) * 1000,
          color: '#24527b',
          weight: 1,
          fillColor: '#24527b',
          fillOpacity: 0.06
        }).addTo(map);
      }
      var allLayers = geoLayers.concat(markerState && markerState.layer ? [markerState.layer] : []).concat(circle ? [circle] : []);
      var group = L.featureGroup(allLayers);
      if (!(markerState && markerState.view) && !(savedView && savedView.zoom) && group.getLayers().length) {
        try { map.fitBounds(group.getBounds().pad(0.1)); } catch (e) {}
      }
      map.on('moveend zoomend', function () {
        try {
          var center = map.getCenter();
          sessionStorage.setItem(storageKey, JSON.stringify({ lat: center.lat, lng: center.lng, zoom: map.getZoom() }));
        } catch (e) {}
      });
      setTimeout(function () {
        try { map.invalidateSize(); } catch (e) {}
      }, 180);
      return { map: map, geoLayers: geoLayers, marker: markerState && markerState.layer ? markerState.layer : null, circle: circle };
    });
  }


  function initMapOverview() {
    var el = document.getElementById('overview-map');
    if (!el) return;
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

  function initRulesOverview() {
    var root = document.getElementById('rules-overview-root');
    if (!root) return;
    var lawBrowser = parseJson(root.dataset.law, []);
    var controlType = document.getElementById('overview_control_type');
    var fisheryType = document.getElementById('overview_fishery_type');
    var species = document.getElementById('overview_species');
    var speciesList = document.getElementById('overview_species_options');
    var gearType = document.getElementById('overview_gear_type');
    var meta = document.getElementById('rules-overview-meta');
    var findings = document.getElementById('rules-overview-findings');
    var sources = document.getElementById('rules-overview-sources');

    function currentLawSection() {
      var key = String(controlType.value || '').toLowerCase().indexOf('kom') === 0 ? 'kommersiell' : 'fritidsfiske';
      return lawBrowser.filter(function (item) { return item.key === key; })[0] || null;
    }

    function syncOptions() {
      var section = currentLawSection();
      var fisheryValue = fisheryType.value;
      var gearValue = gearType.value;
      var speciesValue = species.value;
      if (!section) return;
      fisheryType.innerHTML = '<option value="">Velg</option>' + section.species.map(function (item) { return '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'; }).join('');
      gearType.innerHTML = '<option value="">Velg</option>' + section.gear.map(function (item) { return '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'; }).join('');
      speciesList.innerHTML = section.species.map(function (item) { return '<option value="' + escapeHtml(item) + '"></option>'; }).join('');
      if (fisheryValue) fisheryType.value = fisheryValue;
      if (gearValue) gearType.value = gearValue;
      if (!speciesValue && fisheryType.value) species.value = fisheryType.value;
    }

    function renderBundle(bundle) {
      meta.innerHTML = '<strong>' + escapeHtml(bundle.title || 'Kontrollpunkter') + '</strong><div class="small muted">' + escapeHtml(bundle.description || '') + '</div>';
      findings.innerHTML = buildReadonlyFindingsHtml(bundle.items || []);
      sources.innerHTML = (bundle.sources || []).map(sourceChip).join('');
    }

    function loadBundle() {
      var speciesVal = species.value || fisheryType.value || '';
      if (!controlType.value || !speciesVal || !gearType.value) {
        meta.innerHTML = 'Velg kontrolltype, art og redskap først.';
        findings.innerHTML = '';
        sources.innerHTML = '';
        return;
      }
      var params = new URLSearchParams({
        control_type: controlType.value,
        species: speciesVal,
        gear_type: gearType.value,
        area_status: '',
        control_date: ''
      });
      meta.innerHTML = 'Henter kontrollpunkter ...';
      fetch(root.dataset.rulesUrl + '?' + params.toString())
        .then(function (r) { return r.json(); })
        .then(renderBundle)
        .catch(function () { meta.innerHTML = 'Kunne ikke hente kontrollpunkter akkurat nå.'; });
    }

    controlType.addEventListener('change', syncOptions);
    fisheryType.addEventListener('change', function () { if (!species.value || species.value === fisheryType.dataset.lastValue) species.value = fisheryType.value; fisheryType.dataset.lastValue = fisheryType.value; });
    document.getElementById('btn-overview-load-rules').addEventListener('click', loadBundle);
    findings.addEventListener('click', function (event) {
      if (!event.target.classList.contains('help-toggle')) return;
      var card = event.target.closest('.finding-card');
      var box = card && card.querySelector('.help-text');
      if (box) box.classList.toggle('hidden');
    });
    syncOptions();
  }

  function initCaseApp() {
    var root = document.getElementById('case-app');
    if (!root) return;

    var lawBrowser = parseJson(root.dataset.lawBrowser, []);
    var mapCatalog = parseJson(root.dataset.mapCatalog, []);
    var latestZoneResult = null;

    var form = document.getElementById('case-form');
    var findingsInput = document.getElementById('findings_json');
    var sourcesInput = document.getElementById('source_snapshot_json');
    var crewInput = document.getElementById('crew_json');
    var externalActorsInput = document.getElementById('external_actors_json');
    var interviewInput = document.getElementById('interview_sessions_json');
    var findingsList = document.getElementById('findings-list');
    var sourceList = document.getElementById('rule-source-list');
    var metaBox = document.getElementById('rule-bundle-meta');
    var zoneResult = document.getElementById('zone-result');
    var registryResult = document.getElementById('registry-result');
    var registryCandidates = document.getElementById('registry-candidates');
    var hummerRegistryStatus = document.getElementById('hummer-registry-status');
    var gearSummaryStatus = document.getElementById('gear-summary-status');
    var observedGearCount = document.getElementById('observed_gear_count');
    var summaryPreview = document.getElementById('summary-preview');
    var caseMap = document.getElementById('case-position-map');

    var controlType = document.getElementById('control_type');
    var fisheryType = document.getElementById('fishery_type');
    var species = document.getElementById('species');
    var gearType = document.getElementById('gear_type');
    var startTime = document.getElementById('start_time');
    var endTime = document.getElementById('end_time');
    var latitude = document.getElementById('latitude');
    var longitude = document.getElementById('longitude');
    var areaStatus = document.getElementById('area_status');
    var areaName = document.getElementById('area_name');
    var locationName = document.getElementById('location_name');
    var caseBasis = document.getElementById('case_basis');
    var basisSourceName = document.getElementById('basis_source_name');
    var basisDetails = document.getElementById('basis_details');
    var suspectName = document.getElementById('suspect_name');
    var suspectNameCommercial = document.getElementById('suspect_name_commercial');
    var suspectPhone = document.getElementById('suspect_phone');
    var suspectAddress = document.getElementById('suspect_address');
    var suspectPostPlace = document.getElementById('suspect_post_place');
    var suspectBirthdate = document.getElementById('suspect_birthdate');
    var hummerParticipantNo = document.getElementById('hummer_participant_no');
    var hummerLastRegistered = document.getElementById('hummer_last_registered');
    var vesselName = document.getElementById('vessel_name');
    var vesselReg = document.getElementById('vessel_reg');
    var radioCallSign = document.getElementById('radio_call_sign');
    var lookupText = document.getElementById('lookup_text');
    var lookupName = document.getElementById('lookup_name');
    var lookupIdentifier = document.getElementById('lookup_identifier');
    var notes = document.getElementById('notes');
    var summary = document.getElementById('summary');
    var hearingText = document.getElementById('hearing_text');
    var selectedFindingCard = document.getElementById('selected-finding-card');
    var evidenceFindingKey = document.getElementById('evidence_finding_key');
    var evidenceLawText = document.getElementById('evidence_law_text');
    var evidenceSeizureRef = document.getElementById('evidence_seizure_ref');
    var evidenceCaption = document.getElementById('evidence_caption');
    var evidenceReason = document.getElementById('evidence_violation_reason');

    var leisureFields = document.getElementById('leisure-fields');
    var commercialFields = document.getElementById('commercial-fields');
    var personModeHint = document.getElementById('person-mode-hint');

    var findingsState = parseJson(findingsInput.value, []) || [];
    var sourcesState = parseJson(sourcesInput.value, []) || [];
    var crewState = parseJson(crewInput.value, []) || [];
    var externalActorsState = parseJson(externalActorsInput.value, []) || [];
    var interviewState = parseJson(interviewInput ? interviewInput.value : '[]', []) || [];
    var candidateState = [];
    var mapState = { lat: Number(latitude.value || 0), lng: Number(longitude.value || 0), layer: null, draggable: true, allowMapMove: true, radiusKm: 50, followAutoPosition: true, manualPosition: false, lastDeviceLat: null, lastDeviceLng: null };
    var locationWatchId = null;
    var mediaRecorder = null;
    var mediaChunks = [];
    var autosaveTimer = null;
    var autosaveInFlight = false;
    var lastAutosaveFingerprint = '';
    var latestGearSummary = null;

    if (!startTime.value) {
      var now = new Date();
      var iso = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      startTime.value = iso;
    }

    var panes = Array.prototype.slice.call(document.querySelectorAll('.step-pane'));
    var stepButtons = Array.prototype.slice.call(document.querySelectorAll('.step-btn'));
    var stepStorageKey = 'kv-case-step:' + root.dataset.caseId;
    var currentStep = 1;
    function showStep(step, options) {
      options = options || {};
      currentStep = step;
      try { sessionStorage.setItem(stepStorageKey, String(step)); } catch (e) {}
      panes.forEach(function (pane) { pane.classList.toggle('active', Number(pane.dataset.step) === step); });
      stepButtons.forEach(function (btn) { btn.classList.toggle('active', Number(btn.dataset.stepTarget) === step); });
      if (step === 2) {
        setTimeout(function () {
          updateCaseMap();
          if (caseMap && caseMap._kvLeafletMap) {
            try { caseMap._kvLeafletMap.invalidateSize(); } catch (e) {}
          }
        }, 180);
      }
      if (options.scroll !== false) window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    stepButtons.forEach(function (btn) { btn.addEventListener('click', function () { showStep(Number(btn.dataset.stepTarget)); }); });
    document.querySelectorAll('[data-next-step]').forEach(function (btn) { btn.addEventListener('click', function () { showStep(Math.min(currentStep + 1, panes.length)); }); });
    document.querySelectorAll('[data-prev-step]').forEach(function (btn) { btn.addEventListener('click', function () { showStep(Math.max(currentStep - 1, 1)); }); });

    function currentLawSection() {
      var key = String(controlType.value || '').toLowerCase().indexOf('kom') === 0 ? 'kommersiell' : 'fritidsfiske';
      return lawBrowser.filter(function (item) { return item.key === key; })[0] || null;
    }

    function syncOptions() {
      var section = currentLawSection();
      var fisheryValue = fisheryType.value;
      var gearValue = gearType.value;
      var speciesValue = species.value;
      if (!section) return;
      fisheryType.innerHTML = '<option value="">Velg</option>' + section.species.map(function (item) { return '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'; }).join('');
      gearType.innerHTML = '<option value="">Velg</option>' + section.gear.map(function (item) { return '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'; }).join('');
      document.getElementById('species_options').innerHTML = section.species.map(function (item) { return '<option value="' + escapeHtml(item) + '"></option>'; }).join('');
      if (fisheryValue) fisheryType.value = fisheryValue;
      if (gearValue) gearType.value = gearValue;
      if (!speciesValue && fisheryType.value) species.value = fisheryType.value;
      var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
      leisureFields.classList.toggle('hidden', isCommercial);
      commercialFields.classList.toggle('hidden', !isCommercial);
      personModeHint.innerHTML = isCommercial ? 'Kommersiell kontroll: vis fartøysnavn, fiskerimerke og radiokallesignal.' : 'Fritidsfiske: vis navn, adresse, mobilnummer, fødselsdato og hummerdeltakernummer.';
      if (isCommercial) {
        suspectNameCommercial.value = suspectName.value;
      }
    }

    function renderCrew() {
      var wrap = document.getElementById('crew-list');
      if (!wrap) return;
      wrap.innerHTML = crewState.map(function (item, idx) {
        return [
          '<div class="crew-row" data-index="' + idx + '">',
          '<input class="crew-name" placeholder="Navn" value="' + escapeHtml(item.name || '') + '" />',
          '<select class="crew-role">',
          ['Vitne', 'Båtfører', 'Båtassistent'].map(function (role) { return '<option value="' + role + '" ' + (role === item.role ? 'selected' : '') + '>' + role + '</option>'; }).join(''),
          '</select>',
          '<button type="button" class="btn btn-danger btn-small crew-remove">Fjern</button>',
          '</div>'
        ].join('');
      }).join('');
      crewInput.value = JSON.stringify(crewState);
      scheduleAutosave('Roller oppdatert');
    }

    document.getElementById('btn-add-crew').addEventListener('click', function () {
      crewState.push({ name: '', role: 'Vitne' });
      renderCrew();
    setAutosaveStatus('Klar for autosave', 'is-saved');
    });
    document.getElementById('crew-list').addEventListener('input', function (event) {
      var row = event.target.closest('.crew-row');
      if (!row) return;
      var idx = Number(row.dataset.index);
      crewState[idx] = crewState[idx] || { name: '', role: 'Vitne' };
      crewState[idx].name = row.querySelector('.crew-name').value;
      crewState[idx].role = row.querySelector('.crew-role').value;
      crewInput.value = JSON.stringify(crewState);
      scheduleAutosave('Roller oppdatert');
    });
    document.getElementById('crew-list').addEventListener('click', function (event) {
      if (!event.target.classList.contains('crew-remove')) return;
      var row = event.target.closest('.crew-row');
      if (!row) return;
      crewState.splice(Number(row.dataset.index), 1);
      renderCrew();
    setAutosaveStatus('Klar for autosave', 'is-saved');
    });

    function syncExternalActors() {
      externalActorsState = Array.prototype.slice.call(document.querySelectorAll('#external-actors input[type="checkbox"]:checked')).map(function (el) { return el.value; });
      externalActorsInput.value = JSON.stringify(externalActorsState);
    }
    document.getElementById('external-actors').addEventListener('change', syncExternalActors);
    syncExternalActors();
    renderCrew();
    setAutosaveStatus('Klar for autosave', 'is-saved');

    function mergeSources(rows) {
      var seen = {};
      sourcesState = sourcesState.concat(rows || []).filter(function (item) {
        var key = [item.name || '', item.ref || '', item.url || ''].join('|');
        if (seen[key]) return false;
        seen[key] = true;
        return true;
      });
      sourcesInput.value = JSON.stringify(sourcesState);
      sourceList.innerHTML = sourcesState.map(sourceChip).join('');
      scheduleAutosave('Kildespor oppdatert');
    }

    function renderFindings() {
      findingsInput.value = JSON.stringify(findingsState);
      findingsList.innerHTML = findingsState.map(buildEditableFindingHtml).join('');
      document.querySelectorAll('#findings-list .finding-card').forEach(function(card){
        var idx = Number(card.dataset.index);
        evaluateMarkerLimit(card, findingsState[idx]);
      });
    }

    function loadRules() {
      var speciesVal = species.value || fisheryType.value || '';
      if (!controlType.value || !speciesVal || !gearType.value) {
        metaBox.innerHTML = 'Velg kontrolltype, art og redskap først.';
        findingsState = [];
        renderFindings();
        return;
      }
      var params = new URLSearchParams({
        control_type: controlType.value,
        species: speciesVal,
        gear_type: gearType.value,
        area_status: areaStatus.value || '',
        area_name: areaName.value || '',
        area_notes: zoneResult ? (zoneResult.textContent || '') : '',
        control_date: startTime.value || '',
        lat: latitude.value || '',
        lng: longitude.value || ''
      });
      metaBox.innerHTML = 'Henter lovpunkter ...';
      fetch(root.dataset.rulesUrl + '?' + params.toString())
        .then(function (r) { return r.json(); })
        .then(function (bundle) {
          metaBox.innerHTML = '<strong>' + escapeHtml(bundle.title || 'Kontrollpunkter') + '</strong><div class="small muted">' + escapeHtml(bundle.description || '') + '</div>';
          var currentByKey = {};
          findingsState.forEach(function (item) { currentByKey[item.key] = item; });
          findingsState = (bundle.items || []).map(function (item) {
            var current = currentByKey[item.key] || {};
            return Object.assign({}, item, current, { status: current.status || item.status || 'ikke kontrollert', notes: current.notes || item.notes || '' });
          });
          renderFindings();
          sourcesState = bundle.sources || [];
          sourcesInput.value = JSON.stringify(sourcesState);
          sourceList.innerHTML = sourcesState.map(sourceChip).join('');
        })
        .catch(function () {
          metaBox.innerHTML = 'Kunne ikke hente lovpunkter akkurat nå.';
        });
    }

    function updateSelectedFinding(item, deviationRow) {
      if (!item) {
        evidenceFindingKey.value = '';
        evidenceLawText.value = '';
        if (evidenceSeizureRef) evidenceSeizureRef.value = '';
        selectedFindingCard.innerHTML = 'Velg et kontrollpunkt med avvik i steg 4 for å forhåndsfylle hjemmel og begrunnelse.';
        return;
      }
      deviationRow = deviationRow || null;
      evidenceFindingKey.value = item.key || '';
      evidenceLawText.value = item.law_text || item.help_text || '';
      if (evidenceSeizureRef) evidenceSeizureRef.value = deviationRow && deviationRow.seizure_ref ? deviationRow.seizure_ref : '';
      if (!evidenceCaption.value) evidenceCaption.value = deviationRow && deviationRow.violation ? deviationRow.violation : (item.label || item.key || '');
      if (!evidenceReason.value) evidenceReason.value = deviationRow && deviationRow.violation ? deviationRow.violation : (item.notes || item.auto_note || '');
      var extra = '';
      if (deviationRow) {
        extra = '<div class="small muted">Beslag/ref: ' + escapeHtml(deviationRow.seizure_ref || '') + (deviationRow.gear_ref ? ' · redskap ' + escapeHtml(deviationRow.gear_ref) : '') + (deviationRow.quantity ? ' · antall ' + escapeHtml(deviationRow.quantity) : '') + '</div>';
      }
      selectedFindingCard.innerHTML = '<strong>Valgt kontrollpunkt:</strong> ' + escapeHtml(item.label || item.key || '') + '<div class="small muted">' + escapeHtml(item.law_name || item.source_name || '') + ' ' + escapeHtml(item.section || item.source_ref || '') + '</div><div class="small muted">' + escapeHtml(item.summary_text || item.law_text || item.help_text || '') + '</div>' + extra;
      showStep(5, { scroll: true });
    }

    function currentCoordText() {
      if (!latitude.value || !longitude.value) return '';
      return String(latitude.value) + ', ' + String(longitude.value);
    }

    function currentControlDateLabel() {
      var raw = startTime && startTime.value ? startTime.value : '';
      var dt = raw ? new Date(raw) : new Date();
      if (Number.isNaN(dt.getTime())) dt = new Date();
      return dt.toLocaleString('nb-NO', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    }

    function manualPositionText() {
      return mapState.manualPosition ? 'Manuell posisjon satt. Bruk «Bruk / oppdater automatisk posisjon» for å gå tilbake til kontrollørens sanntidsposisjon.' : '';
    }

    function syncMarkerPositionInputs() {
      var current = currentCoordText();
      if (!current) return;
      findingsState.forEach(function (item) {
        if (!itemSupportsMarkerPositions(item)) return;
        var pos = ensureMarkerState(item);
        pos.current = current;
      });
      document.querySelectorAll('.finding-card').forEach(function (card) {
        var input = card.querySelector('.marker-current');
        if (input) input.value = current;
      });
      findingsInput.value = JSON.stringify(findingsState);
    }

    function updateCaseMap() {
      if (caseMap && caseMap._kvLeafletMap) {
        try { var _center = caseMap._kvLeafletMap.getCenter(); mapState.view = { lat: _center.lat, lng: _center.lng, zoom: caseMap._kvLeafletMap.getZoom() }; } catch (e) {}
      }
      mapState.lat = Number(latitude.value || 0);
      mapState.lng = Number(longitude.value || 0);
      mapState.draggable = true;
      mapState.allowMapMove = true;
      mapState.onMove = function (lat, lng) {
        mapState.manualPosition = false;
        latitude.value = Number(lat).toFixed(6);
        longitude.value = Number(lng).toFixed(6);
        mapState.lat = Number(latitude.value);
        mapState.lng = Number(longitude.value);
        checkZone();
        scheduleAutosave('Kartposisjon oppdatert');
      };
      mapState.onManualMove = function (lat, lng) {
        mapState.followAutoPosition = false;
        mapState.manualPosition = true;
        latitude.value = Number(lat).toFixed(6);
        longitude.value = Number(lng).toFixed(6);
        mapState.lat = Number(latitude.value);
        mapState.lng = Number(longitude.value);
        checkZone();
        scheduleAutosave('Manuell kartposisjon oppdatert');
      };
      createPortalMap(caseMap, mapCatalog, mapState);
      syncMarkerPositionInputs();
    }

    function checkZone() {
      if (!latitude.value || !longitude.value) {
        zoneResult.innerHTML = 'Legg inn posisjon først.';
        return;
      }
      var params = new URLSearchParams({
        lat: latitude.value,
        lng: longitude.value,
        species: species.value || fisheryType.value || '',
        gear_type: gearType.value || ''
      });
      zoneResult.innerHTML = 'Sjekker områdestatus ...';
      fetch(root.dataset.zonesUrl + '?' + params.toString())
        .then(function (r) { return r.json(); })
        .then(function (result) {
          latestZoneResult = result || null;
          areaStatus.value = result.match ? (result.status || 'regulert område') : 'ingen treff';
          areaName.value = result.match ? (result.name || '') : '';
          if (result.location_name) locationName.value = result.location_name;
          else if (result.nearest_place) locationName.value = result.nearest_place;
          zoneResult.innerHTML = zoneResultHtml(result);
          findingsState = findingsState.filter(function (row) {
            return ['hummer_fredningsomrade_redskap', 'stengt_omrade_status', 'fredningsomrade_status', 'maksimalmal_omrade', 'regulert_omrade'].indexOf(row.key) === -1;
          });
          if (result.match && result.recommended_violation && result.recommended_violation.item) {
            var areaItem = result.recommended_violation.item;
            var existing = findingsState.filter(function (row) { return row.key === areaItem.key; })[0];
            if (!existing) {
              findingsState.push(areaItem);
            } else {
              existing.status = areaItem.status || existing.status;
              if (areaItem.notes) existing.notes = areaItem.notes;
              if (areaItem.law_text) existing.law_text = areaItem.law_text;
              if (areaItem.summary_text) existing.summary_text = areaItem.summary_text;
            }
          }
          renderFindings();
          if (result.match && result.hits && result.hits.length) {
            mergeSources(result.hits.map(function (hit) { return { name: hit.source || 'Karttreff', ref: hit.name || hit.layer || 'Områdetreff', url: hit.url || '' }; }));
          }
          updateCaseMap();
          loadGearSummary();
          if (controlType.value && (species.value || fisheryType.value) && gearType.value) loadRules();
        })
        .catch(function () {
          latestZoneResult = null;
          zoneResult.innerHTML = 'Kunne ikke sjekke områdestatus.';
          updateCaseMap();
        });
    }

    function applyAutoPosition(lat, lng) {
      mapState.manualPosition = false;
      latitude.value = Number(lat).toFixed(6);
      longitude.value = Number(lng).toFixed(6);
      mapState.lat = Number(latitude.value);
      mapState.lng = Number(longitude.value);
      updateCaseMap();
      checkZone();
      scheduleAutosave('Posisjon oppdatert');
    }

    function startLocationWatch() {
      if (!navigator.geolocation) {
        zoneResult.innerHTML = 'Denne enheten støtter ikke geolokasjon i nettleseren.';
        return;
      }
      mapState.followAutoPosition = true;
      if (mapState.lastDeviceLat !== null && mapState.lastDeviceLng !== null) {
        applyAutoPosition(mapState.lastDeviceLat, mapState.lastDeviceLng);
      }
      if (locationWatchId !== null) return;
      locationWatchId = navigator.geolocation.watchPosition(function (position) {
        mapState.lastDeviceLat = Number(position.coords.latitude.toFixed(6));
        mapState.lastDeviceLng = Number(position.coords.longitude.toFixed(6));
        if (mapState.followAutoPosition === false) return;
        applyAutoPosition(mapState.lastDeviceLat, mapState.lastDeviceLng);
      }, function (err) {
        zoneResult.innerHTML = 'Kunne ikke hente posisjon: ' + escapeHtml(err.message || err);
      }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
    }

    document.getElementById('btn-check-zone').addEventListener('click', checkZone);
    document.getElementById('btn-use-location').addEventListener('click', startLocationWatch);
    latitude.addEventListener('change', updateCaseMap);
    longitude.addEventListener('change', updateCaseMap);


    function updateExternalSearchLinks() {
      var query = [lookupName.value || suspectName.value || suspectNameCommercial.value || '', lookupIdentifier.value || '', suspectAddress.value || '', (suspectPostPlace ? suspectPostPlace.value : '') || ''].filter(Boolean).join(' ').trim();
      var btn1881 = document.getElementById('btn-search-1881');
      var btnGulesider = document.getElementById('btn-search-gulesider');
      if (btn1881) btn1881.onclick = function () { window.open('https://www.1881.no/?query=' + encodeURIComponent(query), '_blank', 'noopener'); };
      if (btnGulesider) btnGulesider.onclick = function () { window.open('https://www.gulesider.no/' + encodeURIComponent(query) + '/personer', '_blank', 'noopener'); };
    }

    function renderGearSummary(payload) {
      latestGearSummary = payload || null;
      if (observedGearCount && payload && payload.count_total !== undefined && payload.count_total !== null) { observedGearCount.value = payload.count_total; }
      if (!gearSummaryStatus) return;
      if (!payload) {
        gearSummaryStatus.innerHTML = 'Ingen oversikt over antall redskap tilgjengelig ennå.';
        return;
      }
      var parts = [];
      if (payload.limit !== null && payload.limit !== undefined) parts.push('<strong>Veiledende grense:</strong> ' + escapeHtml(String(payload.limit)));
      parts.push('<strong>Registrert i tidligere saker:</strong> ' + escapeHtml(String(payload.count_total || 0)));
      var statusClass = payload.warning ? 'status-warn' : 'status-ok';
      var body = '<div class="status-title ' + statusClass + '">' + (payload.warning ? 'Varsel om antall redskap' : 'Antall redskap innenfor veiledende grense') + '</div>';
      body += '<div class="small" style="margin-top:6px">' + parts.join(' · ') + '</div>';
      if (payload.warning) body += '<div class="small muted" style="margin-top:6px">' + escapeHtml(payload.warning) + '</div>';
      if (payload.matches && payload.matches.length) {
        body += '<div class="small muted" style="margin-top:6px">Tidligere saker: ' + payload.matches.slice(0, 5).map(function (row) { return (row.case_number || '?') + ' (' + (row.count || 0) + ')'; }).join(', ') + '</div>';
      }
      gearSummaryStatus.innerHTML = body;
    }

    function loadGearSummary() {
      if (!gearSummaryStatus) return;
      var params = new URLSearchParams({
        phone: suspectPhone.value || '',
        name: suspectName.value || suspectNameCommercial.value || '',
        address: [suspectAddress.value || '', (suspectPostPlace ? suspectPostPlace.value : '') || ''].filter(Boolean).join(', '),
        species: species.value || fisheryType.value || '',
        gear_type: gearType.value || '',
        area_name: areaName.value || '',
        area_status: areaStatus.value || '',
        control_type: controlType.value || '',
        vessel_reg: vesselReg.value || '',
        radio_call_sign: radioCallSign.value || '',
        hummer_participant_no: hummerParticipantNo.value || '',
        case_id: root.dataset.caseId || ''
      });
      fetch('/api/gear/summary?' + params.toString())
        .then(function (r) { return r.json(); })
        .then(function(payload){ renderGearSummary(payload); renderFindings(); })
        .catch(function () { if (gearSummaryStatus) gearSummaryStatus.innerHTML = 'Kunne ikke hente oversikt over antall redskap.'; });
    }

    function applyPerson(person, fallbackLast) {
      var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
      if (person.name) {
        suspectName.value = person.name;
        suspectNameCommercial.value = person.name;
        lookupName.value = person.name;
      }
      if (!isCommercial && person.address) suspectAddress.value = person.address;
      if (!isCommercial && person.post_place && suspectPostPlace) suspectPostPlace.value = person.post_place;
      if (!isCommercial && person.phone) {
        suspectPhone.value = person.phone;
        lookupIdentifier.value = person.phone;
      }
      if (!isCommercial && person.birthdate) suspectBirthdate.value = person.birthdate;
      if (person.vessel_name) vesselName.value = person.vessel_name;
      if (person.vessel_reg) {
        vesselReg.value = person.vessel_reg;
        if (isCommercial) lookupIdentifier.value = person.vessel_reg;
      }
      if (person.radio_call_sign) radioCallSign.value = person.radio_call_sign;
      if (!isCommercial && (person.hummer_participant_no || person.participant_no)) {
        hummerParticipantNo.value = person.hummer_participant_no || person.participant_no;
        if (!lookupIdentifier.value) lookupIdentifier.value = hummerParticipantNo.value;
      }
      var lastRegistered = person.hummer_last_registered || person.registered_date_display || person.last_registered_display || person.last_registered_year || fallbackLast || '';
      if (!isCommercial && hummerLastRegistered) hummerLastRegistered.value = lastRegistered;
      updateExternalSearchLinks();
      loadGearSummary();
      scheduleAutosave('Person/fartøy oppdatert');
      return lastRegistered;
    }

    function renderRegistryCandidates(candidates) {
      candidateState = (candidates || []).filter(function (item) { return item && (item.name || item.vessel_reg || item.vessel_name || item.participant_no); });
      if (!candidateState.length) {
        registryCandidates.classList.add('hidden');
        registryCandidates.innerHTML = '';
        return;
      }
      registryCandidates.classList.remove('hidden');
      registryCandidates.innerHTML = candidateState.map(function (item, index) {
        var primary = item.name || item.vessel_name || 'Ukjent';
        var secondary = [item.address || '', item.post_place || '', item.fisher_type || ''].filter(Boolean).join(item.address && item.post_place ? ', ' : '');
        var tertiary = [item.vessel_name || '', item.vessel_reg || '', item.radio_call_sign || '', item.participant_no || '', item.source || ''].filter(Boolean).join(' · ');
        return [
          '<article class="registry-candidate-card" data-index="' + index + '">',
          '<div><strong>' + escapeHtml(primary) + '</strong>',
          '<div class="muted small">' + escapeHtml(secondary) + '</div>',
          tertiary ? '<div class="muted small">' + escapeHtml(tertiary) + '</div>' : '',
          '</div>',
          '<button class="btn btn-secondary btn-small registry-candidate-apply" type="button">Bruk treff</button>',
          '</article>'
        ].join('');
      }).join('');
    }

    registryCandidates.addEventListener('click', function (event) {
      if (!event.target.classList.contains('registry-candidate-apply')) return;
      var card = event.target.closest('.registry-candidate-card');
      var item = candidateState[Number(card.dataset.index)] || null;
      if (!item) return;
      applyPerson(item, item.hummer_last_registered || '');
      renderHummerStatus({ found: Boolean(item.hummer_participant_no), person: item, message: item.hummer_participant_no ? 'Treff valgt fra kandidatlisten.' : 'Treff valgt, men ingen hummerregistrering funnet i kandidatdata.' });
      registryResult.innerHTML = '<strong>Treff valgt</strong><div class="small muted">Skjemaet er oppdatert fra valgt kandidat.</div>';
    });

    function applyHints(hints) {
      if (!hints) return;
      var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
      if (hints.name && !suspectName.value) {
        suspectName.value = hints.name;
        suspectNameCommercial.value = hints.name;
        lookupName.value = hints.name;
      }
      if (!isCommercial && hints.address && !suspectAddress.value) suspectAddress.value = hints.address;
      if (!isCommercial && hints.post_place && suspectPostPlace && !suspectPostPlace.value) suspectPostPlace.value = hints.post_place;
      if (!isCommercial && hints.phone && !suspectPhone.value) {
        suspectPhone.value = hints.phone;
        lookupIdentifier.value = hints.phone;
      }
      if (!isCommercial && hints.birthdate && !suspectBirthdate.value) suspectBirthdate.value = hints.birthdate;
      if (!isCommercial && hints.hummer_participant_no && !hummerParticipantNo.value) hummerParticipantNo.value = hints.hummer_participant_no;
      if (isCommercial && hints.vessel_reg && !vesselReg.value) {
        vesselReg.value = hints.vessel_reg;
        lookupIdentifier.value = hints.vessel_reg;
      }
      if (isCommercial && hints.radio_call_sign && !radioCallSign.value) radioCallSign.value = hints.radio_call_sign;
      if (hints.phone && !lookupIdentifier.value && !isCommercial) lookupIdentifier.value = hints.phone;
      updateExternalSearchLinks();
      scheduleAutosave('Autofyll oppdatert');
    }

    function renderHummerStatus(result) {
      if (!hummerRegistryStatus) return;
      if (!result) {
        hummerRegistryStatus.innerHTML = '<div class="status-title">Ingen registerstatus</div><div class="muted small">Ingen søk er kjørt ennå.</div>';
        return;
      }
      var person = (result.person || {});
      var lastSeason = person.registered_date_display || person.last_registered_display || person.hummer_last_registered || person.last_registered_year || '';
      var fisherType = person.fisher_type || person.type_fisher || '';
      var sourceLabel = person.source || result.source || '';
      if (result.found) {
        hummerRegistryStatus.innerHTML = [
          '<div class="status-title status-ok">Registrering funnet</div>',
          person.name ? '<div><strong>Navn:</strong> ' + escapeHtml(person.name) + '</div>' : '',
          (person.participant_no || person.hummer_participant_no) ? '<div><strong>Deltakernummer:</strong> ' + escapeHtml(person.participant_no || person.hummer_participant_no) + '</div>' : '',
          fisherType ? '<div><strong>Type fisker:</strong> ' + escapeHtml(fisherType) + '</div>' : '',
          lastSeason ? '<div><strong>Registrert / påmeldt:</strong> ' + escapeHtml(lastSeason) + '</div>' : '',
          sourceLabel ? '<div class="muted small">Kilde: ' + escapeHtml(sourceLabel) + '</div>' : '',
          result.message ? '<div class="muted small">' + escapeHtml(result.message) + '</div>' : ''
        ].join('');
      } else {
        hummerRegistryStatus.innerHTML = [
          '<div class="status-title status-warn">Ingen bekreftet registrering</div>',
          lastSeason ? '<div><strong>Registrert / påmeldt:</strong> ' + escapeHtml(lastSeason) + '</div>' : '',
          result.message ? '<div class="muted small">' + escapeHtml(result.message) + '</div>' : '<div class="muted small">Ingen treff i hummerregisteret for oppgitt navn eller deltakernummer.</div>'
        ].join('');
      }
    }

    function applyRegistryResult(result) {
      var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
      applyHints(result.hints || {});
      var fallbackLast = (result.hummer_check && result.hummer_check.person && (result.hummer_check.person.last_registered_display || result.hummer_check.person.last_registered_year)) || '';
      renderRegistryCandidates(result.candidates || []);
      renderHummerStatus(result.hummer_check || null);
      if (!result.found) {
        if (!isCommercial && hummerLastRegistered) hummerLastRegistered.value = fallbackLast;
        registryResult.innerHTML = '<strong>Ikke søkbar / ingen direkte treff</strong>';
        renderRegistryCandidates((result.candidates || []));
        updateExternalSearchLinks();
        loadGearSummary();
        return;
      }
      var person = result.person || {};
      var lastRegistered = applyPerson(person, fallbackLast);
      var messages = ['<strong>Treff</strong>'];
      if (person.match_reason) messages.push('<div class="small muted">Matchgrunnlag: ' + escapeHtml(person.match_reason) + '</div>');
      if (result.hummer_check) messages.push('<div class="small muted">Hummerregister: ' + escapeHtml(result.hummer_check.found ? (result.hummer_check.message || 'treff') : (result.hummer_check.message || 'ingen treff')) + '</div>');
      if (lastRegistered) messages.push('<div class="small muted">Sist registrert i hummerregister: ' + escapeHtml(lastRegistered) + '</div>');
      if (result.vipps_message) messages.push('<div class="small muted">' + escapeHtml(result.vipps_message) + '</div>');
      registryResult.innerHTML = messages.join('');
      renderRegistryCandidates(result.candidates || []);
      updateExternalSearchLinks();
      loadGearSummary();
      scheduleAutosave('Registertreff oppdatert');
      if (person.source_url) mergeSources([{ name: person.source || 'Register', ref: 'Oppslag', url: person.source_url }]);
    }

    function lookupRegistry() {
      var identifier = lookupIdentifier.value || '';
      var inferred = classifyLookupIdentifier(identifier);
      var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
      if (!isCommercial && inferred.phone) suspectPhone.value = inferred.phone;
      if (!isCommercial && inferred.hummer_participant_no) hummerParticipantNo.value = inferred.hummer_participant_no;
      if (inferred.vessel_reg) vesselReg.value = inferred.vessel_reg;
      if (inferred.radio_call_sign) radioCallSign.value = inferred.radio_call_sign;
      var params = new URLSearchParams({
        phone: (!isCommercial ? (suspectPhone.value || inferred.phone || '') : ''),
        vessel_reg: (vesselReg.value || inferred.vessel_reg || ''),
        radio_call_sign: (radioCallSign.value || inferred.radio_call_sign || ''),
        name: lookupName.value || suspectName.value || suspectNameCommercial.value || '',
        tag_text: lookupText.value || '',
        hummer_participant_no: (!isCommercial ? (hummerParticipantNo.value || inferred.hummer_participant_no || '') : '')
      });
      registryResult.innerHTML = 'Søker i register ...';
      updateExternalSearchLinks();
      fetch(root.dataset.registryUrl + '?' + params.toString())
        .then(function (r) { return r.json(); })
        .then(applyRegistryResult)
        .catch(function () { registryResult.innerHTML = '<strong>Ikke søkbar / ingen direkte treff</strong>'; });
    }
    document.getElementById('btn-lookup-person').addEventListener('click', lookupRegistry);

    function markerItemHasTeineCounter(item) {
      if (!item) return false;
      var key = String(item.key || '');
      return key === 'hummer_merking' || key === 'vak_merking' || key === 'samleteine_merking';
    }

    function evaluateMarkerLimit(card, item) {
      if (!card || !item || !markerItemHasTeineCounter(item)) return;
      var totalInput = card.querySelector('.marker-total');
      if (!totalInput) return;
      var total = Number(totalInput.value || 0);
      var limit = latestGearSummary && latestGearSummary.limit !== null && latestGearSummary.limit !== undefined ? Number(latestGearSummary.limit) : null;
      var statusSel = card.querySelector('.finding-status');
      if (!limit || !statusSel) return;
      if (total > limit) {
        var overshoot = Math.max(total - limit, 0);
        item.auto_note = 'Ved kontroll ble det registrert ' + total + ' teiner/redskap i dette kontrollpunktet. Tillatt antall etter gjeldende kontrollgrunnlag er ' + limit + '. Overskridelsen utgjør ' + overshoot + ' teiner/redskap.';
        if (statusSel.value !== 'avvik') statusSel.value = 'avvik';
        item.status = 'avvik';
        var btn = card.querySelector('.finding-evidence-btn');
        if (btn) btn.classList.remove('hidden');
      } else {
        item.auto_note = '';
      }
      findingsInput.value = JSON.stringify(findingsState);
    }

    function generateBasisText() {
      var basis = String(caseBasis.value || 'patruljeobservasjon');
      var preset = String((document.getElementById('basis_preset') || {}).value || 'auto');
      var speciesLabel = String(species.value || fisheryType.value || 'aktuelt fiskeri').trim();
      var gearLabel = String(gearType.value || 'redskap').trim();
      var sourceName = (basisSourceName.value || '').trim();
      var dateLabel = currentControlDateLabel();
      var area = areaContextForNarrative();
      var locationLabel = (locationName.value || area || 'aktuelt kontrollområde').trim();
      var placeLabel = area ? ('i ' + area) : ('ved ' + locationLabel);
      var theme = [controlType.value || '', speciesLabel, gearLabel].filter(Boolean).join(' / ');

      function basisOpeningPhrase() {
        var normalized = String(sourceName || '').trim().toLowerCase();
        var defaultSources = {
          '': true,
          'kystvaktpatrulje': true,
          'kv patrulje': true,
          'kystvakten lettbåt': true,
          'kystvaktens lettbåt': true
        };
        if (basis !== 'tips' && basis !== 'anmeldelse' && !defaultSources[normalized]) {
          return 'Det ble fra lettbåt fra ' + sourceName + ' gjennomført';
        }
        return 'Det ble fra Kystvakten lettbåt gjennomført';
      }

      function autoPreset() {
        var gearLower = gearLabel.toLowerCase();
        var speciesLower = speciesLabel.toLowerCase();
        if (basis === 'anmeldelse') return 'followup-report';
        if (basis === 'tips' && area) return 'tips-area';
        if (basis === 'tips' && (speciesLower.indexOf('hummer') !== -1 || gearLower.indexOf('teine') !== -1 || gearLower.indexOf('ruse') !== -1)) return 'tips-redskap';
        if (speciesLower.indexOf('hummer') !== -1) return 'patrol-hummer';
        if (gearLower.indexOf('samleteine') !== -1 || gearLower.indexOf('sanketeine') !== -1) return 'patrol-samleteine';
        if (gearLower.indexOf('garn') !== -1 || gearLower.indexOf('lenke') !== -1) return 'patrol-garnlenke';
        if (gearLower.indexOf('teine') !== -1 || gearLower.indexOf('ruse') !== -1) return 'patrol-fixed';
        if (basis === 'tips') return 'tips-redskap';
        return 'patrol-general';
      }

      if (preset === 'auto') preset = autoPreset();

      var opening = basisOpeningPhrase();
      var texts = {
        'patrol-general': opening + ' planlagt kontroll den ' + dateLabel + ' med fokus på ' + theme + ' ' + placeLabel + '. Patruljeformålet var å kontrollere identitet, ansvarssubjekt, posisjon, redskap, fangst, oppbevaring og øvrige vilkår av betydning for regelverket, samt å dokumentere faktiske observasjoner på en måte som kan gi grunnlag for videre vurdering og eventuell anmeldelse.',
        'patrol-fixed': opening + ' målrettet kontroll av faststående redskap den ' + dateLabel + ' ' + placeLabel + '. Patruljeformålet var å kontrollere plassering, merking av vak og redskap, røkting, fangst og oppbevaring, samt å sikre notoritet rundt eventuelle avvik knyttet til bruk av teiner, ruser eller annet faststående redskap.',
        'patrol-hummer': opening + ' hummeroppsyn den ' + dateLabel + ' ' + placeLabel + '. Patruljeformålet var å kontrollere påmelding til hummerfiske, deltakernummer, merking av vak og hummerredskap, antall teiner, fluktåpninger, rømningshull, minstemål, oppbevaring og eventuelle område- eller sesongbegrensninger, samt å dokumentere faktiske forhold i en anmeldelsesegnet form.',
        'patrol-samleteine': opening + ' særskilt kontroll av samleteine / sanketeine den ' + dateLabel + ' ' + placeLabel + '. Patruljeformålet var å kontrollere om redskapen var korrekt merket, om oppbevaring av hummer i sjø skjedde i samsvar med regelverket, og om eventuelle lengdemålinger, registreringer og øvrige vilkår var oppfylt og tilstrekkelig dokumentert.',
        'patrol-garnlenke': opening + ' kontroll av garnlenke / lenkefiske den ' + dateLabel + ' ' + placeLabel + '. Patruljeformålet var å dokumentere start- og sluttposisjon, kontrollere merking og plassering av vak, avklare ansvarlig fartøy eller person og vurdere om redskapen sto i samsvar med gjeldende område- og redskapsbestemmelser.',
        'tips-redskap': opening + ' kontroll den ' + dateLabel + ' etter mottatte opplysninger om mulig ulovlig bruk av redskap ' + placeLabel + '. Formålet var å verifisere tipset gjennom stedlig kontroll, identifisere ansvarlig person eller fartøy, og sikre objektiv dokumentasjon av redskap, posisjon, fangst og andre forhold som kunne ha betydning for en eventuell anmeldelse.',
        'tips-area': opening + ' kontroll den ' + dateLabel + ' etter mottatte opplysninger om mulig fiske eller oppbevaring i fredningsområde, stengt felt eller annet regulert område ' + placeLabel + '. Formålet var å fastslå faktisk posisjon, kontrollere valgt redskap og dokumentere om gjeldende områdebestemmelser var overholdt eller brutt.',
        'tips-minstemal': opening + ' kontroll den ' + dateLabel + ' etter mottatte opplysninger om mulig fangst eller oppbevaring under minstemål ' + placeLabel + '. Formålet var å gjennomføre kontrollmålinger, dokumentere fangstens størrelse og avklare om det forelå overtredelse av minstemålsreglene eller andre tilknyttede bestemmelser.',
        'followup-report': opening + ' kontroll den ' + dateLabel + ' som oppfølging av tidligere registrert sak eller anmeldelse ' + placeLabel + '. Formålet var å kontrollere faktum på nytt, sikre ytterligere bevis og avklare om det forelå nye eller vedvarende brudd på regelverket, herunder forhold av betydning for etterfølgende saksbehandling.',
      };

      if (!texts[preset]) {
        texts[preset] = opening + ' kontroll den ' + dateLabel + ' med fokus på ' + theme + ' ' + placeLabel + '. Patruljeformålet var å kontrollere redskap, posisjon, fangst, oppbevaring og identitetsopplysninger, og å dokumentere eventuelle avvik i en form som kan brukes videre i oppsummering og anmeldelse.';
      }

      if (basis === 'tips' && preset.indexOf('tips-') !== 0) {
        texts[preset] += ' Kontrollen var samtidig utløst av mottatte opplysninger som skulle kontrolleres og holdes opp mot det som faktisk ble observert på stedet.';
      } else if (basis === 'anmeldelse' && preset !== 'followup-report') {
        texts[preset] += ' Kontrollen ble også sett i sammenheng med tidligere registrerte opplysninger i saken.';
      }

      basisDetails.value = texts[preset];
      scheduleAutosave('Standardtekst satt inn');
    }
    document.getElementById('btn-generate-basis').addEventListener('click', generateBasisText);
    var polishBasisBtn = document.getElementById('btn-polish-basis');
    if (polishBasisBtn) polishBasisBtn.addEventListener('click', function () {
      fetch('/api/text/polish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'basis', text: basisDetails.value, case_basis: caseBasis.value, source_name: basisSourceName.value || '', location: locationName.value || areaContextForNarrative() || '' })
      }).then(function (r) { return r.json(); }).then(function (payload) {
        if (payload && payload.text) { basisDetails.value = payload.text; scheduleAutosave('Rettet grunnlagstekst'); }
      }).catch(function () {});
    });

    var autosaveStatus = document.getElementById('autosave-status');
    function setAutosaveStatus(textLabel, mode) {
      if (!autosaveStatus) return;
      autosaveStatus.textContent = textLabel;
      autosaveStatus.classList.remove('is-saving', 'is-saved', 'is-error');
      if (mode) autosaveStatus.classList.add(mode);
    }

    function formFingerprint() {
      return JSON.stringify({
        control_type: controlType.value || '', fishery_type: fisheryType.value || '', species: species.value || '', gear_type: gearType.value || '',
        lat: latitude.value || '', lng: longitude.value || '', area_status: areaStatus.value || '', area_name: areaName.value || '', location_name: locationName.value || '',
        suspect_name: suspectName.value || '', suspect_address: suspectAddress.value || '', suspect_post_place: (suspectPostPlace ? suspectPostPlace.value : '') || '', suspect_phone: suspectPhone.value || '',
        hummer_participant_no: hummerParticipantNo.value || '', vessel_reg: vesselReg.value || '', radio_call_sign: radioCallSign.value || '',
        findings: findingsState, crew: crewState, external: externalActorsState, interviews: interviewState, notes: notes ? notes.value : '', summary: summary ? summary.value : '', hearing: hearingText ? hearingText.value : ''
      });
    }

    function performAutosave(reason) {
      if (!root.dataset.autosaveUrl || autosaveInFlight) return;
      var fingerprint = formFingerprint();
      if (fingerprint === lastAutosaveFingerprint) return;
      autosaveInFlight = true;
      setAutosaveStatus('Lagrer …', 'is-saving');
      var formData = new FormData(form);
      formData.set('findings_json', JSON.stringify(findingsState));
      formData.set('source_snapshot_json', JSON.stringify(sourcesState));
      formData.set('crew_json', JSON.stringify(crewState));
      formData.set('external_actors_json', JSON.stringify(externalActorsState));
      formData.set('interview_sessions_json', JSON.stringify(interviewState));
      fetch(root.dataset.autosaveUrl, { method: 'POST', body: formData })
        .then(function (r) { return r.json(); })
        .then(function (payload) {
          autosaveInFlight = false;
          lastAutosaveFingerprint = fingerprint;
          setAutosaveStatus('Lagret ' + new Date().toLocaleTimeString('nb-NO', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), 'is-saved');
        })
        .catch(function () {
          autosaveInFlight = false;
          setAutosaveStatus('Autosave feilet', 'is-error');
        });
    }

    function scheduleAutosave(reason) {
      if (autosaveTimer) window.clearTimeout(autosaveTimer);
      autosaveTimer = window.setTimeout(function () { performAutosave(reason); }, 900);
    }

    document.addEventListener('input', function (event) {
      var target = event.target;
      if (!target) return;
      if (target.form === form || target.getAttribute('form') === 'case-form' || target.closest('#case-form')) scheduleAutosave('Skjemadata endret');
    });
    document.addEventListener('change', function (event) {
      var target = event.target;
      if (!target) return;
      if (target.form === form || target.getAttribute('form') === 'case-form' || target.closest('#case-form')) scheduleAutosave('Skjemadata endret');
    });

    controlType.addEventListener('change', function () { syncOptions(); loadRules(); loadGearSummary(); });
    fisheryType.addEventListener('change', function () { if (!species.value || species.value === fisheryType.dataset.lastValue) species.value = fisheryType.value; fisheryType.dataset.lastValue = fisheryType.value; loadRules(); loadGearSummary(); });
    gearType.addEventListener('change', function () { loadRules(); loadGearSummary(); });
    species.addEventListener('change', function () { loadRules(); loadGearSummary(); });
    startTime.addEventListener('change', loadRules);
    suspectNameCommercial.addEventListener('input', function () { suspectName.value = suspectNameCommercial.value; lookupName.value = suspectNameCommercial.value; updateExternalSearchLinks(); loadGearSummary(); });
    suspectName.addEventListener('input', function () { suspectNameCommercial.value = suspectName.value; lookupName.value = suspectName.value; updateExternalSearchLinks(); loadGearSummary(); });
    suspectAddress.addEventListener('input', function () { updateExternalSearchLinks(); loadGearSummary(); });
    suspectPhone.addEventListener('input', function () { updateExternalSearchLinks(); loadGearSummary(); });
    if (observedGearCount) observedGearCount.addEventListener('input', loadGearSummary);

    findingsList.addEventListener('change', function (event) {
      var card = event.target.closest('.finding-card');
      if (!card) return;
      var idx = Number(card.dataset.index);
      if (event.target.classList.contains('finding-status')) {
        findingsState[idx].status = event.target.value;
        if (event.target.value !== 'avvik') {
          findingsState[idx].deviation_units = findingsState[idx].deviation_units || [];
        }
        findingsInput.value = JSON.stringify(findingsState);
        renderFindings();
        scheduleAutosave('Kontrollpunktstatus endret');
      }
    });
    findingsList.addEventListener('input', function (event) {
      var card = event.target.closest('.finding-card');
      if (!card) return;
      var idx = Number(card.dataset.index);
      var item = findingsState[idx];
      if (event.target.classList.contains('finding-notes')) {
        item.notes = event.target.value;
        findingsInput.value = JSON.stringify(findingsState);
        scheduleAutosave('Kontrollpunktnotat oppdatert');
      }
      if (event.target.classList.contains('measurement-reference') || event.target.classList.contains('measurement-length') || event.target.classList.contains('measurement-photo') || event.target.classList.contains('measurement-note')) {
        var rowEl = event.target.closest('.measurement-row');
        if (!rowEl) return;
        var mIdx = Number(rowEl.dataset.measureIndex);
        var rows = ensureMeasurementState(item);
        rows[mIdx] = rows[mIdx] || { reference: '', length_cm: '', photo_ref: '', note: '' };
        rows[mIdx].reference = rowEl.querySelector('.measurement-reference').value;
        rows[mIdx].length_cm = rowEl.querySelector('.measurement-length').value;
        rows[mIdx].photo_ref = rowEl.querySelector('.measurement-photo').value;
        rows[mIdx].note = rowEl.querySelector('.measurement-note').value;
        item.measurement_summary = measurementSummaryText(item);
        var preview = card.querySelector('.finding-measurements .structured-preview');
        if (preview) preview.textContent = item.measurement_summary;
        findingsInput.value = JSON.stringify(findingsState);
        scheduleAutosave('Lengdemåling oppdatert');
      }
      if (event.target.classList.contains('marker-current') || event.target.classList.contains('marker-start') || event.target.classList.contains('marker-end') || event.target.classList.contains('marker-total') || event.target.classList.contains('marker-approved') || event.target.classList.contains('marker-deviations')) {
        var pos = ensureMarkerState(item);
        pos.current = (card.querySelector('.marker-current') || {}).value || '';
        pos.start = (card.querySelector('.marker-start') || {}).value || '';
        pos.end = (card.querySelector('.marker-end') || {}).value || '';
        pos.total = (card.querySelector('.marker-total') || {}).value || '';
        pos.approved = (card.querySelector('.marker-approved') || {}).value || '';
        pos.deviations = (card.querySelector('.marker-deviations') || {}).value || '';
        item.marker_summary = markerSummaryText(item);
        var mp = card.querySelector('.finding-marker-positions .structured-preview');
        if (mp) mp.textContent = item.marker_summary;
        evaluateMarkerLimit(card, item);
        findingsInput.value = JSON.stringify(findingsState);
        scheduleAutosave('Markeringsdata oppdatert');
      }
      if (event.target.classList.contains('deviation-seizure-ref') || event.target.classList.contains('deviation-gear-kind') || event.target.classList.contains('deviation-gear-ref') || event.target.classList.contains('deviation-quantity') || event.target.classList.contains('deviation-violation') || event.target.classList.contains('deviation-note')) {
        var dRowEl = event.target.closest('.deviation-row');
        if (!dRowEl) return;
        var dIdx = Number(dRowEl.dataset.devIndex);
        var dRows = ensureDeviationState(item);
        dRows[dIdx] = dRows[dIdx] || { seizure_ref: '', gear_kind: '', gear_ref: '', quantity: '', violation: '', note: '' };
        dRows[dIdx].gear_kind = (dRowEl.querySelector('.deviation-gear-kind') || {}).value || '';
        dRows[dIdx].gear_ref = (dRowEl.querySelector('.deviation-gear-ref') || {}).value || '';
        dRows[dIdx].quantity = (dRowEl.querySelector('.deviation-quantity') || {}).value || '';
        dRows[dIdx].violation = (dRowEl.querySelector('.deviation-violation') || {}).value || '';
        dRows[dIdx].note = (dRowEl.querySelector('.deviation-note') || {}).value || '';
        syncDeviationDefaults(item);
        item.deviation_summary = deviationSummaryText(item);
        var dp = card.querySelector('.finding-deviations .structured-preview');
        if (dp) dp.textContent = item.deviation_summary;
        findingsInput.value = JSON.stringify(findingsState);
        scheduleAutosave('Avviksrad oppdatert');
      }
    });
    findingsList.addEventListener('click', function (event) {
      var card = event.target.closest('.finding-card');
      if (!card) return;
      var idx = Number(card.dataset.index);
      var item = findingsState[idx];
      if (event.target.classList.contains('help-toggle')) {
        var box = card.querySelector('.help-text');
        if (box) box.classList.toggle('hidden');
      }
      if (event.target.classList.contains('finding-evidence-btn')) {
        updateSelectedFinding(item);
      }
      if (event.target.classList.contains('measurement-add')) {
        ensureMeasurementState(item).push({ reference: '', length_cm: '', photo_ref: '', note: '' });
        renderFindings();
        scheduleAutosave('Ny lengdemåling lagt til');
      }
      if (event.target.classList.contains('measurement-remove')) {
        var rowEl = event.target.closest('.measurement-row');
        var mIdx = Number(rowEl.dataset.measureIndex);
        ensureMeasurementState(item).splice(mIdx, 1);
        item.measurement_summary = measurementSummaryText(item);
        renderFindings();
        scheduleAutosave('Lengdemåling fjernet');
      }
      if (event.target.classList.contains('marker-current-fill') || event.target.classList.contains('marker-current-refresh')) {
        ensureMarkerState(item).current = currentCoordText();
        item.marker_summary = markerSummaryText(item);
        renderFindings();
        scheduleAutosave('Kontrollørposisjon satt');
      }
      if (event.target.classList.contains('marker-start-fill')) {
        ensureMarkerState(item).start = currentCoordText();
        item.marker_summary = markerSummaryText(item);
        renderFindings();
        scheduleAutosave('Startposisjon satt');
      }
      if (event.target.classList.contains('marker-end-fill')) {
        ensureMarkerState(item).end = currentCoordText();
        item.marker_summary = markerSummaryText(item);
        renderFindings();
        scheduleAutosave('Sluttposisjon satt');
      }
      if (event.target.classList.contains('deviation-add')) {
        ensureDeviationState(item).push({ seizure_ref: '', gear_kind: String((document.getElementById('gear_type') || {}).value || 'Teine').trim() || 'Teine', gear_ref: '', quantity: '1', violation: suggestedDeviationText(item), note: '' });
        renderFindings();
        scheduleAutosave('Ny avviksrad lagt til');
      }
      if (event.target.classList.contains('deviation-remove')) {
        var dRow = event.target.closest('.deviation-row');
        var dIdx = Number(dRow.dataset.devIndex);
        ensureDeviationState(item).splice(dIdx, 1);
        item.deviation_summary = deviationSummaryText(item);
        renderFindings();
        scheduleAutosave('Avviksrad fjernet');
      }
      if (event.target.classList.contains('deviation-evidence-link')) {
        var dRow2 = event.target.closest('.deviation-row');
        var dIdx2 = Number(dRow2.dataset.devIndex);
        var chosen = ensureDeviationState(item)[dIdx2] || null;
        updateSelectedFinding(item, chosen);
      }
    });

    document.getElementById('btn-clear-evidence-target').addEventListener('click', function () {
      evidenceFindingKey.value = '';
      evidenceLawText.value = '';
      if (evidenceSeizureRef) evidenceSeizureRef.value = '';
      evidenceCaption.value = '';
      evidenceReason.value = '';
      selectedFindingCard.innerHTML = 'Velg et kontrollpunkt med avvik i steg 4 for å forhåndsfylle hjemmel og begrunnelse.';
    });

    function serializeInterviews() {
      if (interviewInput) interviewInput.value = JSON.stringify(interviewState);
    }

    function buildInterviewCombinedText() {
      if (!interviewState.length) return hearingText.value || '';
      return interviewState.map(function (entry, idx) {
        var header = 'Avhør ' + (idx + 1) + ': ' + (entry.name || 'Ukjent');
        var lines = [header, 'Rolle: ' + (entry.role || 'Avhørt')];
        if (entry.method || entry.place) lines.push('Sted/metode: ' + [entry.method || '', entry.place || ''].filter(Boolean).join(' - '));
        if (entry.start || entry.end) lines.push('Tid: ' + [entry.start || '', entry.end || ''].filter(Boolean).join(' til '));
        if (entry.summary) lines.push('Sammendrag: ' + entry.summary);
        lines.push(entry.transcript || '');
        return lines.join('\n');
      }).join('\n\n');
    }

    function renderInterviews() {
      var wrap = document.getElementById('interview-list');
      if (!wrap) return;
      if (!interviewState.length) {
        wrap.innerHTML = '<div class="callout">Ingen avhør registrert ennå.</div>';
        serializeInterviews();
        return;
      }
      wrap.innerHTML = interviewState.map(function (entry, idx) {
        return [
          '<article class="interview-card" data-index="' + idx + '">',
          '<div class="grid-two compact-grid-form">',
          '<label><span>Navn</span><input class="interview-name" value="' + escapeHtml(entry.name || '') + '" /></label>',
          '<label><span>Rolle</span><input class="interview-role" value="' + escapeHtml(entry.role || 'Avhørt') + '" /></label>',
          '<label><span>Avhørsmåte</span><input class="interview-method" value="' + escapeHtml(entry.method || 'Telefon / på stedet') + '" /></label>',
          '<label><span>Sted</span><input class="interview-place" value="' + escapeHtml(entry.place || locationName.value || '') + '" /></label>',
          '<label><span>Start</span><input class="interview-start" type="datetime-local" value="' + escapeHtml(entry.start || startTime.value || '') + '" /></label>',
          '<label><span>Slutt</span><input class="interview-end" type="datetime-local" value="' + escapeHtml(entry.end || endTime.value || '') + '" /></label>',
          '<label class="span-2"><span>Transkripsjon / forklaring</span><textarea class="interview-transcript" rows="6">' + escapeHtml(entry.transcript || '') + '</textarea></label>',
          '<label class="span-2"><span>AI-sammendrag</span><textarea class="interview-summary" rows="3">' + escapeHtml(entry.summary || '') + '</textarea></label>',
          '</div>',
          '<div class="actions-row wrap margin-top-s">',
          '<button type="button" class="btn btn-secondary btn-small interview-summarize">Lag sammendrag</button>',
          '<button type="button" class="btn btn-secondary btn-small interview-polish">Rettskriv</button>',
          '<button type="button" class="btn btn-danger btn-small interview-remove">Fjern</button>',
          '</div>',
          '</article>'
        ].join('');
      }).join('');
      serializeInterviews();
    }

    function syncInterviewsFromDom() {
      document.querySelectorAll('#interview-list .interview-card').forEach(function (card) {
        var idx = Number(card.dataset.index);
        interviewState[idx] = interviewState[idx] || {};
        interviewState[idx].name = card.querySelector('.interview-name').value;
        interviewState[idx].role = card.querySelector('.interview-role').value;
        interviewState[idx].method = card.querySelector('.interview-method').value;
        interviewState[idx].place = card.querySelector('.interview-place').value;
        interviewState[idx].start = card.querySelector('.interview-start').value;
        interviewState[idx].end = card.querySelector('.interview-end').value;
        interviewState[idx].transcript = card.querySelector('.interview-transcript').value;
        interviewState[idx].summary = card.querySelector('.interview-summary').value;
      });
      serializeInterviews();
      hearingText.value = buildInterviewCombinedText();
    }

    function activeInterviewTranscript() {
      var focused = document.activeElement;
      if (focused && focused.classList && focused.classList.contains('interview-transcript')) return focused;
      var first = document.querySelector('#interview-list .interview-transcript');
      return first || hearingText;
    }

    var addInterviewBtn = document.getElementById('btn-add-interview');
    if (addInterviewBtn) addInterviewBtn.addEventListener('click', function () {
      interviewState.push({ name: suspectName.value || suspectNameCommercial.value || '', role: 'Avhørt', method: 'Telefon / på stedet', place: locationName.value || '', start: startTime.value || '', end: endTime.value || '', transcript: '', summary: '' });
      renderInterviews();
    });
    var syncInterviewsBtn = document.getElementById('btn-sync-interviews');
    if (syncInterviewsBtn) syncInterviewsBtn.addEventListener('click', syncInterviewsFromDom);
    document.getElementById('interview-list').addEventListener('input', function () { syncInterviewsFromDom(); });
    document.getElementById('interview-list').addEventListener('click', function (event) {
      var card = event.target.closest('.interview-card');
      if (!card) return;
      var idx = Number(card.dataset.index);
      if (event.target.classList.contains('interview-remove')) {
        interviewState.splice(idx, 1);
        renderInterviews();
        hearingText.value = buildInterviewCombinedText();
        return;
      }
      if (event.target.classList.contains('interview-summarize') || event.target.classList.contains('interview-polish')) {
        syncInterviewsFromDom();
        var entry = interviewState[idx] || {};
        var mode = event.target.classList.contains('interview-summarize') ? 'interview_summary' : 'generic';
        var sourceText = mode === 'interview_summary' ? (entry.transcript || '') : ((entry.transcript || '') + '\n' + (entry.summary || ''));
        fetch('/api/text/polish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: mode, text: sourceText, subject: entry.name || '' })
        }).then(function (r) { return r.json(); }).then(function (payload) {
          if (mode === 'interview_summary') entry.summary = payload.text || entry.summary;
          else entry.transcript = payload.text || entry.transcript;
          renderInterviews();
          hearingText.value = buildInterviewCombinedText();
        }).catch(function () {});
      }
    });

    function uploadAudioFile(file) {
      if (!file) return;
      var audioStatus = document.getElementById('audio-status');
      var activeTranscript = activeInterviewTranscript();
      var activeCard = activeTranscript.closest ? activeTranscript.closest('.interview-card') : null;
      var labelName = activeCard ? (activeCard.querySelector('.interview-name').value || 'ukjent') : (suspectName.value || suspectNameCommercial.value || 'ukjent');
      var formData = new FormData();
      formData.append('caption', 'Lydopptak avhør - ' + labelName);
      formData.append('file', file, file.name || 'avhor.webm');
      audioStatus.innerHTML = 'Laster opp lydfil ...';
      fetch('/cases/' + root.dataset.caseId + '/evidence', { method: 'POST', body: formData }).then(function () {
        audioStatus.innerHTML = 'Lydfil lastet opp. Siden oppdateres ...';
        window.location.reload();
      }).catch(function () { audioStatus.innerHTML = 'Kunne ikke laste opp lydfil.'; });
    }

    var btnUploadAudio = document.getElementById('btn-upload-audio');
    if (btnUploadAudio) btnUploadAudio.addEventListener('click', function () {
      var input = document.getElementById('audio-upload-input');
      if (!input.files || !input.files[0]) { document.getElementById('audio-status').innerHTML = 'Velg en lydfil først.'; return; }
      uploadAudioFile(input.files[0]);
    });

    var speechRec = null;
    function getSpeechRecognition() { return window.SpeechRecognition || window.webkitSpeechRecognition || null; }
    document.getElementById('btn-start-dictation').addEventListener('click', function () {
      var SR = getSpeechRecognition();
      if (!SR) { alert('Nettleseren støtter ikke diktering her.'); return; }
      speechRec = new SR();
      speechRec.lang = 'nb-NO';
      speechRec.continuous = true;
      speechRec.interimResults = true;
      speechRec.onresult = function (event) {
        var out = '';
        for (var i = event.resultIndex; i < event.results.length; i++) out += event.results[i][0].transcript;
        var target = activeInterviewTranscript();
        target.value = (target.value + ' ' + out).trim();
        syncInterviewsFromDom();
      };
      speechRec.start();
    });
    document.getElementById('btn-stop-dictation').addEventListener('click', function () { if (speechRec) speechRec.stop(); });

    document.getElementById('btn-start-recording').addEventListener('click', function () {
      var audioStatus = document.getElementById('audio-status');
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { audioStatus.innerHTML = 'Nettleseren støtter ikke lydopptak.'; return; }
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
        mediaChunks = [];
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = function (event) { if (event.data && event.data.size) mediaChunks.push(event.data); };
        mediaRecorder.onstop = function () {
          var blob = new Blob(mediaChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
          var file = new File([blob], 'avhor-' + Date.now() + '.webm', { type: blob.type || 'audio/webm' });
          uploadAudioFile(file);
          stream.getTracks().forEach(function (track) { track.stop(); });
        };
        mediaRecorder.start();
        audioStatus.innerHTML = 'Lydopptak pågår ...';
      }).catch(function (err) { document.getElementById('audio-status').innerHTML = 'Kunne ikke starte lydopptak: ' + escapeHtml(err.message || err); });
    });
    document.getElementById('btn-stop-recording').addEventListener('click', function () {
      if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
    });


    function ensureTesseract() {
      if (window.Tesseract) return Promise.resolve(window.Tesseract);
      return new Promise(function (resolve, reject) {
        var s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js';
        s.onload = function () { resolve(window.Tesseract); };
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }

    var btnRunOcr = document.getElementById('btn-run-ocr');
    if (btnRunOcr) btnRunOcr.addEventListener('click', function () {
      var input = document.getElementById('ocr-image');
      if (!input || !input.files || !input.files[0]) { registryResult.innerHTML = 'Velg et bilde først.'; return; }
      registryResult.innerHTML = 'Kjører OCR på bilde ...';
      ensureTesseract().then(function (Tesseract) {
        return Tesseract.recognize(input.files[0], 'nor+eng', { tessedit_pageseg_mode: 6, preserve_interword_spaces: '1' });
      }).then(function (result) {
        lookupText.value = result.data.text || '';
        registryResult.innerHTML = '<strong>OCR fullført</strong><div class="small muted">Tekst er hentet ut fra bildet og brukes nå i søket.</div>';
        lookupRegistry();
      }).catch(function (err) {
        registryResult.innerHTML = 'OCR feilet: ' + escapeHtml(err.message || err);
      });
    });

    renderInterviews();
    hearingText.value = buildInterviewCombinedText() || hearingText.value;
    startLocationWatch();
    document.getElementById('btn-generate-summary').addEventListener('click', function () {
      var payload = {
        case_basis: caseBasis.value,
        control_type: controlType.value,
        species: species.value || fisheryType.value || '',
        fishery_type: fisheryType.value,
        gear_type: gearType.value,
        location_name: locationName.value,
        area_name: areaName.value,
        area_status: areaStatus.value,
        suspect_name: suspectName.value || suspectNameCommercial.value,
        basis_details: basisDetails.value,
        start_time: startTime.value,
        latitude: latitude.value,
        longitude: longitude.value,
        findings: findingsState
      };
      summaryPreview.innerHTML = 'Genererer utkast ...';
      fetch(root.dataset.summaryUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (r) { return r.json(); })
        .then(function (drafts) {
          if (!basisDetails.value && drafts.basis_details) basisDetails.value = drafts.basis_details;
          if (!notes.value && drafts.notes) notes.value = drafts.notes;
          if (!summary.value && drafts.summary) summary.value = drafts.summary;
          summaryPreview.innerHTML = '<strong>Genererte utkast</strong><div class="small muted">Grunnlag, notat og sammendrag er oppdatert i skjemaet.</div><div class="preview-text">' + escapeHtml(drafts.complaint_preview || drafts.summary || '') + '</div>';
        }).catch(function () { summaryPreview.innerHTML = 'Kunne ikke generere tekst akkurat nå.'; });
    });

    function performManualSave() {
      if (!root.dataset.autosaveUrl) return;
      if (caseMap && caseMap._kvLeafletMap) {
        try {
          var center = caseMap._kvLeafletMap.getCenter();
          sessionStorage.setItem('kv-map-view:' + (caseMap.id || 'case-map'), JSON.stringify({ lat: center.lat, lng: center.lng, zoom: caseMap._kvLeafletMap.getZoom() }));
        } catch (e) {}
      }
      try { sessionStorage.setItem(stepStorageKey, String(currentStep)); } catch (e) {}
      var formData = new FormData(form);
      formData.set('findings_json', JSON.stringify(findingsState));
      formData.set('source_snapshot_json', JSON.stringify(sourcesState));
      formData.set('crew_json', JSON.stringify(crewState));
      formData.set('external_actors_json', JSON.stringify(externalActorsState));
      formData.set('interview_sessions_json', JSON.stringify(interviewState));
      setAutosaveStatus('Lagrer manuelt …', 'is-saving');
      fetch(root.dataset.autosaveUrl, { method: 'POST', body: formData })
        .then(function (r) { return r.json(); })
        .then(function () {
          lastAutosaveFingerprint = formFingerprint();
          setAutosaveStatus('Lagret manuelt ' + new Date().toLocaleTimeString('nb-NO', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), 'is-saved');
        })
        .catch(function () { setAutosaveStatus('Manuell lagring feilet', 'is-error'); });
    }

    var manualSaveBtn = document.getElementById('btn-manual-save');
    if (manualSaveBtn) manualSaveBtn.addEventListener('click', function(event){
      event.preventDefault();
      performManualSave();
    });

    form.addEventListener('submit', function (event) {
      if (event) event.preventDefault();
      findingsInput.value = JSON.stringify(findingsState);
      crewInput.value = JSON.stringify(crewState);
      externalActorsInput.value = JSON.stringify(externalActorsState);
      sourcesInput.value = JSON.stringify(sourcesState);
      if (interviewInput) interviewInput.value = JSON.stringify(interviewState);
      if (suspectNameCommercial.value && !suspectName.value) suspectName.value = suspectNameCommercial.value;
      if (caseMap && caseMap._kvLeafletMap) {
        try {
          var center = caseMap._kvLeafletMap.getCenter();
          sessionStorage.setItem('kv-map-view:' + (caseMap.id || 'case-map'), JSON.stringify({ lat: center.lat, lng: center.lng, zoom: caseMap._kvLeafletMap.getZoom() }));
        } catch (e) {}
      }
      performManualSave();
    });

    syncOptions();
    updateCaseMap();
    renderFindings();
    if (sourcesState.length) sourceList.innerHTML = sourcesState.map(sourceChip).join('');
    if (controlType.value && (species.value || fisheryType.value) && gearType.value) loadRules();
    try {
      var storedStep = Number(sessionStorage.getItem(stepStorageKey) || '1');
      if (storedStep >= 1 && storedStep <= panes.length) showStep(storedStep, { scroll: false });
    } catch (e) {}
  }

  ready(initMapOverview);
  ready(initRulesOverview);
  ready(initCaseApp);
})();
