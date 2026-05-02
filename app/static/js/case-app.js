(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
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

  var Common = window.KVCommon || {};
  var sharedCreatePortalMap = Common.createPortalMap;
  var secureFetchOptions = Common.secureFetchOptions || window.secureFetchOptions || function (options) {
    var result = Object.assign({ credentials: 'same-origin' }, options || {});
    var method = String(result.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
      var headers = new Headers(result.headers || {});
      var meta = document.querySelector('meta[name="csrf-token"]');
      var token = meta ? String(meta.getAttribute('content') || '') : '';
      if (token && !headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', token);
      result.headers = headers;
    }
    return result;
  };

  function csrfFieldHtml() {
    var token = '';
    try {
      token = (Common.csrfToken && Common.csrfToken()) || (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
    } catch (e) {
      token = '';
    }
    return token ? '<input type="hidden" name="csrf_token" value="' + escapeHtml(token) + '" />' : '';
  }

  var latestZoneResult = null;
  var findingsState = [];
  var evidenceState = [];
  var selectedInlineEvidenceTarget = null;
  var inlineEvidenceFeedback = '';
  var form = null, findingsInput = null, sourcesInput = null, crewInput = null, externalActorsInput = null, personsInput = null, interviewInput = null, seizureReportsInput = null;
  var controlType = null, fisheryType = null, species = null, gearType = null, startTime = null, endTime = null;
  var latitude = null, longitude = null, areaStatus = null, areaName = null, locationName = null, positionCoordinateSummary = null, caseBasis = null, basisSourceName = null, basisDetails = null;
  var suspectName = null, suspectNameCommercial = null, suspectPhone = null, suspectAddress = null, suspectPostPlace = null, suspectBirthdate = null;
  var hummerParticipantNo = null, hummerLastRegistered = null, vesselName = null, vesselReg = null, radioCallSign = null, gearMarkerId = null, lookupText = null, lookupName = null, lookupIdentifier = null;
  var notes = null, summary = null, hearingText = null, ocrAutofillPreview = null;


  function normalizeCoordinateValue(value, decimals) {
    var num = Number(String(value || '').replace(',', '.'));
    if (!isFinite(num)) return String(value || '').trim();
    return num.toFixed(decimals || 6);
  }

  function latLngToDms(latValue, lngValue) {
    var lat = Number(String(latValue || '').replace(',', '.'));
    var lon = Number(String(lngValue || '').replace(',', '.'));
    if (!isFinite(lat) || !isFinite(lon)) return '';
    function format(value, positivePrefix, negativePrefix) {
      var prefix = value >= 0 ? positivePrefix : negativePrefix;
      var abs = Math.abs(value);
      var deg = Math.floor(abs);
      var minFloat = (abs - deg) * 60;
      var min = Math.floor(minFloat);
      var sec = Math.round((minFloat - min) * 60);
      if (sec >= 60) { sec = 0; min += 1; }
      if (min >= 60) { min = 0; deg += 1; }
      return prefix + ' ' + deg + '° ' + min + "' " + sec + '"';
    }
    return format(lat, 'N', 'S') + ' ' + format(lon, 'Ø', 'V');
  }

  function currentCoordText() {
    if (!latitude || !longitude || !latitude.value || !longitude.value) return '';
    return latLngToDms(latitude.value, longitude.value) || 'DMS ikke beregnet';
  }
  window.MKCurrentCoordText = currentCoordText;

  function normalizedNearestPlaceText(result) {
    result = result || latestZoneResult || {};
    var municipality = String(result.municipality || (result.reverse_geocode && result.reverse_geocode.municipality) || '').trim();
    var locality = String(result.locality || (result.reverse_geocode && (result.reverse_geocode.locality || result.reverse_geocode.name)) || result.location_name || result.nearest_place || '').trim();
    if (locality && municipality && locality.toLowerCase().indexOf(municipality.toLowerCase()) === -1) return locality + ', ' + municipality;
    return locality || municipality || '';
  }

  function setNearestPlaceFromResult(result) {
    if (!locationName) return '';
    var label = normalizedNearestPlaceText(result);
    if (label) {
      locationName.value = label;
      try { locationName.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
    }
    return label;
  }

  function normalizeHummerParticipantNo(value) {
    var raw = String(value || '').trim().toUpperCase().replace(/[–—_]/g, '-');
    if (!raw) return '';
    var compact = raw.replace(/\s+/g, '').replace(/-/g, '');
    if (/^20\d{5}$/.test(compact)) return 'H-' + compact.slice(0, 4) + '-' + compact.slice(4);
    if (/^H\d{7}$/.test(compact)) return 'H-' + compact.slice(1, 5) + '-' + compact.slice(5);
    var hMatch = raw.replace(/\s+/g, '').match(/^H-?(\d{4})-?(\d{3})$/i);
    if (hMatch) return 'H-' + hMatch[1] + '-' + hMatch[2];
    return '';
  }

  function normalizeGearMarkerId(value) {
    var raw = String(value || '').trim().toUpperCase().replace(/[–—_]/g, '-');
    if (!raw) return '';
    raw = raw.replace(/\s+/g, '-').replace(/-+/g, '-').replace(/^[-.,;:]+|[-.,;:]+$/g, '');
    var compact = raw.replace(/-/g, '');
    if (/^(?:H\d{7}|20\d{5})$/.test(compact)) return '';
    var lob = raw.match(/^LOB-?HUM-?(\d{3,4})$/i);
    if (lob) return 'LOB-HUM-' + lob[1];
    var dual = compact.match(/^([A-ZÆØÅ]{2,5})([A-ZÆØÅ]{2,5})(\d{3,4})$/i);
    if (dual && dual[1].toUpperCase() !== 'H') return dual[1].toUpperCase() + '-' + dual[2].toUpperCase() + '-' + dual[3];
    var prefixed = compact.match(/^([A-ZÆØÅ]{3,8})(\d{3,4})$/i);
    if (prefixed && prefixed[1].toUpperCase() !== 'H') return prefixed[1].toUpperCase() + '-' + prefixed[2];
    var dashed = raw.match(/^([A-ZÆØÅ]{2,5})-([A-ZÆØÅ]{2,5})-(\d{3,4})$/i);
    if (dashed) return dashed[1].toUpperCase() + '-' + dashed[2].toUpperCase() + '-' + dashed[3];
    return '';
  }

  function classifyLookupIdentifier(identifier) {
    var value = String(identifier || '').trim();
    var compact = value.replace(/\s+/g, '');
    var normalizedHummer = normalizeHummerParticipantNo(value);
    var markerId = normalizeGearMarkerId(value);
    if (!value) return { phone: '', vessel_reg: '', radio_call_sign: '', hummer_participant_no: '', gear_marker_id: '' };
    if (/^(?:\+?47)?\d{8}$/.test(compact)) return { phone: compact.slice(-8), vessel_reg: '', radio_call_sign: '', hummer_participant_no: '', gear_marker_id: '' };
    if (normalizedHummer) return { phone: '', vessel_reg: '', radio_call_sign: '', hummer_participant_no: normalizedHummer, gear_marker_id: '' };
    if (markerId) return { phone: '', vessel_reg: '', radio_call_sign: '', hummer_participant_no: '', gear_marker_id: markerId };
    if (/^[A-ZÆØÅ]{1,3}[- ]?[A-ZÆØÅ]{1,3}[- ]?\d{1,4}$/i.test(value)) return { phone: '', vessel_reg: value.toUpperCase().replace(/\s+/g, ''), radio_call_sign: '', hummer_participant_no: '', gear_marker_id: '' };
    if (/^[A-ZÆØÅ]{1,3}[- ]?\d{1,4}(?:[- ]?[A-ZÆØÅ]{1,2})?$/i.test(value)) return { phone: '', vessel_reg: value.toUpperCase().replace(/\s+/g, ''), radio_call_sign: '', hummer_participant_no: '', gear_marker_id: '' };
    if (/^[A-ZÆØÅ]{2,5}[- ]?\d{0,3}$/i.test(value)) return { phone: '', vessel_reg: '', radio_call_sign: compact.toUpperCase(), hummer_participant_no: '', gear_marker_id: '' };
    return { phone: '', vessel_reg: '', radio_call_sign: '', hummer_participant_no: '', gear_marker_id: '' };
  }


  function normalizeLookupNameCandidate(value) {
    var cleaned = String(value || '').replace(/^(?:navn|eier|ansvarlig|skipper|person)\s*[:#-]?\s*/i, '').replace(/\s+/g, ' ').trim().replace(/^[,;]+|[,;]+$/g, '');
    if (!cleaned) return '';
    if (isBadPersonName(cleaned)) return '';
    if (/\d/.test(cleaned)) return '';
    if (cleaned.split(' ').length < 2) return '';
    return cleaned;
  }

  function isBadPersonName(value) {
    var text = String(value || '').replace(/[|]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/^[,;:-]+|[,;:-]+$/g, '');
    if (!text) return true;
    if (/(?:\bvis\s*(?:telefon|nummer|tlf|mobil)\b|\b(?:telefon|mobil)\s*nummer\b|\bvisnummer\b|\bvistelefon\b|\bring\b|\bsend\s*sms\b|\b1881(?:\.no)?\b|\bgulesider(?:\.no)?\b|\bopplysningen\b|\bnummeropplysning\b|\bpersoner\b|\bbedrift(?:er)?\b|\bfirma\b|\bannonse\b|\bkart\b|\bveibeskrivelse\b|\boppf\u00f8ring\b|\bs\u00f8k\b|\bsok\b|\bresultat(?:er)?\b|\btreff\b)/i.test(text)) return true;
    var compact = text.toLowerCase().replace(/\s+/g, '');
    if (compact === 'visnummer' || compact === 'vistelefon' || compact === 'telefonnummer' || compact === 'mobilnummer' || compact === '1881' || compact === '1881.no' || compact === 'gulesider' || compact === 'gulesider.no' || compact === 'personer' || compact === 'bedrifter' || compact === 'kart' || compact === 'sok' || compact === 's\u00f8k' || compact === 'resultater') return true;
    return false;
  }



  function isBadOcrFragment(value) {
    var text = String(value || '').replace(/[|]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/^[,;:-]+|[,;:-]+$/g, '');
    if (!text) return true;
    if (isBadPersonName(text)) return true;
    if (/(?:\b1881(?:\.no)?\b|\bgulesider(?:\.no)?\b|\bvis\s*(?:nummer|telefon|mobil|tlf)\b|\btelefon\s*nummer\b|\bpersoner\b|\bbedrifter\b|\bkart\b|\bveibeskrivelse\b|\bannonse\b|\bsok\b|\bsøk\b|\bresultat(?:er)?\b|\btreff\b)/i.test(text)) return true;
    if (/^(?:1881|gulesider|vis nummer|vis telefon|personer|bedrifter|kart|resultater)$/i.test(text)) return true;
    return false;
  }

  function normalizeLookupPostPlace(value) {
    var source = String(value || '').replace(/\s+/g, ' ').trim();
    if (isBadOcrFragment(source)) return '';
    var match = source.match(/(\d{4})\s+([A-ZÆØÅa-zæøå][A-Za-zÆØÅæøå\- ]{1,40})/);
    return match ? (match[1] + ' ' + match[2].trim()) : '';
  }

  function splitLookupAddress(value) {
    var cleaned = String(value || '').replace(/^(?:adresse|adr|postadresse)\s*[:#-]?\s*/i, '').replace(/\s+/g, ' ').trim().replace(/^[,;]+|[,;]+$/g, '');
    if (!cleaned || isBadOcrFragment(cleaned)) return { address: '', post_place: '' };
    var postPlace = normalizeLookupPostPlace(cleaned);
    var address = cleaned;
    if (postPlace) address = cleaned.replace(postPlace, '').replace(/[ ,;]+$/g, '').trim();
    return { address: address, post_place: postPlace };
  }

  function lookupLabelLine(line) {
    return /^(?:navn|eier|ansvarlig|skipper|person|adresse|adr|postadresse|poststed|postnummer|postnr(?:\.?|\s*og\s*sted)?|mobil(?:nummer|nr)?|mobiltelefon|telefon(?:nummer)?|tlf(?:nr)?|fødselsdato|fodselsdato|f[øo]dt|hummer\s*deltak(?:er|ar)(?:nr|nummer)?|deltak(?:er|ar)(?:nr|nummer)?|delt\.?\s*nr|fartøysnavn|fiskerimerke|radiokallesignal|kallesignal|radio|merke(?:id)?|merke-id|redskapsmerke|vak|bl[åa]se)\s*[:#-]?$/i.test(String(line || '').trim().replace(/^[,;]+|[,;]+$/g, ''));
  }

  function lookupLineHasFieldPrefix(line) {
    return /^(?:navn|eier|ansvarlig|skipper|person|adresse|adr|postadresse|poststed|postnummer|postnr(?:\.?|\s*og\s*sted)?|mobil(?:nummer|nr)?|mobiltelefon|telefon(?:nummer)?|tlf(?:nr)?|fødselsdato|fodselsdato|f[øo]dt|hummer\s*deltak(?:er|ar)(?:nr|nummer)?|deltak(?:er|ar)(?:nr|nummer)?|delt\.?\s*nr|fart[øo]ysnavn|fart[øo]y|b[åa]tnavn|fiskerimerke|registreringsmerke|radiokallesignal|kallesignal|radio|merke(?:id)?|merke-id|redskapsmerke|vak|bl[åa]se)(?=\s|[:#-]|$)/i.test(String(line || '').trim().replace(/^[,;]+|[,;]+$/g, ''));
  }

  function lookupLineHasGearMarker(line) {
    var text = String(line || '');
    return Boolean(normalizeGearMarkerId(text) || text.match(/\b[A-ZÆØÅ]{2,5}[- ]?[A-ZÆØÅ]{2,5}[- ]?\d{3,4}\b/i));
  }

  function lookupStripGearMarkerText(line) {
    return String(line || '').replace(/\b[A-ZÆØÅ]{2,5}[- ]?[A-ZÆØÅ]{2,5}[- ]?\d{3,4}\b/ig, ' ').replace(/\s+/g, ' ').trim().replace(/^[,;]+|[,;]+$/g, '');
  }

  function extractLabeledLookupValue(lines, inlinePatterns, labelOnlyPatterns, maxLines, joiner) {
    maxLines = Math.max(1, Number(maxLines || 1));
    joiner = joiner || ' ';
    for (var i = 0; i < lines.length; i += 1) {
      var line = String(lines[i] || '').trim();
      if (!line) continue;
      for (var j = 0; j < inlinePatterns.length; j += 1) {
        var inlineMatch = line.match(inlinePatterns[j]);
        if (inlineMatch && inlineMatch[1]) {
          var inlineValue = String(inlineMatch[1] || '').trim();
          if (!isBadOcrFragment(inlineValue)) return inlineValue;
        }
      }
      for (var k = 0; k < labelOnlyPatterns.length; k += 1) {
        if (!labelOnlyPatterns[k].test(line)) continue;
        var collected = [];
        for (var offset = 1; offset <= maxLines; offset += 1) {
          if (i + offset >= lines.length) break;
          var nextLine = String(lines[i + offset] || '').trim();
          if (!nextLine) continue;
          if (isBadOcrFragment(nextLine)) continue;
          if (lookupLabelLine(nextLine)) break;
          collected.push(nextLine);
          if (maxLines <= 1) break;
        }
        if (collected.length) return collected.join(joiner).trim();
      }
    }
    return '';
  }

  function extractLookupHintsFromText(text) {
    var raw = String(text || '');
    var lines = raw.split(/[\r\n]+/).map(function (line) {
      return String(line || '').replace(/[|]/g, ' ').replace(/\s+/g, ' ').trim().replace(/^[,;]+|[,;]+$/g, '');
    }).filter(function (line) { return line && !isBadOcrFragment(line); });
    var joined = lines.join(' | ');
    var hints = { phone: '', vessel_reg: '', radio_call_sign: '', hummer_participant_no: '', gear_marker_id: '', address: '', post_place: '', birthdate: '', name: '', vessel_name: '' };

    function pickPhone(value) {
      var match = String(value || '').replace(/\s+/g, '').match(/(?:\+?47)?(\d{8})(?!\d)/);
      return match ? match[1] : '';
    }

    var labeledName = extractLabeledLookupValue(lines, [/^(?:navn|eier|ansvarlig|skipper|person)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:navn|eier|ansvarlig|skipper|person)(?=\s|[:#-]|$)\s*[:#-]?$/i], 1, ' ');
    var labeledAddress = extractLabeledLookupValue(lines, [/^(?:adresse|adr|postadresse)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:adresse|adr|postadresse)(?=\s|[:#-]|$)\s*[:#-]?$/i], 2, ', ');
    var labeledPostPlace = extractLabeledLookupValue(lines, [/^(?:poststed|postnummer|postnr(?:\.?|\s*og\s*sted)?)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:poststed|postnummer|postnr(?:\.?|\s*og\s*sted)?)(?=\s|[:#-]|$)\s*[:#-]?$/i], 1, ' ');
    var labeledPhone = extractLabeledLookupValue(lines, [/^(?:mobil(?:nummer|nr)?|mobiltelefon|telefon(?:nummer)?|tlf(?:nr)?)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:mobil(?:nummer|nr)?|mobiltelefon|telefon(?:nummer)?|tlf(?:nr)?)(?=\s|[:#-]|$)\s*[:#-]?$/i], 1, ' ');
    var labeledHummer = extractLabeledLookupValue(lines, [/^(?:hummer\s*deltak(?:er|ar)(?:nummer|nr)?|deltak(?:er|ar)(?:nummer|nr)?|delt\.?\s*nr)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:hummer\s*deltak(?:er|ar)(?:nummer|nr)?|deltak(?:er|ar)(?:nummer|nr)?|delt\.?\s*nr)(?=\s|[:#-]|$)\s*[:#-]?$/i], 1, ' ');
    var labeledVessel = extractLabeledLookupValue(lines, [/^(?:fiskerimerke|registreringsmerke|fart[øo]y(?:s)?merke)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:fiskerimerke|registreringsmerke|fart[øo]y(?:s)?merke)(?=\s|[:#-]|$)\s*[:#-]?$/i], 1, ' ');
    var labeledRadio = extractLabeledLookupValue(lines, [/^(?:radiokallesignal|kallesignal|radio\s*call\s*sign)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:radiokallesignal|kallesignal|radio\s*call\s*sign)(?=\s|[:#-]|$)\s*[:#-]?$/i], 1, ' ');
    var labeledVesselName = extractLabeledLookupValue(lines, [/^(?:fart[øo]ysnavn|fart[øo]y|b[åa]tnavn)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:fart[øo]ysnavn|fart[øo]y|b[åa]tnavn)(?=\s|[:#-]|$)\s*[:#-]?$/i], 1, ' ');
    var labeledMarker = extractLabeledLookupValue(lines, [/^(?:merke(?:id)?|merke-id|redskapsmerke|vak|bl[åa]se)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:merke(?:id)?|merke-id|redskapsmerke|vak|bl[åa]se)(?=\s|[:#-]|$)\s*[:#-]?$/i], 1, ' ');
    var labeledBirthdate = extractLabeledLookupValue(lines, [/^(?:fødselsdato|fodselsdato|f[øo]dt)(?=\s|[:#-]|$)\s*[:#-]?\s*(.+)$/i], [/^(?:fødselsdato|fodselsdato|f[øo]dt)(?=\s|[:#-]|$)\s*[:#-]?$/i], 1, ' ');

    if (labeledName) hints.name = normalizeLookupNameCandidate(labeledName);
    if (labeledAddress) {
      var splitAddress = splitLookupAddress(labeledAddress);
      if (splitAddress.address) hints.address = splitAddress.address;
      if (splitAddress.post_place) hints.post_place = splitAddress.post_place;
    }
    if (labeledPostPlace && !hints.post_place) hints.post_place = normalizeLookupPostPlace(labeledPostPlace);
    if (labeledPhone) hints.phone = pickPhone(labeledPhone);
    if (labeledHummer) hints.hummer_participant_no = normalizeHummerParticipantNo(labeledHummer);
    if (labeledVessel && !hints.hummer_participant_no && !lookupLineHasGearMarker(labeledVessel)) hints.vessel_reg = String(labeledVessel || '').replace(/\s+/g, '').toUpperCase();
    if (labeledRadio && !hints.radio_call_sign) hints.radio_call_sign = String(labeledRadio || '').replace(/\s+/g, '').toUpperCase();
    if (labeledVesselName && !hints.vessel_name) hints.vessel_name = String(labeledVesselName || '').replace(/^(?:fart[øo]ysnavn|fart[øo]y|b[åa]tnavn)\s*[:#-]?\s*/i, '').trim();
    if (labeledMarker && !hints.gear_marker_id) hints.gear_marker_id = normalizeGearMarkerId(labeledMarker) || String(labeledMarker || '').replace(/\s+/g, '').toUpperCase();
    if (labeledBirthdate) {
      var birth = String(labeledBirthdate || '').match(/(\d{2}[.\-/]\d{2}[.\-/]\d{4})/);
      if (birth) hints.birthdate = birth[1].replace(/[\-/]/g, '.');
    }

    if (!hints.phone) hints.phone = pickPhone(joined);
    if (!hints.hummer_participant_no) {
      var hummerDirect = joined.match(/\b(?:H[- ]?\d{4}[- ]?\d{3}|20\d{5})\b/i);
      if (hummerDirect) hints.hummer_participant_no = normalizeHummerParticipantNo(hummerDirect[0] || '');
    }
    if (labeledMarker && !hints.gear_marker_id) hints.gear_marker_id = normalizeGearMarkerId(labeledMarker) || String(labeledMarker || '').replace(/\s+/g, '').toUpperCase();
    if (!hints.gear_marker_id) {
      var markerDirect = joined.match(/\b[A-ZÆØÅ]{2,5}[- ]?[A-ZÆØÅ]{2,5}[- ]?\d{3,4}\b/i);
      if (markerDirect) hints.gear_marker_id = normalizeGearMarkerId(markerDirect[0] || '');
    }
    if (!hints.birthdate) {
      var joinedBirth = joined.match(/(\d{2}[.\-/]\d{2}[.\-/]\d{4})/);
      if (joinedBirth) hints.birthdate = joinedBirth[1].replace(/[\-/]/g, '.');
    }
    if (!hints.post_place) {
      for (var p = 0; p < lines.length; p += 1) {
        var postPlace = normalizeLookupPostPlace(lines[p]);
        if (postPlace) {
          hints.post_place = postPlace;
          break;
        }
      }
    }
    if (!hints.address) {
      for (var a = 0; a < lines.length; a += 1) {
        var line = lines[a];
        if (isBadOcrFragment(line) || lookupLabelLine(line) || lookupLineHasFieldPrefix(line) || lookupLineHasGearMarker(line)) continue;
        if (/\d/.test(line) && /[A-Za-zÆØÅæøå]/.test(line) && !/^\d{4}\s/.test(line) && !/^(?:mobil|telefon|tlf|navn|eier|ansvarlig|skipper|person|fødselsdato|fodselsdato|f[øo]dt|hummer|deltak)/i.test(line)) {
          var split = splitLookupAddress(line);
          hints.address = split.address || line;
          if (split.post_place && !hints.post_place) hints.post_place = split.post_place;
          break;
        }
      }
    }
    if (!hints.name) {
      for (var n = 0; n < lines.length; n += 1) {
        if (isBadOcrFragment(lines[n]) || lookupLabelLine(lines[n]) || lookupLineHasFieldPrefix(lines[n]) || lookupLineHasGearMarker(lines[n])) continue;
        var candidate = normalizeLookupNameCandidate(lookupStripGearMarkerText(lines[n]));
        if (candidate) {
          hints.name = candidate;
          break;
        }
      }
    }
    return hints;
  }

  function autofillField(field, value, options) {
    if (!field || value === undefined || value === null) return false;
    var next = String(value || '').trim();
    if (!next) return false;
    var current = String(field.value || '').trim();
    if (current === next) return false;
    var allowOverwrite = !!(options && options.allowOverwrite);
    if (!current || /^ukjent$/i.test(current) || (allowOverwrite && current.length < next.length)) {
      field.value = next;
      return true;
    }
    return false;
  }


  function sourceChip(item) {
    var label = '<strong>' + escapeHtml(item.name || 'Kilde') + '</strong><span>' + escapeHtml(item.ref || '') + '</span>';
    if (item.url) return '<a class="source-chip" href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' + label + '</a>';
    return '<div class="source-chip">' + label + '</div>';
  }

  function normalizedSeasonValue(value) {
    return String(value || '').replace('-sesongen', '').trim();
  }

  function hummerSeasonText(value) {
    var year = normalizedSeasonValue(value);
    return year ? ('Påmeldt hummerfisket i ' + year) : '';
  }

  function currentAutofillSnapshot() {
    return {
      name: String((suspectName && suspectName.value) || (suspectNameCommercial && suspectNameCommercial.value) || (lookupName && lookupName.value) || '').trim(),
      address: String((suspectAddress && suspectAddress.value) || '').trim(),
      post_place: String((suspectPostPlace && suspectPostPlace.value) || '').trim(),
      phone: String((suspectPhone && suspectPhone.value) || '').trim(),
      hummer_participant_no: String((hummerParticipantNo && hummerParticipantNo.value) || '').trim(),
      birthdate: String((suspectBirthdate && suspectBirthdate.value) || '').trim(),
      vessel_reg: String((vesselReg && vesselReg.value) || '').trim(),
      radio_call_sign: String((radioCallSign && radioCallSign.value) || '').trim(),
      gear_marker_id: String((gearMarkerId && gearMarkerId.value) || '').trim(),
      vessel_name: String((vesselName && vesselName.value) || '').trim(),
      season: String((hummerLastRegistered && hummerLastRegistered.value) || '').trim()
    };
  }

  function renderAutofillPreview(meta) {
    if (!ocrAutofillPreview) return;
    var snapshot = currentAutofillSnapshot();
    var items = [
      snapshot.name ? ['Navn', snapshot.name] : null,
      snapshot.address ? ['Adresse', snapshot.address] : null,
      snapshot.post_place ? ['Postnr. og sted', snapshot.post_place] : null,
      snapshot.phone ? ['Mobil', snapshot.phone] : null,
      snapshot.hummer_participant_no ? ['Deltakernummer', snapshot.hummer_participant_no] : null,
      snapshot.birthdate ? ['Fødselsdato', snapshot.birthdate] : null,
      snapshot.vessel_reg ? ['Fiskerimerke', snapshot.vessel_reg] : null,
      snapshot.radio_call_sign ? ['Radiokallesignal', snapshot.radio_call_sign] : null,
      snapshot.gear_marker_id ? ['Merke-ID / vak/blåse', snapshot.gear_marker_id] : null,
      snapshot.vessel_name ? ['Fartøysnavn', snapshot.vessel_name] : null,
      snapshot.season ? ['Registerstatus', hummerSeasonText(snapshot.season) || snapshot.season] : null
    ].filter(Boolean);
    if (!items.length) {
      ocrAutofillPreview.classList.add('hidden');
      ocrAutofillPreview.innerHTML = '';
      return;
    }
    var source = meta && meta.source ? String(meta.source) : '';
    var detail = meta && meta.detail ? String(meta.detail) : '';
    ocrAutofillPreview.classList.remove('hidden');
    ocrAutofillPreview.innerHTML = [
      '<div class="map-relevant-head">',
      '<strong>Autofylte opplysninger</strong>',
      '<span class="muted small">' + escapeHtml(source || 'OCR og registeroppslag') + (detail ? ' · ' + escapeHtml(detail) : '') + '</span>',
      '</div>',
      '<div class="ocr-preview-grid">',
      items.map(function (item) {
        return '<div class="ocr-preview-item"><span>' + escapeHtml(item[0]) + '</span><strong>' + escapeHtml(item[1]) + '</strong></div>';
      }).join(''),
      '</div>'
    ].join('');
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
    if (!result || !result.match || String(result.status || '').toLowerCase() === 'ingen treff') {
      return '<strong>Ingen regulert sone registrert</strong><div class="small muted">Posisjonen ligger ikke i registrert fredningsområde, stengt område eller annen regulert sone.</div>' + (result && (result.location_name || result.nearest_place) ? '<div class="small muted">Nærmeste sted: ' + escapeHtml(result.location_name || result.nearest_place) + '</div>' : '');
    }
    var parts = ['<strong>' + escapeHtml(result.status || '') + '</strong>'];
    if (result.name) parts.push('<div><strong>Område:</strong> ' + escapeHtml(result.name) + '</div>');
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
    return Boolean(item && item.supports_measurements) || key === 'hummer_minstemal' || key === 'hummer_maksimalmal' || key.indexOf('minstemal_') === 0;
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

  function parseMeasurementLimitValue(value) {
    var raw = String(value || '').trim().replace(',', '.');
    if (!raw || raw.indexOf('/') !== -1) return NaN;
    var parsed = Number(raw);
    return isFinite(parsed) ? parsed : NaN;
  }

  function formatMeasurementNumber(value) {
    if (!isFinite(value)) return '';
    var rounded = Math.round(Number(value) * 10) / 10;
    if (Math.abs(rounded - Math.round(rounded)) < 0.0001) return String(Math.round(rounded)).replace('.', ',');
    return rounded.toFixed(1).replace('.', ',');
  }

  function measurementMinLimit(item) {
    return parseMeasurementLimitValue(item && (item.applied_min_size_cm || item.min_size_cm));
  }

  function measurementMaxLimit(item) {
    return parseMeasurementLimitValue(item && (item.applied_max_size_cm || item.max_size_cm));
  }

  function formatMeasurementDeltaText(diffCm, relation, limitLabel, limitValue) {
    var absCm = Math.abs(diffCm);
    var diffMm = Math.round(absCm * 10);
    return formatMeasurementNumber(absCm) + ' cm (' + String(diffMm) + ' mm) ' + relation + ' ' + limitLabel + ' (' + formatMeasurementNumber(limitValue) + ' cm)';
  }

  function evaluateMeasurementRow(item, row) {
    var rawLength = String(row && row.length_cm || '').trim().replace(',', '.');
    if (!rawLength) return { status: '', text: 'Legg inn måling i cm for automatisk vurdering.', violation: '' };
    var lengthValue = Number(rawLength);
    if (!isFinite(lengthValue)) return { status: 'invalid', text: 'Ugyldig måling. Oppgi lengde i cm.', violation: '' };
    var minLimit = measurementMinLimit(item);
    var maxLimit = measurementMaxLimit(item);
    if (isFinite(minLimit) && lengthValue < minLimit) {
      var underText = formatMeasurementDeltaText(minLimit - lengthValue, 'under', 'minstemålet', minLimit);
      return { status: 'under_min', text: underText, violation: 'Målt ' + formatMeasurementNumber(lengthValue) + ' cm – ' + underText + '.' };
    }
    if (isFinite(maxLimit) && lengthValue >= maxLimit) {
      if (Math.abs(lengthValue - maxLimit) < 0.0001) {
        var equalText = 'Målingen ligger på maksimalmålet (' + formatMeasurementNumber(maxLimit) + ' cm), som ikke er tillatt i dette området.';
        return { status: 'over_max', text: equalText, violation: 'Målt ' + formatMeasurementNumber(lengthValue) + ' cm – ' + equalText };
      }
      var overText = formatMeasurementDeltaText(lengthValue - maxLimit, 'over', 'maksimalmålet', maxLimit);
      return { status: 'over_max', text: overText, violation: 'Målt ' + formatMeasurementNumber(lengthValue) + ' cm – ' + overText + '.' };
    }
    if (isFinite(minLimit) && isFinite(maxLimit)) {
      return { status: 'ok', text: 'Innenfor lovlig målintervall (' + formatMeasurementNumber(minLimit) + ' cm til under ' + formatMeasurementNumber(maxLimit) + ' cm).', violation: '' };
    }
    if (isFinite(minLimit)) {
      return { status: 'ok', text: 'Innenfor minstemålet (' + formatMeasurementNumber(minLimit) + ' cm).', violation: '' };
    }
    if (isFinite(maxLimit)) {
      return { status: 'ok', text: 'Innenfor maksimalmålet (' + formatMeasurementNumber(maxLimit) + ' cm).', violation: '' };
    }
    return { status: 'ok', text: 'Målt til ' + formatMeasurementNumber(lengthValue) + ' cm.', violation: '' };
  }

  function defaultMeasurementRow() {
    return { seizure_ref: '', reference: '', linked_seizure_ref: '', position: '', length_cm: '', note: '', delta_text: '', violation_text: '', measurement_state: '' };
  }

  function syncMeasurementDefaults(item) {
    ensureMeasurementState(item).forEach(function (row) {
      row.linked_seizure_ref = String(row.linked_seizure_ref || '').trim();
      var ref = String(row.seizure_ref || row.reference || '').trim();
      if (row.linked_seizure_ref) ref = row.linked_seizure_ref;
      if (!ref) ref = formatMeasurementSeizureRef(nextSeizureSequence());
      row.seizure_ref = ref;
      row.reference = ref;
      if (!row.position && currentCoordText()) row.position = currentCoordText();
      ensureDeviationLinks(row);
      var evaluation = evaluateMeasurementRow(item, row);
      row.delta_text = evaluation.text || '';
      row.violation_text = evaluation.violation || '';
      row.measurement_state = evaluation.status || '';
    });
    item.measurement_summary = measurementSummaryText(item);
  }

  function ensureMarkerState(item) {
    var defaultLinked = /lenke|garnlenke|teinelenke/i.test(String((item && (item.label || item.key || item.summary_text)) || '') + ' ' + String((gearType && gearType.value) || ''));
    if (!item.marker_positions || typeof item.marker_positions !== 'object') item.marker_positions = { is_linked: defaultLinked, current: '', start: '', end: '', total: '', approved: '', deviations: '' };
    if (item.marker_positions.is_linked === undefined) item.marker_positions.is_linked = defaultLinked;
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
      var legacyRef = row.gear_ref ? (' / tidligere ID ' + row.gear_ref) : '';
      var qty = row.quantity ? (' / antall ' + row.quantity) : '';
      var position = row.position ? (' / posisjon ' + row.position) : '';
      var violation = row.violation || 'ikke spesifisert avvik';
      var note = row.note ? (' / ' + row.note) : '';
      var links = deviationLinksSummary(row);
      var linkText = links ? (' / ' + links) : '';
      var groupText = 'Lenke ' + (Number(row.link_group_index || 0) + 1) + ' / ';
      return groupText + ref + gearKind + legacyRef + qty + position + ': ' + violation + note + linkText;
    }).join('; ');
  }


  function seizureBaseCaseNumber() {
    var raw = String((document.getElementById('case-app') || {}).dataset.caseNumber || '').trim().toUpperCase();
    if (!raw) return 'BESLAG';
    var direct = raw.match(/^([A-Z\u00c6\u00d8\u00c50-9]{2,10})\s*(\d{2})\s+(\d{1,4})$/i);
    if (direct) return direct[1].toUpperCase() + direct[2] + '-' + String(direct[3]).padStart(3, '0');
    var hyphenated = raw.match(/^([A-Z\u00c6\u00d8\u00c50-9]{2,10})(\d{2})[- ](\d{1,4})$/i);
    if (hyphenated) return hyphenated[1].toUpperCase() + hyphenated[2] + '-' + String(hyphenated[3]).padStart(3, '0');
    var parts = raw.split(/\s+/).filter(Boolean);
    if (parts.length >= 3 && /^\d{2}$/.test(parts[1]) && /^\d{1,4}$/.test(parts[2])) {
      return parts[0].toUpperCase() + parts[1] + '-' + String(parts[2]).padStart(3, '0');
    }
    return raw.replace(/\s+/g, '-');
  }

  function formatSeizureRef(sequence) {
    return seizureBaseCaseNumber() + '-' + String(sequence || nextSeizureSequence()).padStart(3, '0');
  }

  function formatMeasurementSeizureRef(sequence) {
    return seizureBaseCaseNumber() + ' - Måling -' + String(sequence || nextSeizureSequence()).padStart(3, '0');
  }

  function deviationGearOptions() {
    return ['Hummerteine', 'Krabbeteine', 'Garn', 'Ruse', 'Samleteine', 'Sanketeine', 'Teine', 'Garnlenke', 'Teinelenke', 'Line', 'Jukse', 'Annet'];
  }

  function normalizeDeviationGearKind(value) {
    var raw = String(value || '').trim().toLowerCase();
    if (!raw) return 'Teine';
    if (raw.indexOf('hummer') !== -1) return 'Hummerteine';
    if (raw.indexOf('krabbe') !== -1) return 'Krabbeteine';
    if (raw.indexOf('samleteine') !== -1) return 'Samleteine';
    if (raw.indexOf('sanketeine') !== -1) return 'Sanketeine';
    if (raw.indexOf('garnlenke') !== -1 || raw.indexOf('lenkekontroll') !== -1) return 'Garnlenke';
    if (raw.indexOf('teinelenke') !== -1) return 'Teinelenke';
    if (raw.indexOf('garn') !== -1) return 'Garn';
    if (raw.indexOf('ruse') !== -1) return 'Ruse';
    if (raw.indexOf('line') !== -1) return 'Line';
    if (raw.indexOf('jukse') !== -1) return 'Jukse';
    if (raw.indexOf('teine') !== -1) return 'Teine';
    return 'Annet';
  }

  var controlLinkModeEnabled = false;
  var controlLinkPageCount = 1;
  var controlLinkActiveIndex = 0;

  function ensureControlLinkState() {
    var maxGroup = 0;
    (findingsState || []).forEach(function (finding) {
      ensureDeviationState(finding).forEach(function (row) {
        var group = Number(row.link_group_index || 0);
        if (isFinite(group) && group > maxGroup) maxGroup = group;
      });
    });
    controlLinkPageCount = Math.max(controlLinkPageCount || 1, maxGroup + 1, 1);
    if (!isFinite(controlLinkActiveIndex) || controlLinkActiveIndex < 0) controlLinkActiveIndex = 0;
    if (controlLinkActiveIndex >= controlLinkPageCount) controlLinkActiveIndex = controlLinkPageCount - 1;
    return { enabled: Boolean(controlLinkModeEnabled), count: controlLinkPageCount, activeIndex: controlLinkActiveIndex };
  }

  function setActiveControlLinkIndex(index) {
    ensureControlLinkState();
    var idx = Number(index || 0);
    if (!isFinite(idx) || idx < 0) idx = 0;
    if (idx >= controlLinkPageCount) idx = controlLinkPageCount - 1;
    controlLinkActiveIndex = idx;
    (findingsState || []).forEach(function (finding) {
      finding.active_deviation_link_index = controlLinkActiveIndex;
    });
  }

  function renderControlLinkToolbar() {
    if (!controlLinkToolbar) return;
    var state = ensureControlLinkState();
    var tabs = [];
    for (var i = 0; i < state.count; i += 1) {
      var active = i === state.activeIndex ? ' is-active' : '';
      tabs.push('<button type="button" class="control-link-tab' + active + '" data-link-index="' + i + '" aria-pressed="' + (i === state.activeIndex ? 'true' : 'false') + '">Lenke ' + (i + 1) + '</button>');
    }
    controlLinkToolbar.innerHTML = [
      '<div class="control-link-card">',
      '<label class="check-chip"><input type="checkbox" id="control-link-mode" ' + (state.enabled ? 'checked' : '') + ' /> Lenke</label>',
      '<div class="control-link-tabs" role="tablist" aria-label="Lenker">' + tabs.join('') + '</div>',
      '<button type="button" class="btn btn-secondary btn-small" id="control-link-add">Legg til lenke</button>',
      '</div>'
    ].join('');
  }

  function deviationReportDraftText(item, row) {
    row = row || {};
    var parts = [];
    var ref = String(row.seizure_ref || '').trim();
    var kind = String(row.gear_kind || defaultDeviationGearKind()).trim();
    var quantity = String(row.quantity || '1').trim();
    var violation = String(row.violation || suggestedDeviationText(item)).trim();
    var position = String(row.position || currentCoordText()).trim();
    if (ref) parts.push('Beslagsnummer: ' + ref + '.');
    parts.push('Gjenstand: ' + quantity + ' ' + kind.toLowerCase() + '.');
    if (violation) parts.push('Grunnlag for beslag/avvik: ' + violation + '.');
    if (position) parts.push('Posisjon: ' + position + '.');
    parts.push('Bildebevis kan tas med kamera eller lastes opp og legges i illustrasjonsrapporten.');
    return parts.join(' ');
  }

  function defaultDeviationGearKind() {
    return normalizeDeviationGearKind((document.getElementById('gear_type') || {}).value || 'Teine');
  }

  function defaultDeviationRow(item) {
    var activeGroup = Number(controlLinkModeEnabled ? controlLinkActiveIndex : (item && item.active_deviation_link_index || 0));
    if (!isFinite(activeGroup) || activeGroup < 0) activeGroup = 0;
    return { seizure_ref: '', linked_seizure_ref: '', gear_kind: defaultDeviationGearKind(), gear_ref: '', quantity: '1', position: currentCoordText(), violation: suggestedDeviationText(item), note: '', links: [defaultDeviationLink()], active_link_index: 0, link_group_index: activeGroup };
  }

  function defaultDeviationLink() {
    return { start: currentCoordText(), end: '', note: '' };
  }

  function ensureDeviationLinks(row) {
    if (!row) return [];
    if (!Array.isArray(row.links)) row.links = [];
    row.links = row.links.map(function (entry) {
      return {
        start: String(entry && entry.start || '').trim(),
        end: String(entry && entry.end || '').trim(),
        note: String(entry && entry.note || '').trim()
      };
    });
    var idx = Number(row.active_link_index || 0);
    if (!isFinite(idx) || idx < 0) idx = 0;
    if (row.links.length && idx >= row.links.length) idx = row.links.length - 1;
    row.active_link_index = row.links.length ? idx : 0;
    return row.links;
  }

  function activeDeviationLinkIndex(row) {
    var links = ensureDeviationLinks(row);
    return links.length ? Number(row.active_link_index || 0) : -1;
  }

  function deviationLinksSummary(row) {
    var links = ensureDeviationLinks(row);
    if (!links.length) return '';
    return links.map(function (entry, idx) {
      var parts = ['Lenke ' + (idx + 1)];
      if (entry.start) parts.push('start ' + entry.start);
      if (entry.end) parts.push('slutt ' + entry.end);
      if (entry.note) parts.push(entry.note);
      return parts.join(': ');
    }).join(' | ');
  }

  function normalizeDeviationLinkGroups(item) {
    var rows = ensureDeviationState(item);
    var maxGroup = 0;
    rows.forEach(function (row, idx) {
      if (!row) row = rows[idx] = defaultDeviationRow(item);
      ensureDeviationLinks(row);
      var group = Number(row.link_group_index);
      if (!isFinite(group) || group < 0) {
        group = Number(row.active_link_index || 0);
        if (!isFinite(group) || group < 0) group = idx;
      }
      group = Math.max(0, Math.floor(group));
      row.link_group_index = group;
      if (group > maxGroup) maxGroup = group;
    });
    var active = Number(item && item.active_deviation_link_index || 0);
    if (!isFinite(active) || active < 0) active = 0;
    if (active > maxGroup) active = maxGroup;
    item.active_deviation_link_index = active;
    return { rows: rows, activeIndex: active, count: Math.max(1, maxGroup + 1) };
  }

  function deviationGroupTabsHtml(item) {
    var state = normalizeDeviationLinkGroups(item);
    var buttons = [];
    for (var idx = 0; idx < state.count; idx += 1) {
      var count = state.rows.filter(function (row) { return Number(row.link_group_index || 0) === idx; }).length;
      var active = idx === state.activeIndex ? ' is-active' : '';
      buttons.push('<button type="button" class="deviation-group-tab' + active + '" data-link-index="' + idx + '" aria-pressed="' + (idx === state.activeIndex ? 'true' : 'false') + '">Lenke ' + (idx + 1) + (count ? ' · ' + count : '') + '</button>');
    }
    return [
      '<div class="deviation-group-tabs" role="tablist" aria-label="Lenker for avvik">',
      '<div class="deviation-group-tabs-scroll">' + buttons.join('') + '</div>',
      '<div class="deviation-group-actions">',
      '<button type="button" class="btn btn-secondary btn-small deviation-group-add">Ny lenke</button>',
      '<button type="button" class="btn btn-secondary btn-small deviation-add-group">Nytt avvik her</button>',
      '</div>',
      '</div>'
    ].join('');
  }

  function deviationLinksHtml(row, dIndex) {
    var links = ensureDeviationLinks(row);
    var activeIdx = activeDeviationLinkIndex(row);
    var nav = links.length ? '<div class="deviation-link-tabs-nav" role="tablist">' + links.map(function (_entry, linkIndex) {
      var active = linkIndex === activeIdx ? ' is-active' : '';
      return '<button type="button" class="deviation-link-tab-btn' + active + '" data-link-index="' + linkIndex + '" role="tab" aria-selected="' + (linkIndex === activeIdx ? 'true' : 'false') + '">Lenke ' + (linkIndex + 1) + '</button>';
    }).join('') + '</div>' : '';
    var tabs = links.map(function (entry, linkIndex) {
      var active = linkIndex === activeIdx;
      return [
        '<div class="deviation-link-tab' + (active ? ' is-active' : '') + '" data-link-index="' + linkIndex + '"' + (active ? '' : ' hidden') + '>',
        '<div class="deviation-link-head"><strong>Lenke ' + (linkIndex + 1) + '</strong><button type="button" class="btn btn-danger btn-small deviation-link-remove">Fjern</button></div>',
        '<div class="grid-two compact-grid-form">',
        '<label><span>Start</span><input class="deviation-link-start" value="' + escapeHtml(entry.start || '') + '" /></label>',
        '<div class="actions-row wrap align-end"><button type="button" class="btn btn-secondary btn-small deviation-link-start-fill">Bruk posisjon</button></div>',
        '<label><span>Slutt</span><input class="deviation-link-end" value="' + escapeHtml(entry.end || '') + '" /></label>',
        '<div class="actions-row wrap align-end"><button type="button" class="btn btn-secondary btn-small deviation-link-end-fill">Bruk posisjon</button></div>',
        '<label class="span-2"><span>Merknad lenke</span><input class="deviation-link-note" value="' + escapeHtml(entry.note || '') + '" /></label>',
        '</div>',
        '</div>'
      ].join('');
    }).join('');
    return [
      '<div class="deviation-links" data-dev-index="' + dIndex + '">',
      '<div class="deviation-links-head"><span>Lenker</span><button type="button" class="btn btn-secondary btn-small deviation-link-add">Legg til lenke</button></div>',
      nav,
      tabs || '<div class="small muted">Ingen lenker registrert.</div>',
      '</div>'
    ].join('');
  }

  function suggestedDeviationText(item) {
    var key = String(item && item.key || '').toLowerCase();
    var label = String(item && (item.label || item.summary_text || item.key) || 'Registrert avvik').trim();
    var mapped = {
      'vak_merking': 'Manglende eller feil merking av vak / redskap',
      'hummer_merking': 'Manglende eller feil merking av hummerredskap',
      'samleteine_merking': 'Samleteine / sanketeine uten korrekt merking',
      'hummer_fluktapning': 'Hummerteine uten påbudt fluktåpning',
      'fluktapning': 'Redskap uten påbudt fluktåpning',
      'hummer_ratentrad': 'Hummerteine uten påbudt råtnetråd eller rømningshull',
      'ratentrad': 'Redskap uten påbudt råtnetråd eller rømningshull',
      'hummer_minstemal': 'Oppbevaring eller fangst av hummer under minstemål',
      'hummer_lengdekrav': 'Oppbevaring eller fangst av hummer utenfor tillatt lengdekrav',
      'hummer_rogn': 'Oppbevaring eller fangst av rognhummer',
      'hummerdeltakernummer': 'Fiske etter hummer uten gyldig deltakernummer',
      'hummer_antall_teiner_fritid': 'Bruk av for mange hummerteiner',
      'hummer_antall_teiner_komm': 'Bruk av for mange hummerteiner',
      'antall_teiner': 'Bruk av for mange teiner / redskap',
      'stengt_omrade_status': 'Redskap satt i stengt område',
      'fredningsomrade_status': 'Redskap satt i fredningsområde',
      'hummer_fredningsomrade_redskap': 'Redskap satt i hummerfredningsområde',
      'hummer_maksimalmal': 'Oppbevaring eller fangst av hummer over maksimalmål',
      'maksimalmal_omrade': 'Fiske i område med særskilt maksimalmål for hummer'
    };
    return mapped[key] || label;
  }

  function deviationUnitLabel(row) {
    if (!row) return '';
    var parts = [String(row.seizure_ref || '').trim(), String(row.gear_kind || '').trim()];
    var legacyRef = String(row.gear_ref || '').trim();
    if (legacyRef) parts.push(legacyRef);
    return parts.filter(Boolean).join(' · ');
  }

  function collectDeviationUnits(currentRow) {
    var unitsByRef = {};
    function addUnit(row, fallbackKind) {
      var ref = String(row && (row.seizure_ref || row.reference || row.ref) || '').trim();
      if (!ref) return;
      if (currentRow && row === currentRow) return;
      if (!unitsByRef[ref]) {
        unitsByRef[ref] = {
          seizure_ref: ref,
          gear_kind: String((row && (row.gear_kind || row.type)) || fallbackKind || '').trim(),
          gear_ref: String(row && row.gear_ref || '').trim(),
          position: String(row && row.position || '').trim()
        };
      }
      if (!unitsByRef[ref].gear_kind && row && (row.gear_kind || row.type)) unitsByRef[ref].gear_kind = String(row.gear_kind || row.type).trim();
      if (!unitsByRef[ref].gear_ref && row && row.gear_ref) unitsByRef[ref].gear_ref = String(row.gear_ref).trim();
      if (!unitsByRef[ref].position && row && row.position) unitsByRef[ref].position = String(row.position).trim();
    }
    findingsState.forEach(function (finding) {
      ensureDeviationState(finding).forEach(function (row) { addUnit(row, defaultDeviationGearKind()); });
      ensureMeasurementState(finding).forEach(function (row) { addUnit(row, 'Måling'); });
    });
    (seizureReportsState || []).forEach(function (row) { addUnit(row, row && row.type ? row.type : 'Beslag'); });
    if (currentRow && currentRow.linked_seizure_ref) {
      var currentRef = String(currentRow.linked_seizure_ref || '').trim();
      if (currentRef && !unitsByRef[currentRef]) {
        unitsByRef[currentRef] = { seizure_ref: currentRef, gear_kind: String(currentRow.gear_kind || '').trim(), gear_ref: String(currentRow.gear_ref || '').trim(), position: String(currentRow.position || '').trim() };
      }
    }
    return Object.keys(unitsByRef).sort().map(function (key) { return unitsByRef[key]; });
  }


  function findDeviationUnitByRef(ref, currentRow) {
    ref = String(ref || '').trim();
    if (!ref) return null;
    var units = collectDeviationUnits(currentRow);
    for (var i = 0; i < units.length; i += 1) {
      if (String(units[i].seizure_ref || '') === ref) return units[i];
    }
    if (currentRow && String(currentRow.seizure_ref || '').trim() === ref) {
      return { seizure_ref: ref, gear_kind: String(currentRow.gear_kind || '').trim(), gear_ref: String(currentRow.gear_ref || '').trim(), position: String(currentRow.position || '').trim() };
    }
    return null;
  }

  function deviationExistingGearOptionsHtml(row) {
    var selectedRef = String(row && row.linked_seizure_ref || '').trim();
    var units = collectDeviationUnits(row);
    var options = ['<option value="">Nytt redskap (automatisk beslag nr.)</option>'];
    units.forEach(function (unit) {
      var label = deviationUnitLabel(unit) || unit.seizure_ref || 'Tidligere registrert redskap';
      options.push('<option value="' + escapeHtml(unit.seizure_ref) + '" ' + (selectedRef === unit.seizure_ref ? 'selected' : '') + '>' + escapeHtml(label) + '</option>');
    });
    if (selectedRef && !units.some(function (unit) { return String(unit.seizure_ref || '') === selectedRef; })) {
      var fallback = findDeviationUnitByRef(selectedRef, row) || { seizure_ref: selectedRef, gear_kind: row && row.gear_kind || '', gear_ref: row && row.gear_ref || '' };
      options.push('<option value="' + escapeHtml(selectedRef) + '" selected>' + escapeHtml(deviationUnitLabel(fallback) || selectedRef) + '</option>');
    }
    return options.join('');
  }

  function nextSeizureSequence() {
    var maxSeq = 0;
    function scanRef(refValue) {
      var match = /-(\d{3})\s*$/.exec(String(refValue || ''));
      if (!match) return;
      var seq = Number(match[1] || 0);
      if (seq > maxSeq) maxSeq = seq;
    }
    findingsState.forEach(function (finding) {
      ensureDeviationState(finding).forEach(function (row) {
        scanRef(row.seizure_ref);
      });
      ensureMeasurementState(finding).forEach(function (row) {
        scanRef(row.seizure_ref || row.reference);
      });
    });
    return maxSeq + 1;
  }

  function syncDeviationDefaults(item) {
    ensureDeviationState(item).forEach(function (row) {
      row.linked_seizure_ref = String(row.linked_seizure_ref || '').trim();
      if (!row.gear_kind) row.gear_kind = defaultDeviationGearKind();
      else row.gear_kind = normalizeDeviationGearKind(row.gear_kind);
      if (!row.quantity) row.quantity = '1';
      if (!row.violation) row.violation = suggestedDeviationText(item);
      if (row.linked_seizure_ref) {
        var linked = findDeviationUnitByRef(row.linked_seizure_ref, row);
        row.seizure_ref = row.linked_seizure_ref;
        if (linked && linked.gear_kind) row.gear_kind = normalizeDeviationGearKind(linked.gear_kind);
        if (linked && linked.gear_ref && !row.gear_ref) row.gear_ref = linked.gear_ref;
      } else if (!row.seizure_ref) {
        row.seizure_ref = formatSeizureRef(nextSeizureSequence());
      }
      if (!row.position && currentCoordText()) row.position = currentCoordText();
      var rowLinks = ensureDeviationLinks(row);
      if (!rowLinks.length) { row.links = [defaultDeviationLink()]; row.active_link_index = 0; }
    });
    item.deviation_summary = deviationSummaryText(item);
  }

  function evidenceIsImage(item) {
    return !item || !item.mime_type || String(item.mime_type).indexOf('audio/') !== 0;
  }

  function selectedInlineTargetMatches(item, row) {
    if (!selectedInlineEvidenceTarget || !item || !row) return false;
    return String(selectedInlineEvidenceTarget.finding_key || '') === String(item.key || '') && String(selectedInlineEvidenceTarget.seizure_ref || '') === String(row.seizure_ref || '');
  }

  function evidenceItemsForDeviation(item, row) {
    return (evidenceState || []).filter(function (entry) {
      if (!evidenceIsImage(entry)) return false;
      if (row && row.seizure_ref && String(entry.seizure_ref || '') === String(row.seizure_ref || '')) return true;
      return !row && item && item.key && String(entry.finding_key || '') === String(item.key || '');
    });
  }

  function deviationTargetSummary(item, row) {
    if (!item || !row) return 'Ingen rad valgt ennå.';
    var parts = [row.seizure_ref || 'uten beslag', row.gear_kind || 'redskap', row.violation || suggestedDeviationText(item)];
    if (row.position) parts.push('posisjon ' + row.position);
    if (row.gear_ref) parts.push('tidligere ID ' + row.gear_ref);
    return parts.filter(Boolean).join(' · ');
  }

  function deviationInfoBoxHtml(item, rows) {
    rows = rows || [];
    if (!rows.length || String(item.status || '').toLowerCase() !== 'avvik') return '';
    var activeRow = null;
    rows.forEach(function (row) {
      if (!activeRow && selectedInlineTargetMatches(item, row)) activeRow = row;
    });
    if (!activeRow) activeRow = rows[0] || null;
    var linked = evidenceItemsForDeviation(item, activeRow);
    var linkedPreview = linked.length ? linked.slice(0, 3).map(function (entry) {
      return '<div class="small muted">\u2022 ' + escapeHtml(entry.caption || entry.original_filename || 'Bildebevis') + '</div>';
    }).join('') : '<div class="small muted">Ingen bilder koblet.</div>';
    var feedback = activeRow && selectedInlineTargetMatches(item, activeRow) && inlineEvidenceFeedback ? '<div class="small deviation-upload-status">' + escapeHtml(inlineEvidenceFeedback) + '</div>' : '';
    var knownUnits = collectDeviationUnits(null);
    var knownSummary = knownUnits.length ? knownUnits.slice(0, 6).map(function (row) { return deviationUnitLabel(row); }).join(', ') + (knownUnits.length > 6 ? ' ...' : '') : 'Ingen tidligere beslag.';
    return [
      '<div class="callout deviation-info-box">',
      '<strong>Redskap/beslag</strong>',
      '<div class="small muted">Beslagsnr. settes automatisk. Velg tidligere beslag for flere avvik p\u00e5 samme redskap.</div>',
      '<div class="small muted">Tidligere: ' + escapeHtml(knownSummary) + '</div>',
      '<div class="small" style="margin-top:8px"><strong>Bilde:</strong> ' + escapeHtml(deviationTargetSummary(item, activeRow)) + '</div>',
      '<div class="small muted">Bilder: ' + escapeHtml(String(linked.length)) + '</div>',
      linkedPreview,
      '<div class="actions-row wrap margin-top-s"><button type="button" class="btn btn-secondary btn-small inline-evidence-camera">Kamera</button><button type="button" class="btn btn-secondary btn-small inline-evidence-file">Bilde</button></div>',
      feedback,
      '</div>'
    ].join('');
  }

  function measurementSummaryText(item) {
    var rows = ensureMeasurementState(item);
    if (!rows.length) return '';
    return rows.map(function (row, idx) {
      var ref = row.seizure_ref || row.reference || ('Måling ' + (idx + 1));
      var length = row.length_cm ? (String(row.length_cm).replace('.', ',') + ' cm') : 'ukjent lengde';
      var delta = row.delta_text ? (' – ' + row.delta_text) : '';
      var posText = row.position ? (' / posisjon ' + row.position) : '';
      var note = row.note ? (' (' + row.note + ')') : '';
      return ref + ': ' + length + delta + posText + note;
    }).join('; ');
  }

  function markerSummaryText(item) {
    var pos = ensureMarkerState(item);
    var parts = [];
    if (pos.current) parts.push('Kontrollørposisjon: ' + pos.current);
    if (pos.is_linked && pos.start) parts.push('Startposisjon lenke: ' + pos.start);
    if (pos.is_linked && pos.end) parts.push('Sluttposisjon lenke: ' + pos.end);
    if (pos.total) parts.push('Kontrollerte teiner: ' + pos.total);
    if (pos.approved) parts.push('Godkjente: ' + pos.approved);
    if (pos.deviations) parts.push('Med avvik: ' + pos.deviations);
    return parts.join(' | ');
  }

  function measurementSectionHtml(item, index) {
    if (!itemSupportsMeasurements(item)) return '';
    var rows = ensureMeasurementState(item);
    syncMeasurementDefaults(item);
    var minLabel = item.applied_min_size_cm || item.min_size_cm ? ('Minstekrav: ' + escapeHtml(String(item.applied_min_size_cm || item.min_size_cm)) + ' cm') : '';
    var maxLabel = item.applied_max_size_cm || item.max_size_cm ? (' / Maks: ' + escapeHtml(String(item.applied_max_size_cm || item.max_size_cm)) + ' cm') : '';
    return [
      '<div class="finding-extra finding-measurements">',
      '<div class="subhead">Lengdemålinger' + (minLabel || maxLabel ? ' <span class="muted small">' + minLabel + maxLabel + '</span>' : '') + '</div>',
      '<div class="small muted">Målinger får eget målingsnummer eller kan knyttes til et tidligere registrert beslag/redskap. Posisjon knyttes til samme beslagnummer slik at bildebevis og illustrasjonsrapport sorteres riktig.</div>',
      '<div class="measurement-list">' + rows.map(function (row, mIndex) {
        var evaluationClass = 'measurement-evaluation';
        if (row.measurement_state === 'under_min' || row.measurement_state === 'over_max') evaluationClass += ' is-alert';
        else if (row.measurement_state === 'ok') evaluationClass += ' is-ok';
        var linkedMode = Boolean(String(row.linked_seizure_ref || '').trim());
        return [
          '<div class="measurement-row" data-measure-index="' + mIndex + '">',
          '<input class="measurement-reference" placeholder="Beslag / ref" value="' + escapeHtml(row.reference || '') + '" readonly />',
          '<select class="measurement-existing-gear" title="Knytt måling til tidligere beslag/redskap">' + deviationExistingGearOptionsHtml(row).replace('Nytt redskap (automatisk beslag nr.)', 'Ny måling (automatisk målingsnr.)') + '</select>',
          '<input class="measurement-length" type="number" step="0.1" placeholder="cm (0,1 = 1 mm)" value="' + escapeHtml(row.length_cm || '') + '" />',
          '<input class="measurement-position" placeholder="Posisjon for måling/beslag" value="' + escapeHtml(row.position || '') + '" />',
          '<button type="button" class="btn btn-secondary btn-small measurement-position-fill">Bruk posisjon</button>',
          '<div class="' + evaluationClass + '">' + escapeHtml(row.delta_text || 'Legg inn måling i cm for automatisk vurdering.') + '</div>',
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
    var linkHidden = pos.is_linked ? '' : ' hidden';
    var parts = ['<div class="finding-extra finding-marker-positions">'];
    parts.push('<div class="subhead">Merking av vak / kontrollposisjon</div>');
    if (showPositions) {
      parts.push('<label class="check-chip marker-linked-wrap"><input class="marker-is-linked" type="checkbox" ' + (pos.is_linked ? 'checked' : '') + ' /> Redskapet er lenke / har start- og sluttposisjon</label>');
      parts.push('<div class="grid-two compact-grid-form margin-top-s">');
      parts.push('<label><span>Kontrollørposisjon</span><input class="marker-current" value="' + escapeHtml(pos.current || '') + '" /></label>');
      parts.push('<div class="actions-row wrap align-end"><button type="button" class="btn btn-secondary btn-small marker-current-fill">Bruk nåværende posisjon</button><button type="button" class="btn btn-secondary btn-small marker-current-refresh">Oppdater</button></div>');
      parts.push('</div>');
      parts.push('<div class="marker-link-positions grid-two compact-grid-form margin-top-s' + linkHidden + '">');
      parts.push('<label><span>Startposisjon lenke/garn</span><input class="marker-start" value="' + escapeHtml(pos.start || '') + '" /></label>');
      parts.push('<div class="actions-row wrap align-end"><button type="button" class="btn btn-secondary btn-small marker-start-fill">Sett start = nåværende</button></div>');
      parts.push('<label><span>Sluttposisjon lenke/garn</span><input class="marker-end" value="' + escapeHtml(pos.end || '') + '" /></label>');
      parts.push('<div class="actions-row wrap align-end"><button type="button" class="btn btn-secondary btn-small marker-end-fill">Sett slutt = nåværende</button></div>');
      parts.push('</div>');
      parts.push('<div class="small muted">Hvis redskapet ikke er lenke, vises bare kontrollørposisjon. Start/sluttposisjon åpnes når lenke er krysset av.</div>');
    }
    if (showCounts) {
      parts.push('<div class="grid-three compact-grid-form margin-top-s">');
      parts.push('<label><span>Antall teiner/redskap kontrollert</span><input class="marker-total" type="number" min="0" value="' + escapeHtml(pos.total || '') + '" /></label>');
      parts.push('<label><span>Antall godkjente</span><input class="marker-approved" type="number" min="0" value="' + escapeHtml(pos.approved || '') + '" /></label>');
      parts.push('<label><span>Antall med avvik</span><input class="marker-deviations" type="number" min="0" value="' + escapeHtml(pos.deviations || '') + '" /></label>');
      parts.push('</div>');
      parts.push('<div class="small muted">Bruk avviksradene under til å registrere flere konkrete redskap med eget beslagnummer. Flere avvik kan kobles til samme beslag.</div>');
    }
    parts.push('<div class="small muted structured-preview">' + escapeHtml(markerSummaryText(item)) + '</div>');
    parts.push('</div>');
    return parts.join('');
  }


  function deviationSectionHtml(item) {
    var rows = ensureDeviationState(item);
    syncDeviationDefaults(item);
    var groupState = normalizeDeviationLinkGroups(item);
    rows = groupState.rows;
    var activeGroup = groupState.activeIndex;
    var isAvvik = String(item.status || '').toLowerCase() === 'avvik';
    return [
      '<div class="finding-extra finding-deviations ' + (isAvvik ? '' : 'hidden') + '">',
      '<div class="subhead">Legg til redskap/beslag</div>',
      '<div class="small muted deviation-short-help">Bla mellom lenker øverst. Hvert avvik kan ha eget eller gjenbrukt beslagsnummer.</div>',
      '<div class="deviation-list">' + rows.map(function (row, dIndex) {
        var linkedCount = evidenceItemsForDeviation(item, row).length;
        var selectedClass = selectedInlineTargetMatches(item, row) ? ' deviation-row-selected' : '';
        var linkedMode = Boolean(String(row.linked_seizure_ref || '').trim());
        var rowGroup = Number(row.link_group_index || 0);
        var groupHidden = rowGroup === activeGroup ? '' : ' hidden';
        return [
          '<div class="deviation-row' + selectedClass + '" data-dev-index="' + dIndex + '" data-link-group-index="' + rowGroup + '" data-seizure-ref="' + escapeHtml(String(row.seizure_ref || '')) + '"' + groupHidden + '>',
          '<div class="deviation-row-head"><strong>Lenke ' + (rowGroup + 1) + ' · Avvik ' + (dIndex + 1) + '</strong><span class="muted small">' + escapeHtml(row.seizure_ref || 'Beslag opprettes') + '</span></div>',
          '<div class="deviation-row-fields">',
          '<input class="deviation-seizure-ref" placeholder="Beslagsnr." title="Beslagsnummer" value="' + escapeHtml(row.seizure_ref || '') + '" readonly />',
          '<select class="deviation-existing-gear" title="Tidligere beslag/redskap i saken">' + deviationExistingGearOptionsHtml(row) + '</select>',
          '<select class="deviation-gear-kind" title="Type redskap" ' + (linkedMode ? 'disabled' : '') + '>' + deviationGearOptions().map(function (opt) { return '<option value="' + escapeHtml(opt) + '" ' + (String(row.gear_kind || '') === opt ? 'selected' : '') + '>' + escapeHtml(opt) + '</option>'; }).join('') + '</select>',
          '<input class="deviation-quantity" type="number" min="1" placeholder="Antall" value="' + escapeHtml(row.quantity || '') + '" />',
          '<input class="deviation-position" placeholder="Posisjon" value="' + escapeHtml(row.position || '') + '" />',
          '<button type="button" class="btn btn-secondary btn-small deviation-position-fill">Bruk posisjon</button>',
          '<input class="deviation-violation" placeholder="Korttekst avvik" value="' + escapeHtml(row.violation || '') + '" />',
          '<input class="deviation-note" placeholder="Manuell merknad" value="' + escapeHtml(row.note || '') + '" />',
          '<textarea class="deviation-report-draft span-2" rows="3" readonly title="Autogenerert tekst til beslagsrapport">' + escapeHtml(deviationReportDraftText(item, row)) + '</textarea>',
          '<button type="button" class="btn btn-secondary btn-small deviation-evidence-link ' + (isAvvik ? '' : 'hidden') + '">' + (linkedCount ? ('Bilde (' + linkedCount + ')') : 'Bilde') + '</button>',
          '<button type="button" class="btn btn-secondary btn-small deviation-camera ' + (isAvvik ? '' : 'hidden') + '">Kamera</button>',
          '<button type="button" class="btn btn-secondary btn-small deviation-file ' + (isAvvik ? '' : 'hidden') + '">Legg til bilde</button>',
          '<button type="button" class="btn btn-danger btn-small deviation-remove">Fjern</button>',
          '</div>',
          '</div>'
        ].join('');
      }).join('') + '</div>',
      '<div class="actions-row wrap"><button type="button" class="btn btn-secondary btn-small deviation-add">Legg til redskap/beslag</button></div>',
      '<div class="small muted structured-preview">' + escapeHtml(deviationSummaryText(item)) + '</div>',
      deviationInfoBoxHtml(item, rows),
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
      isAvvik ? '<button type="button" class="btn btn-secondary btn-small deviation-add-top">Legg til redskap/beslag</button>' : '',
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
      isAvvik ? '<div class="finding-body-actions actions-row wrap"><button type="button" class="btn btn-primary btn-small deviation-add-body">Legg til redskap/beslag</button></div>' : '',
      measurementSectionHtml(item, index),
      markerSectionHtml(item),
      deviationSectionHtml(item),
      (item.auto_note ? '<div class="callout area-warning margin-top-s"><strong>Automatisk varsel</strong><div>' + escapeHtml(item.auto_note) + '</div></div>' : ''),
      '<div class="actions-row wrap">',
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
    if (sharedCreatePortalMap) return sharedCreatePortalMap(el, layers, markerState);
    if (!el || !window.L) return Promise.resolve(null);
    var storageKey = 'kv-map-view:' + (el.id || 'map');
    var savedView = null;
    try {
      savedView = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    } catch (e) { savedView = null; }

    function validLatLng(lat, lng) {
      return isFinite(lat) && isFinite(lng) && Math.abs(Number(lat)) <= 90 && Math.abs(Number(lng)) <= 180 && !(Math.abs(Number(lat)) < 0.000001 && Math.abs(Number(lng)) < 0.000001);
    }

    function caseIcon() {
      return L.divIcon({ className: 'kv-case-marker', html: '<div class="leaflet-case-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
    }

    function userIcon() {
      return L.divIcon({ className: 'kv-user-marker', html: '<div class="leaflet-user-dot"></div>', iconSize: [16, 16], iconAnchor: [8, 8] });
    }

    var state = el._kvPortalState;
    if (!state) {
      var initialView = (markerState && markerState.view) || savedView || ((markerState && validLatLng(markerState.lat, markerState.lng)) ? { lat: markerState.lat, lng: markerState.lng, zoom: markerState.defaultZoom || 11 } : ((markerState && validLatLng(markerState.deviceLat, markerState.deviceLng)) ? { lat: markerState.deviceLat, lng: markerState.deviceLng, zoom: markerState.defaultZoom || 13 } : null));
      var map = L.map(el, { zoomControl: true }).setView(initialView ? [initialView.lat, initialView.lng] : [63.5, 11], initialView ? initialView.zoom : 5);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap'
      }).addTo(map);
      state = {
        map: map,
        storageKey: storageKey,
        overlaysById: {},
        legendControl: null,
        markerState: markerState || {},
        clickBound: false
      };
      map.on('moveend zoomend', function () {
        try {
          var center = map.getCenter();
          sessionStorage.setItem(storageKey, JSON.stringify({ lat: center.lat, lng: center.lng, zoom: map.getZoom() }));
        } catch (e) {}
      });
      el._kvPortalState = state;
      el._kvLeafletMap = map;
    }

    state.markerState = markerState || {};
    var map = state.map;
    var activeLayerIds = {};

    var promises = (layers || []).map(function (layer) {
      var cacheKey = String(layer.id);
      activeLayerIds[cacheKey] = true;
      if (state.overlaysById[cacheKey]) return Promise.resolve();
      var dataPromise = portalFeatureCache[cacheKey]
        ? Promise.resolve(portalFeatureCache[cacheKey])
        : fetch('/api/map/features?layer_id=' + encodeURIComponent(layer.id))
            .then(function (r) { return r.json(); })
            .then(function (data) {
              var normalized = normalizeFeatureCollection(data);
              if (normalized.features && normalized.features.length) portalFeatureCache[cacheKey] = normalized;
              return normalized;
            });
      return dataPromise.then(function (data) {
        data = normalizeFeatureCollection(data);
        if (!data.features.length) return;
        var geo = L.geoJSON(data, {
          style: function () {
            return { color: layer.color || '#c1121f', weight: 2.5, fillColor: layer.color || '#c1121f', fillOpacity: 0.2 };
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
        state.overlaysById[cacheKey] = geo;
      }).catch(function () {});
    });

    return Promise.all(promises).then(function () {
      Object.keys(state.overlaysById).forEach(function (key) {
        if (activeLayerIds[key]) return;
        try { map.removeLayer(state.overlaysById[key]); } catch (e) {}
        delete state.overlaysById[key];
      });

      if (state.legendControl) {
        try { map.removeControl(state.legendControl); } catch (e) {}
        state.legendControl = null;
      }
      if (layers && layers.length) {
        var legendControl = L.control({ position: 'bottomleft' });
        legendControl.onAdd = function () {
          var div = L.DomUtil.create('div', 'leaflet-legend-control');
          div.innerHTML = '<div class="leaflet-legend-title">Kartlag</div>' + (layers || []).map(function (layer) {
            return '<div class="leaflet-legend-row"><span class="leaflet-legend-swatch" style="background:' + escapeHtml(layer.color || '#c1121f') + '"></span><span>' + escapeHtml(layer.name || '') + '</span></div>';
          }).join('');
          return div;
        };
        legendControl.addTo(map);
        state.legendControl = legendControl;
      }

      var ms = state.markerState || {};
      var hasCase = validLatLng(ms.lat, ms.lng);
      var hasDevice = ms.showDeviceMarker !== false && validLatLng(ms.deviceLat, ms.deviceLng);

      if (hasCase) {
        if (!state.caseMarker) {
          state.caseMarker = L.marker([ms.lat, ms.lng], { draggable: !!ms.draggable, icon: caseIcon() }).addTo(map);
          state.caseMarker.on('dragend', function (event) {
            var currentState = el._kvPortalState && el._kvPortalState.markerState ? el._kvPortalState.markerState : {};
            var ll = event.target.getLatLng();
            if (typeof currentState.onManualMove === 'function') currentState.onManualMove(ll.lat, ll.lng);
            else if (typeof currentState.onMove === 'function') currentState.onMove(ll.lat, ll.lng);
          });
        }
        state.caseMarker.setLatLng([ms.lat, ms.lng]);
        state.caseMarker.setIcon(caseIcon());
        if (state.caseMarker.dragging) {
          if (ms.draggable) state.caseMarker.dragging.enable();
          else state.caseMarker.dragging.disable();
        }
        state.caseMarker.bindPopup('Kontrollposisjon');
        if (!state.caseRadius) {
          state.caseRadius = L.circle([ms.lat, ms.lng], {
            radius: (ms.radiusKm || 50) * 1000,
            color: '#24527b',
            weight: 1,
            fillColor: '#24527b',
            fillOpacity: 0.06
          }).addTo(map);
        } else {
          state.caseRadius.setLatLng([ms.lat, ms.lng]);
          state.caseRadius.setRadius((ms.radiusKm || 50) * 1000);
        }
      } else {
        if (state.caseMarker) { try { map.removeLayer(state.caseMarker); } catch (e) {} state.caseMarker = null; }
        if (state.caseRadius) { try { map.removeLayer(state.caseRadius); } catch (e) {} state.caseRadius = null; }
      }

      if (hasDevice) {
        if (!state.deviceMarker) {
          state.deviceMarker = L.marker([ms.deviceLat, ms.deviceLng], { icon: userIcon(), interactive: false }).addTo(map);
        }
        state.deviceMarker.setLatLng([ms.deviceLat, ms.deviceLng]);
        state.deviceMarker.setIcon(userIcon());
        state.deviceMarker.bindPopup('Enhetens posisjon');
        if (!state.deviceAccuracy) {
          state.deviceAccuracy = L.circle([ms.deviceLat, ms.deviceLng], {
            radius: Math.max(8, Number(ms.deviceAccuracy || 12)),
            color: '#1e7bff',
            weight: 1,
            fillColor: '#1e7bff',
            fillOpacity: 0.12,
            interactive: false
          }).addTo(map);
        } else {
          state.deviceAccuracy.setLatLng([ms.deviceLat, ms.deviceLng]);
          state.deviceAccuracy.setRadius(Math.max(8, Number(ms.deviceAccuracy || 12)));
        }
      } else {
        if (state.deviceMarker) { try { map.removeLayer(state.deviceMarker); } catch (e) {} state.deviceMarker = null; }
        if (state.deviceAccuracy) { try { map.removeLayer(state.deviceAccuracy); } catch (e) {} state.deviceAccuracy = null; }
      }

      if (!state.clickBound) {
        map.on('click', function (event) {
          var currentState = el._kvPortalState && el._kvPortalState.markerState ? el._kvPortalState.markerState : {};
          if (!currentState.allowMapMove) return;
          if (typeof currentState.onManualMove !== 'function' && typeof currentState.onMove !== 'function') return;
          if (!state.caseMarker) {
            state.caseMarker = L.marker(event.latlng, { draggable: !!currentState.draggable, icon: caseIcon() }).addTo(map);
            state.caseMarker.on('dragend', function (dragEvent) {
              var liveState = el._kvPortalState && el._kvPortalState.markerState ? el._kvPortalState.markerState : {};
              var ll = dragEvent.target.getLatLng();
              if (typeof liveState.onManualMove === 'function') liveState.onManualMove(ll.lat, ll.lng);
              else if (typeof liveState.onMove === 'function') liveState.onMove(ll.lat, ll.lng);
            });
          }
          state.caseMarker.setLatLng(event.latlng);
          if (typeof currentState.onManualMove === 'function') currentState.onManualMove(event.latlng.lat, event.latlng.lng);
          else currentState.onMove(event.latlng.lat, event.latlng.lng);
        });
        state.clickBound = true;
      }

      if (ms.recenterTo === 'device' && hasDevice) map.setView([ms.deviceLat, ms.deviceLng], ms.recenterZoom || Math.max(map.getZoom(), 15));
      else if (ms.recenterTo === 'case' && hasCase) map.setView([ms.lat, ms.lng], ms.recenterZoom || Math.max(map.getZoom(), 14));

      setTimeout(function () {
        try { map.invalidateSize(); } catch (e) {}
      }, 120);
      return { map: map, geoLayers: Object.keys(state.overlaysById).map(function (key) { return state.overlaysById[key]; }), marker: state.caseMarker || null, circle: state.caseRadius || null, deviceMarker: state.deviceMarker || null, accuracyCircle: state.deviceAccuracy || null };
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
          statusEl.innerHTML = 'Kunne ikke sjekke verneområder akkurat nå.';
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
    controlType = document.getElementById('overview_control_type');
    fisheryType = document.getElementById('overview_fishery_type');
    species = document.getElementById('overview_species');
    var speciesList = document.getElementById('overview_species_options');
    gearType = document.getElementById('overview_gear_type');
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
      if (!controlType.value || !speciesVal) {
        meta.innerHTML = 'Velg kontrolltype og art/fiskeri først. Redskap kan legges til for mer presist regelverk.';
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
    if (!root.dataset.caseId && window.KVLocalCases && typeof window.KVLocalCases.generateLocalCaseId === 'function') {
      root.dataset.caseId = window.KVLocalCases.generateLocalCaseId();
      root.dataset.caseUrl = '/cases/offline/new?local_id=' + encodeURIComponent(root.dataset.caseId);
    }

    var lawBrowser = parseJson(root.dataset.lawBrowser, []);
    var mapCatalog = parseJson(root.dataset.mapCatalog, []);
    var mapFilterWrap = document.getElementById('map-layer-filters');
    var mapFilterStorageKey = 'kv-map-layer-filter-1-8-6:' + root.dataset.caseId;
    var activeLayerStatuses = { 'fredningsområde': true, 'stengt område': true, 'maksimalmål område': true, 'regulert område': true, 'nullfiskeområde': true };
    try {
      localStorage.removeItem('kv-map-layer-filter:' + root.dataset.caseId);
    } catch (e) {}

    function normalizeSelectionText(value) {
      return String(value || '').toLowerCase().replace(/[_/]+/g, ' ').replace(/[–—-]+/g, ' ').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim();
    }

    var fisheryAliases = {
      'hummer': ['hummer'],
      'taskekrabbe': ['taskekrabbe'],
      'torsk': ['torsk', 'kysttorsk', 'skrei'],
      'kveite': ['kveite'],
      'laks i sjø': ['laks i sjo', 'laks', 'laksefjord', 'laksefjorder'],
      'sjøørret': ['sjoorret', 'sjorret'],
      'makrell': ['makrell'],
      'hyse': ['hyse'],
      'sei': ['sei', 'seinot'],
      'leppefisk': ['leppefisk'],
      'sjøkreps': ['sjokreps'],
      'kongekrabbe': ['kongekrabbe'],
      'snøkrabbe': ['snokrabbe'],
      'makrellstørje': ['makrellstorje', 'storje'],
      'sild': ['sild', 'nvg sild', 'nvgsild'],
      'nvg-sild': ['nvg sild', 'nvgsild'],
      'reke': ['reke'],
      'breiflabb': ['breiflabb'],
      'blåkveite': ['blakveite'],
      'lange': ['lange'],
      'brosme': ['brosme'],
      'kolmule': ['kolmule'],
      'øyepål': ['oyepal'],
      'hestmakrell': ['hestmakrell'],
      'flatøsters': ['flatosters'],
      'steinbit': ['steinbit']
    };

    var gearAliases = {
      'teine': ['teine', 'teiner'],
      'samleteine / sanketeine': ['samleteine', 'sanketeine'],
      'line': ['line'],
      'krokredskap': ['krokredskap', 'krokbegrensning'],
      'trål': ['tral', 'stormasket tral', 'stormasket trål'],
      'pelagisk trål': ['pelagisk tral', 'pelagisk trål'],
      'not': ['not', 'seinot'],
      'ringnot': ['ringnot'],
      'garn': ['garn'],
      'ruse': ['ruse'],
      'jukse': ['jukse'],
      'håndsnøre': ['handsnore', 'håndsnøre'],
      'fiskestang': ['fiskestang'],
      'dorg': ['dorg']
    };

    function canonicalSelection(value, aliasMap) {
      var normalized = normalizeSelectionText(value);
      if (!normalized) return '';
      var keys = Object.keys(aliasMap || {});
      for (var i = 0; i < keys.length; i += 1) {
        var canonical = keys[i];
        var tokens = [normalizeSelectionText(canonical)].concat((aliasMap[canonical] || []).map(normalizeSelectionText));
        for (var j = 0; j < tokens.length; j += 1) {
          if (!tokens[j]) continue;
          if (normalized === tokens[j] || normalized.indexOf(tokens[j]) !== -1) return canonical;
        }
      }
      return normalized;
    }

    function currentFisherySelection() {
      return canonicalSelection(species && species.value ? species.value : (fisheryType && fisheryType.value ? fisheryType.value : ''), fisheryAliases);
    }

    function currentGearSelection() {
      return canonicalSelection(gearType && gearType.value ? gearType.value : '', gearAliases);
    }

    function currentControlSelection() {
      var normalized = normalizeSelectionText(controlType && controlType.value ? controlType.value : '');
      if (!normalized) return '';
      if (normalized.indexOf('kom') === 0 || normalized.indexOf('yrkes') !== -1) return 'kommersiell';
      return 'fritidsfiske';
    }

    function selectionProfileLayerIds() {
      var fisherySel = currentFisherySelection();
      var controlSel = currentControlSelection();
      var gearSel = currentGearSelection();
      if (controlSel === 'fritidsfiske') {
        if (fisherySel === 'hummer') return [3, 35, 75, 76, 77, 78, 82, 83, 85, 87, 91, 92, 94, 208];
        if (fisherySel === 'torsk') return [3, 35, 75, 78, 82, 83, 85, 87, 91, 92, 94, 208];
        if (fisherySel === 'flatøsters') return [3, 35, 73, 75, 78, 87, 91, 92, 208];
        if (fisherySel === 'leppefisk') return [3, 35, 75, 78, 84, 87, 91, 92, 208];
        if (fisherySel === 'steinbit') return [75, 78, 87, 91, 92, 200, 208];
        if (fisherySel === 'laks i sjø' || fisherySel === 'sjøørret') return [3, 35, 75, 78, 87, 91, 92, 208];
        return [3, 35, 75, 78, 82, 83, 85, 87, 91, 92, 94, 208];
      }
      if (controlSel === 'kommersiell') {
        var base = [75, 78, 88, 89, 90, 91, 92, 139, 140, 32, 33, 74, 95, 96, 97, 25, 26];
        if (gearSel === 'trål' || gearSel === 'pelagisk trål') base = [75, 78, 88, 89, 90, 91, 139, 140, 25, 26];
        if (fisherySel === 'tare') base = [75, 89, 90, 91];
        if (fisherySel === 'torsk' || fisherySel === 'hyse' || fisherySel === 'sei') base = base.concat([82, 83, 85, 94]);
        return base.filter(function (value, idx, arr) { return arr.indexOf(value) === idx; });
      }
      if (fisherySel === 'hummer') return [3, 35, 75, 76, 77, 78, 82, 83, 85, 87, 91, 92, 94, 208];
      if (fisherySel === 'torsk') return [3, 35, 75, 78, 82, 83, 85, 87, 91, 92, 94, 208];
      if (fisherySel === 'flatøsters') return [3, 35, 73, 75, 78, 87, 91, 92, 208];
      if (fisherySel === 'leppefisk') return [3, 35, 75, 78, 84, 87, 91, 92, 208];
      if (fisherySel === 'steinbit') return [75, 78, 87, 91, 92, 200, 208];
      if (fisherySel === 'laks i sjø' || fisherySel === 'sjøørret') return [3, 35, 75, 78, 87, 91, 92, 208];
      return [];
    }

    function hasMapSelection() {
      return Boolean(currentControlSelection() || currentFisherySelection() || currentGearSelection());
    }

    function isRestrictiveLawLayer(layer) {
      if (!layer) return false;
      var blob = normalizeSelectionText([layer.name, layer.description, layer.status, layer.panel_group, layer.selection_summary, layer.selection_blob].join(' '));
      var status = normalizeSelectionText(layer.status || '');
      var nonLawTokens = ['kystnaere fiskeridata', 'kystnaer fiskeridata', 'kystnaere', 'gytefelt', 'gyteomrade', 'oppvekst', 'oppvekstomrade', 'beiteomrade', 'fiskeplass', 'fiskeplasser', 'rekefelt', 'lassettingsplass', 'lasettingsplass', 'skjellforekomst', 'havbeitelokalitet', 'statistikkomrade', 'dybde', 'sjokart'];
      var lawTokens = ['forbud', 'fiskeforbud', 'fredning', 'fredningsomrade', 'stengt', 'stengte', 'nullfiske', 'maksimalmal', 'regulering', 'regulert', 'forskrift', 'lov', 'j melding', 'j-melding', 'jmelding', 'verneomrade', 'bunnhabitat', 'korall', 'begrensning', 'restriksjon'];
      var strongLawTokens = ['forbud', 'fiskeforbud', 'forbud mot', 'fredning', 'fredningsomrade', 'stengt', 'stengte', 'nullfiske', 'maksimalmal', 'begrensning', 'restriksjon', 'verneomrade', 'bunnhabitat', 'korall', 'tralforbud', 'krokbegrensning'];
      var openAreaTokens = ['apne omrader', 'apent omrade', 'open area', 'open areas', 'tobis apne', 'tobis aapne'];
      var hasLaw = ['stengt omrade', 'fredningsomrade', 'maksimalmal omrade', 'regulert omrade', 'nullfiskeomrade'].indexOf(status) !== -1 || lawTokens.some(function (token) { return blob.indexOf(token) !== -1; });
      if (status === 'fiskeriomrade') return false;
      if (blob.indexOf('kystnaere fiskeridata') !== -1 || blob.indexOf('kystnaer fiskeridata') !== -1) return false;
      if (openAreaTokens.some(function (token) { return blob.indexOf(token) !== -1; }) && !strongLawTokens.some(function (token) { return blob.indexOf(token) !== -1; })) return false;
      if (nonLawTokens.some(function (token) { return blob.indexOf(token) !== -1; }) && !hasLaw) return false;
      if (layer.is_restrictive_law_layer === false) return false;
      if (layer.is_restrictive_law_layer === true && hasLaw) return true;
      return hasLaw;
    }

    function layerAllowedBySelectionProfile(layer) {
      var id = Number(layer && layer.id);
      if (!isFinite(id)) return false;
      var preferredIds = selectionProfileLayerIds();
      if (!hasMapSelection()) return false;
      if (layer && layer.is_generic && isRestrictiveLawLayer(layer)) return true;
      if (!preferredIds.length) return layerSelectionScore(layer) > 0;
      if (preferredIds.indexOf(id) !== -1) return true;
      return layerSelectionScore(layer) > 0;
    }

    function layerMatchesCurrentSelection(layer) {
      if (!isRestrictiveLawLayer(layer)) return false;
      var restrictionText = normalizeSelectionText([layer.name, layer.description, layer.status, layer.selection_summary, layer.panel_group].join(' '));
      var latNum = latitude && latitude.value ? Number(String(latitude.value).replace(',', '.')) : null;
      if (restrictionText.indexOf('svalbard') !== -1 && !(latNum !== null && latNum > 70)) return false;
      if (/(breivikfjorden|borgundfjorden|henningsvaer|lofotfiske)/.test(restrictionText) && !/(torsk|skrei|kommersiell|yrkes)/.test([currentFisherySelection(), currentControlSelection(), restrictionText].join(' '))) return false;
      var status = String(layer.status || '').trim().toLowerCase();
      if (Object.prototype.hasOwnProperty.call(activeLayerStatuses, status) && !activeLayerStatuses[status]) return false;
      // 1.8.7: Temakartet kan vise bredt uten valg, men under kontroll
      // skal kartet bare vise lovregulerte lag som passer valgt kontrolltype,
      // art/fiskeri og redskap.
      if (!hasMapSelection()) return true;
      return layerAllowedBySelectionProfile(layer);
    }

    function layerSelectionScore(layer) {
      var score = 0;
      var fisherySel = currentFisherySelection();
      var gearSel = currentGearSelection();
      var controlSel = currentControlSelection();
      var fisheryTags = Array.isArray(layer.fishery_tags) ? layer.fishery_tags.map(function (item) { return canonicalSelection(item, fisheryAliases); }).filter(Boolean) : [];
      var gearTags = Array.isArray(layer.gear_tags) ? layer.gear_tags.map(function (item) { return canonicalSelection(item, gearAliases); }).filter(Boolean) : [];
      var controlTags = Array.isArray(layer.control_tags) ? layer.control_tags.map(function (item) {
        var normalized = normalizeSelectionText(item);
        if (!normalized) return '';
        return normalized.indexOf('kom') === 0 ? 'kommersiell' : (normalized.indexOf('fritid') !== -1 ? 'fritidsfiske' : normalized);
      }).filter(Boolean) : [];
      if (controlSel && controlTags.indexOf(controlSel) !== -1) score += 3;
      if (fisherySel && fisheryTags.indexOf(fisherySel) !== -1) score += 4;
      if (gearSel && gearTags.indexOf(gearSel) !== -1) score += 2;
      if (String(layer.status || '').toLowerCase() === 'stengt område') score += 1;
      return score;
    }

    function defaultVisibleMapCatalog(forcedLayerIds) {
      var forced = Array.isArray(forcedLayerIds) ? forcedLayerIds.map(function (value) { return Number(value); }).filter(function (value) { return isFinite(value); }) : [];
      var visible = filteredMapCatalog().filter(function (layer) {
        var id = Number(layer && layer.id);
        if (forced.indexOf(id) !== -1) return true;
        return layerAllowedBySelectionProfile(layer) || layerSelectionScore(layer) > 0;
      });
      if (!visible.length) visible = filteredMapCatalog().slice(0, 8);
      return mergeRelevantMapLayers(visible, forced);
    }

    function filteredMapCatalog() {
      var rows = (mapCatalog || []).filter(function (layer) {
        return layerMatchesCurrentSelection(layer);
      });
      return rows.slice().sort(function (a, b) {
        var scoreDiff = layerSelectionScore(b) - layerSelectionScore(a);
        if (scoreDiff) return scoreDiff;
        return String(a.name || '').localeCompare(String(b.name || ''), 'nb');
      });
    }

    function layerDefinitionById(layerId) {
      var numericId = Number(layerId);
      if (!isFinite(numericId)) return null;
      var rows = mapCatalog || [];
      for (var i = 0; i < rows.length; i += 1) {
        if (Number(rows[i] && rows[i].id) === numericId) return rows[i];
      }
      for (var j = 0; j < rows.length; j += 1) {
        var legacyIds = Array.isArray(rows[j] && rows[j].legacy_ids) ? rows[j].legacy_ids : [];
        for (var k = 0; k < legacyIds.length; k += 1) {
          if (Number(legacyIds[k]) === numericId) return rows[j];
        }
      }
      return null;
    }

    function resolveCatalogLayerId(layerId, layerName) {
      var layer = layerDefinitionById(layerId);
      if (layer && isFinite(Number(layer.id))) return Number(layer.id);
      var wantedName = String(layerName || '').trim().toLowerCase();
      if (!wantedName) return isFinite(Number(layerId)) ? Number(layerId) : null;
      var rows = mapCatalog || [];
      for (var i = 0; i < rows.length; i += 1) {
        var name = String(rows[i] && rows[i].name || '').trim().toLowerCase();
        if (name && name === wantedName) return Number(rows[i].id);
      }
      return isFinite(Number(layerId)) ? Number(layerId) : null;
    }

    function mergeRelevantMapLayers(baseLayers, forcedLayerIds) {
      var merged = [];
      var seen = {};
      function pushLayer(layer) {
        var id = Number(layer && layer.id);
        if (!isFinite(id) || seen[id]) return;
        seen[id] = true;
        merged.push(layer);
      }
      (baseLayers || []).forEach(pushLayer);
      (forcedLayerIds || []).forEach(function (layerId) {
        var layer = layerDefinitionById(layerId);
        if (layer) pushLayer(layer);
      });
      return merged.sort(function (a, b) {
        var forceA = seen[Number(a && a.id)] && (forcedLayerIds || []).indexOf(Number(a && a.id)) !== -1 ? 1 : 0;
        var forceB = seen[Number(b && b.id)] && (forcedLayerIds || []).indexOf(Number(b && b.id)) !== -1 ? 1 : 0;
        if (forceA !== forceB) return forceB - forceA;
        var scoreDiff = layerSelectionScore(b) - layerSelectionScore(a);
        if (scoreDiff) return scoreDiff;
        return String(a && a.name || '').localeCompare(String(b && b.name || ''), 'nb');
      });
    }

    function zoneMatchedLayerIds(result) {
      var ids = [];
      var seen = {};
      var hits = result && result.match && Array.isArray(result.hits) ? result.hits : [];
      hits.forEach(function (hit) {
        var rawIds = [];
        if (hit && Array.isArray(hit.layer_ids) && hit.layer_ids.length) rawIds = hit.layer_ids.slice();
        else if (hit && hit.layer_id !== undefined && hit.layer_id !== null && hit.layer_id !== '') rawIds = [hit.layer_id];
        rawIds.forEach(function (rawLayerId) {
          var resolvedId = resolveCatalogLayerId(rawLayerId, hit && (hit.layer || hit.layer_name || hit.name));
          if (!isFinite(Number(resolvedId)) || seen[Number(resolvedId)]) return;
          var resolvedLayer = layerDefinitionById(resolvedId);
          if (resolvedLayer && !layerMatchesCurrentSelection(resolvedLayer)) return;
          seen[Number(resolvedId)] = true;
          ids.push(Number(resolvedId));
        });
      });
      return ids;
    }

    function visibleFeatureDetailLayerIds(limit, forcedLayerIds) {
      limit = Math.max(4, Number(limit || 8));
      var prioritized = filteredMapCatalog().filter(function (layer) {
        return ['stengt område', 'fredningsområde', 'maksimalmål område', 'regulert område', 'nullfiskeområde'].indexOf(String(layer.status || '').toLowerCase()) !== -1;
      });
      return mergeRelevantMapLayers(prioritized, forcedLayerIds).slice(0, limit).map(function (layer) { return Number(layer.id); }).filter(function (value) { return isFinite(value); });
    }

    function mapToneClass(status) {
      var key = String(status || '').trim().toLowerCase();
      if (key === 'stengt område' || key === 'nullfiskeområde') return 'stengt';
      if (key === 'fredningsområde') return 'fredning';
      if (key === 'maksimalmål område') return 'maksimal';
      if (key === 'regulert område') return 'regulert';
      if (key === 'fiskeriområde') return 'fiskeri';
      return 'annet';
    }

    function renderRelevantAreaPanel(zoneResult) {
      if (!caseRelevantAreasList) return;
      var items = [];
      var seen = {};
      var zoneHits = zoneResult && zoneResult.match && Array.isArray(zoneResult.hits) ? zoneResult.hits : [];
      zoneHits.forEach(function (hit) {
        var key = 'zone:' + String(hit.zone_id || hit.name || hit.layer || '');
        if (!key || seen[key]) return;
        seen[key] = true;
        items.push({
          title: hit.name || hit.layer || hit.status || 'Områdetreff',
          status: hit.status || 'regulert område',
          summary: hit.notes || ('Treff ved ' + (nearestPlace && nearestPlace.value ? nearestPlace.value : 'valgt sted') + '.'),
          meta: [hit.source || '', hit.layer || ''].filter(Boolean),
          emphasis: 'Kontrollposisjon'
        });
      });
      filteredMapCatalog().forEach(function (layer) {
        var key = 'layer:' + String(layer && (layer.id || layer.name) || '');
        if (!key || seen[key]) return;
        seen[key] = true;
        var metaBits = [];
        if (Array.isArray(layer.control_tags) && layer.control_tags.length) metaBits.push('Kontroll: ' + layer.control_tags.join(', '));
        if (Array.isArray(layer.fishery_tags) && layer.fishery_tags.length) metaBits.push('Fiskeri: ' + layer.fishery_tags.join(', '));
        if (Array.isArray(layer.gear_tags) && layer.gear_tags.length) metaBits.push('Redskap: ' + layer.gear_tags.join(', '));
        items.push({
          title: layer.name || ('Lag ' + String(layer.id || '')),
          status: layer.status || 'annet lag',
          summary: layer.selection_summary || layer.description || 'Relevant temalag i gjeldende profil.',
          meta: metaBits,
          emphasis: layerSelectionScore(layer) > 0 ? 'Profiltreff' : 'Temalag'
        });
      });
      if (!items.length) {
        caseRelevantAreasList.innerHTML = '<div class="muted small">Ingen verneområder matcher valgt kontrolltype, art, fiskeri og redskap.</div>';
        return;
      }
      caseRelevantAreasList.innerHTML = items.map(function (item) {
        return [
          '<details class="map-relevant-item">',
          '<summary><span><strong>' + escapeHtml(item.title || 'Område') + '</strong></span><span class="map-tone ' + escapeHtml(mapToneClass(item.status)) + '">' + escapeHtml(item.status || 'Temalag') + '</span></summary>',
          '<div class="map-relevant-meta">',
          item.emphasis ? '<span class="map-quick-tag">' + escapeHtml(item.emphasis) + '</span>' : '',
          '</div>',
          item.summary ? '<div class="muted small">' + escapeHtml(item.summary) + '</div>' : '',
          item.meta && item.meta.length ? '<div class="map-quick-tags">' + item.meta.map(function (meta) { return '<span class="map-quick-tag">' + escapeHtml(meta) + '</span>'; }).join('') + '</div>' : '',
          '</details>'
        ].join('');
      }).join('');
    }

    function syncMapSelectionStatus() {
      if (!mapSelectionStatus) return;
      var layerCount = (mapState && typeof mapState.visibleLayerCount === 'number' && mapState.visibleLayerCount > 0) ? mapState.visibleLayerCount : filteredMapCatalog().length;
      var fisherySel = species && species.value ? species.value : (fisheryType && fisheryType.value ? fisheryType.value : '');
      var gearSel = gearType && gearType.value ? gearType.value : '';
      var controlSel = controlType && controlType.value ? controlType.value : '';
      var parts = [];
      if (controlSel) parts.push(controlSel);
      if (fisherySel) parts.push(fisherySel);
      if (gearSel) parts.push(gearSel);
      mapSelectionStatus.innerHTML = 'Verneomr\u00e5der: ' + layerCount + (parts.length ? ' · <strong>' + escapeHtml(parts.join(' / ')) + '</strong>' : '');
      renderRelevantAreaPanel(latestZoneResult);
    }
    function syncLayerFiltersUi() {
      if (!mapFilterWrap) return;
      mapFilterWrap.style.display = '';
      Array.prototype.forEach.call(mapFilterWrap.querySelectorAll('input[data-layer-filter]'), function (input) {
        var key = String(input.getAttribute('data-layer-filter') || '').trim().toLowerCase();
        input.checked = activeLayerStatuses[key] !== false;
      });
    }

    function currentMapBbox() {
      if (!caseMap || !caseMap._kvLeafletMap || typeof caseMap._kvLeafletMap.getBounds !== 'function') return null;
      var bounds = caseMap._kvLeafletMap.getBounds();
      return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()];
    }


    function roundForOffline(value) {
      return Math.round(Number(value || 0) * 10) / 10;
    }

    function currentOfflineWarmKey() {
      var bbox = currentMapBbox();
      var layerIds = mergeRelevantMapLayers(filteredMapCatalog(), zoneMatchedLayerIds(latestZoneResult)).slice(0, 12).map(function (layer) { return Number(layer.id); }).filter(function (value) { return isFinite(value); }).sort(function (a, b) { return a - b; });
      if (!bbox || !layerIds.length) return '';
      return layerIds.join(',') + '|' + bbox.map(roundForOffline).join(',');
    }

    function collectTileUrls(layer, map, padding) {
      if (!layer || !map || typeof layer.getTileUrl !== 'function' || typeof map.getZoom !== 'function') return [];
      var pixelBounds = typeof map.getPixelBounds === 'function' ? map.getPixelBounds() : null;
      if (!pixelBounds || typeof layer._pxBoundsToTileRange !== 'function') return [];
      var range = layer._pxBoundsToTileRange(pixelBounds);
      if (!range || !range.min || !range.max) return [];
      padding = Math.max(0, Number(padding || 0));
      var urls = [];
      var zoom = map.getZoom();
      for (var x = range.min.x - padding; x <= range.max.x + padding; x += 1) {
        for (var y = range.min.y - padding; y <= range.max.y + padding; y += 1) {
          try {
            var url = layer.getTileUrl({ x: x, y: y, z: zoom });
            if (url) urls.push(url);
          } catch (e) {}
        }
      }
      return urls;
    }

    function uniqueUrls(urls) {
      var seen = {};
      return (urls || []).filter(function (url) {
        var key = String(url || '');
        if (!key || seen[key]) return false;
        seen[key] = true;
        return true;
      });
    }

    function prefetchUrlsToCache(urls, cacheName) {
      if (!('caches' in window) || !Array.isArray(urls) || !urls.length) return Promise.resolve(0);
      return caches.open(cacheName).then(function (cache) {
        var index = 0;
        var stored = 0;
        var concurrency = 4;
        return new Promise(function (resolve) {
          function next() {
            if (index >= urls.length && concurrency <= 0) {
              resolve(stored);
              return;
            }
            while (concurrency > 0 && index < urls.length) {
              var url = urls[index++];
              concurrency -= 1;
              fetch(url, { mode: 'no-cors', credentials: 'omit' })
                .then(function (response) {
                  if (response && (response.ok || response.type === 'opaque')) {
                    stored += 1;
                    return cache.put(url, response.clone()).catch(function () {});
                  }
                })
                .catch(function () {})
                .finally(function () {
                  concurrency += 1;
                  next();
                });
            }
          }
          next();
        });
      }).catch(function () { return 0; });
    }

    function prefetchVisibleMapTiles(padding) {
      if (!caseMap || !caseMap._kvLeafletMap) return Promise.resolve({ count: 0, urls: [] });
      var map = caseMap._kvLeafletMap;
      var urls = [];
      map.eachLayer(function (layer) {
        if (typeof layer.getTileUrl !== 'function') return;
        urls = urls.concat(collectTileUrls(layer, map, padding == null ? 2 : padding));
      });
      urls = uniqueUrls(urls);
      return prefetchUrlsToCache(urls, 'kv-kontroll-1-8-7-map-tiles').then(function (count) {
        return { count: count, urls: urls };
      });
    }

    function deleteUrlsFromTileCaches(urls) {
      if (!('caches' in window) || !Array.isArray(urls) || !urls.length) return Promise.resolve(0);
      return caches.keys().then(function (keys) {
        var targetKeys = keys.filter(function (key) { return String(key || '').indexOf('map-tiles') !== -1; });
        return Promise.all(targetKeys.map(function (key) {
          return caches.open(key).then(function (cache) {
            return Promise.all(urls.map(function (url) { return cache.delete(url).catch(function () { return false; }); }));
          });
        })).then(function (results) {
          var removed = 0;
          (results || []).forEach(function (row) {
            (row || []).forEach(function (value) { if (value) removed += 1; });
          });
          return removed;
        });
      }).catch(function () { return 0; });
    }

    function packageLabelFromInputs() {
      var name = '';
      if (areaName && areaName.value) name = areaName.value;
      if (!name && locationName && locationName.value) name = locationName.value;
      if (!name && species && species.value) name = species.value;
      if (!name && fisheryType && fisheryType.value) name = fisheryType.value;
      return name ? ('Kartpakke · ' + name) : '';
    }

    function formatTimestamp(ts) {
      var value = Number(ts || 0);
      if (!value) return 'ukjent';
      try {
        return new Date(value).toLocaleString('nb-NO', { dateStyle: 'short', timeStyle: 'short' });
      } catch (e) {
        return new Date(value).toISOString();
      }
    }

    function formatBBoxSummary(bbox) {
      if (!Array.isArray(bbox) || bbox.length !== 4) return '';
      var west = Number(bbox[0]);
      var south = Number(bbox[1]);
      var east = Number(bbox[2]);
      var north = Number(bbox[3]);
      if (!isFinite(west) || !isFinite(south) || !isFinite(east) || !isFinite(north)) return '';
      var centerLat = ((south + north) / 2).toFixed(3);
      var centerLng = ((west + east) / 2).toFixed(3);
      return centerLat + ', ' + centerLng;
    }

    function packageStatus(row) {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.summarizePackage === 'function')) {
        return { stale: false, expired: false, ageDays: 0 };
      }
      return window.KVLocalMap.summarizePackage(row);
    }

    function renderOfflinePackages(rows) {
      if (!offlinePackagesList) return;
      var items = Array.isArray(rows) ? rows.slice() : [];
      if (!items.length) {
        offlinePackagesList.innerHTML = '<div class="offline-package-empty">Ingen offline-kartpakker er lagret på enheten ennå.</div>';
        if (offlinePackagesSummary) offlinePackagesSummary.textContent = 'Ingen offline-kartpakker er lagret på denne enheten ennå.';
        return;
      }
      var totalFeatures = 0;
      var totalTiles = 0;
      offlinePackagesList.innerHTML = items.map(function (row) {
        var state = packageStatus(row);
        var featureCount = Number(row && row.feature_count || 0);
        var tileCount = Number(row && row.tile_count || 0);
        totalFeatures += isFinite(featureCount) ? featureCount : 0;
        totalTiles += isFinite(tileCount) ? tileCount : 0;
        var badgeClass = state.expired ? 'expired' : (state.stale ? 'stale' : '');
        var badgeText = state.expired ? 'Utløpt' : (state.stale ? 'Bør oppdateres' : 'Oppdatert');
        var label = row && row.label ? row.label : ('Kartpakke ' + formatBBoxSummary(row && row.requested_bbox));
        return '<div class="offline-package-card ' + badgeClass + '" data-package-id="' + escapeHtml(row.id || '') + '">' +
          '<div class="split-row"><strong>' + escapeHtml(label) + '</strong><span class="offline-package-badge ' + badgeClass + '">' + escapeHtml(badgeText) + '</span></div>' +
          '<div class="offline-package-meta">' +
            '<span>Område: ' + escapeHtml(formatBBoxSummary(row && row.requested_bbox)) + '</span>' +
            '<span>Lag: ' + escapeHtml(String((row && row.layer_count) || (row && row.layer_ids ? row.layer_ids.length : 0) || 0)) + '</span>' +
            '<span>Objekter: ' + escapeHtml(String(featureCount || 0)) + '</span>' +
            '<span>Kartbilder: ' + escapeHtml(String(tileCount || 0)) + '</span>' +
            '<span>Sist oppdatert: ' + escapeHtml(formatTimestamp(row && row.updated_at)) + '</span>' +
          '</div>' +
          '<div class="offline-package-actions">' +
            '<button type="button" class="btn btn-secondary btn-small" data-offline-package-action="open">Vis område</button>' +
            '<button type="button" class="btn btn-secondary btn-small" data-offline-package-action="refresh">Oppdater</button>' +
            '<button type="button" class="btn btn-secondary btn-small" data-offline-package-action="delete">Slett</button>' +
          '</div>' +
        '</div>';
      }).join('');
      if (offlinePackagesSummary) {
        offlinePackagesSummary.textContent = items.length + ' offline-kartpakker er lagret på enheten. ' + totalFeatures + ' kartobjekter og ' + totalTiles + ' kartbilder er tilgjengelige lokalt.';
      }
    }

    function refreshOfflinePackageList() {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.listPackages === 'function')) {
        renderOfflinePackages([]);
        return Promise.resolve([]);
      }
      return window.KVLocalMap.listPackages().then(function (rows) {
        renderOfflinePackages(rows || []);
        return rows || [];
      }).catch(function () {
        renderOfflinePackages([]);
        return [];
      });
    }

    function maintainOfflinePackages(backgroundOnly) {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.cleanupPackages === 'function')) return Promise.resolve({ removed: [], kept: [] });
      return window.KVLocalMap.cleanupPackages({ maxPackages: 8, purgeAfterMs: 30 * 24 * 60 * 60 * 1000 }).then(function (result) {
        var removedRows = result && Array.isArray(result.removed) ? result.removed : [];
        return Promise.all(removedRows.map(function (row) { return deleteUrlsFromTileCaches(row && row.tile_urls || []); })).then(function () {
          if (!backgroundOnly && mapOfflineStatus && removedRows.length) {
            mapOfflineStatus.textContent = 'Gamle kartpakker ble ryddet bort automatisk (' + removedRows.length + ' fjernet).';
          }
          return refreshOfflinePackageList().then(function () { return result; });
        });
      }).catch(function () { return refreshOfflinePackageList().then(function () { return { removed: [], kept: [] }; }); });
    }

    function focusOfflinePackage(row) {
      if (!row || !Array.isArray(row.bbox) || row.bbox.length !== 4 || !caseMap || !caseMap._kvLeafletMap) return;
      var map = caseMap._kvLeafletMap;
      map.fitBounds([[row.bbox[1], row.bbox[0]], [row.bbox[3], row.bbox[2]]], { padding: [18, 18] });
      if (window.KVLocalMap && typeof window.KVLocalMap.touchPackage === 'function') window.KVLocalMap.touchPackage(row.id).catch(function () {});
      if (mapOfflineStatus) mapOfflineStatus.textContent = 'Viser offline-kartpakke: ' + (row.label || formatBBoxSummary(row.requested_bbox));
      refreshOfflinePackageList();
    }

    function deleteOfflinePackage(packageId) {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.deletePackage === 'function')) return Promise.resolve();
      return window.KVLocalMap.deletePackage(packageId).then(function (row) {
        if (!row) return null;
        return deleteUrlsFromTileCaches(row.tile_urls || []).then(function () { return row; });
      }).then(function (row) {
        if (row && mapOfflineStatus) mapOfflineStatus.textContent = 'Offline-kartpakke slettet fra enheten.';
        return maintainOfflinePackages(true).then(function () { return row; });
      });
    }

    function downloadCurrentMapToDevice(options) {
      options = options || {};
      if (!btnDownloadMapOffline && !options.allowWithoutButton) return Promise.resolve();
      var bbox = Array.isArray(options.requestBBox) ? options.requestBBox : currentMapBbox();
      var layerIds = Array.isArray(options.layerIds) && options.layerIds.length ? options.layerIds : filteredMapCatalog().map(function (layer) { return Number(layer.id); }).filter(function (value) { return isFinite(value); });
      if (!bbox || !layerIds.length) {
        if (mapOfflineStatus && !options.silent) mapOfflineStatus.textContent = 'Kunne ikke laste ned kartdata akkurat nå.';
        return Promise.resolve();
      }
      if (mapOfflineStatus && !options.silent) mapOfflineStatus.textContent = options.packageId ? 'Oppdaterer offline-kartpakke på enheten ...' : 'Lagrer offline-kartpakke på enheten ...';
      var expandFactor = Number(options.expandFactor || 1.8);
      var url = '/api/map/offline-package?bbox=' + encodeURIComponent(bbox.join(',')) + '&layer_ids=' + encodeURIComponent(layerIds.join(',')) + '&expand=' + encodeURIComponent(String(expandFactor));
      return fetch(url, { credentials: 'same-origin' })
        .then(function (response) { return response.json(); })
        .then(function (payload) {
          var bundle = payload && payload.bundle ? payload.bundle : { type: 'FeatureCollection', features: [], layers: [] };
          var tilePromise = options.skipTiles ? Promise.resolve({ count: 0, urls: [] }) : (options.packageRow ? Promise.resolve({ count: Number(options.packageRow.tile_count || 0), urls: Array.isArray(options.packageRow.tile_urls) ? options.packageRow.tile_urls : [] }) : prefetchVisibleMapTiles(2));
          return tilePromise.then(function (tileInfo) {
            if (window.KVLocalMap && typeof window.KVLocalMap.saveOfflinePackage === 'function') {
              return window.KVLocalMap.saveOfflinePackage(layerIds, bbox, payload, {
                packageId: options.packageId,
                label: options.label || packageLabelFromInputs(),
                tile_urls: tileInfo.urls,
                tile_count: tileInfo.count,
                expandFactor: expandFactor,
                createdAt: options.packageRow && options.packageRow.created_at ? options.packageRow.created_at : undefined
              }).catch(function () { return null; }).then(function (savedRow) {
                return { bundle: bundle, tileInfo: tileInfo, savedRow: savedRow };
              });
            }
            return { bundle: bundle, tileInfo: tileInfo, savedRow: null };
          });
        })
        .then(function (result) {
          var featureCount = result && result.bundle && Array.isArray(result.bundle.features) ? result.bundle.features.length : 0;
          var tileCount = result && result.tileInfo && isFinite(Number(result.tileInfo.count)) ? Number(result.tileInfo.count) : 0;
          if (mapOfflineStatus && !options.silent) {
            mapOfflineStatus.textContent = (options.packageId ? 'Offline-kartpakke oppdatert.' : 'Offline-kart lagret på enheten.') + ' ' + featureCount + ' kartobjekter og ' + tileCount + ' kartbilder er klare for dette området.';
          }
          return maintainOfflinePackages(true).then(function () { return refreshOfflinePackageList(); });
        })
        .catch(function () {
          if (mapOfflineStatus && !options.silent) mapOfflineStatus.textContent = 'Kunne ikke laste ned offline-kart akkurat nå.';
        });
    }

    function bboxAroundPoint(lat, lng, kmRadius) {
      var latNum = Number(lat);
      var lngNum = Number(lng);
      var radius = Math.max(0.5, Number(kmRadius || 8));
      if (!isFinite(latNum) || !isFinite(lngNum)) return null;
      var dLat = radius / 111.32;
      var cosLat = Math.cos(latNum * Math.PI / 180);
      var dLng = radius / (111.32 * Math.max(0.25, Math.abs(cosLat)));
      return [lngNum - dLng, latNum - dLat, lngNum + dLng, latNum + dLat];
    }

    function relevantOfflineLayerIds() {
      var rows = defaultVisibleMapCatalog(zoneMatchedLayerIds(latestZoneResult));
      var ids = rows.map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); });
      if (!ids.length) {
        ids = filteredMapCatalog().slice(0, 10).map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); });
      }
      return ids.filter(function (value, idx, arr) { return arr.indexOf(value) === idx; }).slice(0, 16);
    }

    function currentOfflineWarmKey() {
      var latNum = latitude && latitude.value ? Number(String(latitude.value).replace(',', '.')) : NaN;
      var lngNum = longitude && longitude.value ? Number(String(longitude.value).replace(',', '.')) : NaN;
      if (!isFinite(latNum) || !isFinite(lngNum)) return '';
      return [Math.round(latNum * 1000), Math.round(lngNum * 1000), currentControlSelection(), currentFisherySelection(), currentGearSelection(), relevantOfflineLayerIds().join(',')].join(':');
    }

    function warmOfflineRegulationPackage() {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.saveOfflinePackage === 'function')) return Promise.resolve(null);
      var bbox = bboxAroundPoint(latitude && latitude.value, longitude && longitude.value, 8);
      var ids = relevantOfflineLayerIds();
      if (!bbox || !ids.length) return Promise.resolve(null);
      var key = currentOfflineWarmKey();
      if (!key || mapState._lastOfflineWarmKey === key) return Promise.resolve(null);
      mapState._lastOfflineWarmKey = key;
      if (mapOfflineStatus) mapOfflineStatus.textContent = 'Lagrer relevante reguleringsområder lokalt ...';
      return downloadCurrentMapToDevice({
        requestBBox: bbox,
        layerIds: ids,
        expandFactor: 1.4,
        allowWithoutButton: true,
        skipTiles: true,
        silent: true,
        label: 'Reguleringer ved kontrollposisjon'
      }).then(function () {
        if (mapOfflineStatus) mapOfflineStatus.textContent = 'Relevante reguleringsområder er lagret lokalt.';
        return refreshOfflinePackageList();
      }).catch(function () {
        if (mapOfflineStatus) mapOfflineStatus.textContent = 'Kunne ikke lagre reguleringsområder lokalt akkurat nå.';
        return null;
      });
    }

    function scheduleOfflineRegulationWarm(delay) {
      if (mapState._offlineWarmTimer) window.clearTimeout(mapState._offlineWarmTimer);
      mapState._offlineWarmTimer = window.setTimeout(function () {
        mapState._offlineWarmTimer = null;
        warmOfflineRegulationPackage();
      }, Math.max(300, Number(delay || 900)));
    }


    function refreshOfflinePackage(packageId, silent) {
      if (!(window.KVLocalMap && typeof window.KVLocalMap.getPackage === 'function')) return Promise.resolve();
      return window.KVLocalMap.getPackage(packageId).then(function (row) {
        if (!row) return null;
        return downloadCurrentMapToDevice({
          packageId: row.id,
          packageRow: row,
          requestBBox: row.requested_bbox || row.bbox,
          layerIds: row.layer_ids || [],
          label: row.label || '',
          expandFactor: row.expand_factor || 1.8,
          allowWithoutButton: true,
          silent: silent === true
        });
      });
    }

    function autoRefreshStalePackages() {
      if (!navigator.onLine || !(window.KVLocalMap && typeof window.KVLocalMap.listPackages === 'function')) return Promise.resolve();
      return window.KVLocalMap.listPackages().then(function (rows) {
        var staleRows = (rows || []).filter(function (row) {
          var state = packageStatus(row);
          return state && state.stale && !state.expired;
        }).slice(0, 2);
        if (!staleRows.length) return rows || [];
        return staleRows.reduce(function (promise, row) {
          return promise.then(function () { return refreshOfflinePackage(row.id, true); });
        }, Promise.resolve()).then(function () { return refreshOfflinePackageList(); });
      }).catch(function () { return []; });
    }

    if (btnDownloadMapOffline) btnDownloadMapOffline.addEventListener('click', function () { downloadCurrentMapToDevice(); });
    if (btnRefreshOfflinePackages) btnRefreshOfflinePackages.addEventListener('click', function () {
      if (mapOfflineStatus) mapOfflineStatus.textContent = 'Oppdaterer lagrede kartpakker ...';
      maintainOfflinePackages(true).then(function () { return autoRefreshStalePackages(); }).then(function () {
        if (mapOfflineStatus) mapOfflineStatus.textContent = 'Lagrede kartpakker er kontrollert og oppdatert der det var behov.';
      });
    });
    if (offlinePackagesList) offlinePackagesList.addEventListener('click', function (event) {
      var button = event.target.closest('[data-offline-package-action]');
      if (!button) return;
      var card = button.closest('[data-package-id]');
      var packageId = card ? String(card.getAttribute('data-package-id') || '') : '';
      if (!packageId || !(window.KVLocalMap && typeof window.KVLocalMap.getPackage === 'function')) return;
      var action = String(button.getAttribute('data-offline-package-action') || '');
      if (action === 'delete') {
        deleteOfflinePackage(packageId);
        return;
      }
      if (action === 'refresh') {
        refreshOfflinePackage(packageId);
        return;
      }
      window.KVLocalMap.getPackage(packageId).then(function (row) { focusOfflinePackage(row); });
    });

    latestZoneResult = null;

    form = document.getElementById('case-form');
    findingsInput = document.getElementById('findings_json');
    sourcesInput = document.getElementById('source_snapshot_json');
    crewInput = document.getElementById('crew_json');
    externalActorsInput = document.getElementById('external_actors_json');
    personsInput = document.getElementById('persons_json');
    interviewInput = document.getElementById('interview_sessions_json');
    seizureReportsInput = document.getElementById('seizure_reports_json');
    var interviewNotConducted = document.getElementById('interview_not_conducted');
    var interviewNotConductedReason = document.getElementById('interview_not_conducted_reason');
    var interviewGuidanceText = document.getElementById('interview_guidance_text');
    var findingsList = document.getElementById('findings-list');
    var controlLinkToolbar = document.getElementById('control-link-toolbar');
    var sourceList = document.getElementById('rule-source-list');
    var metaBox = document.getElementById('rule-bundle-meta');
    var zoneResult = document.getElementById('zone-result');
    var areaStatusDetail = document.getElementById('area-status-detail');
    var manualPositionStatus = document.getElementById('manual-position-status');
    var mapSelectionStatus = document.getElementById('map-selection-status');
    var btnDownloadMapOffline = document.getElementById('btn-download-map-offline');
    var btnRefreshOfflinePackages = document.getElementById('btn-refresh-offline-packages');
    var mapOfflineStatus = document.getElementById('map-offline-status');
    var offlinePackagesSummary = document.getElementById('offline-packages-summary');
    var offlinePackagesList = document.getElementById('offline-packages-list');
    var registryResult = document.getElementById('registry-result');
    var registryCandidates = document.getElementById('registry-candidates');
    var hummerRegistryStatus = document.getElementById('hummer-registry-status');
    var gearSummaryStatus = document.getElementById('gear-summary-status');
    var observedGearCount = document.getElementById('observed_gear_count');
    var summaryPreview = document.getElementById('summary-preview');
    var caseMap = document.getElementById('case-position-map');
    var caseMapCard = document.getElementById('case-map-card');
    var btnToggleCaseMapFullscreen = document.getElementById('btn-toggle-case-map-fullscreen');

    function setCaseMapFocusMode(active) {
      if (!caseMapCard) return;
      var enabled = !!active;
      caseMapCard.classList.toggle('is-map-focus', enabled);
      document.body.classList.toggle('case-map-focus-mode', enabled);
      if (btnToggleCaseMapFullscreen) btnToggleCaseMapFullscreen.textContent = enabled ? 'Lukk kart' : '\u00c5pne kart';
      setTimeout(function () {
        if (caseMap && caseMap._kvLeafletMap && typeof caseMap._kvLeafletMap.invalidateSize === 'function') {
          try { caseMap._kvLeafletMap.invalidateSize(); } catch (e) {}
        }
      }, 120);
    }
    if (btnToggleCaseMapFullscreen && !btnToggleCaseMapFullscreen.dataset.mapFocusBound) {
      btnToggleCaseMapFullscreen.dataset.mapFocusBound = '1';
      btnToggleCaseMapFullscreen.addEventListener('click', function () {
        setCaseMapFocusMode(!(caseMapCard && caseMapCard.classList.contains('is-map-focus')));
      });
    }
    if (caseMap && !caseMap.dataset.mapFocusTapBound) {
      caseMap.dataset.mapFocusTapBound = '1';
      caseMap.addEventListener('click', function (event) {
        if (!caseMapCard || caseMapCard.classList.contains('is-map-focus')) return;
        if (event.target && event.target.closest && event.target.closest('.leaflet-control')) return;
        setCaseMapFocusMode(true);
      });
    }

    if (btnDownloadMapOffline && !btnDownloadMapOffline.dataset.offlineBound) {
      btnDownloadMapOffline.dataset.offlineBound = '1';
      btnDownloadMapOffline.addEventListener('click', function () { downloadCurrentMapToDevice(); });
    }
    if (btnRefreshOfflinePackages && !btnRefreshOfflinePackages.dataset.offlineBound) {
      btnRefreshOfflinePackages.dataset.offlineBound = '1';
      btnRefreshOfflinePackages.addEventListener('click', function () {
        if (mapOfflineStatus) mapOfflineStatus.textContent = 'Oppdaterer lagrede kartpakker ...';
        maintainOfflinePackages(true).then(function () { return autoRefreshStalePackages(); }).then(function () {
          if (mapOfflineStatus) mapOfflineStatus.textContent = 'Lagrede kartpakker er kontrollert og oppdatert der det var behov.';
        });
      });
    }
    if (offlinePackagesList && !offlinePackagesList.dataset.offlineBound) {
      offlinePackagesList.dataset.offlineBound = '1';
      offlinePackagesList.addEventListener('click', function (event) {
        var button = event.target.closest('[data-offline-package-action]');
        if (!button) return;
        var card = button.closest('[data-package-id]');
        var packageId = card ? String(card.getAttribute('data-package-id') || '') : '';
        if (!packageId || !(window.KVLocalMap && typeof window.KVLocalMap.getPackage === 'function')) return;
        var action = String(button.getAttribute('data-offline-package-action') || '');
        if (action === 'delete') {
          deleteOfflinePackage(packageId);
          return;
        }
        if (action === 'refresh') {
          refreshOfflinePackage(packageId);
          return;
        }
        window.KVLocalMap.getPackage(packageId).then(function (row) { focusOfflinePackage(row); });
      });
    }

    controlType = document.getElementById('control_type');
    fisheryType = document.getElementById('fishery_type');
    species = document.getElementById('species');
    gearType = document.getElementById('gear_type');
    startTime = document.getElementById('start_time');
    endTime = document.getElementById('end_time');
    latitude = document.getElementById('latitude');
    longitude = document.getElementById('longitude');
    areaStatus = document.getElementById('area_status');
    areaName = document.getElementById('area_name');
    locationName = document.getElementById('location_name');
    positionCoordinateSummary = document.getElementById('position-coordinate-summary');
    caseBasis = document.getElementById('case_basis');
    basisSourceName = document.getElementById('basis_source_name');
    basisDetails = document.getElementById('basis_details');
    suspectName = document.getElementById('suspect_name');
    suspectNameCommercial = document.getElementById('suspect_name_commercial');
    suspectPhone = document.getElementById('suspect_phone');
    suspectAddress = document.getElementById('suspect_address');
    suspectPostPlace = document.getElementById('suspect_post_place');
    suspectBirthdate = document.getElementById('suspect_birthdate');
    hummerParticipantNo = document.getElementById('hummer_participant_no');
    hummerLastRegistered = document.getElementById('hummer_last_registered');
    vesselName = document.getElementById('vessel_name');
    vesselReg = document.getElementById('vessel_reg');
    radioCallSign = document.getElementById('radio_call_sign');
    gearMarkerId = document.getElementById('gear_marker_id');
    lookupText = document.getElementById('lookup_text');
    lookupName = document.getElementById('lookup_name');
    lookupIdentifier = document.getElementById('lookup_identifier');
    notes = document.getElementById('notes');
    summary = document.getElementById('summary');
    hearingText = document.getElementById('hearing_text');
    var selectedFindingCard = document.getElementById('selected-finding-card');
    var evidenceFindingKey = document.getElementById('evidence_finding_key');
    var evidenceLawText = document.getElementById('evidence_law_text');
    var evidenceSeizureRef = document.getElementById('evidence_seizure_ref');
    var evidenceCaption = document.getElementById('evidence_caption');
    var evidenceReason = document.getElementById('evidence_violation_reason');
    var evidenceGrid = document.getElementById('evidence-grid');
    var audioList = document.getElementById('audio-list');
    var evidenceUploadForm = document.getElementById('evidence-upload-form');
    var evidenceFileInput = document.getElementById('evidence-file-input');
    var ocrCameraInput = document.getElementById('ocr-image-camera');
    var ocrFileInput = document.getElementById('ocr-image-file');
    var inlineEvidenceCameraInput = document.getElementById('inline-evidence-camera-input');
    var inlineEvidenceFileInput = document.getElementById('inline-evidence-file-input');
    var ocrSelectedFileBox = document.getElementById('ocr-selected-file');
    ocrAutofillPreview = document.getElementById('ocr-autofill-preview');
    var localMediaStatus = document.getElementById('local-media-status');
    var localMediaStatusText = document.getElementById('local-media-status-text');
    var btnLookupPerson = document.getElementById('btn-lookup-person');
    var btnPhoneLookup = document.getElementById('btn-phone-lookup');
    var btnSyncLocalMedia = document.getElementById('btn-sync-local-media');
    var localCaseStatusBox = document.getElementById('local-case-status-box');
    var localCaseStatusText = document.getElementById('local-case-status-text');
    var btnSyncCaseDraft = document.getElementById('btn-sync-case-draft');
    var btnDiscardLocalCase = document.getElementById('btn-discard-local-case');
    var cameraCaptureModal = document.getElementById('camera-capture-modal');
    var cameraCaptureTitle = document.getElementById('camera-capture-title');
    var cameraCaptureDescription = document.getElementById('camera-capture-description');
    var cameraCaptureVideo = document.getElementById('camera-capture-video');
    var cameraCaptureStatus = document.getElementById('camera-capture-status');
    var caseRelevantAreasList = document.getElementById('case-relevant-areas-list');
    var mapLayerPanelHost = document.getElementById('case-map-layer-panel-host');
    var toggleZoneHitOverlay = document.getElementById('toggle-zone-hit-overlay');
    var zoneHitOverlayText = document.getElementById('toggle-zone-hit-overlay-text');
    var areaRestrictionSelect = document.getElementById('area_restriction_select');
    var areaRestrictionDetail = document.getElementById('area-restriction-detail');
    var seizureReportList = document.getElementById('seizure-report-list');
    var btnRefreshSeizureReport = document.getElementById('btn-refresh-seizure-report');
    var btnAddSeizureReport = document.getElementById('btn-add-seizure-report');

    var leisureFields = document.getElementById('leisure-fields');
    var commercialFields = document.getElementById('commercial-fields');
    var personModeHint = document.getElementById('person-mode-hint');

    findingsState = parseJson(findingsInput.value, []) || [];
    var sourcesState = parseJson(sourcesInput.value, []) || [];
    var crewState = parseJson(crewInput.value, []) || [];
    var externalActorsState = parseJson(externalActorsInput.value, []) || [];
    var personsState = parseJson(personsInput ? personsInput.value : '[]', []) || [];
    var interviewState = parseJson(interviewInput ? interviewInput.value : '[]', []) || [];
    var seizureReportsState = parseJson(seizureReportsInput ? seizureReportsInput.value : '[]', []) || [];
    var candidateState = [];
    var registryLookupTimer = null;
    var registryLookupInFlight = false;
    var pendingRegistryLookup = false;
    var lastRegistryLookupKey = '';
    var lastSuccessfulRegistryLookupKey = '';
    evidenceState = parseJson(root.dataset.evidence, []) || [];
    selectedInlineEvidenceTarget = null;
    inlineEvidenceFeedback = '';
    resetOcrSelectedFile();
    var positionModeStorageKey = 'kv-case-position-mode:' + root.dataset.caseId;
    var storedPositionMode = '';
    try {
      storedPositionMode = String(localStorage.getItem(positionModeStorageKey) || '').trim().toLowerCase();
    } catch (e) {
      storedPositionMode = '';
    }
    if (storedPositionMode !== 'manual' && storedPositionMode !== 'auto') storedPositionMode = '';
    var zoneOverlayStorageKey = 'kv-case-zone-overlay-1.8.7:' + root.dataset.caseId;
    var zoneOverlayEnabled = true;
    // Treffende verne-/reguleringsområder skal alltid tegnes i kartet.
    // Tidligere lagret 'skjul'-valg fra eldre PWA-versjoner ignoreres.
    if (toggleZoneHitOverlay) toggleZoneHitOverlay.checked = true;
    syncZoneHitOverlayToggleText();
    var hasInitialCoords = Boolean(latitude.value && longitude.value);
    var mapState = {
      lat: Number(latitude.value || 0),
      lng: Number(longitude.value || 0),
      layer: null,
      draggable: true,
      allowMapMove: true,
      radiusKm: 50,
      followAutoPosition: storedPositionMode !== 'manual',
      manualPosition: storedPositionMode === 'manual',
      lastDeviceLat: null,
      lastDeviceLng: null,
      deviceLat: null,
      deviceLng: null,
      deviceAccuracy: null,
      showDeviceMarker: storedPositionMode !== 'manual',
      recenterTo: '',
      visibleLayerCount: 0,
      lastZoneCheckLat: null,
      lastZoneCheckLng: null,
      lastZoneCheckTs: 0,
      lastAutoSaveLat: null,
      lastAutoSaveLng: null,
      lastAutoSaveTs: 0,
      lastMapRenderLat: null,
      lastMapRenderLng: null,
      lastMapRenderTs: 0,
      pendingZoneTimer: null,
      autoRecenterOnce: !hasInitialCoords && storedPositionMode !== 'manual',
      lastProgrammaticRecenterTs: 0
    };
    var zoneCheckController = null;
    var zoneCheckSequence = 0;
    var lastZoneCheckKey = '';
    var lastZoneCheckAt = 0;
    var lastZoneCheckResult = null;
    if (mapState.manualPosition && !hasInitialCoords) {
      mapState.manualPosition = false;
      mapState.followAutoPosition = true;
    }
    mapState.onFeaturesRendered = function (payload) {
      var seenLayers = {};
      (payload && payload.features ? payload.features : []).forEach(function (feature) {
        if (feature && feature.layerId !== undefined && feature.layerId !== null) seenLayers[String(feature.layerId)] = true;
      });
      mapState.visibleLayerCount = Object.keys(seenLayers).length;
      syncMapSelectionStatus();
      renderRelevantAreaPanel(latestZoneResult);
    };

    function zoneHitColor(status) {
      var key = String(status || '').trim().toLowerCase();
      if (key === 'stengt område' || key === 'nullfiskeområde') return '#b5171e';
      if (key === 'fredningsområde') return '#f4a261';
      if (key === 'maksimalmål område') return '#bc4749';
      if (key === 'regulert område') return '#355070';
      if (key === 'fiskeriområde') return '#2a9d8f';
      return '#1f4f82';
    }

    function clearZoneHitOverlay() {
      if (!caseMap || !caseMap._kvLeafletMap || !caseMap._kvPortalState) return;
      var state = caseMap._kvPortalState;
      if (state.zoneHitOverlay) {
        try { caseMap._kvLeafletMap.removeLayer(state.zoneHitOverlay); } catch (e) {}
        state.zoneHitOverlay = null;
      }
      state.zoneHitBounds = null;
    }

    function zoneHitOverlayActive() {
      return zoneOverlayEnabled !== false;
    }

    function syncZoneHitOverlayToggleText() {
      if (!zoneHitOverlayText) return;
      zoneHitOverlayText.textContent = zoneHitOverlayActive() ? 'Treffområder er synlige i kartet' : 'Treffområder er skjult i kartet';
    }

    function zoneHitFeatureCollection(result) {
      var hits = result && result.match && Array.isArray(result.hits) ? result.hits : [];
      var features = [];
      var seen = {};
      hits.forEach(function (hit) {
        var feature = hit && (hit.feature || hit.geojson || hit.geometry_feature);
        if (!feature || feature.type !== 'Feature' || !feature.geometry) return;
        var props = Object.assign({}, feature.properties || {});
        if (!props.__layer_id && hit.layer_id !== undefined && hit.layer_id !== null) props.__layer_id = hit.layer_id;
        if (!props.__layer_name && (hit.layer || hit.layer_name)) props.__layer_name = hit.layer || hit.layer_name;
        if (!props.__layer_status && hit.status) props.__layer_status = hit.status;
        if (!props.__layer_color) props.__layer_color = zoneHitColor(hit.status);
        if (!props.__layer_description && hit.notes) props.__layer_description = hit.notes;
        if (!props.__layer_url && hit.url) props.__layer_url = hit.url;
        if (!props.name && hit.name) props.name = hit.name;
        var dedupe = JSON.stringify([props.__layer_id || props.__layer_name || hit.name || '', feature.geometry]);
        if (seen[dedupe]) return;
        seen[dedupe] = true;
        features.push({ type: 'Feature', geometry: feature.geometry, properties: props });
      });
      return { type: 'FeatureCollection', features: features };
    }

    function syncZoneHitOverlay(result) {
      syncZoneHitOverlayToggleText();
      clearZoneHitOverlay();
      if (!zoneHitOverlayActive()) return;
      if (!caseMap || !caseMap._kvLeafletMap || !window.L) return;
      var collection = zoneHitFeatureCollection(result);
      if (!collection.features.length) return;
      var state = caseMap._kvPortalState || {};
      var overlay = L.geoJSON(collection, {
        interactive: false,
        bubblingMouseEvents: false,
        style: function (feature) {
          var props = feature && feature.properties ? feature.properties : {};
          var color = props.__layer_color || zoneHitColor(props.__layer_status || '');
          return { color: color, weight: 5, opacity: 1, fillColor: color, fillOpacity: 0.16, dashArray: '10 6' };
        },
        pointToLayer: function (feature, latlng) {
          var props = feature && feature.properties ? feature.properties : {};
          var color = props.__layer_color || zoneHitColor(props.__layer_status || '');
          return L.circleMarker(latlng, { radius: 10, color: color, weight: 3, fillColor: color, fillOpacity: 0.92, interactive: false });
        }
      }).addTo(caseMap._kvLeafletMap);
      if (overlay && typeof overlay.bringToFront === 'function') overlay.bringToFront();
      state.zoneHitOverlay = overlay;
      try {
        state.zoneHitBounds = overlay && typeof overlay.getBounds === 'function' ? overlay.getBounds() : null;
      } catch (e) {
        state.zoneHitBounds = null;
      }
      caseMap._kvPortalState = state;
    }
    function persistPositionMode(mode) {
      var normalized = String(mode || '').trim().toLowerCase() === 'manual' ? 'manual' : 'auto';
      try { localStorage.setItem(positionModeStorageKey, normalized); } catch (e) {}
    }

    function distanceMeters(lat1, lng1, lat2, lng2) {
      if (!isFinite(lat1) || !isFinite(lng1) || !isFinite(lat2) || !isFinite(lng2)) return Infinity;
      var toRad = Math.PI / 180;
      var dLat = (lat2 - lat1) * toRad;
      var dLng = (lng2 - lng1) * toRad;
      var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
      return 6371000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }
    var locationWatchId = null;
    var autoLocationAttempted = false;
    var mediaRecorder = null;
    var mediaChunks = [];
    var recordingSegmentTimer = null;
    var recordingSessionId = '';
    var recordingSegmentIndex = 0;
    var recordingElapsedStart = 0;
    var recordingPausedByRotation = false;
    var selectedOcrFile = null;
    var preparedOcrFileCache = {};
    var lastOcrEvidenceSignature = '';
    var cameraCaptureState = null;
    var autosaveTimer = null;
    var autosaveInFlight = false;
    var autosavePending = false;
    var lastAutosaveFingerprint = '';
    var latestGearSummary = null;
    var LocalMedia = window.KVLocalMedia || null;
    var LocalCases = window.KVLocalCases || null;
    var currentUserId = String(root.dataset.currentUserId || (window.MKCurrentUser && window.MKCurrentUser.id) || '').trim();
    var currentDeviceId = (LocalCases && typeof LocalCases.currentDeviceId === 'function') ? LocalCases.currentDeviceId() : ((LocalMedia && typeof LocalMedia.currentDeviceId === 'function') ? LocalMedia.currentDeviceId() : 'device-unknown');
    var caseVersionInput = document.getElementById('case_version');
    var clientMutationInput = document.getElementById('client_mutation_id');

    function ownerOptions() {
      return { owner_user_id: currentUserId };
    }

    function ensureMutationId() {
      var value = '';
      try {
        value = (window.crypto && typeof window.crypto.randomUUID === 'function') ? window.crypto.randomUUID() : ('mutation-' + Date.now() + '-' + Math.random().toString(16).slice(2));
      } catch (e) {
        value = 'mutation-' + Date.now() + '-' + Math.random().toString(16).slice(2);
      }
      if (clientMutationInput) clientMutationInput.value = value;
      return value;
    }

    function applyServerSaveMeta(meta) {
      meta = meta || {};
      if (meta.version !== undefined && meta.version !== null && String(meta.version) !== '') {
        root.dataset.caseVersion = String(meta.version);
        if (caseVersionInput) caseVersionInput.value = String(meta.version);
      }
      if (meta.saved_at || meta.updated_at || meta.server_updated_at) {
        root.dataset.caseUpdatedAt = String(meta.saved_at || meta.updated_at || meta.server_updated_at || '');
      }
    }

    var isOfflineNewCase = String(root.dataset.offlineNew || '0') === '1';
    var createCaseUrl = String(root.dataset.createCaseUrl || '');
    var localMediaSyncInFlight = false;
    var localCaseSaveTimer = null;
    var localCaseSyncInFlight = false;
    var localCaseRestoreApplied = false;
    var suspendAutosave = false;
    var localEvidenceObjectUrls = {};
    var summaryDraftCache = {};
    var summaryRequestInFlight = null;
    var caseShellSummary = document.getElementById('case-shell-summary');

    if (caseShellSummary) {
      var shellKey = 'case-shell-summary:' + String(root.dataset.caseId || 'new');
      try {
        var storedShell = sessionStorage.getItem(shellKey);
        if (storedShell === 'open') caseShellSummary.open = true;
        else if (storedShell === 'closed') caseShellSummary.open = false;
      } catch (e) {}
      caseShellSummary.addEventListener('toggle', function () {
        try { sessionStorage.setItem(shellKey, caseShellSummary.open ? 'open' : 'closed'); } catch (e) {}
      });
    }

    if (!startTime.value) {
      var now = new Date();
      var iso = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      startTime.value = iso;
    }

    var panes = Array.prototype.slice.call(document.querySelectorAll('.step-pane'));
    var stepButtons = Array.prototype.slice.call(document.querySelectorAll('.step-btn'));
    var mobilePrevStep = document.getElementById('mobile-prev-step');
    var mobileNextStep = document.getElementById('mobile-next-step');
    var mobileStepLabel = document.getElementById('mobile-step-label');
    var topPrevStep = document.getElementById('top-prev-step');
    var topNextStep = document.getElementById('top-next-step');
    var topStepLabel = document.getElementById('top-step-label');
    var stepStorageKey = 'kv-case-step:' + root.dataset.caseId;
    var currentStep = 1;

    function localMediaSupported() {
      return !!(LocalMedia && typeof LocalMedia.supported === 'function' && LocalMedia.supported());
    }

    function localCaseSupported() {
      return !!(LocalCases && typeof LocalCases.supported === 'function' && LocalCases.supported());
    }

    function isLocalOnlyCase() {
      return isOfflineNewCase || !/^\d+$/.test(String(root.dataset.caseId || ''));
    }

    function currentCaseUrl() {
      if (root.dataset.caseUrl) return String(root.dataset.caseUrl);
      if (LocalCases && typeof LocalCases.buildCaseUrl === 'function') return LocalCases.buildCaseUrl(root.dataset.caseId || '');
      return isLocalOnlyCase()
        ? ('/cases/offline/new?local_id=' + encodeURIComponent(String(root.dataset.caseId || '')))
        : ('/cases/' + encodeURIComponent(String(root.dataset.caseId || '')) + '/edit');
    }

    function updateCaseNumberDisplay(caseNumber) {
      var value = String(caseNumber || '').trim();
      if (!value) return;
      root.dataset.caseNumber = value;
      Array.prototype.forEach.call(document.querySelectorAll('.case-disclosure-number'), function (node) { node.textContent = value; });
      Array.prototype.forEach.call(document.querySelectorAll('.case-header-line h1'), function (node) { node.textContent = value; });
      var suffixInput = form.querySelector('input[name="case_number_suffix"]');
      var match = value.match(/(\d{3})$/);
      if (suffixInput && match) suffixInput.value = match[1];
      document.title = value + ' · Minfiskerikontroll';
    }

    function endpointForCase(caseId, suffix) {
      return '/cases/' + encodeURIComponent(String(caseId || '')) + suffix;
    }

    function applyServerCaseIdentity(serverCaseId, serverCaseUrl, serverCaseNumber, savedAt) {
      var id = String(serverCaseId || '').trim();
      if (!id) return;
      root.dataset.caseId = id;
      root.dataset.caseUrl = serverCaseUrl || endpointForCase(id, '/edit');
      root.dataset.autosaveUrl = endpointForCase(id, '/autosave').replace('/cases/', '/api/cases/');
      root.dataset.caseUpdatedAt = savedAt || new Date().toISOString();
      root.dataset.offlineNew = '0';
      isOfflineNewCase = false;
      if (form) form.setAttribute('action', endpointForCase(id, '/save'));
      Array.prototype.forEach.call(document.querySelectorAll('a[href$="/preview"]'), function (node) {
        node.setAttribute('href', endpointForCase(id, '/preview'));
      });
      Array.prototype.forEach.call(document.querySelectorAll('form[action$="/interview-pdf"]'), function (node) {
        node.setAttribute('action', endpointForCase(id, '/interview-pdf'));
      });
      Array.prototype.forEach.call(document.querySelectorAll('form[action$="/bundle"]'), function (node) {
        node.setAttribute('action', endpointForCase(id, '/bundle'));
      });
      Array.prototype.forEach.call(document.querySelectorAll('form[action$="/pdf"]'), function (node) {
        node.setAttribute('action', endpointForCase(id, '/pdf'));
      });
      Array.prototype.forEach.call(document.querySelectorAll('form[action$="/evidence"]'), function (node) {
        node.setAttribute('action', endpointForCase(id, '/evidence'));
      });
      if (serverCaseNumber) updateCaseNumberDisplay(serverCaseNumber);
    }

    function parseJsonResponse(response, fallbackMessage) {
      return response.text().then(function (text) {
        var payload = null;
        try { payload = text ? JSON.parse(text) : {}; } catch (e) { payload = { detail: text || fallbackMessage || 'Ukjent feil' }; }
        if (!response.ok || (payload && payload.ok === false)) {
          var message = (payload && (payload.error || payload.detail || payload.message)) || fallbackMessage || ('HTTP ' + response.status);
          var error = new Error(String(message));
          error.status = response.status;
          error.payload = payload || {};
          throw error;
        }
        return payload || {};
      });
    }

    function isMissingServerCaseError(error) {
      var text = String((error && error.message) || (error && error.payload && (error.payload.detail || error.payload.error)) || '').toLowerCase();
      return error && Number(error.status || 0) === 404 && (text.indexOf('fant ikke saken') !== -1 || text.indexOf('case') !== -1);
    }

    function updateLocalCaseStatus(message, isError, options) {
      options = options || {};
      if (!localCaseStatusBox) return;
      if (!localCaseSupported()) {
        localCaseStatusBox.classList.add('hidden');
        return;
      }
      if (!message && !options.forceShow) {
        localCaseStatusBox.classList.add('hidden');
        return;
      }
      localCaseStatusBox.classList.remove('hidden');
      localCaseStatusBox.classList.toggle('alert-error', !!isError);
      if (localCaseStatusText) {
        localCaseStatusText.textContent = message || 'Lagret lokalt.';
      }
      if (btnSyncCaseDraft) {
        btnSyncCaseDraft.classList.toggle('hidden', options.showSync === false);
        btnSyncCaseDraft.disabled = !!options.syncing;
      }
      if (btnDiscardLocalCase) btnDiscardLocalCase.classList.toggle('hidden', options.showDiscard === false);
    }

    function requestLocalPersistence() {
      var tasks = [];
      if (localMediaSupported() && LocalMedia.requestPersistence) tasks.push(LocalMedia.requestPersistence().catch(function () { return false; }));
      if (localCaseSupported() && LocalCases.requestPersistence) tasks.push(LocalCases.requestPersistence().catch(function () { return false; }));
      return Promise.all(tasks).catch(function () { return []; });
    }

    function serializeCaseFormData() {
      findingsInput.value = JSON.stringify(findingsState);
      crewInput.value = JSON.stringify(crewState);
      externalActorsInput.value = JSON.stringify(externalActorsState);
      if (personsInput) personsInput.value = JSON.stringify(personsState);
      sourcesInput.value = JSON.stringify(sourcesState);
      if (interviewInput) interviewInput.value = JSON.stringify(interviewState);
      syncSeizureReportsFromDom();
      if (seizureReportsInput) seizureReportsInput.value = JSON.stringify(seizureReportsState || []);
      if (suspectNameCommercial.value && !suspectName.value) suspectName.value = suspectNameCommercial.value;
      var formData = new FormData(form);
      formData.set('findings_json', JSON.stringify(findingsState));
      formData.set('source_snapshot_json', JSON.stringify(sourcesState));
      formData.set('crew_json', JSON.stringify(crewState));
      formData.set('external_actors_json', JSON.stringify(externalActorsState));
      formData.set('persons_json', JSON.stringify(personsState));
      formData.set('interview_sessions_json', JSON.stringify(interviewState));
      formData.set('seizure_reports_json', JSON.stringify(seizureReportsState || []));
      formData.set('case_version', String(root.dataset.caseVersion || (caseVersionInput && caseVersionInput.value) || ''));
      formData.set('client_mutation_id', ensureMutationId());
      formData.set('device_id', currentDeviceId);
      if (isOfflineNewCase) formData.set('local_case_id', String(root.dataset.caseId || ''));
      return formData;
    }

    function snapshotFormValues() {
      var formData = serializeCaseFormData();
      var rows = [];
      formData.forEach(function (value, key) {
        if (value instanceof File) return;
        rows.push([String(key || ''), String(value == null ? '' : value)]);
      });
      return rows;
    }

    function applyFormSnapshot(rows) {
      if (!Array.isArray(rows)) return;
      var grouped = {};
      rows.forEach(function (entry) {
        if (!Array.isArray(entry) || !entry.length) return;
        var key = String(entry[0] || '');
        if (!key) return;
        if (!grouped[key]) grouped[key] = [];
        grouped[key].push(String(entry[1] == null ? '' : entry[1]));
      });
      Array.prototype.forEach.call(form.elements, function (field) {
        if (!field || !field.name || field.type === 'file') return;
        var values = grouped[field.name];
        if (!values || !values.length) return;
        if (field.type === 'checkbox') {
          field.checked = values.indexOf(String(field.value)) !== -1 || values.indexOf('true') !== -1;
          return;
        }
        if (field.type === 'radio') {
          field.checked = values.indexOf(String(field.value)) !== -1;
          return;
        }
        if (field.tagName === 'SELECT' && field.multiple) {
          Array.prototype.forEach.call(field.options, function (opt) {
            opt.selected = values.indexOf(String(opt.value)) !== -1;
          });
          return;
        }
        field.value = values[values.length - 1];
      });
    }

    function currentMapViewSnapshot() {
      if (caseMap && caseMap._kvLeafletMap) {
        try {
          var center = caseMap._kvLeafletMap.getCenter();
          return { lat: center.lat, lng: center.lng, zoom: caseMap._kvLeafletMap.getZoom() };
        } catch (e) {}
      }
      try {
        return JSON.parse(sessionStorage.getItem('kv-map-view:' + (caseMap && caseMap.id ? caseMap.id : 'case-map')) || 'null');
      } catch (e) {
        return null;
      }
    }

    function collectLocalCaseDraft() {
      return {
        case_id: String(root.dataset.caseId || ''),
        case_number: String(root.dataset.caseNumber || ''),
        case_url: String(currentCaseUrl()),
        owner_user_id: currentUserId,
        device_id: currentDeviceId,
        case_version: String(root.dataset.caseVersion || (caseVersionInput && caseVersionInput.value) || ''),
        server_updated_at: String(root.dataset.caseUpdatedAt || ''),
        updated_at: Date.now(),
        sync_state: 'pending',
        current_step: Number(currentStep || 1),
        position_mode: mapState && mapState.manualPosition ? 'manual' : 'auto',
        map_view: currentMapViewSnapshot(),
        form_values: snapshotFormValues(),
        findings: JSON.parse(JSON.stringify(findingsState || [])),
        sources: JSON.parse(JSON.stringify(sourcesState || [])),
        crew: JSON.parse(JSON.stringify(crewState || [])),
        external_actors: JSON.parse(JSON.stringify(externalActorsState || [])),
        persons: JSON.parse(JSON.stringify(personsState || [])),
        interviews: JSON.parse(JSON.stringify(interviewState || [])),
        seizure_reports: JSON.parse(JSON.stringify(seizureReportsState || [])),
        summary_cache: JSON.parse(JSON.stringify(summaryDraftCache || {})),
        meta: {
          location_name: String(locationName && locationName.value || ''),
          control_type: String(controlType && controlType.value || ''),
          species: String(species && species.value || fisheryType && fisheryType.value || ''),
          gear_type: String(gearType && gearType.value || '')
        }
      };
    }

    function persistLocalCaseDraft(options) {
      options = options || {};
      if (!localCaseSupported() || !root.dataset.caseId) return Promise.resolve(null);
      var draft = collectLocalCaseDraft();
      return LocalCases.putDraft(draft, ownerOptions()).then(function (saved) {
        if (!options.silent) updateLocalCaseStatus('Lagret lokalt. Synk venter.', false, { forceShow: true, showSync: true, showDiscard: true });
        return saved;
      }).catch(function () {
        if (!options.silent) updateLocalCaseStatus('Lokal lagring feilet.', true, { forceShow: true, showSync: false, showDiscard: false });
        return null;
      });
    }

    function scheduleLocalCaseDraftSave(reason) {
      if (!localCaseSupported() || suspendAutosave) return;
      if (localCaseSaveTimer) window.clearTimeout(localCaseSaveTimer);
      localCaseSaveTimer = window.setTimeout(function () {
        persistLocalCaseDraft({ silent: true });
      }, 250);
    }

    function applyExternalActorsStateToDom() {
      var wrap = document.getElementById('external-actors');
      if (!wrap) return;
      Array.prototype.forEach.call(wrap.querySelectorAll('input[type="checkbox"]'), function (input) {
        input.checked = (externalActorsState || []).indexOf(input.value) !== -1;
      });
      externalActorsInput.value = JSON.stringify(externalActorsState || []);
    }

    function refreshCaseUiFromState(options) {
      options = options || {};
      suspendAutosave = true;
      try {
        findingsInput.value = JSON.stringify(findingsState || []);
        crewInput.value = JSON.stringify(crewState || []);
        externalActorsInput.value = JSON.stringify(externalActorsState || []);
        if (personsInput) personsInput.value = JSON.stringify(personsState || []);
        sourcesInput.value = JSON.stringify(sourcesState || []);
        if (interviewInput) interviewInput.value = JSON.stringify(interviewState || []);
        if (seizureReportsInput) seizureReportsInput.value = JSON.stringify(seizureReportsState || []);
        syncOptions();
        applyExternalActorsStateToDom();
        renderCrew();
        renderPersons();
        renderFindings();
        renderInterviews();
        renderSeizureReports({ mergeDefaults: true });
        syncInterviewDisabledState();
        if (sourceList) sourceList.innerHTML = (sourcesState || []).map(sourceChip).join('');
        updateExternalSearchLinks();
        syncManualPositionNotice();
        scheduleNearestPlaceResolve({}, 120);
        updateCaseMap();
        loadGearSummary();
        if (options.loadRules !== false && controlType.value && (species.value || fisheryType.value)) loadRules();
        if (options.step && options.step >= 1 && options.step <= panes.length) showStep(options.step, { scroll: false });
      } finally {
        suspendAutosave = false;
        lastAutosaveFingerprint = formFingerprint();
        setAutosaveStatus('Lagret lokalt', 'is-saved');
      }
    }

    function restoreLocalCaseDraft() {
      if (!localCaseSupported() || !root.dataset.caseId) return Promise.resolve(false);
      return LocalCases.getDraft(root.dataset.caseId, ownerOptions()).then(function (draft) {
        if (!draft || !draft.form_values || !draft.form_values.length) return false;
        var serverUpdatedMs = Date.parse(String(root.dataset.caseUpdatedAt || '')) || 0;
        var draftUpdatedMs = Number(draft.updated_at || 0);
        var lastServerSyncMs = Date.parse(String(draft.last_server_sync_at || draft.server_updated_at || '')) || 0;
        var hasUnsyncedChanges = String(draft.sync_state || 'pending') !== 'synced' || draftUpdatedMs > lastServerSyncMs + 1000;
        if (!hasUnsyncedChanges && draftUpdatedMs <= serverUpdatedMs + 1000) return false;
        applyFormSnapshot(draft.form_values || []);
        findingsState = parseJson(JSON.stringify(draft.findings || []), []) || [];
        sourcesState = parseJson(JSON.stringify(draft.sources || []), []) || [];
        crewState = parseJson(JSON.stringify(draft.crew || []), []) || [];
        externalActorsState = parseJson(JSON.stringify(draft.external_actors || []), []) || [];
        personsState = parseJson(JSON.stringify(draft.persons || []), []) || [];
        interviewState = parseJson(JSON.stringify(draft.interviews || []), []) || [];
        seizureReportsState = parseJson(JSON.stringify(draft.seizure_reports || []), []) || [];
        summaryDraftCache = parseJson(JSON.stringify(draft.summary_cache || {}), {}) || {};
        if (draft.position_mode === 'manual') {
          persistPositionMode('manual');
          mapState.followAutoPosition = false;
          mapState.manualPosition = true;
          mapState.showDeviceMarker = false;
        } else {
          persistPositionMode('auto');
          mapState.followAutoPosition = true;
          mapState.manualPosition = false;
          mapState.showDeviceMarker = true;
        }
        if (draft.map_view) {
          try { sessionStorage.setItem('kv-map-view:' + (caseMap && caseMap.id ? caseMap.id : 'case-map'), JSON.stringify(draft.map_view)); } catch (e) {}
        }
        localCaseRestoreApplied = true;
        refreshCaseUiFromState({ step: Number(draft.current_step || currentStep || 1), loadRules: true });
        updateLocalCaseStatus('Lokal kladd gjenopprettet.', false, { forceShow: true, showSync: true, showDiscard: true });
        if (LocalCases.incrementRestoreCount) LocalCases.incrementRestoreCount(root.dataset.caseId).catch(function () { return null; });
        return true;
      }).catch(function () {
        return false;
      });
    }

    function markLocalCaseSynced(serverUpdatedAt) {
      if (!localCaseSupported() || !root.dataset.caseId) return Promise.resolve(null);
      return LocalCases.markSynced(root.dataset.caseId, { server_updated_at: serverUpdatedAt || new Date().toISOString(), last_server_sync_at: serverUpdatedAt || new Date().toISOString() }).then(function (row) {
        updateLocalCaseStatus('Lokal sak er synket med serveren.', false, { forceShow: true, showSync: true, showDiscard: false });
        return row;
      }).catch(function () { return null; });
    }

    function discardLocalCaseDraft() {
      if (!localCaseSupported() || !root.dataset.caseId) return Promise.resolve(false);
      if (!window.confirm('Forkaste lokal versjon av saken på denne enheten? Endringer som ikke er synket går tapt.')) return Promise.resolve(false);
      return LocalCases.removeDraft(root.dataset.caseId, ownerOptions()).then(function () {
        updateLocalCaseStatus('Lokal versjon er fjernet fra enheten.', false, { forceShow: true, showSync: false, showDiscard: false });
        if (isLocalOnlyCase()) {
          window.location.href = '/dashboard';
          return true;
        }
        return true;
      }).catch(function () { return false; });
    }

    function ensureInitialOfflineDraft() {
      if (!isOfflineNewCase || !localCaseSupported() || !root.dataset.caseId) return Promise.resolve(false);
      return LocalCases.getDraft(root.dataset.caseId, ownerOptions()).then(function (draft) {
        if (draft && draft.case_id) return false;
        return persistLocalCaseDraft({ silent: true }).then(function (saved) {
          if (saved) updateLocalCaseStatus('Ny lokal sak er opprettet på enheten. Synk saken når du er klar.', false, { forceShow: true, showSync: true, showDiscard: true });
          return !!saved;
        });
      }).catch(function () { return false; });
    }

    function createServerCaseFromLocalDraft(options) {
      options = options || {};
      if (!createCaseUrl) return Promise.resolve(false);
      if (localCaseSyncInFlight && !options.force) return Promise.resolve(false);
      if (navigator.onLine === false) {
        return persistLocalCaseDraft({ silent: true }).then(function () {
          updateLocalCaseStatus('Lagret lokalt. Mangler nett.', true, { forceShow: true, showSync: true, showDiscard: true });
          return false;
        });
      }
      localCaseSyncInFlight = true;
      var shouldRedirectAfterCreate = options.redirectAfterCreate !== false && isOfflineNewCase;
      if (!options.silent) updateLocalCaseStatus('Oppretter saken på server og flytter lokal kladd ...', false, { forceShow: true, showSync: true, syncing: true, showDiscard: true });
      var localCaseId = String(root.dataset.caseId || '');
      persistLocalCaseDraft({ silent: true });
      var formData = serializeCaseFormData();
      return fetch(createCaseUrl, secureFetchOptions({ method: 'POST', body: formData }))
        .then(function (r) { return parseJsonResponse(r, 'Kunne ikke opprette saken på server.'); })
        .then(function (payload) {
          var serverCaseId = String(payload.case_id || '');
          var serverCaseUrl = String(payload.case_url || ('/cases/' + serverCaseId + '/edit'));
          var serverCaseNumber = String(payload.case_number || root.dataset.caseNumber || '');
          var savedAt = String(payload.saved_at || new Date().toISOString());
          applyServerSaveMeta({ version: payload.version, saved_at: savedAt });
          var tasks = [];
          if (localCaseSupported() && LocalCases.reassignDraft) tasks.push(LocalCases.reassignDraft(localCaseId, serverCaseId, { case_number: serverCaseNumber, case_url: serverCaseUrl, sync_state: 'synced', server_updated_at: savedAt, last_server_sync_at: savedAt }));
          if (localMediaSupported() && LocalMedia.reassignCase) tasks.push(LocalMedia.reassignCase(localCaseId, serverCaseId));
          return Promise.all(tasks).catch(function () { return []; }).then(function () {
            localCaseSyncInFlight = false;
            applyServerCaseIdentity(serverCaseId, serverCaseUrl, serverCaseNumber, savedAt);
            updateLocalCaseStatus('Saken er opprettet og synket med serveren.', false, { forceShow: true, showSync: false, showDiscard: false });
            if (shouldRedirectAfterCreate) {
              window.location.href = serverCaseUrl + (serverCaseUrl.indexOf('?') === -1 ? '?restored_local=1' : '&restored_local=1');
              return false;
            }
            return true;
          });
        })
        .catch(function (error) {
          localCaseSyncInFlight = false;
          persistLocalCaseDraft({ silent: true });
          if (error && error.message === 'duplicate_case_number') {
            updateLocalCaseStatus('Kunne ikke synke lokal sak fordi saksnummeret finnes allerede. Endre løpenummeret og prøv igjen.', true, { forceShow: true, showSync: true, showDiscard: true });
          } else {
            updateLocalCaseStatus('Lagret lokalt. Serverkopi feilet.', true, { forceShow: true, showSync: true, showDiscard: true });
          }
          return false;
        });
    }

    function syncLocalCaseDraft(options) {
      options = options || {};
      if (isLocalOnlyCase()) return createServerCaseFromLocalDraft(options);
      if (!root.dataset.autosaveUrl) return Promise.resolve(true);
      if (localCaseSyncInFlight && !options.force) return Promise.resolve(false);
      if (navigator.onLine === false) {
        return persistLocalCaseDraft({ silent: true }).then(function () {
          updateLocalCaseStatus('Lagret lokalt. Synk venter.', true, { forceShow: true, showSync: true, showDiscard: true });
          return false;
        });
      }
      localCaseSyncInFlight = true;
      if (!options.silent) updateLocalCaseStatus('Synker lokal sak til server ...', false, { forceShow: true, showSync: true, syncing: true, showDiscard: true });
      var formData = serializeCaseFormData();
      return fetch(root.dataset.autosaveUrl, secureFetchOptions({ method: 'POST', body: formData }))
        .then(function (r) { return parseJsonResponse(r, 'Kunne ikke lagre saken på server.'); })
        .then(function (payload) {
          localCaseSyncInFlight = false;
          applyServerSaveMeta(payload || {});
          lastAutosaveFingerprint = formFingerprint();
          setAutosaveStatus('Synket', 'is-saved');
          return markLocalCaseSynced(payload && payload.saved_at ? payload.saved_at : new Date().toISOString()).then(function () {
            return true;
          });
        })
        .catch(function (error) {
          localCaseSyncInFlight = false;
          if (isMissingServerCaseError(error) && createCaseUrl) {
            updateLocalCaseStatus('Serveren finner ikke saken. Oppretter ny serverkopi ...', true, { forceShow: true, showSync: true, syncing: true, showDiscard: true });
            return createServerCaseFromLocalDraft(Object.assign({}, options, { force: true, redirectAfterCreate: false, silent: true }));
          }
          if (error && (Number(error.status || 0) === 409 || String(error.message || '').indexOf('case_conflict') !== -1)) {
            var payload = error.payload || {};
            if (payload.current_version) root.dataset.caseConflictVersion = String(payload.current_version);
            if (payload.current_updated_at) root.dataset.caseConflictUpdatedAt = String(payload.current_updated_at);
            persistLocalCaseDraft({ silent: true });
            updateLocalCaseStatus('Saken er endret et annet sted. Last inn på nytt eller behold lokal kopi.', true, { forceShow: true, showSync: true, showDiscard: true });
            setAutosaveStatus('Konflikt', 'is-error');
            return false;
          }
          persistLocalCaseDraft({ silent: true });
          updateLocalCaseStatus('Lagret lokalt. Ikke synket.', true, { forceShow: true, showSync: true, showDiscard: true });
          setAutosaveStatus('Lokalt', 'is-saved');
          return false;
        });
    }

    function ensureLocalCaseSyncedBeforeAction() {
      return syncLocalCaseDraft({ force: true, redirectAfterCreate: false }).then(function (synced) {
        if (synced) return true;
        updateLocalCaseStatus('Forhåndsvisning og eksport krever at saken finnes på serveren. Trykk Synk sak og prøv igjen når synk er fullført.', true, { forceShow: true, showSync: true, showDiscard: true });
        try { window.alert('Saken må synkes til server før forhåndsvisning eller dokumenteksport. Trykk Synk sak og prøv igjen.'); } catch (e) {}
        return false;
      }).catch(function () {
        updateLocalCaseStatus('Kunne ikke kontrollere at saken er synket. Prøv igjen om litt.', true, { forceShow: true, showSync: true, showDiscard: true });
        return false;
      });
    }

    function evidenceFileUrl(entry) {
      if (!entry) return '';
      if (entry.local_pending && entry.local_blob && typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function') {
        if (!localEvidenceObjectUrls[String(entry.id || '')]) {
          try {
            localEvidenceObjectUrls[String(entry.id || '')] = URL.createObjectURL(entry.local_blob);
          } catch (e) {
            localEvidenceObjectUrls[String(entry.id || '')] = '';
          }
        }
        return localEvidenceObjectUrls[String(entry.id || '')] || '';
      }
      return String(entry.url || ('/cases/' + root.dataset.caseId + '/evidence/' + String(entry.id || '') + '/file'));
    }

    function revokeLocalEvidenceObjectUrl(entryId) {
      var key = String(entryId || '');
      var url = localEvidenceObjectUrls[key];
      if (!url || typeof URL === 'undefined' || typeof URL.revokeObjectURL !== 'function') return;
      try { URL.revokeObjectURL(url); } catch (e) {}
      delete localEvidenceObjectUrls[key];
    }

    function evidenceIsAudio(item) {
      return !!item && String(item.mime_type || '').toLowerCase().indexOf('audio/') === 0;
    }

    function removeEvidenceCard(entryId) {
      if (!evidenceGrid) return;
      Array.prototype.forEach.call(evidenceGrid.querySelectorAll('[data-evidence-id]'), function (card) {
        if (String(card.getAttribute('data-evidence-id') || '') !== String(entryId || '')) return;
        try { card.remove(); } catch (e) { if (card.parentNode) card.parentNode.removeChild(card); }
      });
    }

    function removeAudioCard(entryId) {
      if (!audioList) return;
      Array.prototype.forEach.call(audioList.querySelectorAll('[data-audio-id]'), function (card) {
        if (String(card.getAttribute('data-audio-id') || '') !== String(entryId || '')) return;
        try { card.remove(); } catch (e) { if (card.parentNode) card.parentNode.removeChild(card); }
      });
    }

    function pendingLocalMediaEntries() {
      return (evidenceState || []).filter(function (entry) { return !!(entry && entry.local_pending); });
    }

    function pendingLocalEvidenceEntries() {
      return pendingLocalMediaEntries().filter(function (entry) { return evidenceIsImage(entry); });
    }

    function pendingLocalAudioEntries() {
      return pendingLocalMediaEntries().filter(function (entry) { return evidenceIsAudio(entry); });
    }

    function updateLocalMediaStatus(message, isError) {
      if (!localMediaStatus) return;
      var pendingImages = pendingLocalEvidenceEntries().length;
      var pendingAudio = pendingLocalAudioEntries().length;
      var pendingCount = pendingImages + pendingAudio;
      if (!localMediaSupported()) {
        localMediaStatus.classList.add('hidden');
        return;
      }
      if (!message && !pendingCount) {
        localMediaStatus.classList.add('hidden');
        return;
      }
      localMediaStatus.classList.remove('hidden');
      if (localMediaStatusText) {
        if (message) {
          localMediaStatusText.textContent = message;
        } else {
          var bits = [];
          if (pendingImages) bits.push(pendingImages + ' bilde' + (pendingImages === 1 ? '' : 'r'));
          if (pendingAudio) bits.push(pendingAudio + ' lydfil' + (pendingAudio === 1 ? '' : 'er'));
          localMediaStatusText.textContent = bits.join(' og ') + ' lokalt. Synk venter.';
        }
      }
      localMediaStatus.classList.toggle('alert-error', !!isError);
      if (btnSyncLocalMedia) btnSyncLocalMedia.classList.toggle('hidden', pendingCount === 0 && !message);
    }

    function upsertEvidenceStateEntry(entry, prepend) {
      var filtered = (evidenceState || []).filter(function (row) { return String(row && row.id || '') !== String(entry && entry.id || ''); });
      evidenceState = prepend === false ? filtered.concat([entry]) : [entry].concat(filtered);
    }

    function removeEvidenceStateEntry(entryId) {
      evidenceState = (evidenceState || []).filter(function (row) { return String(row && row.id || '') !== String(entryId || ''); });
      revokeLocalEvidenceObjectUrl(entryId);
      removeEvidenceCard(entryId);
      removeAudioCard(entryId);
      updateLocalMediaStatus();
    }

    function localRecordToEvidence(record) {
      return {
        id: record.id,
        url: '',
        mime_type: record.mime_type || (record.file && record.file.type) || 'image/jpeg',
        original_filename: record.original_filename || (record.file && record.file.name) || 'vedlegg.bin',
        caption: record.caption || '',
        finding_key: record.finding_key || '',
        law_text: record.law_text || '',
        violation_reason: record.violation_reason || '',
        seizure_ref: record.seizure_ref || '',
        local_pending: true,
        local_sync_state: record.sync_state || 'pending',
        local_error: record.last_error || '',
        local_blob: record.file || null,
        local_signature: record.dedupe_signature || '',
        kind: record.kind || (LocalMedia && typeof LocalMedia.inferKind === 'function' ? LocalMedia.inferKind(record) : (String(record.mime_type || '').toLowerCase().indexOf('audio/') === 0 ? 'audio' : 'image'))
      };
    }

    function postEvidenceToServer(file, payload) {
      var formData = new FormData();
      formData.append('caption', payload.caption || '');
      formData.append('finding_key', payload.finding_key || '');
      formData.append('law_text', payload.law_text || '');
      formData.append('violation_reason', payload.violation_reason || '');
      formData.append('seizure_ref', payload.seizure_ref || '');
      formData.append('device_id', currentDeviceId);
      formData.append('local_media_id', payload.local_media_id || payload.local_id || '');
      formData.append('file', file, file.name || ('vedlegg-' + Date.now() + '.bin'));
      return fetch('/api/cases/' + root.dataset.caseId + '/evidence', secureFetchOptions({ method: 'POST', body: formData }))
        .then(function (response) {
          return response.json().then(function (payloadJson) { return { ok: response.ok, payload: payloadJson || {} }; }).catch(function () { return { ok: response.ok, payload: {} }; });
        })
        .then(function (result) {
          if (!result.ok || !result.payload || !result.payload.ok || !result.payload.evidence) {
            throw new Error((result.payload && result.payload.message) || 'Kunne ikke lagre vedlegg i saken.');
          }
          return result.payload.evidence;
        });
    }

    function toUploadFile(fileOrBlob, fallbackName, fallbackType) {
      if (typeof File !== 'undefined' && fileOrBlob instanceof File) return Promise.resolve(fileOrBlob);
      var blob = fileOrBlob instanceof Blob ? fileOrBlob : new Blob([fileOrBlob], { type: (fileOrBlob && fileOrBlob.type) || fallbackType || 'application/octet-stream' });
      return Promise.resolve(new File([blob], fallbackName || ('vedlegg-' + Date.now() + '.bin'), { type: blob.type || fallbackType || 'application/octet-stream', lastModified: Date.now() }));
    }

    function buildLocalEvidenceRecord(file, payload, options) {
      options = options || {};
      var kind = String(options.kind || (LocalMedia && typeof LocalMedia.inferKind === 'function' ? LocalMedia.inferKind({ mime_type: file && file.type }) : ((file && file.type && String(file.type).toLowerCase().indexOf('audio/') === 0) ? 'audio' : 'image')) || 'image').toLowerCase();
      return {
        id: LocalMedia && typeof LocalMedia.generateId === 'function' ? LocalMedia.generateId() : ('local-' + Date.now() + '-' + Math.random().toString(16).slice(2)),
        case_id: String(root.dataset.caseId || ''),
        owner_user_id: currentUserId,
        device_id: currentDeviceId,
        created_at: Date.now(),
        sync_state: 'pending',
        kind: kind,
        source_kind: options.sourceKind || kind,
        original_filename: file.name || ((kind === 'audio' ? 'avhor-' : 'bilde-') + Date.now()),
        mime_type: file.type || (kind === 'audio' ? 'audio/webm' : 'image/jpeg'),
        caption: payload.caption || '',
        finding_key: payload.finding_key || '',
        law_text: payload.law_text || '',
        violation_reason: payload.violation_reason || '',
        seizure_ref: payload.seizure_ref || '',
        dedupe_signature: options.signature || '',
        group_id: options.groupId || '',
        segment_index: options.segmentIndex || 0,
        file: file
      };
    }

    function buildAudioCaption(baseName, segmentIndex) {
      var text = String(baseName || 'Lydopptak');
      if (segmentIndex > 0) return text + ' - del ' + segmentIndex;
      return text;
    }

    function queueLocalMediaUpload(file, payload, options) {
      options = options || {};
      if (!file) return Promise.reject(new Error('Velg en fil først.'));
      if (!root.dataset.caseId) return Promise.reject(new Error('Saken mangler ID.'));
      var kind = String(options.kind || (LocalMedia && typeof LocalMedia.inferKind === 'function' ? LocalMedia.inferKind({ mime_type: file.type }) : ((String(file.type || '').toLowerCase().indexOf('audio/') === 0) ? 'audio' : 'image')) || 'image').toLowerCase();
      var signature = options.signature || fileSignature(file);
      if (signature && (options.preventDuplicate !== false) && (evidenceState || []).some(function (entry) {
        return !!entry && (String(entry.local_signature || '') === String(signature) || String(entry.server_signature || '') === String(signature));
      })) {
        return Promise.resolve(null);
      }
      function insertAndMaybeSync(stored, syncSilently) {
        var entry = localRecordToEvidence(stored);
        upsertEvidenceStateEntry(entry, true);
        if (kind === 'audio') appendAudioCard(entry);
        else appendEvidenceCard(entry);
        updateLocalMediaStatus(options.statusMessage || (kind === 'audio' ? 'Lyd lagret lokalt.' : 'Bilde lagret lokalt.'));
        if (signature && kind === 'image') lastOcrEvidenceSignature = signature;
        setAutosaveStatus(options.autosaveMessage || (kind === 'audio' ? 'Lydfil lagret lokalt' : 'Bilde lagret lokalt'), 'is-saved');
        if (options.autoSync === true) syncLocalMediaQueue({ onlyId: stored.id, silent: syncSilently !== false });
        else updateLocalMediaStatus(options.statusMessage || (kind === 'audio' ? 'Lyd lokalt. Synk venter.' : 'Bilde lokalt. Synk venter.'));
        return entry;
      }
      if (!localMediaSupported()) {
        return Promise.resolve(file).then(function (prepared) {
          return postEvidenceToServer(prepared, payload).then(function (serverEntry) {
            upsertEvidenceStateEntry(serverEntry, true);
            if (kind === 'audio') appendAudioCard(serverEntry);
            else appendEvidenceCard(serverEntry);
            return serverEntry;
          });
        });
      }
      if (kind === 'audio' && LocalMedia && typeof LocalMedia.requestPersistence === 'function') {
        LocalMedia.requestPersistence().catch(function () { return false; });
      }
      var record = buildLocalEvidenceRecord(file, payload, {
        sourceKind: options.sourceKind || kind,
        signature: signature,
        kind: kind,
        groupId: options.groupId || '',
        segmentIndex: options.segmentIndex || 0
      });
      return LocalMedia.put(record, ownerOptions()).then(function (stored) {
        return insertAndMaybeSync(stored, options.silentSync !== false);
      }).catch(function () {
        return Promise.resolve(file).then(function (prepared) {
          return postEvidenceToServer(prepared, payload).then(function (serverEntry) {
            upsertEvidenceStateEntry(serverEntry, true);
            if (kind === 'audio') appendAudioCard(serverEntry);
            else appendEvidenceCard(serverEntry);
            return serverEntry;
          });
        });
      });
    }

    function queueLocalEvidenceUpload(file, payload, options) {
      options = options || {};
      return queueLocalMediaUpload(file, payload, Object.assign({}, options, { kind: 'image' }));
    }

    function queueLocalAudioUpload(file, payload, options) {
      options = options || {};
      return queueLocalMediaUpload(file, payload, Object.assign({}, options, { kind: 'audio' }));
    }

    function syncOneLocalMediaRecord(record) {
      if (!record) return Promise.resolve(null);
      var kind = String(record.kind || (LocalMedia && typeof LocalMedia.inferKind === 'function' ? LocalMedia.inferKind(record) : ((String(record.mime_type || '').toLowerCase().indexOf('audio/') === 0) ? 'audio' : 'image')) || 'image').toLowerCase();
      return LocalMedia.update(record.id, { sync_state: 'uploading', last_error: '' }).catch(function () { return null; }).then(function () {
        return toUploadFile(record.file, record.original_filename || ((kind === 'audio' ? 'avhor-' : 'bilde-') + Date.now()), record.mime_type || (kind === 'audio' ? 'audio/webm' : 'image/jpeg'));
      }).then(function (preparedFile) {
        return postEvidenceToServer(preparedFile, {
          caption: record.caption || '',
          finding_key: record.finding_key || '',
          law_text: record.law_text || '',
          violation_reason: record.violation_reason || '',
          seizure_ref: record.seizure_ref || '',
          local_media_id: record.id || ''
        });
      }).then(function (serverEntry) {
        removeEvidenceStateEntry(record.id);
        return LocalMedia.update(record.id, {
          sync_state: 'synced',
          last_error: '',
          server_evidence_id: serverEntry && serverEntry.id ? serverEntry.id : '',
          server_filename: serverEntry && serverEntry.filename ? serverEntry.filename : '',
          server_received_at: new Date().toISOString()
        }).catch(function () { return null; }).then(function () {
          upsertEvidenceStateEntry(serverEntry, true);
          if (kind === 'audio') appendAudioCard(serverEntry);
          else appendEvidenceCard(serverEntry);
          return serverEntry;
        });
      }).catch(function (err) {
        var message = err && err.message ? err.message : ('Kunne ikke synke ' + (kind === 'audio' ? 'lydfil' : 'bilde') + ' akkurat nå.');
        return LocalMedia.update(record.id, { sync_state: 'failed', last_error: message }).catch(function () { return null; }).then(function () {
          var failedEntry = localRecordToEvidence(Object.assign({}, record, { sync_state: 'failed', last_error: message, kind: kind }));
          upsertEvidenceStateEntry(failedEntry, false);
          if (kind === 'audio') {
            removeAudioCard(record.id);
            appendAudioCard(failedEntry);
          } else {
            removeEvidenceCard(record.id);
            appendEvidenceCard(failedEntry);
          }
          updateLocalMediaStatus('Kunne ikke synke ett eller flere lokale vedlegg akkurat nå.', true);
          return null;
        });
      });
    }

    function syncLocalMediaQueue(options) {
      options = options || {};
      if (!localMediaSupported()) return Promise.resolve([]);
      if (localMediaSyncInFlight && !options.force) return Promise.resolve([]);
      localMediaSyncInFlight = true;
      if (btnSyncLocalMedia) btnSyncLocalMedia.disabled = true;
      return LocalMedia.getPendingByCase(root.dataset.caseId, ownerOptions()).then(function (rows) {
        var nowMs = Date.now();
        var staleUploadMs = 2 * 60 * 1000;
        var queue = (rows || []).filter(function (row) {
          return !options.onlyId || String(row.id) === String(options.onlyId);
        }).filter(function (row) {
          var state = String(row.sync_state || 'pending');
          if (state !== 'uploading') return true;
          return Number(row.updated_at || row.created_at || 0) < (nowMs - staleUploadMs);
        }).sort(function (a, b) { return Number(a.created_at || 0) - Number(b.created_at || 0); });
        if (!queue.length) {
          updateLocalMediaStatus();
          return [];
        }
        if (!options.silent) updateLocalMediaStatus('Synker ' + queue.length + ' lokale vedlegg til saken ...');
        return queue.reduce(function (promise, row) {
          return promise.then(function (items) {
            return syncOneLocalMediaRecord(row).then(function (result) {
              if (result) items.push(result);
              return items;
            });
          });
        }, Promise.resolve([]));
      }).finally(function () {
        localMediaSyncInFlight = false;
        if (btnSyncLocalMedia) btnSyncLocalMedia.disabled = false;
        updateLocalMediaStatus();
      });
    }

    function audioFileUrl(entry) {
      return evidenceFileUrl(entry);
    }

    function buildAudioCardHtml(entry) {
      var isLocal = !!(entry && entry.local_pending);
      var statusLine = '';
      if (isLocal) {
        var stateLabel = entry.local_sync_state === 'failed' ? 'Lokal lagring · synk feilet' : (entry.local_sync_state === 'uploading' ? 'Lokal lagring · synker nå' : 'Lokal lagring · ikke synket ennå');
        statusLine = '<div class="muted small evidence-local-state">' + escapeHtml(stateLabel) + (entry.local_error ? ' · ' + escapeHtml(entry.local_error) : '') + '</div>';
      }
      return [
        '<article class="audio-item' + (isLocal ? ' evidence-card-local' : '') + '" data-audio-id="' + escapeHtml(String(entry.id || '')) + '">',
        '<strong>' + escapeHtml(entry.caption || entry.original_filename || 'Lydopptak') + '</strong>',
        statusLine,
        '<audio controls preload="none" src="' + escapeHtml(audioFileUrl(entry)) + '"></audio>',
        (entry.seizure_ref ? '<div class="muted small">Beslag / referanse: ' + escapeHtml(entry.seizure_ref) + '</div>' : ''),
        '<div class="actions-row wrap">',
        (isLocal
          ? '<button class="btn btn-secondary btn-small" type="button" data-local-sync="' + escapeHtml(String(entry.id || '')) + '">Synk nå</button><button class="btn btn-danger btn-small" type="button" data-local-delete="' + escapeHtml(String(entry.id || '')) + '">Fjern lokalt</button>'
          : '<a class="btn btn-secondary btn-small" href="' + escapeHtml(audioFileUrl(entry)) + '" download>Last ned</a><form method="post" action="/evidence/' + escapeHtml(String(entry.id || '')) + '/delete" data-confirm="Slette lydfil?">' + csrfFieldHtml() + '<button class="btn btn-danger btn-small" type="submit">Slett</button></form>'),
        '</div>',
        '</article>'
      ].join('');
    }

    function appendAudioCard(entry) {
      if (!audioList || !entry || !evidenceIsAudio(entry)) return;
      removeAudioCard(entry.id);
      audioList.insertAdjacentHTML('afterbegin', buildAudioCardHtml(entry));
      if (Common.appendCsrfToForms) Common.appendCsrfToForms(audioList);
    }

    function loadLocalEvidenceFromDevice() {
      if (!localMediaSupported()) {
        updateLocalMediaStatus();
        return Promise.resolve([]);
      }
      return LocalMedia.getPendingByCase(root.dataset.caseId, ownerOptions()).then(function (rows) {
        (rows || []).forEach(function (row) {
          var entry = localRecordToEvidence(row);
          upsertEvidenceStateEntry(entry, false);
          if (evidenceIsAudio(entry)) {
            if (!audioList || !audioList.querySelector('[data-audio-id="' + String(entry.id || '') + '"]')) appendAudioCard(entry);
          } else {
            if (!evidenceGrid || !evidenceGrid.querySelector('[data-evidence-id="' + String(entry.id || '') + '"]')) appendEvidenceCard(entry);
          }
        });
        updateLocalMediaStatus();
        return rows || [];
      }).catch(function () {
        updateLocalMediaStatus('Lokal lagring av bilder og lyd er ikke tilgjengelig i denne nettleseren.', true);
        return [];
      });
    }

    function ensureLocalMediaSyncedBeforeAction() {
      if (!pendingLocalMediaEntries().length) return Promise.resolve(true);
      return syncLocalMediaQueue({}).then(function () {
        if (!pendingLocalMediaEntries().length) return true;
        return window.confirm('Noen vedlegg er ikke synket. Fortsette likevel?');
      });
    }

    function mapStepIsVisible() {
      return currentStep === 2 && document.visibilityState === 'visible';
    }

    function syncStepNavigation() {
      var total = panes.length || 1;
      var activeButton = stepButtons.filter(function (btn) { return Number(btn.dataset.stepTarget) === currentStep; })[0] || null;
      var activeLabel = activeButton ? String(activeButton.textContent || '').replace(/^\s*\d+\.\s*/, '').trim() : '';
      if (mobileStepLabel) mobileStepLabel.textContent = 'Steg ' + currentStep + ' av ' + total + (activeLabel ? ' · ' + activeLabel : '');
      if (topStepLabel) topStepLabel.textContent = currentStep + ' / ' + total;
      [mobilePrevStep, topPrevStep].forEach(function (btn) {
        if (!btn) return;
        btn.disabled = currentStep <= 1;
        btn.classList.toggle('hidden', currentStep <= 1);
      });
      [mobileNextStep, topNextStep].forEach(function (btn) {
        if (!btn) return;
        btn.disabled = currentStep >= total;
        btn.classList.toggle('hidden', currentStep >= total);
      });
    }

    function showStep(step, options) {
      options = options || {};
      currentStep = step;
      try { sessionStorage.setItem(stepStorageKey, String(step)); } catch (e) {}
      panes.forEach(function (pane) { pane.classList.toggle('active', Number(pane.dataset.step) === step); });
      stepButtons.forEach(function (btn) { btn.classList.toggle('active', Number(btn.dataset.stepTarget) === step); });
      syncStepNavigation();
      if (step === 2) {
        setTimeout(function () {
          updateCaseMap();
          if (autoLocationAttempted) startLocationWatch({ deviceOnly: mapState.manualPosition === true, recenter: mapState.manualPosition !== true });
          else maybeAutoStartLocation();
          if (caseMap && caseMap._kvLeafletMap) {
            try { caseMap._kvLeafletMap.invalidateSize(); } catch (e) {}
          }
        }, 180);
      }
      if (step === 4) {
        window.setTimeout(function () { loadRules(); }, 0);
      }
      if (options.scroll !== false) window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    stepButtons.forEach(function (btn) { btn.addEventListener('click', function () { showStep(Number(btn.dataset.stepTarget)); }); });
    document.querySelectorAll('[data-next-step]').forEach(function (btn) { btn.addEventListener('click', function () { showStep(Math.min(currentStep + 1, panes.length)); }); });
    document.querySelectorAll('[data-prev-step]').forEach(function (btn) { btn.addEventListener('click', function () { showStep(Math.max(currentStep - 1, 1)); }); });
    [mobilePrevStep, topPrevStep].forEach(function (btn) {
      if (!btn) return;
      btn.addEventListener('click', function () { showStep(Math.max(currentStep - 1, 1)); });
    });
    [mobileNextStep, topNextStep].forEach(function (btn) {
      if (!btn) return;
      btn.addEventListener('click', function () { showStep(Math.min(currentStep + 1, panes.length)); });
    });

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
          ['Observatør', 'Båtfører', 'Båtassistent'].map(function (role) { return '<option value="' + role + '" ' + (role === item.role ? 'selected' : '') + '>' + role + '</option>'; }).join(''),
          '</select>',
          '<button type="button" class="btn btn-danger btn-small crew-remove">Fjern</button>',
          '</div>'
        ].join('');
      }).join('');
      crewInput.value = JSON.stringify(crewState);
      scheduleAutosave('Roller oppdatert');
    }

    document.getElementById('btn-add-crew').addEventListener('click', function () {
      crewState.push({ name: '', role: 'Observatør' });
      renderCrew();
    setAutosaveStatus('Klar for autosave', 'is-saved');
    });
    document.getElementById('crew-list').addEventListener('input', function (event) {
      var row = event.target.closest('.crew-row');
      if (!row) return;
      var idx = Number(row.dataset.index);
      crewState[idx] = crewState[idx] || { name: '', role: 'Observatør' };
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


    function normalizePersonRole(role) {
      var raw = String(role || '').trim();
      return raw || 'Mistenkt';
    }

    function newPerson(role) {
      var isSuspect = normalizePersonRole(role).toLowerCase().indexOf('mistenkt') !== -1;
      return {
        role: normalizePersonRole(role),
        name: isSuspect ? (suspectName.value || suspectNameCommercial.value || '') : '',
        phone: isSuspect ? (suspectPhone.value || '') : '',
        birthdate: isSuspect ? (suspectBirthdate.value || '') : '',
        address: isSuspect ? (suspectAddress.value || '') : '',
        relation: ''
      };
    }

    function renderPersons() {
      var wrap = document.getElementById('persons-list');
      if (!wrap) return;
      if (!personsState.length) {
        wrap.innerHTML = '<div class="callout">Ingen ekstra personer er lagt til. Hovedperson/fartøy over brukes fortsatt i saken.</div>';
        if (personsInput) personsInput.value = JSON.stringify(personsState || []);
        syncInterviewPersonOptions();
        return;
      }
      wrap.innerHTML = personsState.map(function (person, idx) {
        var role = normalizePersonRole(person.role || 'Mistenkt');
        var roleOptions = ['Mistenkt', 'Siktet', 'Vitne', 'Fornærmet', 'Eier', 'Fører/skipper', 'Annen person'].map(function (option) {
          return '<option value="' + escapeHtml(option) + '" ' + (option === role ? 'selected' : '') + '>' + escapeHtml(option) + '</option>';
        }).join('');
        return [
          '<article class="person-card" data-index="' + idx + '">',
          '<div class="grid-two compact-grid-form">',
          '<label><span>Rolle</span><select class="person-role">' + roleOptions + '</select></label>',
          '<label><span>Navn</span><input class="person-name" value="' + escapeHtml(person.name || '') + '" autocomplete="name" /></label>',
          '<label><span>Telefon</span><input class="person-phone" value="' + escapeHtml(person.phone || '') + '" inputmode="tel" autocomplete="tel" /></label>',
          '<label><span>Fødselsdato / id</span><input class="person-birthdate" value="' + escapeHtml(person.birthdate || '') + '" /></label>',
          '<label class="span-2"><span>Adresse</span><input class="person-address" value="' + escapeHtml(person.address || '') + '" autocomplete="street-address" /></label>',
          '<label class="span-2"><span>Tilknytning / merknad</span><input class="person-relation" value="' + escapeHtml(person.relation || '') + '" placeholder="F.eks. eier av redskap, vitne til observasjon" /></label>',
          '</div>',
          '<div class="actions-row wrap margin-top-s"><button type="button" class="btn btn-secondary btn-small person-to-interview">Opprett avhør</button><button type="button" class="btn btn-danger btn-small person-remove">Fjern</button></div>',
          '</article>'
        ].join('');
      }).join('');
      if (personsInput) personsInput.value = JSON.stringify(personsState || []);
      syncInterviewPersonOptions();
    }

    function syncPersonsFromDom() {
      document.querySelectorAll('#persons-list .person-card').forEach(function (card) {
        var idx = Number(card.dataset.index);
        personsState[idx] = personsState[idx] || {};
        personsState[idx].role = card.querySelector('.person-role').value;
        personsState[idx].name = card.querySelector('.person-name').value;
        personsState[idx].phone = card.querySelector('.person-phone').value;
        personsState[idx].birthdate = card.querySelector('.person-birthdate').value;
        personsState[idx].address = card.querySelector('.person-address').value;
        personsState[idx].relation = card.querySelector('.person-relation').value;
      });
      if (personsInput) personsInput.value = JSON.stringify(personsState || []);
      scheduleAutosave('Personer oppdatert');
      syncInterviewPersonOptions();
    }

    function makeInterviewFromPerson(person) {
      person = person || {};
      var role = normalizePersonRole(person.role || 'Mistenkt');
      return {
        name: person.name || suspectName.value || suspectNameCommercial.value || '',
        role: role,
        method: 'På stedet / telefon',
        place: locationName.value || '',
        start: startTime.value || '',
        end: endTime.value || '',
        transcript: '',
        summary: ''
      };
    }

    function syncInterviewPersonOptions() {
      var select = document.getElementById('interview-person-source');
      if (!select) return;
      var rows = [];
      if (suspectName.value || suspectNameCommercial.value) rows.push({ idx: 'main', role: 'Mistenkt', name: suspectName.value || suspectNameCommercial.value });
      (personsState || []).forEach(function (p, idx) { if (p && p.name) rows.push({ idx: String(idx), role: p.role || 'Person', name: p.name }); });
      select.innerHTML = rows.length ? rows.map(function (row) { return '<option value="' + escapeHtml(row.idx) + '">' + escapeHtml(row.role + ': ' + row.name) + '</option>'; }).join('') : '<option value="">Ingen registrerte personer</option>';
    }

    var addSuspectBtn = document.getElementById('btn-add-suspect');
    if (addSuspectBtn) addSuspectBtn.addEventListener('click', function () { personsState.push(newPerson('Mistenkt')); renderPersons(); scheduleAutosave('Mistenkt lagt til'); });
    var addWitnessPersonBtn = document.getElementById('btn-add-witness-person');
    if (addWitnessPersonBtn) addWitnessPersonBtn.addEventListener('click', function () { personsState.push(newPerson('Vitne')); renderPersons(); scheduleAutosave('Vitne lagt til'); });
    var personsListEl = document.getElementById('persons-list');
    if (personsListEl) {
      personsListEl.addEventListener('input', syncPersonsFromDom);
      personsListEl.addEventListener('change', syncPersonsFromDom);
      personsListEl.addEventListener('click', function (event) {
        var card = event.target.closest('.person-card');
        if (!card) return;
        var idx = Number(card.dataset.index);
        if (event.target.classList.contains('person-remove')) {
          personsState.splice(idx, 1);
          renderPersons();
          scheduleAutosave('Person fjernet');
          return;
        }
        if (event.target.classList.contains('person-to-interview')) {
          syncPersonsFromDom();
          interviewState.push(makeInterviewFromPerson(personsState[idx] || {}));
          renderInterviews();
          scheduleAutosave('Avhør opprettet fra person');
        }
      });
    }
    renderPersons();

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

    function cloneRowList(rows) {
      if (!Array.isArray(rows)) return [];
      return rows.filter(function (row) { return row && typeof row === 'object'; }).map(function (row) { return Object.assign({}, row); });
    }

    function mergeLegacyHummerLengthState(currentByKey) {
      var minCurrent = currentByKey.hummer_minstemal || null;
      var maxCurrent = currentByKey.hummer_maksimalmal || null;
      if (!minCurrent && !maxCurrent) return {};
      var merged = {};
      var statuses = [minCurrent && minCurrent.status, maxCurrent && maxCurrent.status].filter(Boolean);
      if (statuses.indexOf('avvik') !== -1) merged.status = 'avvik';
      else if (statuses.indexOf('godkjent') !== -1) merged.status = 'godkjent';
      else if (statuses.length) merged.status = statuses[0];
      var notes = [];
      [minCurrent && minCurrent.notes, maxCurrent && maxCurrent.notes].forEach(function (note) {
        note = String(note || '').trim();
        if (note && notes.indexOf(note) === -1) notes.push(note);
      });
      if (notes.length) merged.notes = notes.join(' ');
      var measurements = cloneRowList((minCurrent && minCurrent.measurements) || []).concat(cloneRowList((maxCurrent && maxCurrent.measurements) || []));
      if (measurements.length) merged.measurements = measurements;
      var deviations = cloneRowList((minCurrent && minCurrent.deviation_units) || []).concat(cloneRowList((maxCurrent && maxCurrent.deviation_units) || []));
      if (deviations.length) merged.deviation_units = deviations;
      if (minCurrent && minCurrent.auto_note) merged.auto_note = minCurrent.auto_note;
      if (maxCurrent && maxCurrent.auto_note) merged.auto_note = maxCurrent.auto_note;
      return merged;
    }

    function resolveCurrentFinding(item, currentByKey) {
      if (!item || !currentByKey) return {};
      var current = currentByKey[item.key] || null;
      if (current) return current;
      if (String(item.key || '') === 'hummer_lengdekrav') return mergeLegacyHummerLengthState(currentByKey);
      return {};
    }

    function renderFindings() {
      findingsInput.value = JSON.stringify(findingsState);
      ensureControlLinkState();
      renderControlLinkToolbar();
      if (!findingsState.length) {
        findingsList.innerHTML = '<div class="callout">Ingen kontrollpunkter er valgt ennå. Velg kontrolltype, art/fiskeri og redskap for å hente relevante kontrollpunkter automatisk.</div>';
        renderSeizureReports({ mergeDefaults: true });
        updateAreaRestrictionOptions(latestZoneResult);
        return;
      }
      findingsList.innerHTML = findingsState.map(buildEditableFindingHtml).join('');
      document.querySelectorAll('#findings-list .finding-card').forEach(function(card){
        var idx = Number(card.dataset.index);
        evaluateMarkerLimit(card, findingsState[idx]);
      });
      renderSeizureReports({ mergeDefaults: true });
      updateAreaRestrictionOptions(latestZoneResult);
    }


    function areaOptionPayload(label, status, detail, source) {
      return { label: String(label || '').trim(), status: String(status || '').trim(), detail: String(detail || '').trim(), source: String(source || '').trim() };
    }

    function updateAreaRestrictionOptions(result) {
      if (!areaRestrictionSelect || !areaRestrictionDetail) return;
      var rows = [];
      var selectedFishery = String((species && species.value) || (fisheryType && fisheryType.value) || '').toLowerCase();
      var selectedGear = String((gearType && gearType.value) || '').toLowerCase();
      var selectedTokens = [selectedFishery, selectedGear].join(' ');
      var latNum = latitude && latitude.value ? Number(String(latitude.value).replace(',', '.')) : null;
      function textRelevantToSelection(text) {
        text = String(text || '').toLowerCase();
        if (!text) return false;
        if (/svalbard/.test(text) && !(latNum !== null && latNum > 70)) return false;
        if (/breivikfjorden|borgundfjorden|henningsvær|henningsvaer|lofotfiske/.test(text) && !/torsk|skrei|kommersiell|yrkes/.test(selectedTokens + ' ' + text)) return false;
        var isRegulated = /forbud|fredning|fredningsområde|stengt|nullfiske|regulert|maksimalmål|forskrift|lovdata|j-melding|j melding/.test(text);
        if (!isRegulated) return false;
        if (!selectedTokens.trim()) return isRegulated;
        if (/hummer/.test(selectedFishery) && /hummer/.test(text)) return true;
        if (/torsk/.test(selectedFishery) && /torsk|kysttorsk|skrei/.test(text)) return true;
        if (/krabbe/.test(selectedFishery) && /krabbe/.test(text)) return true;
        if (/laks|ørret|orret/.test(selectedFishery) && /laks|ørret|orret|laksefjord/.test(text)) return true;
        if (selectedGear && text.indexOf(selectedGear) !== -1) return true;
        return /stengt|nullfiske|fredningsområde|fredning/.test(text) && !/svalbard|lofotfiske|henningsvær|henningsvaer/.test(text);
      }
      function push(row, forceRelevant) {
        if (!row || !row.label) return;
        var combined = [row.label, row.status, row.detail, row.source].join(' ');
        if (/svalbard/.test(combined.toLowerCase()) && !(latNum !== null && latNum > 70)) return;
        if (!forceRelevant && !textRelevantToSelection(combined)) return;
        var key = [row.label, row.status, row.detail].join('|').toLowerCase();
        for (var i = 0; i < rows.length; i++) {
          if (rows[i]._key === key) return;
        }
        row._key = key;
        rows.push(row);
      }
      result = result || latestZoneResult || {};
      if (result.match) push(areaOptionPayload(result.name || result.status || 'Verneområde', result.status || 'regulert område', result.notes || (result.recommended_violation && result.recommended_violation.message) || '', 'områdesjekk'));
      (result.hits || []).forEach(function (hit) {
        var hitLayerIds = Array.isArray(hit && hit.layer_ids) ? hit.layer_ids : ((hit && hit.layer_id !== undefined && hit.layer_id !== null && hit.layer_id !== '') ? [hit.layer_id] : []);
        if (hitLayerIds.length) {
          var hitRelevant = hitLayerIds.some(function (rawLayerId) {
            var resolvedLayer = layerDefinitionById(resolveCatalogLayerId(rawLayerId, hit && (hit.layer || hit.layer_name || hit.name)));
            return !resolvedLayer || layerMatchesCurrentSelection(resolvedLayer);
          });
          if (!hitRelevant) return;
        }
        var text = [hit.name, hit.layer, hit.source].filter(Boolean).join(' - ');
        var detail = hit.notes || hit.summary || hit.description || hit.law_text || '';
        push(areaOptionPayload(hit.name || hit.layer || 'Verneområde', hit.status || hit.layer || 'regulert område', detail, hit.source || 'kart'));
      });
      filteredMapCatalog().forEach(function (layer) {
        push(areaOptionPayload(layer.name || ('Lag ' + String(layer.id || '')), layer.status || 'temalag', layer.selection_summary || layer.description || '', layer.source || 'kart'), true);
      });
      (findingsState || []).forEach(function (item) {
        var text = [item.label, item.key, item.status, item.notes, item.auto_note, item.summary_text, item.law_text, item.source_name, item.source_ref].join(' ');
        var lower = text.toLowerCase();
        if (lower.indexOf('svalbard') !== -1 && !(latNum !== null && latNum > 70)) return;
        var hasAreaLaw = /verneområde|fredningsområde|stengt område|nullfiskeområde|maksimalmål område|områdeforbud|forbud mot/.test(lower);
        if (hasAreaLaw && textRelevantToSelection(text)) {
          push(areaOptionPayload(areaName && areaName.value ? areaName.value : (item.label || 'Verneområde'), areaStatus && areaStatus.value ? areaStatus.value : (item.status || 'avvik'), item.summary_text || item.notes || item.auto_note || item.law_text || '', item.source_name || item.source_ref || 'kontrollpunkt'));
        }
      });
      areaRestrictionSelect.innerHTML = '';
      if (!rows.length) {
        areaRestrictionSelect.innerHTML = '<option value="">Ingen verneområder funnet for valgt art/redskap</option>';
        areaRestrictionDetail.textContent = 'Velg art/redskap og oppdater posisjon.';
        return;
      }
      rows.forEach(function (row, idx) {
        var opt = document.createElement('option');
        opt.value = String(idx);
        opt.textContent = row.label + (row.status ? ' - ' + row.status : '');
        areaRestrictionSelect.appendChild(opt);
      });
      function showSelected() {
        var row = rows[Number(areaRestrictionSelect.value || 0)] || rows[0];
        areaRestrictionDetail.innerHTML = '<strong>' + escapeHtml(row.label) + '</strong>' + (row.status ? '<div>Status: ' + escapeHtml(row.status) + '</div>' : '') + (row.detail ? '<div class="small muted">' + escapeHtml(row.detail) + '</div>' : '') + (row.source ? '<div class="small muted">Kilde: ' + escapeHtml(row.source) + '</div>' : '');
        if (areaName && row.label) areaName.value = row.label;
        if (areaStatus && row.status) areaStatus.value = row.status;
      }
      areaRestrictionSelect.onchange = function () { showSelected(); scheduleAutosave('Verneområde valgt'); };
      showSelected();
    }

    function normalizedSeizureIssueText(item) {
      var text = [item && item.label, item && item.key, item && item.notes, item && item.auto_note, item && item.summary_text, item && item.law_text].join(' ').toLowerCase();
      return text;
    }

    function isSeizureRelevantFinding(item) {
      if (!item || String(item.status || '').toLowerCase() !== 'avvik') return false;
      return /redskap|teine|ruse|garn|beslag|minstemål|maksimalmål|lengde|hummer|fangst|oppbevaring/.test(normalizedSeizureIssueText(item));
    }

    function defaultSeizureRowsFromFindings() {
      var rows = [];
      var byRef = {};
      function addRow(row) {
        var ref = String(row.seizure_ref || row.reference || '').trim();
        if (!ref || byRef[ref]) return;
        byRef[ref] = true;
        rows.push(row);
      }
      (findingsState || []).forEach(function (item, idx) {
        if (!isSeizureRelevantFinding(item)) return;
        var lawText = item.law_text || item.source_ref || '';
        ensureDeviationState(item).forEach(function (dev, dIdx) {
          syncDeviationDefaults(item);
          addRow({
            seizure_ref: dev.seizure_ref || formatSeizureRef(nextSeizureSequence()),
            source_key: (item.key || ('finding-' + idx)) + ':dev:' + dIdx,
            type: dev.gear_kind || item.label || 'Redskap med avvik',
            quantity: dev.quantity || '1',
            position: dev.position || currentCoordText(),
            description: dev.note || item.notes || item.auto_note || item.summary_text || item.label || 'Registrert avvik',
            law_text: lawText,
            violation_reason: dev.violation || item.auto_note || item.summary_text || item.notes || '',
            auto: true
          });
        });
        ensureMeasurementState(item).forEach(function (row, mIdx) {
          syncMeasurementDefaults(item);
          if (!row.seizure_ref && !row.reference) return;
          addRow({
            seizure_ref: row.seizure_ref || row.reference,
            source_key: (item.key || ('finding-' + idx)) + ':measure:' + mIdx,
            type: 'Lengdemåling',
            quantity: '1',
            position: row.position || currentCoordText(),
            description: item.label || 'Lengdemåling',
            law_text: lawText,
            violation_reason: row.violation_text || row.delta_text || item.auto_note || '',
            auto: true
          });
        });
      });
      return rows;
    }


    function syncSeizureReportsFromDom() {
      if (!seizureReportList) return;
      var cards = Array.prototype.slice.call(seizureReportList.querySelectorAll('[data-seizure-index]'));
      if (!cards.length) {
        if (seizureReportsInput) seizureReportsInput.value = JSON.stringify(seizureReportsState || []);
        return;
      }
      seizureReportsState = cards.map(function (card) {
        function val(sel) { var el = card.querySelector(sel); return el ? String(el.value || '').trim() : ''; }
        var idx = Number(card.getAttribute('data-seizure-index') || 0);
        var prev = seizureReportsState[idx] || {};
        return {
          seizure_ref: val('.seizure-ref') || prev.seizure_ref || '',
          type: val('.seizure-type') || prev.type || '',
          quantity: val('.seizure-quantity') || prev.quantity || '',
          position: val('.seizure-position') || prev.position || '',
          description: val('.seizure-description') || prev.description || '',
          law_text: val('.seizure-law') || prev.law_text || '',
          violation_reason: val('.seizure-reason') || prev.violation_reason || '',
          source_key: prev.source_key || '',
          auto: !!prev.auto
        };
      });
      if (seizureReportsInput) seizureReportsInput.value = JSON.stringify(seizureReportsState || []);
    }

    function mergeSeizureReportsWithDefaults() {
      var existing = Array.isArray(seizureReportsState) ? seizureReportsState.slice() : [];
      var byKey = {};
      existing.forEach(function (row) { if (row && (row.source_key || row.seizure_ref)) byKey[String(row.source_key || row.seizure_ref)] = row; });
      defaultSeizureRowsFromFindings().forEach(function (row) {
        var key = String(row.source_key || row.seizure_ref || '');
        if (!byKey[key]) {
          existing.push(row);
          byKey[key] = row;
        }
      });
      seizureReportsState = existing;
      if (seizureReportsInput) seizureReportsInput.value = JSON.stringify(seizureReportsState || []);
    }

    function renderSeizureReports(options) {
      options = options || {};
      if (!seizureReportList) return;
      if (options.mergeDefaults) mergeSeizureReportsWithDefaults();
      if (!seizureReportsState || !seizureReportsState.length) {
        seizureReportList.innerHTML = '<div class="callout">Ingen beslag eller avviksrader generert ennå.</div>';
        if (seizureReportsInput) seizureReportsInput.value = JSON.stringify([]);
        return;
      }
      seizureReportList.innerHTML = seizureReportsState.map(function (row, idx) {
        var linked = (evidenceState || []).filter(function (ev) { return String(ev.seizure_ref || '').trim() && String(ev.seizure_ref || '').trim() === String(row.seizure_ref || '').trim(); });
        return [
          '<article class="seizure-report-card" data-seizure-index="' + idx + '">',
          '<div class="seizure-report-head"><strong>Beslag ' + escapeHtml(row.seizure_ref || ('B' + String(idx + 1).padStart(2, '0'))) + '</strong><button type="button" class="btn btn-danger btn-small" data-seizure-remove="' + idx + '">Fjern</button></div>',
          '<div class="grid-two compact-grid-form">',
          '<label><span>Beslagsnummer</span><input class="seizure-ref" value="' + escapeHtml(row.seizure_ref || '') + '" /></label>',
          '<label><span>Type</span><input class="seizure-type" value="' + escapeHtml(row.type || '') + '" /></label>',
          '<label><span>Antall</span><input class="seizure-quantity" value="' + escapeHtml(row.quantity || '') + '" /></label>',
          '<label><span>Posisjon knyttet til beslag</span><input class="seizure-position" value="' + escapeHtml(row.position || '') + '" /></label>',
          '<label class="span-2"><span>Lovgrunnlag / kontrollpunkt</span><input class="seizure-law" value="' + escapeHtml(row.law_text || '') + '" /></label>',
          '<label class="span-2"><span>Beskrivelse</span><textarea class="seizure-description" rows="3">' + escapeHtml(row.description || '') + '</textarea></label>',
          '<label class="span-2"><span>Lovbrudd / vurdering</span><textarea class="seizure-reason" rows="3">' + escapeHtml(row.violation_reason || '') + '</textarea></label>',
          '</div>',
          linked.length ? '<div class="small muted margin-top-s">Tilknyttede bilder: ' + escapeHtml(linked.map(function (ev) { return ev.caption || ev.original_filename || ('bilde ' + ev.id); }).join(', ')) + '</div>' : '<div class="small muted margin-top-s">Ingen bilder med dette beslagsnummeret er koblet ennå.</div>',
          '</article>'
        ].join('');
      }).join('');
      Array.prototype.forEach.call(seizureReportList.querySelectorAll('input,textarea'), function (el) {
        el.addEventListener('input', function () { syncSeizureReportsFromDom(); scheduleAutosave('Beslagsrapport oppdatert'); });
      });
      Array.prototype.forEach.call(seizureReportList.querySelectorAll('[data-seizure-remove]'), function (btn) {
        btn.addEventListener('click', function () { var idx = Number(btn.getAttribute('data-seizure-remove')); seizureReportsState.splice(idx, 1); renderSeizureReports(); scheduleAutosave('Beslag fjernet'); });
      });
      if (seizureReportsInput) seizureReportsInput.value = JSON.stringify(seizureReportsState || []);
    }

    if (btnRefreshSeizureReport) btnRefreshSeizureReport.addEventListener('click', function () { mergeSeizureReportsWithDefaults(); renderSeizureReports(); scheduleAutosave('Beslagsrapport oppdatert'); });
    if (btnAddSeizureReport) btnAddSeizureReport.addEventListener('click', function () { seizureReportsState.push({ seizure_ref: formatSeizureRef(nextSeizureSequence()), type: 'Manuelt beslag', quantity: '1', position: currentCoordText(), description: '', law_text: '', violation_reason: '', auto: false }); renderSeizureReports(); scheduleAutosave('Manuelt beslag lagt til'); });

    function appendQueryValue(params, key, value) {
      var raw = String(value == null ? '' : value).trim();
      if (!raw) return;
      params.set(key, raw);
    }

    function appendOptionalNumberQuery(params, key, value) {
      var raw = String(value == null ? '' : value).trim().replace(',', '.');
      if (!raw) return;
      var parsed = Number(raw);
      if (!isFinite(parsed)) return;
      params.set(key, String(parsed));
    }

    function makeClientRuleItem(key, label, lawName, section, lawText, helpText) {
      return {
        key: key,
        label: label,
        status: 'ikke kontrollert',
        notes: '',
        source_name: lawName || 'Lokal kontrollpunktliste',
        source_ref: section || 'Fallback',
        law_name: lawName || 'Lokal kontrollpunktliste',
        section: section || 'Fallback',
        law_text: lawText || helpText || label,
        summary_text: label,
        help_text: helpText || lawText || label
      };
    }

    function clientFallbackRuleBundle(reason) {
      var controlVal = String(controlType && controlType.value || 'Fritidsfiske').trim() || 'Fritidsfiske';
      var speciesVal = String((species && species.value) || (fisheryType && fisheryType.value) || '').trim();
      var gearVal = String(gearType && gearType.value || '').trim();
      var speciesNorm = speciesVal.toLowerCase();
      var gearNorm = gearVal.toLowerCase();
      var items = [];
      function add(key, label, law, section, lawText, helpText) {
        if (items.some(function (row) { return row.key === key; })) return;
        items.push(makeClientRuleItem(key, label, law, section, lawText, helpText));
      }
      add('generell_posisjon_omrade', 'Posisjon og områderegulering', 'Kartgrunnlag / gjeldende regelverk', 'Områdesjekk', 'Kontroller om kontrollposisjonen ligger i fredningsområde, stengt felt, nullfiskeområde eller annen regulert sone.', 'Bruk verneområdekartet og posisjonssjekken. Registrer avvik dersom valgt art/redskap ikke er tillatt i området.');
      add('generell_merking', 'Merking av redskap', 'Høstingsforskriften', 'Merkekrav', 'Kontroller at redskap/vak/blåse er merket slik regelverket krever for valgt fiskeri.', 'Sjekk navn/adresse, deltakernummer, fiskerimerke, kallesignal eller annen påkrevd identifikasjon.');
      if (gearNorm.indexOf('teine') !== -1 || speciesNorm.indexOf('hummer') !== -1 || speciesNorm.indexOf('krabbe') !== -1) {
        add('generell_teine_utforming', 'Utforming av teine/redskap', 'Høstingsforskriften', 'Redskapskrav', 'Kontroller fluktåpninger, rømmingshull/råtnetråd, antall redskap og at redskapet er egnet/lovlig for valgt art.', 'Registrer hvert beslag/redskap separat dersom flere teiner kontrolleres.');
      }
      if (speciesNorm.indexOf('hummer') !== -1) {
        add('hummer_pamelding_merking_fallback', 'Hummer: påmelding, merking og deltakernummer', 'Forskrift om høsting av hummer', 'Påmelding og merking', 'Kontroller påmelding, deltakernummer, merking av vak/blåse og eventuell fartøysmerking.', 'Deltakernummer hører i hummerfeltet. Merke-ID/vak/blåse skal i merke-ID-feltet.');
        add('hummer_flukt_ratentrad_fallback', 'Hummer: fluktåpning og rømmingshull', 'Forskrift om høsting av hummer', 'Fangstredskap', 'Kontroller at hummerteiner har påbudte fluktåpninger og rømmingshull med biologisk nedbrytbar tråd.', 'Ved avvik: legg til redskap/beslag og bilde av aktuell teine.');
        add('hummer_periode_minstemal_fallback', 'Hummer: periode, minstemål og fredning', 'Forskrift om høsting av hummer', 'Fredningstid / minstemål', 'Kontroller dato, fangstperiode, minstemål/maksimalmål der dette gjelder, rognhummer og eventuelle fredningsområder.', 'Automatiske områdeavvik fra kart skal vurderes sammen med dette punktet.');
      }
      if (gearNorm.indexOf('garn') !== -1) {
        add('garn_merking_utforming_fallback', 'Garn: merking, maskevidde og lovlig bruk', 'Høstingsforskriften', 'Garnredskap', 'Kontroller merking, maskevidde, nedsenking, posisjon og om garnfiske er tillatt for valgt art og område.', 'Ved avvik: dokumenter måling, posisjon og bilde.');
      }
      if (gearNorm.indexOf('ruse') !== -1) {
        add('ruse_forbud_fallback', 'Ruse: forbudsperiode og merking', 'Høstingsforskriften', 'Ruse', 'Kontroller om ruse er tillatt i området og perioden, og om redskapet er korrekt merket.', 'Ved avvik: legg til redskap/beslag.');
      }
      if (!items.length) {
        add('generell_kontrollpunktliste', 'Generell kontroll av valgt fiskeri/redskap', 'Gjeldende lov og forskrift', 'Generell kontroll', 'Kontroller valgt fiske/fangst, redskap, merking og posisjon mot gjeldende lov, forskrift og J-meldinger.', 'Velg kontrolltype, art/fiskeri og redskap for mer presise kontrollpunkter.');
      }
      return {
        title: 'Kontrollpunkter' + (speciesVal || gearVal ? ' for ' + [controlVal, speciesVal, gearVal].filter(Boolean).join(' / ') : ''),
        description: reason || 'Lokal kontrollpunktliste brukes slik at punktene vises også ved tregt eller tomt regeloppslag.',
        items: items,
        sources: [{ name: 'Lokal kontrollpunktliste', ref: '1.8.7 fallback', url: '' }]
      };
    }

    function applyRuleBundle(bundle, options) {
      options = options || {};
      bundle = bundle || clientFallbackRuleBundle('Lokal kontrollpunktliste.');
      if (!Array.isArray(bundle.items) || !bundle.items.length) {
        bundle = clientFallbackRuleBundle('Regeloppslaget ga ingen punkter. Lokal kontrollpunktliste vises i stedet.');
      }
      metaBox.innerHTML = '<strong>' + escapeHtml(bundle.title || 'Kontrollpunkter') + '</strong><div class="small muted">' + escapeHtml(bundle.description || '') + '</div>';
      var currentByKey = {};
      findingsState.forEach(function (item) { if (item && item.key) currentByKey[item.key] = item; });
      findingsState = (bundle.items || []).map(function (item) {
        var current = resolveCurrentFinding(item, currentByKey) || {};
        return Object.assign({}, item, current, { status: current.status || item.status || 'ikke kontrollert', notes: current.notes || item.notes || '' });
      });
      renderFindings();
      sourcesState = bundle.sources || [];
      if (sourcesInput) sourcesInput.value = JSON.stringify(sourcesState);
      if (sourceList) sourceList.innerHTML = sourcesState.map(sourceChip).join('');
    }

    function loadRules() {
      var speciesVal = species.value || fisheryType.value || '';
      if (!controlType.value && (speciesVal || gearType.value)) {
        // Fritidsfiske er trygg standard for art/redskap dersom kontrolltype ikke er satt ennå.
        controlType.value = 'Fritidsfiske';
      }
      if (!controlType.value && !speciesVal && !gearType.value) {
        applyRuleBundle(clientFallbackRuleBundle('Velg kontrolltype, art/fiskeri og redskap for mer presise kontrollpunkter.'));
        return;
      }
      var params = new URLSearchParams();
      appendQueryValue(params, 'control_type', controlType.value || 'Fritidsfiske');
      appendQueryValue(params, 'species', speciesVal);
      appendQueryValue(params, 'gear_type', gearType.value);
      appendQueryValue(params, 'area_status', areaStatus.value || '');
      appendQueryValue(params, 'area_name', areaName.value || '');
      appendQueryValue(params, 'area_notes', zoneResult ? (zoneResult.textContent || '') : '');
      appendQueryValue(params, 'control_date', startTime.value || '');
      appendOptionalNumberQuery(params, 'lat', latitude.value || '');
      appendOptionalNumberQuery(params, 'lng', longitude.value || '');
      metaBox.innerHTML = 'Henter lovpunkter ...';
      fetch(root.dataset.rulesUrl + '?' + params.toString())
        .then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (payload) {
            if (!r.ok) {
              var detail = payload && payload.detail ? payload.detail : '';
              if (Array.isArray(detail)) detail = detail.map(function (row) { return row && row.msg ? row.msg : ''; }).filter(Boolean).join(' ');
              throw new Error(detail || 'Kunne ikke hente kontrollpunkter akkurat nå.');
            }
            return payload;
          });
        })
        .then(function (bundle) {
          applyRuleBundle(bundle);
        })
        .catch(function (error) {
          applyRuleBundle(clientFallbackRuleBundle('Kunne ikke hente lovpunkter akkurat nå. Lokal kontrollpunktliste vises i stedet.' + (error && error.message ? ' ' + error.message : '')));
        });
    }

    function resetSelectedFinding() {
      evidenceFindingKey.value = '';
      evidenceLawText.value = '';
      if (evidenceSeizureRef) evidenceSeizureRef.value = '';
      selectedFindingCard.innerHTML = 'Velg avvik for bilde.';
    }

    function updateSelectedFinding(item, deviationRow, options) {
      options = options || {};
      if (!item) {
        resetSelectedFinding();
        return;
      }
      deviationRow = deviationRow || null;
      evidenceFindingKey.value = item.key || '';
      evidenceLawText.value = item.law_text || item.help_text || '';
      if (evidenceSeizureRef) evidenceSeizureRef.value = deviationRow && deviationRow.seizure_ref ? deviationRow.seizure_ref : '';
      if (!evidenceCaption.value) evidenceCaption.value = deviationRow && deviationRow.violation ? deviationRow.violation : (item.label || item.key || '');
      if (!evidenceReason.value) evidenceReason.value = deviationRow && deviationRow.violation ? deviationRow.violation : (item.notes || item.auto_note || '');
      var ref = deviationRow && deviationRow.seizure_ref ? deviationRow.seizure_ref : '';
      var text = ref ? ('Bilde kobles til beslag ' + ref + '.') : 'Bilde kobles til valgt avvik.';
      selectedFindingCard.innerHTML = escapeHtml(text);
      if (options.showStepFive !== false) showStep(5, { scroll: true });
    }

    function currentInlineEvidenceTarget() {
      if (!selectedInlineEvidenceTarget) return null;
      var matchItem = null;
      var matchRow = null;
      findingsState.forEach(function (item) {
        if (matchItem) return;
        if (String(item.key || '') !== String(selectedInlineEvidenceTarget.finding_key || '')) return;
        ensureDeviationState(item).forEach(function (row) {
          if (matchRow) return;
          if (String(row.seizure_ref || '') === String(selectedInlineEvidenceTarget.seizure_ref || '')) {
            matchItem = item;
            matchRow = row;
          }
        });
      });
      if (!matchItem) return null;
      return { item: matchItem, row: matchRow };
    }

    function preferredDeviationRow(item) {
      var rows = ensureDeviationState(item);
      var active = null;
      rows.forEach(function (row) {
        if (!active && selectedInlineTargetMatches(item, row)) active = row;
      });
      return active || rows[0] || null;
    }

    function setInlineEvidenceTarget(item, deviationRow, feedback) {
      if (!item || !deviationRow) {
        selectedInlineEvidenceTarget = null;
        inlineEvidenceFeedback = feedback || '';
        updateSelectedFinding(null, null, { showStepFive: false });
        renderFindings();
        return;
      }
      selectedInlineEvidenceTarget = {
        finding_key: item.key || '',
        seizure_ref: deviationRow.seizure_ref || '',
      };
      inlineEvidenceFeedback = feedback || '';
      evidenceCaption.value = deviationRow.violation || item.label || item.key || '';
      evidenceReason.value = deviationRow.violation || item.notes || item.auto_note || '';
      updateSelectedFinding(item, deviationRow, { showStepFive: false });
      renderFindings();
      flashActiveDeviationRow();
    }

    function flashActiveDeviationRow() {
      window.setTimeout(function () {
        var row = findingsList ? findingsList.querySelector('.deviation-row-selected') : null;
        if (!row && findingsList) row = findingsList.querySelector('.finding-card .deviation-row:not([hidden])');
        if (!row) return;
        row.classList.add('deviation-row-flash');
        try { row.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (e) { try { row.scrollIntoView(); } catch (ignore) {} }
        window.setTimeout(function () { row.classList.remove('deviation-row-flash'); }, 1600);
      }, 0);
    }

    function setInlineEvidenceFeedback(message) {
      inlineEvidenceFeedback = message || '';
      renderFindings();
    }

    function buildEvidenceCardHtml(entry) {
      var isLocal = !!(entry && entry.local_pending);
      var statusLine = '';
      if (isLocal) {
        var stateLabel = entry.local_sync_state === 'failed' ? 'Lokal lagring · synk feilet' : (entry.local_sync_state === 'uploading' ? 'Lokal lagring · synker nå' : 'Lokal lagring · ikke synket ennå');
        statusLine = '<div class="muted small evidence-local-state">' + escapeHtml(stateLabel) + (entry.local_error ? ' · ' + escapeHtml(entry.local_error) : '') + '</div>';
      }
      return [
        '<article class="evidence-card' + (isLocal ? ' evidence-card-local' : '') + '" data-evidence-id="' + escapeHtml(String(entry.id || '')) + '">',
        '<img src="' + escapeHtml(evidenceFileUrl(entry)) + '" alt="' + escapeHtml(entry.caption || entry.original_filename || 'Bildebevis') + '" />',
        '<div class="evidence-body">',
        '<strong>' + escapeHtml(entry.caption || entry.original_filename || 'Bildebevis') + '</strong>',
        statusLine,
        (entry.finding_key ? '<div class="muted small">Kontrollpunkt: ' + escapeHtml(entry.finding_key) + '</div>' : ''),
        (entry.seizure_ref ? '<div class="muted small">Beslag / referanse: ' + escapeHtml(entry.seizure_ref) + '</div>' : ''),
        (entry.violation_reason ? '<div class="muted small">Begrunnelse: ' + escapeHtml(entry.violation_reason) + '</div>' : ''),
        (entry.law_text ? '<div class="muted small">Hjemmel: ' + escapeHtml(entry.law_text) + '</div>' : ''),
        '<div class="actions-row wrap margin-top-s">',
        (isLocal
          ? '<button class="btn btn-secondary btn-small" type="button" data-local-sync="' + escapeHtml(String(entry.id || '')) + '">Synk nå</button><button class="btn btn-danger btn-small" type="button" data-local-delete="' + escapeHtml(String(entry.id || '')) + '">Fjern lokalt</button>'
          : '<form method="post" action="/evidence/' + escapeHtml(String(entry.id || '')) + '/delete" data-confirm="Slette vedlegg?">' + csrfFieldHtml() + '<button class="btn btn-danger btn-small" type="submit">Slett</button></form>'),
        '</div>',
        '</div>',
        '</article>'
      ].join('');
    }

    function appendEvidenceCard(entry) {
      if (!evidenceGrid || !entry || !evidenceIsImage(entry)) return;
      removeEvidenceCard(entry.id);
      evidenceGrid.insertAdjacentHTML('afterbegin', buildEvidenceCardHtml(entry));
      if (Common.appendCsrfToForms) Common.appendCsrfToForms(evidenceGrid);
    }

    function resetOcrSelectedFile() {
      selectedOcrFile = null;
      preparedOcrFileCache = {};
      if (!ocrSelectedFileBox) return;
      ocrSelectedFileBox.classList.add('hidden');
      ocrSelectedFileBox.innerHTML = 'Ingen bildefil valgt ennå.';
    }

    function setSelectedOcrFile(file, label) {
      selectedOcrFile = file || null;
      preparedOcrFileCache = {};
      if (!ocrSelectedFileBox) return;
      if (!file) {
        resetOcrSelectedFile();
        return;
      }
      ocrSelectedFileBox.classList.remove('hidden');
      ocrSelectedFileBox.innerHTML = '<strong>Valgt bildefil:</strong> ' + escapeHtml(file.name || 'kamerabilde.jpg') + '<div class="small muted">' + escapeHtml(label || 'Klar for OCR og automatisk søk.') + '</div>';
    }

    function normalizeOcrText(value) {
      return String(value || '')
        .replace(/\r/g, '\n')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .replace(/[ \t]{2,}/g, ' ')
        .trim();
    }

    function scoreOcrText(value) {
      var text = normalizeOcrText(value);
      if (!text) return 0;
      var alphaNum = (text.match(/[A-Za-zÆØÅæøå0-9]/g) || []).length;
      var lines = text.split(/\n+/).filter(Boolean).length;
      return alphaNum * 4 + Math.min(text.length, 400) + Math.min(lines, 8) * 6;
    }

    function shortOcrPreview(text) {
      var clean = normalizeOcrText(text).replace(/\n+/g, ' • ');
      if (clean.length > 220) return clean.slice(0, 217) + '...';
      return clean;
    }

    function loadImageForOcr(file) {
      return new Promise(function (resolve, reject) {
        var url = URL.createObjectURL(file);
        var image = new Image();
        image.onload = function () {
          URL.revokeObjectURL(url);
          resolve(image);
        };
        image.onerror = function () {
          URL.revokeObjectURL(url);
          reject(new Error('Kunne ikke lese bildefilen i nettleseren.'));
        };
        image.src = url;
      });
    }

    function preprocessImageForOcr(file, mode) {
      return loadImageForOcr(file).then(function (image) {
        var uploadMobile = mode === 'upload-mobile';
        var serverHighRes = mode === 'server-highres';
        var maxSide = serverHighRes ? 2400 : (uploadMobile ? 1600 : (mode === 'document' ? 1800 : 1800));
        var quality = serverHighRes ? 0.92 : (uploadMobile ? 0.84 : (mode === 'document' ? 0.88 : 0.9));
        var longest = Math.max(image.naturalWidth || image.width || 1, image.naturalHeight || image.height || 1);
        var scale = longest > maxSide ? maxSide / longest : 1;
        var width = Math.max(1, Math.round((image.naturalWidth || image.width || 1) * scale));
        var height = Math.max(1, Math.round((image.naturalHeight || image.height || 1) * scale));
        var canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        var ctx = canvas.getContext('2d', { willReadFrequently: true });
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(image, 0, 0, width, height);
        var imageData = ctx.getImageData(0, 0, width, height);
        var data = imageData.data;
        for (var i = 0; i < data.length; i += 4) {
          var gray = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
          gray = (gray - 128) * (serverHighRes ? 1.28 : (uploadMobile ? 1.22 : 1.35)) + 128;
          if (mode === 'threshold') gray = gray > 162 ? 255 : 0;
          else if (mode === 'document' || uploadMobile || serverHighRes) gray = Math.max(0, Math.min(255, gray * (serverHighRes ? 1.05 : 1.08)));
          gray = Math.max(0, Math.min(255, gray));
          data[i] = gray;
          data[i + 1] = gray;
          data[i + 2] = gray;
          data[i + 3] = 255;
        }
        ctx.putImageData(imageData, 0, 0);
        return new Promise(function (resolve, reject) {
          canvas.toBlob(function (blob) {
            if (!blob) {
              reject(new Error('Kunne ikke forberede bilde for OCR.'));
              return;
            }
            resolve(blob);
          }, 'image/jpeg', quality);
        });
      });
    }

    function fileSignature(file) {
      return [file && file.name || '', file && file.size || 0, file && file.lastModified || 0].join('|');
    }

    var OCR_SERVER_TIMEOUT_MS = 60000;
    var OCR_ORIGINAL_MAX_BYTES = 12 * 1024 * 1024;
    var ocrResultCache = Object.create(null);

    function buildOcrUploadFile(file, mode) {
      mode = mode || 'original';
      if (!file) return Promise.reject(new Error('Bildefilen mangler.'));
      if (mode === 'original') return Promise.resolve(file);
      var ua = navigator.userAgent || '';
      var touchPoints = Number(navigator.maxTouchPoints || 0);
      var isAppleMobile = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && touchPoints > 1);
      var processMode = mode === 'server-highres' ? 'server-highres' : (isAppleMobile ? 'upload-mobile' : 'document');
      return preprocessImageForOcr(file, processMode).then(function (blob) {
        var suffix = mode === 'server-highres' ? '-ocr-hires.jpg' : '-ocr.jpg';
        return new File([blob], (String(file.name || 'ocr').replace(/\.[^.]+$/, '') || 'ocr') + suffix, { type: 'image/jpeg', lastModified: Date.now() });
      }).catch(function (err) {
        if (mode !== 'original') return Promise.reject(err || new Error('Kunne ikke optimalisere bildet for OCR.'));
        return file;
      });
    }

    function prefersServerOcrFirst(file) {
      var ua = navigator.userAgent || '';
      var touchPoints = Number(navigator.maxTouchPoints || 0);
      var isAppleMobile = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && touchPoints > 1);
      var isSafari = /^((?!chrome|android).)*safari/i.test(ua);
      var fileType = String(file && file.type || '').toLowerCase();
      var fileName = String(file && file.name || '').toLowerCase();
      var isHeic = /heic|heif/.test(fileType) || /\.(heic|heif)$/.test(fileName);
      var isLarge = Number(file && file.size || 0) > (4 * 1024 * 1024);
      return !!(isHeic || (isAppleMobile && isSafari) || isLarge);
    }

    function shouldAvoidAutomaticBrowserOcr(file) {
      var ua = navigator.userAgent || '';
      var touchPoints = Number(navigator.maxTouchPoints || 0);
      var isAppleMobile = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && touchPoints > 1);
      var isSafari = /^((?!chrome|android).)*safari/i.test(ua);
      var isSmallScreen = false;
      try {
        isSmallScreen = !!(window.matchMedia && window.matchMedia('(max-width: 960px)').matches);
      } catch (e) {}
      return !!(isAppleMobile || (isSafari && isSmallScreen));
    }

    function shouldUseXhrOcrUpload(file) {
      var ua = navigator.userAgent || '';
      var touchPoints = Number(navigator.maxTouchPoints || 0);
      var isAppleMobile = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && touchPoints > 1);
      var isSafari = /^((?!chrome|android).)*safari/i.test(ua);
      var isLarge = Number(file && file.size || 0) > (2 * 1024 * 1024);
      return !!(isAppleMobile || isSafari || isLarge);
    }

    function postFormDataJson(url, formData, options) {
      options = options || {};
      var timeoutMs = Math.max(8000, Number(options.timeoutMs || 45000));
      var onProgress = typeof options.onProgress === 'function' ? options.onProgress : null;
      if (!(options.useXhr === true) || typeof XMLHttpRequest === 'undefined') {
        var controller = typeof AbortController === 'function' ? new AbortController() : null;
        var timer = controller ? setTimeout(function () { try { controller.abort(); } catch (e) {} }, timeoutMs) : null;
        return fetch(url, Object.assign(secureFetchOptions({ method: 'POST', body: formData }), controller ? { signal: controller.signal } : {}))
          .then(function (response) {
            return response.text().catch(function () { return ''; }).then(function (payloadText) {
              var payload = {};
              try { payload = JSON.parse(payloadText || '{}'); } catch (e) { payload = {}; }
              return { ok: response.ok, status: response.status, payload: payload };
            });
          })
          .catch(function (err) {
            if (err && err.name === 'AbortError') throw new Error('Server-OCR brukte for lang tid.');
            throw err;
          })
          .finally(function () { if (timer) clearTimeout(timer); });
      }
      return new Promise(function (resolve, reject) {
        var xhr = new XMLHttpRequest();
        xhr.open('POST', url, true);
        xhr.withCredentials = true;
        xhr.timeout = timeoutMs;
        try {
          var headers = csrfHeaders();
          if (headers && typeof headers.forEach === 'function') {
            headers.forEach(function (value, key) {
              xhr.setRequestHeader(key, value);
            });
          } else {
            var token = csrfToken();
            if (token) xhr.setRequestHeader('X-CSRF-Token', token);
          }
        } catch (e) {}
        if (xhr.upload && onProgress) {
          xhr.upload.onprogress = function (event) {
            if (!event || !event.lengthComputable) return;
            try { onProgress(event.loaded, event.total); } catch (e) {}
          };
        }
        xhr.onload = function () {
          var payload = {};
          try { payload = JSON.parse(xhr.responseText || '{}'); } catch (e) { payload = {}; }
          resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, payload: payload });
        };
        xhr.onerror = function () { reject(new Error('Kunne ikke laste opp bildet til server-OCR.')); };
        xhr.onabort = function () { reject(new Error('Server-OCR ble avbrutt.')); };
        xhr.ontimeout = function () { reject(new Error('Server-OCR brukte for lang tid.')); };
        xhr.send(formData);
      });
    }

    function uploadOcrSourceImage(file, recognizedText) {
      if (!file || !root || !root.dataset.caseId) return Promise.resolve(null);
      var signature = fileSignature(file);
      if (signature && signature === lastOcrEvidenceSignature) return Promise.resolve(null);
      var preview = shortOcrPreview(recognizedText || '');
      return queueLocalEvidenceUpload(file, {
        caption: preview ? ('OCR-kilde - ' + preview) : 'OCR-kilde',
        finding_key: '',
        law_text: '',
        violation_reason: '',
        seizure_ref: ''
      }, {
        sourceKind: 'ocr',
        signature: signature,
        statusMessage: 'OCR-bilde lagret lokalt.',
        autosaveMessage: 'OCR-bilde lagret lokalt',
        autoSync: false
      }).catch(function () { return null; });
    }

    function runServerOcr(file) {
      var originalKey = fileSignature(file);
      if (originalKey && ocrResultCache[originalKey]) {
        if (registryResult) registryResult.innerHTML = 'Bruker nylig OCR-resultat for samme bilde.';
        return Promise.resolve(Object.assign({}, ocrResultCache[originalKey], { strategy: (ocrResultCache[originalKey].strategy || 'server') + ' - hurtigbuffer' }));
      }
      function fileAttemptKey(uploadFile) {
        return [uploadFile && uploadFile.name || '', uploadFile && uploadFile.size || 0, uploadFile && uploadFile.type || ''].join('|');
      }

      function sendAttempt(uploadFile, label) {
        if (registryResult) registryResult.innerHTML = 'Sender bildet til server-OCR (' + escapeHtml(label) + ') ...';
        var formData = new FormData();
        formData.append('file', uploadFile, uploadFile.name || ('ocr-' + Date.now() + '.jpg'));
        return postFormDataJson('/api/ocr/extract', formData, {
          useXhr: shouldUseXhrOcrUpload(uploadFile),
          timeoutMs: OCR_SERVER_TIMEOUT_MS,
          onProgress: function (loaded, total) {
            if (!registryResult || !total) return;
            var pct = Math.max(1, Math.min(100, Math.round((loaded / total) * 100)));
            registryResult.innerHTML = 'Laster opp bildet til server-OCR (' + escapeHtml(label) + ') ...<div class="small muted">' + pct + '%</div>';
          }
        }).then(function (result) {
          var normalizedText = normalizeOcrText(result && result.payload ? (result.payload.text || '') : '');
          if (!result.ok || !result.payload || !normalizedText) {
            throw new Error((result.payload && (result.payload.detail || result.payload.message)) || 'Server-OCR ga ikke lesbar tekst.');
          }
          var rawText = normalizeOcrText(result.payload.raw_text || normalizedText);
          return {
            text: normalizedText,
            raw_text: rawText,
            strategy: (result.payload.strategy || 'server') + ' - ' + label,
            source: 'server',
            hints: (result.payload && result.payload.hints) || extractLookupHintsFromText(rawText || normalizedText),
            elapsed_ms: result.payload.elapsed_ms || null,
            cached: !!result.payload.cached
          };
        });
      }

      if (registryResult) registryResult.innerHTML = 'Forbereder bildet for server-OCR ...';
      var seen = {};
      var mobileFirst = shouldUseXhrOcrUpload(file) || prefersServerOcrFirst(file);
      var originalAllowed = Number(file && file.size || 0) > 0 && Number(file && file.size || 0) <= OCR_ORIGINAL_MAX_BYTES;
      var attempts = [];
      if (mobileFirst) {
        attempts.push(function () { return buildOcrUploadFile(file, 'document').then(function (uploadFile) { return { file: uploadFile, label: 'optimalisert mobilbilde' }; }); });
        attempts.push(function () { return buildOcrUploadFile(file, 'server-highres').then(function (uploadFile) { return { file: uploadFile, label: 'forbedret original' }; }); });
        if (originalAllowed) attempts.push(function () { return Promise.resolve({ file: file, label: 'originalbilde' }); });
      } else {
        if (originalAllowed) attempts.push(function () { return Promise.resolve({ file: file, label: 'originalbilde' }); });
        attempts.push(function () { return buildOcrUploadFile(file, 'server-highres').then(function (uploadFile) { return { file: uploadFile, label: 'forbedret original' }; }); });
        attempts.push(function () { return buildOcrUploadFile(file, 'document').then(function (uploadFile) { return { file: uploadFile, label: 'dokumentmodus' }; }); });
      }

      function nextAttempt(index, lastError) {
        if (index >= attempts.length) return Promise.reject(lastError || new Error('Server-OCR ga ikke lesbar tekst.'));
        return attempts[index]().then(function (candidate) {
          if (!candidate || !candidate.file) return nextAttempt(index + 1, lastError);
          if (String(candidate.label || '') === 'originalbilde' && !originalAllowed) return nextAttempt(index + 1, lastError);
          var key = fileAttemptKey(candidate.file);
          if (seen[key]) return nextAttempt(index + 1, lastError);
          seen[key] = true;
          return sendAttempt(candidate.file, candidate.label).catch(function (err) {
            var msg = String(err && err.message || err || '').toLowerCase();
            if (msg.indexOf('for lang tid') !== -1 || msg.indexOf('for stort') !== -1) {
              if (err && typeof err === 'object') err._stopOcrRetry = true;
              return Promise.reject(err);
            }
            return nextAttempt(index + 1, err);
          });
        }).catch(function (err) {
          if (err && err._stopOcrRetry) return Promise.reject(err);
          return nextAttempt(index + 1, err || lastError);
        });
      }

      return nextAttempt(0, null).then(function (result) {
        if (originalKey && result && result.text) ocrResultCache[originalKey] = Object.assign({}, result);
        return result;
      });
    }


    function runBrowserOcr(file) {
      var attempts = [];
      return Promise.allSettled([
        preprocessImageForOcr(file, 'document'),
        preprocessImageForOcr(file, 'threshold')
      ]).then(function (variantResults) {
        var preparedA = variantResults[0].status === 'fulfilled' ? variantResults[0].value : file;
        var preparedB = variantResults[1].status === 'fulfilled' ? variantResults[1].value : preparedA;
        return ensureTesseract().then(function (Tesseract) {
          function recognizeAttempt(source, label, pageSegMode) {
            if (registryResult) registryResult.innerHTML = 'Kjører lokal OCR (' + escapeHtml(label) + ') ...';
            return Tesseract.recognize(source, 'nor+eng', {
              tessedit_pageseg_mode: pageSegMode,
              preserve_interword_spaces: '1',
              logger: function (message) {
                if (!registryResult || !message || message.status !== 'recognizing text') return;
                var pct = typeof message.progress === 'number' ? Math.round(message.progress * 100) : null;
                registryResult.innerHTML = 'Kjører lokal OCR (' + escapeHtml(label) + ') ...' + (pct !== null ? '<div class="small muted">' + pct + '%</div>' : '');
              }
            }).then(function (result) {
              attempts.push({
                text: normalizeOcrText(result && result.data ? result.data.text : ''),
                strategy: label,
                source: 'browser'
              });
            }).catch(function () {
              attempts.push({ text: '', strategy: label, source: 'browser' });
            });
          }
          return recognizeAttempt(preparedA, 'forbedret bilde', 6)
            .then(function () { return recognizeAttempt(preparedB, 'høy kontrast', 11); })
            .then(function () { return recognizeAttempt(file, 'originalfil', 6); });
        });
      }).then(function () {
        var best = attempts.sort(function (a, b) { return scoreOcrText(b.text) - scoreOcrText(a.text); })[0] || null;
        if (!best || scoreOcrText(best.text) < 18) throw new Error('Ingen tydelig tekst ble funnet i bildet.');
        best.hints = extractLookupHintsFromText(best.text || '');
        return best;
      });
    }

    function applyOcrResult(result) {
      var text = normalizeOcrText(result && result.text ? result.text : '');
      var rawText = normalizeOcrText(result && result.raw_text ? result.raw_text : '');
      var lookupPayloadText = scoreOcrText(rawText) > scoreOcrText(text) ? rawText : text;
      if (!lookupPayloadText) throw new Error('OCR ga ingen lesbar tekst.');
      var textHints = extractLookupHintsFromText(rawText || text);
      var hints = Object.assign({}, textHints, (result && result.hints) || {});
      lookupText.value = lookupPayloadText;
      if (hints) {
        applyHints(hints);
        if (hints.hummer_participant_no && !lookupIdentifier.value) lookupIdentifier.value = hints.hummer_participant_no;
        if (hints.phone && !lookupIdentifier.value) lookupIdentifier.value = hints.phone;
        if (hints.vessel_reg && !lookupIdentifier.value) lookupIdentifier.value = hints.vessel_reg;
      }
      if (registryResult) {
        var confidence = Number(result && result.confidence);
        var confidenceText = isFinite(confidence) ? (' · sikkerhet ' + Math.max(0, Math.min(100, Math.round(confidence))) + '%') : '';
        var reviewText = result && result.needs_manual_review ? '<div class="callout area-warning margin-top-s"><strong>Kontroller manuelt</strong><div>OCR er usikker. Se gjennom merkeskilt, navn/adresse og nummer før du går videre.</div></div>' : '';
        registryResult.innerHTML = '<strong>OCR fullført</strong><div class="small muted">' + escapeHtml(result.source === 'server' ? 'Server-OCR brukt' : 'Lokal OCR brukt') + ' · ' + escapeHtml(result.strategy || '') + confidenceText + '. Skjemaet er fylt fra bildet. Registeroppslag kjøres ikke automatisk.</div><div class="small muted">' + escapeHtml(shortOcrPreview(lookupPayloadText)) + '</div>' + reviewText;
      }
      var detailText = (result.strategy || 'Tekst lest fra bilde') + (result && result.needs_manual_review ? ' · kontroller manuelt' : '');
      renderAutofillPreview({ source: result.source === 'server' ? 'Server-OCR' : 'Lokal OCR', detail: detailText });
      loadGearSummary();
      scheduleAutosave('OCR-felt fylt fra bilde');
      return result;
    }

    function runOcrFromFile(file) {
      if (!file) {
        registryResult.innerHTML = 'Velg eller ta et bilde først.';
        return Promise.resolve(null);
      }
      registryResult.innerHTML = 'Forbereder bildet lokalt og starter tekstlesing ...';
      var browserOffline = typeof navigator !== 'undefined' && navigator.onLine === false;
      var useServerFirst = !browserOffline || prefersServerOcrFirst(file);
      var avoidBrowserFallback = shouldAvoidAutomaticBrowserOcr(file);
      var ocrPromise = useServerFirst
        ? (function () {
            if (registryResult) registryResult.innerHTML = 'Forbereder og sender optimalisert bilde til server-OCR ...';
            return runServerOcr(file).catch(function (error) {
              if (avoidBrowserFallback) {
                if (registryResult) registryResult.innerHTML = 'Server-OCR fant ikke tydelig tekst. Lokal OCR i mobilnettleseren hoppes over for å unngå heng. Prøv et tydeligere bilde eller last opp på nytt.';
                throw error;
              }
              if (registryResult) registryResult.innerHTML = 'Server-OCR fant ikke tydelig tekst. Prøver lokal OCR i nettleseren ...';
              return runBrowserOcr(file);
            });
          }())
        : runBrowserOcr(file).catch(function () {
            if (registryResult) registryResult.innerHTML = 'Lokal OCR fant ikke tydelig tekst. Prøver server-OCR ...';
            return runServerOcr(file);
          });
      return ocrPromise
        .then(function (result) {
          applyOcrResult(result);
          return uploadOcrSourceImage(file, result && result.text ? result.text : '').then(function () {
            if (registryResult) {
              registryResult.innerHTML += '<div class="small muted margin-top-s">OCR-bilde lokalt. Synk venter.</div>';
            }
            return result;
          });
        })
        .catch(function (err) {
          if (registryResult) registryResult.innerHTML = 'OCR feilet: ' + escapeHtml(err.message || err);
          return null;
        });
    }

    function prefersNativeCaptureInput() {
      var ua = navigator.userAgent || '';
      var touchPoints = Number(navigator.maxTouchPoints || 0);
      return /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && touchPoints > 1);
    }

    function setCameraCaptureStatus(message, isError) {
      if (!cameraCaptureStatus) return;
      cameraCaptureStatus.classList.remove('hidden');
      cameraCaptureStatus.textContent = String(message || '');
      cameraCaptureStatus.classList.toggle('alert', !!isError);
      cameraCaptureStatus.classList.toggle('alert-error', !!isError);
    }

    function stopCameraCaptureStream() {
      var stream = cameraCaptureState && cameraCaptureState.stream ? cameraCaptureState.stream : (cameraCaptureVideo && cameraCaptureVideo.srcObject ? cameraCaptureVideo.srcObject : null);
      if (stream && stream.getTracks) {
        try { stream.getTracks().forEach(function (track) { track.stop(); }); } catch (e) {}
      }
      if (cameraCaptureVideo) {
        try { cameraCaptureVideo.pause(); } catch (e) {}
        cameraCaptureVideo.srcObject = null;
      }
      if (cameraCaptureState) delete cameraCaptureState.stream;
    }

    function closeCameraCapture() {
      stopCameraCaptureStream();
      cameraCaptureState = null;
      if (cameraCaptureModal) {
        cameraCaptureModal.classList.add('hidden');
        cameraCaptureModal.setAttribute('aria-hidden', 'true');
      }
      if (cameraCaptureStatus) cameraCaptureStatus.classList.add('hidden');
    }

    function openCameraCapture(options) {
      options = options || {};
      stopCameraCaptureStream();
      var fallbackInput = options.fallbackInput || null;
      if (prefersNativeCaptureInput() && fallbackInput) {
        fallbackInput.click();
        return;
      }
      if (!cameraCaptureModal || !cameraCaptureVideo) {
        if (fallbackInput) fallbackInput.click();
        return;
      }
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (fallbackInput) fallbackInput.click();
        else setCameraCaptureStatus('Kamera støttes ikke i denne nettleseren.', true);
        return;
      }
      cameraCaptureState = {
        title: options.title || 'Kamera',
        description: options.description || 'Ta bilde direkte og bruk det videre i saken.',
        onFile: options.onFile || null,
        fallbackInput: fallbackInput,
        filenamePrefix: options.filenamePrefix || 'capture',
      };
      if (cameraCaptureTitle) cameraCaptureTitle.textContent = cameraCaptureState.title;
      if (cameraCaptureDescription) cameraCaptureDescription.textContent = cameraCaptureState.description;
      setCameraCaptureStatus('Starter kamera ...', false);
      cameraCaptureModal.classList.remove('hidden');
      cameraCaptureModal.setAttribute('aria-hidden', 'false');
      navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false }).then(function (stream) {
        if (!cameraCaptureState) {
          stream.getTracks().forEach(function (track) { track.stop(); });
          return;
        }
        cameraCaptureState.stream = stream;
        cameraCaptureVideo.srcObject = stream;
        return cameraCaptureVideo.play();
      }).then(function () {
        setCameraCaptureStatus('Kamera klart. Ta bilde når motivet er tydelig.', false);
      }).catch(function (err) {
        setCameraCaptureStatus('Kunne ikke starte kamera: ' + escapeHtml(err.message || err), true);
        if (fallbackInput) fallbackInput.click();
      });
    }

    function captureCameraFile() {
      if (!cameraCaptureState || !cameraCaptureVideo) return;
      if (!cameraCaptureVideo.videoWidth || !cameraCaptureVideo.videoHeight) {
        setCameraCaptureStatus('Kamera er ikke klart ennå. Prøv igjen om et øyeblikk.', true);
        return;
      }
      var canvas = document.createElement('canvas');
      canvas.width = cameraCaptureVideo.videoWidth;
      canvas.height = cameraCaptureVideo.videoHeight;
      var context = canvas.getContext('2d');
      context.drawImage(cameraCaptureVideo, 0, 0, canvas.width, canvas.height);
      var onFile = cameraCaptureState.onFile;
      var filenamePrefix = cameraCaptureState.filenamePrefix || 'capture';
      canvas.toBlob(function (blob) {
        if (!blob) {
          setCameraCaptureStatus('Kunne ikke lage bildefil fra kamera.', true);
          return;
        }
        var file = new File([blob], filenamePrefix + '-' + Date.now() + '.jpg', { type: 'image/jpeg' });
        closeCameraCapture();
        if (typeof onFile === 'function') onFile(file);
      }, 'image/jpeg', 0.84);
    }

    function uploadInlineEvidenceFile(file) {
      var target = currentInlineEvidenceTarget();
      if (!file) return;
      if (!target || !target.item || !target.row) {
        setInlineEvidenceFeedback('Velg først en avviksrad før bildebevis kan lagres.');
        return;
      }
      var item = target.item;
      var row = target.row;
      var captionParts = [item.label || 'Bildebevis', row.gear_kind || 'redskap', row.seizure_ref || '', row.gear_ref || ''];
      setInlineEvidenceFeedback('Lagrer bildebevis lokalt ...');
      queueLocalEvidenceUpload(file, {
        caption: captionParts.filter(Boolean).join(' - '),
        finding_key: item.key || '',
        law_text: item.law_text || item.help_text || '',
        violation_reason: row.violation || suggestedDeviationText(item),
        seizure_ref: row.seizure_ref || ''
      }, {
        sourceKind: 'inline-evidence',
        statusMessage: 'Bildebevis lokalt. Synk venter.',
        autosaveMessage: 'Bildebevis lagret lokalt'
      }).then(function (entry) {
        if (!entry) return;
        evidenceCaption.value = entry.caption || evidenceCaption.value;
        evidenceReason.value = entry.violation_reason || evidenceReason.value;
        updateSelectedFinding(item, row, { showStepFive: false });
        inlineEvidenceFeedback = 'Bildebevis lagret lokalt.';
        renderFindings();
      }).catch(function (err) {
        setInlineEvidenceFeedback(err.message || 'Kunne ikke lagre bildebevis.');
      });
    }

    function normalizeCoordinateValue(value, decimals) {
      var num = Number(String(value || '').replace(',', '.'));
      if (!isFinite(num)) return String(value || '').trim();
      return num.toFixed(decimals || 6);
    }

    function latLngToDms(latValue, lngValue) {
    var lat = Number(String(latValue || '').replace(',', '.'));
    var lon = Number(String(lngValue || '').replace(',', '.'));
    if (!isFinite(lat) || !isFinite(lon)) return '';
    function format(value, positivePrefix, negativePrefix) {
      var prefix = value >= 0 ? positivePrefix : negativePrefix;
      var abs = Math.abs(value);
      var deg = Math.floor(abs);
      var minFloat = (abs - deg) * 60;
      var min = Math.floor(minFloat);
      var sec = Math.round((minFloat - min) * 60);
      if (sec >= 60) { sec = 0; min += 1; }
      if (min >= 60) { min = 0; deg += 1; }
      return prefix + ' ' + deg + '° ' + min + "' " + sec + '"';
    }
    return format(lat, 'N', 'S') + ' ' + format(lon, 'Ø', 'V');
  }

    function currentCoordText() {
      if (!latitude || !longitude || !latitude.value || !longitude.value) return '';
      return latLngToDms(latitude.value, longitude.value) || 'DMS ikke beregnet';
    }
    window.MKCurrentCoordText = currentCoordText;

    function normalizedNearestPlaceText(result) {
      result = result || latestZoneResult || {};
      var municipality = String(result.municipality || (result.reverse_geocode && result.reverse_geocode.municipality) || '').trim();
      var locality = String(result.locality || (result.reverse_geocode && (result.reverse_geocode.locality || result.reverse_geocode.name)) || result.location_name || result.nearest_place || '').trim();
      if (locality && municipality && locality.toLowerCase().indexOf(municipality.toLowerCase()) === -1) return locality + ', ' + municipality;
      return locality || municipality || '';
    }

    function setNearestPlaceFromResult(result) {
      if (!locationName) return '';
      var label = normalizedNearestPlaceText(result);
      if (label) {
        locationName.value = label;
        try { locationName.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
      }
      return label;
    }

    function syncPositionCoordinateSummary() {
      if (!positionCoordinateSummary) return;
      var text = currentCoordText();
      if (text) {
        positionCoordinateSummary.textContent = text;
        positionCoordinateSummary.classList.remove('muted');
      } else {
        positionCoordinateSummary.textContent = 'DMS vises her når posisjon er satt.';
        positionCoordinateSummary.classList.add('muted');
      }
    }

    function currentControlDateLabel() {
      var raw = startTime && startTime.value ? startTime.value : '';
      var dt = raw ? new Date(raw) : new Date();
      if (Number.isNaN(dt.getTime())) dt = new Date();
      return dt.toLocaleString('nb-NO', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    }

    function manualPositionText() {
      if (mapState.manualPosition) return 'Manuell posisjon. Dra r\u00f8d n\u00e5l i kartet.';
      if (mapState.deviceLat !== null && mapState.deviceLng !== null) return 'GPS aktiv. R\u00f8d n\u00e5l brukes i omr\u00e5desjekk.';
      return 'Bruk GPS eller sett posisjon manuelt i kart.';
    }

    function syncManualPositionNotice() {
      syncPositionCoordinateSummary();
      if (!manualPositionStatus) return;
      manualPositionStatus.classList.remove('hidden');
      manualPositionStatus.innerHTML = manualPositionText();
    }

    function updateAreaStatusDetail(result) {
      var nearestName = normalizedNearestPlaceText(result);
      if (nearestName) setNearestPlaceFromResult(result);
      syncPositionCoordinateSummary();
      if (areaStatusDetail) {
        areaStatusDetail.classList.add('hidden');
        areaStatusDetail.innerHTML = '';
      }
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

    function updateCaseMap(options) {
      options = options || {};
      if (caseMap && caseMap._kvLeafletMap) {
        try { var _center = caseMap._kvLeafletMap.getCenter(); mapState.view = { lat: _center.lat, lng: _center.lng, zoom: caseMap._kvLeafletMap.getZoom() }; } catch (e) {}
      }
      mapState.lat = Number(latitude.value || 0);
      mapState.lng = Number(longitude.value || 0);
      mapState.draggable = true;
      mapState.allowMapMove = false;
      mapState.onMove = function (lat, lng) {
        mapState.manualPosition = false;
        mapState.showDeviceMarker = true;
        latitude.value = Number(lat).toFixed(6);
        longitude.value = Number(lng).toFixed(6);
        mapState.lat = Number(latitude.value);
        mapState.lng = Number(longitude.value);
        scheduleNearestPlaceResolve({}, 120);
        scheduleZoneCheck({}, 350);
        scheduleAutosave('Kartposisjon oppdatert');
      };
      mapState.onManualMove = function (lat, lng) {
        mapState.followAutoPosition = false;
        mapState.manualPosition = true;
        mapState.showDeviceMarker = false;
        persistPositionMode('manual');
        latitude.value = Number(lat).toFixed(6);
        longitude.value = Number(lng).toFixed(6);
        mapState.lat = Number(latitude.value);
        mapState.lng = Number(longitude.value);
        syncManualPositionNotice();
        scheduleZoneCheck({ force: true }, 250);
        scheduleAutosave('Manuell kartposisjon oppdatert');
      };
      mapState.recenterTo = options.recenterTo || '';
      mapState.recenterZoom = options.recenterZoom || null;
      if (mapState.recenterTo) mapState.lastProgrammaticRecenterTs = Date.now();
      mapState.showDeviceMarker = mapState.manualPosition !== true;
      var zoneLayerIds = zoneMatchedLayerIds(latestZoneResult);
      var displayLayers = mergeRelevantMapLayers(filteredMapCatalog(), zoneLayerIds);
      var defaultVisibleIds = defaultVisibleMapCatalog(zoneLayerIds).map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); });
      var featureDetailIds = visibleFeatureDetailLayerIds(8, zoneLayerIds);
      var allLayerIds = displayLayers.map(function (layer) { return Number(layer && layer.id); }).filter(function (value) { return isFinite(value); });
      var fisheryPortalService = root.dataset.portalMapserver || (caseMap && caseMap.dataset ? (caseMap.dataset.portalMapserver || '') : '') || 'https://portal.fiskeridir.no/server/rest/services/fiskeridirWMS_fiskeri/MapServer';
      var vernPortalService = root.dataset.portalVernMapserver || (caseMap && caseMap.dataset ? (caseMap.dataset.portalVernMapserver || '') : '') || 'https://portal.fiskeridir.no/server/rest/services/Fiskeridir_vern/MapServer';
      // 1.8.7: aktuelle verneområder/reguleringer skal vises direkte i kartet
      // når posisjonssjekken har gitt treff. Uten treff beholdes rask rastervisning.
      mapState.fetchFeatureDetails = options.fetchFeatureDetails === true || mapState.requestFeatureDetails === true || zoneLayerIds.length > 0;
      mapState.featureDetailLayerIds = featureDetailIds;
      mapState.defaultVisibleLayerIds = defaultVisibleIds;
      mapState.highlightLayerIds = zoneLayerIds.slice();
      mapState.detailFetchThresholdZoom = zoneLayerIds.length > 0 ? 0 : 13;
      mapState.enableAreaPopup = true;
      mapState.showLegend = false;
      mapState.showLayerPanel = !!mapLayerPanelHost;
      mapState.layerPanelDefaultOpen = false;
      mapState.layerPanelKey = 'case-map-1-8-7';
      mapState.layerPanelTargetSelector = mapLayerPanelHost ? '#case-map-layer-panel-host' : '';
      mapState.rasterLayerIds = allLayerIds;
      mapState.identifyLayerIds = allLayerIds;
      mapState.mapServerUrl = fisheryPortalService;
      mapState.portalFisheryService = fisheryPortalService;
      mapState.portalVernService = vernPortalService;
      mapState.rasterServicesAuto = true;
      mapState.rasterChunkSize = 32;
      mapState.rasterOpacity = 0.9;
      mapState.rasterServices = null;
      createPortalMap(caseMap, displayLayers, mapState).then(function () {
        if (options.recenterTo) {
          mapState.recenterTo = '';
          mapState.recenterZoom = null;
          mapState.autoRecenterOnce = false;
        }
        clearTimeout(mapState._offlineWarmTimer);
        scheduleOfflineRegulationWarm(1100);
        renderRelevantAreaPanel(latestZoneResult);
        syncZoneHitOverlay(latestZoneResult);
      });
      syncManualPositionNotice();
      syncMarkerPositionInputs();
    }

    function areaHitLayerIds(hit) {
      if (hit && Array.isArray(hit.layer_ids) && hit.layer_ids.length) return hit.layer_ids.slice();
      if (hit && hit.layer_id !== undefined && hit.layer_id !== null && hit.layer_id !== '') return [hit.layer_id];
      return [];
    }

    function areaHitMatchesCurrentSelection(hit) {
      hit = hit || {};
      var layerIds = areaHitLayerIds(hit);
      if (layerIds.length) {
        return layerIds.some(function (rawLayerId) {
          var resolvedLayer = layerDefinitionById(resolveCatalogLayerId(rawLayerId, hit.layer || hit.layer_name || hit.name));
          return resolvedLayer && layerMatchesCurrentSelection(resolvedLayer);
        });
      }
      var status = String(hit.status || '').trim().toLowerCase();
      if (status === 'fiskeriområde' || status === 'fiskeriomrade') return false;
      var text = normalizeSelectionText([hit.name, hit.layer, hit.description, hit.notes, hit.summary, hit.law_text, hit.source].join(' '));
      if (/svalbard/.test(text)) {
        var latNum = latitude && latitude.value ? Number(String(latitude.value).replace(',', '.')) : null;
        if (!(latNum !== null && latNum > 70)) return false;
      }
      if (!/(forbud|fredning|fredningsomrade|stengt|nullfiske|regulert|maksimalmal|forskrift|lov|j melding|j-melding|jmelding|verneomrade|begrensning)/.test(text)) return false;
      var selected = normalizeSelectionText([currentFisherySelection(), currentGearSelection(), currentControlSelection()].join(' '));
      if (!selected) return true;
      if (/hummer/.test(selected) && /hummer/.test(text)) return true;
      if (/torsk/.test(selected) && /(torsk|kysttorsk|skrei)/.test(text)) return true;
      if (/krabbe/.test(selected) && /krabbe/.test(text)) return true;
      if (currentGearSelection() && text.indexOf(normalizeSelectionText(currentGearSelection())) !== -1) return true;
      return /(stengt|nullfiske|fredning|fiskeforbud|totalforbud|forbud mot)/.test(text);
    }

    function autoAreaFindingKey(hit, index) {
      var raw = [
        hit && (hit.layer_id || (hit.layer_ids || [])[0]) || '',
        hit && (hit.name || hit.layer || hit.status || '') || '',
        hit && (hit.status || '') || '',
        hit && (hit.source || hit.database || '') || ''
      ].join('|');
      if (!raw.replace(/\|/g, '').trim()) raw = String(index || 0);
      return 'auto_area_' + hashString(raw);
    }

    function autoAreaFindingFromHit(result, hit, index) {
      hit = hit || {};
      var base = result && result.recommended_violation && result.recommended_violation.item ? Object.assign({}, result.recommended_violation.item) : {};
      var label = String(hit.name || hit.layer || base.label || result.name || 'Verneområde').trim();
      var status = String(hit.status || base.area_status || result.status || 'regulert område').trim();
      var detail = String(hit.notes || hit.summary || hit.description || hit.law_text || base.summary_text || base.notes || '').trim();
      var source = String(hit.source || hit.database || base.source_name || 'Fiskeridirektoratets kartportal').trim();
      var item = Object.assign(base, {
        key: autoAreaFindingKey(hit, index),
        auto_area_finding: true,
        status: 'avvik',
        label: label,
        area_name: label,
        area_status: status,
        source_name: source,
        source_ref: String(hit.layer || hit.layer_name || status || '').trim(),
        notes: detail || ('Kontrollstedet ligger i ' + label + '.'),
        summary_text: detail || ('Kontrollstedet ligger i ' + label + '.'),
        auto_note: 'Kontrollstedet ligger i ' + label + (status ? ' (' + status + ')' : '') + '.',
        law_text: detail || base.law_text || ''
      });
      var rows = ensureDeviationState(item);
      if (!rows.length) rows.push(defaultDeviationRow(item));
      rows[0].violation = rows[0].violation || ('Kontrollstedet ligger i ' + label + (status ? ' (' + status + ')' : '') + '.');
      rows[0].position = rows[0].position || currentCoordText();
      syncDeviationDefaults(item);
      return item;
    }

    function autoAreaFindingsFromZoneResult(result) {
      if (!result || !result.match) return [];
      var hits = Array.isArray(result.hits) ? result.hits : [];
      var rows = [];
      var seen = {};
      hits.forEach(function (hit, index) {
        if (!areaHitMatchesCurrentSelection(hit)) return;
        var key = autoAreaFindingKey(hit, index);
        if (seen[key]) return;
        seen[key] = true;
        rows.push(autoAreaFindingFromHit(result, hit, index));
      });
      if (!rows.length && result.recommended_violation && result.recommended_violation.item) {
        rows.push(autoAreaFindingFromHit(result, {
          name: result.name || result.status || 'Verneområde',
          status: result.status || 'regulert område',
          notes: result.notes || result.recommended_violation.message || '',
          source: 'områdesjekk'
        }, 0));
      }
      return rows;
    }

    var zoneResultStoragePrefix = 'kv-zone-result-1.8.7:';
    var nearestPlaceStoragePrefix = 'kv-nearest-place-1.8.7:';
    var nearestPlaceController = null;
    var nearestPlaceSequence = 0;
    var nearestPlaceTimer = null;

    function currentPlaceRequestKey(latValue, lngValue) {
      var latNum = Number(String(latValue || (latitude && latitude.value) || '').replace(',', '.'));
      var lngNum = Number(String(lngValue || (longitude && longitude.value) || '').replace(',', '.'));
      if (!isFinite(latNum) || !isFinite(lngNum)) return '';
      return latNum.toFixed(4) + ':' + lngNum.toFixed(4);
    }

    function readStoredNearestPlace(key) {
      if (!key || !window.sessionStorage) return null;
      try {
        var row = JSON.parse(sessionStorage.getItem(nearestPlaceStoragePrefix + key) || 'null');
        if (!row || !row.ts || !row.result) return null;
        if ((Date.now() - Number(row.ts)) > 6 * 60 * 60 * 1000) return null;
        return row.result;
      } catch (e) {
        return null;
      }
    }

    function writeStoredNearestPlace(key, result) {
      if (!key || !result || !window.sessionStorage) return;
      try { sessionStorage.setItem(nearestPlaceStoragePrefix + key, JSON.stringify({ ts: Date.now(), result: result })); } catch (e) {}
    }

    function applyNearestPlaceResult(result, options) {
      options = options || {};
      var label = setNearestPlaceFromResult(result || {});
      if (label) {
        syncManualPositionNotice();
        if (!options.silent) scheduleAutosave('Nærmeste sted oppdatert');
      }
      return label;
    }

    function resolveNearestPlace(options) {
      options = options || {};
      if (!latitude || !longitude || !latitude.value || !longitude.value) return Promise.resolve('');
      var key = currentPlaceRequestKey(latitude.value, longitude.value);
      if (!key) return Promise.resolve('');
      var cached = !options.force ? readStoredNearestPlace(key) : null;
      if (cached) {
        var cachedLabel = applyNearestPlaceResult(cached, { silent: true });
        if (cachedLabel) return Promise.resolve(cachedLabel);
      }
      if (nearestPlaceController && typeof nearestPlaceController.abort === 'function') {
        try { nearestPlaceController.abort(); } catch (e) {}
      }
      nearestPlaceController = (typeof AbortController !== 'undefined') ? new AbortController() : null;
      var sequence = ++nearestPlaceSequence;
      var params = new URLSearchParams({ lat: latitude.value, lng: longitude.value });
      var fetchOptions = { credentials: 'same-origin', cache: 'no-store', headers: { 'Cache-Control': 'no-cache' } };
      if (nearestPlaceController) fetchOptions.signal = nearestPlaceController.signal;
      var url = (root && root.dataset && root.dataset.geoReverseUrl) ? root.dataset.geoReverseUrl : '/api/geo/reverse';
      return fetch(url + '?' + params.toString(), fetchOptions)
        .then(function (r) {
          if (!r.ok) throw new Error('Stedsoppslag feilet (' + r.status + ').');
          return r.json();
        })
        .then(function (result) {
          if (sequence !== nearestPlaceSequence) return '';
          writeStoredNearestPlace(key, result || {});
          return applyNearestPlaceResult(result || {}, options);
        })
        .catch(function (err) {
          if (err && err.name === 'AbortError') return '';
          return '';
        });
    }

    function scheduleNearestPlaceResolve(options, delay) {
      options = options || {};
      var wait = Math.max(0, Number(delay || 120));
      if (nearestPlaceTimer) window.clearTimeout(nearestPlaceTimer);
      return new Promise(function (resolve) {
        nearestPlaceTimer = window.setTimeout(function () {
          nearestPlaceTimer = null;
          resolve(resolveNearestPlace(options));
        }, wait);
      });
    }

    function readStoredZoneResult(key) {
      if (!key || !window.sessionStorage) return null;
      try {
        var cached = JSON.parse(sessionStorage.getItem(zoneResultStoragePrefix + key) || 'null');
        if (!cached || !cached.result || !cached.ts) return null;
        if ((Date.now() - Number(cached.ts || 0)) > 10 * 60 * 1000) return null;
        return cached.result;
      } catch (e) {
        return null;
      }
    }

    function writeStoredZoneResult(key, result) {
      if (!key || !result || !window.sessionStorage) return;
      try {
        sessionStorage.setItem(zoneResultStoragePrefix + key, JSON.stringify({ ts: Date.now(), result: result }));
      } catch (e) {}
    }

    function currentZoneRequestKey() {
      var latKey = Number(latitude.value || 0).toFixed(4);
      var lngKey = Number(longitude.value || 0).toFixed(4);
      return [
        latKey,
        lngKey,
        String(species.value || fisheryType.value || '').trim().toLowerCase(),
        String(gearType.value || '').trim().toLowerCase(),
        String(controlType.value || '').trim().toLowerCase()
      ].join('|');
    }

    function applyZoneCheckResult(result, options) {
      options = options || {};
      result = result || {};
      latestZoneResult = result || null;
      areaStatus.value = result.match ? (result.status || 'regulert område') : 'ingen treff';
      areaName.value = result.match ? (result.name || '') : '';
      setNearestPlaceFromResult(result);
      if (zoneResult) zoneResult.innerHTML = zoneResultHtml(result);
      updateAreaStatusDetail(result);
      updateAreaRestrictionOptions(result);
      syncManualPositionNotice();
      findingsState = findingsState.filter(function (row) {
        if (row && row.auto_area_finding) return false;
        return ['hummer_fredningsomrade_redskap', 'stengt_omrade_status', 'fredningsomrade_status', 'maksimalmal_omrade', 'regulert_omrade'].indexOf(row.key) === -1;
      });
      autoAreaFindingsFromZoneResult(result).forEach(function (areaItem) {
        var existing = findingsState.filter(function (row) { return row.key === areaItem.key; })[0];
        if (!existing) {
          findingsState.push(areaItem);
        } else {
          existing.status = areaItem.status || existing.status;
          existing.auto_area_finding = true;
          if (areaItem.notes) existing.notes = areaItem.notes;
          if (areaItem.law_text) existing.law_text = areaItem.law_text;
          if (areaItem.summary_text) existing.summary_text = areaItem.summary_text;
          if (areaItem.auto_note) existing.auto_note = areaItem.auto_note;
          if (!ensureDeviationState(existing).length) ensureDeviationState(existing).push(defaultDeviationRow(existing));
          syncDeviationDefaults(existing);
        }
      });
      renderFindings();
      if (result.match && result.hits && result.hits.length) {
        mergeSources(result.hits.map(function (hit) { return { name: hit.source || 'Karttreff', ref: hit.name || hit.layer || 'Områdetreff', url: hit.url || '' }; }));
      }
      renderRelevantAreaPanel(result);
      if (!options.skipMapUpdate) updateCaseMap();
      if (!options.skipSupplementaryLoads) {
        loadGearSummary();
        if (controlType.value && (species.value || fisheryType.value)) loadRules();
      }
      scheduleOfflineRegulationWarm(900);
      return result;
    }

    function checkZone(options) {
      options = options || {};
      if (!latitude.value || !longitude.value) {
        if (zoneResult) zoneResult.innerHTML = 'Legg inn posisjon først.';
        updateAreaStatusDetail(null);
        renderRelevantAreaPanel(null);
        return Promise.resolve(null);
      }
      var requestKey = currentZoneRequestKey();
      var now = Date.now();
      if (!options.force && lastZoneCheckResult && lastZoneCheckKey === requestKey && (now - lastZoneCheckAt) < 12000) {
        return Promise.resolve(applyZoneCheckResult(lastZoneCheckResult, { skipMapUpdate: true, skipSupplementaryLoads: true }));
      }
      var storedZoneResult = !options.force ? readStoredZoneResult(requestKey) : null;
      if (storedZoneResult) {
        applyZoneCheckResult(storedZoneResult, { skipMapUpdate: true, skipSupplementaryLoads: true });
      }
      var params = new URLSearchParams({
        lat: latitude.value,
        lng: longitude.value,
        species: species.value || fisheryType.value || '',
        gear_type: gearType.value || '',
        control_type: controlType.value || ''
      });
      if (zoneCheckController && typeof zoneCheckController.abort === 'function') {
        try { zoneCheckController.abort(); } catch (e) {}
      }
      zoneCheckController = (typeof AbortController !== 'undefined') ? new AbortController() : null;
      var sequence = ++zoneCheckSequence;
      if (zoneResult) zoneResult.innerHTML = storedZoneResult ? 'Oppdaterer verneområder ...' : 'Sjekker verneområder ...';
      var fetchOptions = { credentials: 'same-origin', cache: 'no-store', headers: { 'Cache-Control': 'no-cache' } };
      if (zoneCheckController) fetchOptions.signal = zoneCheckController.signal;
      return fetch(root.dataset.zonesUrl + '?' + params.toString(), fetchOptions)
        .then(function (r) {
          if (!r.ok) throw new Error('Områdesjekk feilet (' + r.status + ').');
          return r.json();
        })
        .then(function (result) {
          if (sequence !== zoneCheckSequence) return null;
          lastZoneCheckKey = requestKey;
          lastZoneCheckAt = Date.now();
          lastZoneCheckResult = result || null;
          writeStoredZoneResult(requestKey, result || null);
          return applyZoneCheckResult(result);
        })
        .catch(function (err) {
          if (err && err.name === 'AbortError') return null;
          latestZoneResult = null;
          if (zoneResult) zoneResult.innerHTML = 'Kunne ikke sjekke verneområder.';
          updateAreaStatusDetail(null);
          syncManualPositionNotice();
          renderRelevantAreaPanel(null);
          updateCaseMap();
          return null;
        });
    }

    function scheduleZoneCheck(options, delay) {
      options = options || {};
      var wait = Math.max(0, Number(delay || 450));
      if (mapState.pendingZoneTimer) window.clearTimeout(mapState.pendingZoneTimer);
      return new Promise(function (resolve) {
        mapState.pendingZoneTimer = window.setTimeout(function () {
          mapState.pendingZoneTimer = null;
          resolve(checkZone(options));
        }, wait);
      });
    }

    function applyAutoPosition(lat, lng, accuracy, shouldRecenter) {
      mapState.followAutoPosition = true;
      mapState.manualPosition = false;
      mapState.showDeviceMarker = true;
      persistPositionMode('auto');
      latitude.value = Number(lat).toFixed(6);
      longitude.value = Number(lng).toFixed(6);
      mapState.lat = Number(latitude.value);
      mapState.lng = Number(longitude.value);
      mapState.deviceLat = Number(lat);
      mapState.deviceLng = Number(lng);
      mapState.deviceAccuracy = Number(accuracy || mapState.deviceAccuracy || 12);
      syncManualPositionNotice();
      scheduleNearestPlaceResolve({}, 80);
      var recenterNow = !!shouldRecenter || mapState.autoRecenterOnce === true;
      var now = Date.now();
      var shouldRenderMap = recenterNow || !isFinite(mapState.lastMapRenderLat) || !isFinite(mapState.lastMapRenderLng) || (now - mapState.lastMapRenderTs) > 1200 || distanceMeters(mapState.lastMapRenderLat, mapState.lastMapRenderLng, mapState.lat, mapState.lng) > 6;
      if (shouldRenderMap) {
        mapState.lastMapRenderLat = mapState.lat;
        mapState.lastMapRenderLng = mapState.lng;
        mapState.lastMapRenderTs = now;
        updateCaseMap(recenterNow ? { recenterTo: 'device', recenterZoom: null } : {});
      }
      if (recenterNow) mapState.autoRecenterOnce = false;
      var shouldZoneCheck = !isFinite(mapState.lastZoneCheckLat) || !isFinite(mapState.lastZoneCheckLng) || (now - mapState.lastZoneCheckTs) > 15000 || distanceMeters(mapState.lastZoneCheckLat, mapState.lastZoneCheckLng, mapState.lat, mapState.lng) > Math.max(25, Number(mapState.deviceAccuracy || 0) * 1.5);
      if (shouldZoneCheck) {
        mapState.lastZoneCheckLat = mapState.lat;
        mapState.lastZoneCheckLng = mapState.lng;
        mapState.lastZoneCheckTs = now;
        scheduleZoneCheck({}, 650);
      }
      var shouldAutosave = !isFinite(mapState.lastAutoSaveLat) || !isFinite(mapState.lastAutoSaveLng) || (now - mapState.lastAutoSaveTs) > 30000 || distanceMeters(mapState.lastAutoSaveLat, mapState.lastAutoSaveLng, mapState.lat, mapState.lng) > 20;
      if (shouldAutosave) {
        mapState.lastAutoSaveLat = mapState.lat;
        mapState.lastAutoSaveLng = mapState.lng;
        mapState.lastAutoSaveTs = now;
        scheduleAutosave('Posisjon oppdatert');
      }
    }

    function setManualPositionFromMapCenter() {
      mapState.followAutoPosition = false;
      mapState.manualPosition = true;
      persistPositionMode('manual');
      var chosenLat = Number(latitude.value || 0);
      var chosenLng = Number(longitude.value || 0);
      if (!(isFinite(chosenLat) && isFinite(chosenLng) && (chosenLat || chosenLng))) {
        if (mapState.lastDeviceLat !== null && mapState.lastDeviceLng !== null) {
          chosenLat = mapState.lastDeviceLat;
          chosenLng = mapState.lastDeviceLng;
        } else if (caseMap && caseMap._kvLeafletMap) {
          var center = caseMap._kvLeafletMap.getCenter();
          chosenLat = center.lat;
          chosenLng = center.lng;
        } else {
          chosenLat = 63.5;
          chosenLng = 11;
        }
      }
      latitude.value = Number(chosenLat).toFixed(6);
      longitude.value = Number(chosenLng).toFixed(6);
      mapState.lat = Number(latitude.value);
      mapState.lng = Number(longitude.value);
      syncManualPositionNotice();
      scheduleNearestPlaceResolve({ force: true }, 80);
      updateCaseMap({ recenterTo: 'case' });
      scheduleZoneCheck({ force: true }, 250);
      scheduleAutosave('Manuell posisjon aktivert');
    }

    var devicePositionStorageKey = 'kv-device-position-1.8.7';
    function readCachedDevicePosition() {
      if (!window.localStorage) return null;
      try {
        var cached = JSON.parse(localStorage.getItem(devicePositionStorageKey) || 'null');
        if (!cached || !isFinite(Number(cached.lat)) || !isFinite(Number(cached.lng))) return null;
        if ((Date.now() - Number(cached.ts || 0)) > 15 * 60 * 1000) return null;
        return { lat: Number(cached.lat), lng: Number(cached.lng), accuracy: Number(cached.accuracy || 50) };
      } catch (e) {
        return null;
      }
    }

    function storeCachedDevicePosition(lat, lng, accuracy) {
      if (!window.localStorage) return;
      try {
        localStorage.setItem(devicePositionStorageKey, JSON.stringify({ ts: Date.now(), lat: Number(lat), lng: Number(lng), accuracy: Number(accuracy || 50) }));
      } catch (e) {}
    }

    function startLocationWatch(options) {
      options = options || {};
      var deviceOnly = !!options.deviceOnly || mapState.manualPosition === true;
      var recenter = !!options.recenter;
      if (!navigator.geolocation) {
        if (zoneResult) zoneResult.innerHTML = 'Denne enheten støtter ikke geolokasjon i nettleseren.';
        syncManualPositionNotice();
        return;
      }
      mapState.followAutoPosition = !deviceOnly;
      mapState.showDeviceMarker = !mapState.manualPosition;
      function applyDevicePosition(lat, lng, accuracy, shouldRecenter) {
        mapState.lastDeviceLat = Number(lat);
        mapState.lastDeviceLng = Number(lng);
        mapState.deviceLat = Number(lat);
        mapState.deviceLng = Number(lng);
        mapState.deviceAccuracy = Number(accuracy || mapState.deviceAccuracy || 12);
        storeCachedDevicePosition(lat, lng, mapState.deviceAccuracy);
        syncManualPositionNotice();
        if (deviceOnly || !mapStepIsVisible()) {
          updateCaseMap(deviceOnly && mapStepIsVisible() && shouldRecenter ? { recenterTo: 'device' } : {});
          return;
        }
        applyAutoPosition(lat, lng, accuracy, shouldRecenter);
      }
      if (mapState.lastDeviceLat !== null && mapState.lastDeviceLng !== null) {
        applyDevicePosition(mapState.lastDeviceLat, mapState.lastDeviceLng, mapState.deviceAccuracy || 12, recenter);
      } else {
        var cachedDevicePosition = readCachedDevicePosition();
        if (cachedDevicePosition) applyDevicePosition(cachedDevicePosition.lat, cachedDevicePosition.lng, cachedDevicePosition.accuracy, recenter);
      }
      var handleGeoPosition = function (position, shouldRecenter) {
        var currentLat = Number(position.coords.latitude.toFixed(6));
        var currentLng = Number(position.coords.longitude.toFixed(6));
        var currentAccuracy = Number(position.coords.accuracy || 12);
        applyDevicePosition(currentLat, currentLng, currentAccuracy, shouldRecenter);
      };
      navigator.geolocation.getCurrentPosition(function (position) {
        handleGeoPosition(position, recenter);
      }, function (err) {
        if (zoneResult) zoneResult.innerHTML = 'Kunne ikke hente posisjon raskt. Prøver videre ...';
        syncManualPositionNotice();
      }, { enableHighAccuracy: false, timeout: 1500, maximumAge: 600000 });
      window.setTimeout(function () {
        navigator.geolocation.getCurrentPosition(function (position) {
          handleGeoPosition(position, recenter && !readCachedDevicePosition());
        }, function () {}, { enableHighAccuracy: true, timeout: 6000, maximumAge: 60000 });
      }, 150);
      if (locationWatchId !== null) return;
      locationWatchId = navigator.geolocation.watchPosition(function (position) {
        var currentLat = Number(position.coords.latitude.toFixed(6));
        var currentLng = Number(position.coords.longitude.toFixed(6));
        var currentAccuracy = Number(position.coords.accuracy || 12);
        mapState.lastDeviceLat = currentLat;
        mapState.lastDeviceLng = currentLng;
        mapState.deviceAccuracy = currentAccuracy;
        mapState.deviceLat = currentLat;
        mapState.deviceLng = currentLng;
        storeCachedDevicePosition(currentLat, currentLng, currentAccuracy);
        if (mapState.followAutoPosition === false || !mapStepIsVisible()) {
          updateCaseMap();
          syncManualPositionNotice();
          return;
        }
        applyAutoPosition(currentLat, currentLng, currentAccuracy, false);
      }, function (err) {
        if (zoneResult) zoneResult.innerHTML = 'Kunne ikke hente posisjon: ' + escapeHtml(err.message || err) + '. Du kan fortsatt sette posisjon manuelt i kartet.';
        syncManualPositionNotice();
      }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 });
    }

    function maybeAutoStartLocation() {
      if (autoLocationAttempted || !navigator.geolocation) return;
      autoLocationAttempted = true;
      var start = function () { startLocationWatch({ deviceOnly: mapState.manualPosition === true, recenter: mapState.manualPosition !== true }); };
      if (navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({ name: 'geolocation' }).then(function (permission) {
          if (!permission || permission.state === 'denied') {
            syncManualPositionNotice();
            return;
          }
          start();
        }).catch(function () { start(); });
      } else {
        start();
      }
    }

    function stopLocationWatch() {
      if (locationWatchId === null || !navigator.geolocation) return;
      try { navigator.geolocation.clearWatch(locationWatchId); } catch (e) {}
      locationWatchId = null;
    }

    function cleanupCasePageResources() {
      stopLocationWatch();
      if (cameraCaptureVideo && cameraCaptureVideo.srcObject && cameraCaptureVideo.srcObject.getTracks) {
        try { cameraCaptureVideo.srcObject.getTracks().forEach(function (track) { track.stop(); }); } catch (e) {}
        cameraCaptureVideo.srcObject = null;
      }
      if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        try { mediaRecorder.stop(); } catch (e) {}
      }
    }

    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') {
        stopLocationWatch();
        persistLocalCaseDraft({ silent: true });
        return;
      }
      if (currentStep !== 2) return;
      startLocationWatch({ deviceOnly: mapState.manualPosition === true, recenter: mapState.manualPosition !== true });
    });
    window.addEventListener('pagehide', function () { persistLocalCaseDraft({ silent: true }); cleanupCasePageResources(); });
    window.addEventListener('beforeunload', function () { persistLocalCaseDraft({ silent: true }); cleanupCasePageResources(); });

    document.getElementById('btn-check-zone').addEventListener('click', checkZone);
    document.getElementById('btn-use-location').addEventListener('click', function () {
      mapState.autoRecenterOnce = true;
      startLocationWatch({ deviceOnly: false, recenter: true });
    });
    var btnSetManualPosition = document.getElementById('btn-set-manual-position');
    if (btnSetManualPosition) btnSetManualPosition.addEventListener('click', setManualPositionFromMapCenter);
    if (mapFilterWrap) {
      syncLayerFiltersUi();
      Array.prototype.forEach.call(mapFilterWrap.querySelectorAll('input[data-layer-filter]'), function (input) {
        input.addEventListener('change', function () {
          var key = String(input.getAttribute('data-layer-filter') || '').trim().toLowerCase();
          activeLayerStatuses[key] = !!input.checked;
          try { localStorage.setItem(mapFilterStorageKey, JSON.stringify(activeLayerStatuses)); } catch (e) {}
          syncMapSelectionStatus();
          updateCaseMap();
        });
      });
    }
    if (toggleZoneHitOverlay) {
      toggleZoneHitOverlay.checked = zoneOverlayEnabled !== false;
      syncZoneHitOverlayToggleText();
      toggleZoneHitOverlay.addEventListener('change', function () {
        zoneOverlayEnabled = !!toggleZoneHitOverlay.checked;
        try { localStorage.setItem(zoneOverlayStorageKey, zoneOverlayEnabled ? '1' : '0'); } catch (e) {}
        syncZoneHitOverlayToggleText();
        syncZoneHitOverlay(latestZoneResult);
      });
    }
    function applyManualCoordinateFields() {
      if (!latitude.value || !longitude.value) {
        updateCaseMap();
        return;
      }
      mapState.followAutoPosition = false;
      mapState.manualPosition = true;
      syncManualPositionNotice();
      scheduleNearestPlaceResolve({ force: true }, 80);
      updateCaseMap({ recenterTo: 'case' });
      scheduleZoneCheck({ force: true }, 250);
      scheduleAutosave('Manuell posisjon oppdatert');
    }

    latitude.addEventListener('change', applyManualCoordinateFields);
    longitude.addEventListener('change', applyManualCoordinateFields);


    function updateExternalSearchLinks() {
      var query = [lookupName.value || suspectName.value || suspectNameCommercial.value || '', lookupIdentifier.value || '', suspectAddress.value || '', (suspectPostPlace ? suspectPostPlace.value : '') || ''].filter(Boolean).join(' ').trim();
      var btn1881 = document.getElementById('btn-search-1881');
      var btnGulesider = document.getElementById('btn-search-gulesider');
      if (btn1881) btn1881.onclick = function () { window.open('https://www.1881.no/?query=' + encodeURIComponent(query), '_blank', 'noopener'); };
      if (btnGulesider) btnGulesider.onclick = function () { window.open('https://www.gulesider.no/' + encodeURIComponent(query) + '/personer', '_blank', 'noopener'); };
    }

    function renderGearSummary(payload) {
      latestGearSummary = payload || null;
      if (observedGearCount) observedGearCount.value = '0';
      if (!gearSummaryStatus) return;
      gearSummaryStatus.innerHTML = [
        '<div class="status-title status-ok">Oppsummeringen bygger bare på kontrollpunktene</div>',
        '<div class="small" style="margin-top:6px"><strong>Tidligere registrert på samme person/fartøy i appen:</strong> 0</div>',
        '<div class="small muted" style="margin-top:6px">Tidligere registrerte teiner/redskap på samme person eller fartøy tas ikke med i oppsummering eller anmeldelsestekst. Bare faktiske avvik og lovbrudd fra steg 4 brukes videre.</div>'
      ].join('');
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
      if (person.name && !isBadPersonName(person.name)) {
        autofillField(suspectName, person.name);
        autofillField(suspectNameCommercial, person.name);
        autofillField(lookupName, person.name);
      }
      if (!isCommercial && person.address) autofillField(suspectAddress, person.address);
      if (!isCommercial && person.post_place && suspectPostPlace) autofillField(suspectPostPlace, person.post_place);
      if (!isCommercial && person.phone) {
        autofillField(suspectPhone, person.phone);
      }
      if (!isCommercial && person.birthdate) autofillField(suspectBirthdate, person.birthdate);
      if (person.vessel_name) autofillField(vesselName, person.vessel_name);
      if (person.vessel_reg) {
        autofillField(vesselReg, person.vessel_reg);
        if (isCommercial) autofillField(lookupIdentifier, person.vessel_reg);
      }
      if (person.radio_call_sign) autofillField(radioCallSign, person.radio_call_sign);
      if (person.gear_marker_id && gearMarkerId) autofillField(gearMarkerId, normalizeGearMarkerId(person.gear_marker_id) || person.gear_marker_id);
      if (!isCommercial && (person.hummer_participant_no || person.participant_no)) {
        autofillField(hummerParticipantNo, person.hummer_participant_no || person.participant_no);
        autofillField(lookupIdentifier, hummerParticipantNo.value || person.hummer_participant_no || person.participant_no);
      } else if (!isCommercial && person.phone && !lookupIdentifier.value) {
        autofillField(lookupIdentifier, person.phone);
      }
      var lastRegistered = person.hummer_last_registered || person.registered_date_display || person.last_registered_display || person.last_registered_year || fallbackLast || '';
      if (!isCommercial && hummerLastRegistered) autofillField(hummerLastRegistered, normalizedSeasonValue(lastRegistered));
      updateExternalSearchLinks();
      renderAutofillPreview({ source: 'Registertreff', detail: person.source || 'Oppdatert fra register' });
      loadGearSummary();
      scheduleAutosave('Person/fartøy oppdatert');
      return lastRegistered;
    }

    function renderRegistryCandidates(candidates) {
      candidateState = (candidates || []).filter(function (item) { if (!item) return false; if (item.name && isBadPersonName(item.name)) item.name = ''; return item.name || item.vessel_reg || item.vessel_name || item.participant_no || item.hummer_participant_no; });
      if (!candidateState.length) {
        registryCandidates.classList.add('hidden');
        registryCandidates.innerHTML = '';
        return;
      }
      registryCandidates.classList.remove('hidden');
      registryCandidates.innerHTML = candidateState.map(function (item, index) {
        var primary = item.name || item.vessel_name || 'Ukjent';
        var season = item.hummer_last_registered || item.last_registered_display || item.last_registered_year || '';
        var seasonText = hummerSeasonText(season);
        var secondary = [item.address || '', item.post_place || '', item.fisher_type || '', seasonText].filter(Boolean).join(item.address && item.post_place ? ', ' : ' · ');
        var tertiary = [item.vessel_name || '', item.vessel_reg || '', item.radio_call_sign || '', item.participant_no || item.hummer_participant_no || '', item.source || ''].filter(Boolean).join(' · ');
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
      var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
      applyPerson(item, item.hummer_last_registered || '');
      if (item.name && !isBadPersonName(item.name)) autofillField(lookupName, item.name);
      if (!isCommercial && (item.hummer_participant_no || item.participant_no)) {
        autofillField(hummerParticipantNo, item.hummer_participant_no || item.participant_no);
        autofillField(lookupIdentifier, hummerParticipantNo.value || item.hummer_participant_no || item.participant_no);
      } else if (!isCommercial && item.phone) {
        autofillField(lookupIdentifier, item.phone);
      } else if (item.vessel_reg) {
        autofillField(lookupIdentifier, item.vessel_reg);
      }
      registryResult.innerHTML = '<strong>Treff valgt</strong><div class="small muted">Oppdaterer kontaktopplysninger og registerdata ...</div>';
      lookupRegistry()
        .catch(function () {
          renderHummerStatus({ found: Boolean(item.hummer_participant_no || item.participant_no), person: item, message: (item.hummer_participant_no || item.participant_no) ? 'Treff valgt fra kandidatlisten.' : 'Treff valgt, men ingen hummerregistrering funnet i kandidatdata.' });
          registryResult.innerHTML = '<strong>Treff valgt</strong><div class="small muted">Skjemaet er oppdatert fra valgt kandidat.</div>';
        });
    });


function applyHints(hints) {
  if (!hints) return;
  var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
  var changed = false;
  if (hints.name && !isBadPersonName(hints.name)) {
    changed = autofillField(suspectName, hints.name) || changed;
    changed = autofillField(suspectNameCommercial, hints.name) || changed;
    changed = autofillField(lookupName, hints.name) || changed;
  }
  if (!isCommercial && hints.address && !isBadOcrFragment(hints.address)) changed = autofillField(suspectAddress, hints.address) || changed;
  if (!isCommercial && hints.post_place && suspectPostPlace && !isBadOcrFragment(hints.post_place)) changed = autofillField(suspectPostPlace, hints.post_place) || changed;
  if (!isCommercial && hints.phone) {
    changed = autofillField(suspectPhone, hints.phone) || changed;
    changed = autofillField(lookupIdentifier, hints.phone) || changed;
  }
  if (!isCommercial && hints.birthdate) changed = autofillField(suspectBirthdate, hints.birthdate) || changed;
  if (!isCommercial && hints.hummer_participant_no) {
    changed = autofillField(hummerParticipantNo, hints.hummer_participant_no) || changed;
    changed = autofillField(lookupIdentifier, hints.hummer_participant_no) || changed;
  }
  if (hints.vessel_reg) {
    changed = autofillField(vesselReg, hints.vessel_reg) || changed;
    if (isCommercial || !lookupIdentifier.value) changed = autofillField(lookupIdentifier, hints.vessel_reg) || changed;
  }
  if (hints.radio_call_sign) changed = autofillField(radioCallSign, hints.radio_call_sign) || changed;
  if (hints.vessel_name) changed = autofillField(vesselName, hints.vessel_name) || changed;
  if (hints.gear_marker_id && gearMarkerId) {
    var markerValue = normalizeGearMarkerId(hints.gear_marker_id) || String(hints.gear_marker_id || '').trim().toUpperCase();
    changed = autofillField(gearMarkerId, markerValue) || changed;
    if (!lookupIdentifier.value) changed = autofillField(lookupIdentifier, markerValue) || changed;
  }
  updateExternalSearchLinks();
  renderAutofillPreview({ source: 'OCR og bildegjenkjenning', detail: changed ? 'Skjemaet er oppdatert automatisk' : 'Felt kontrollert automatisk' });
  if (changed) {
    loadGearSummary();
    scheduleAutosave('Autofyll oppdatert');
  }
}

function renderHummerStatus(result) {
      if (!hummerRegistryStatus) return;
      if (!result) {
        hummerRegistryStatus.innerHTML = '<div class="status-title">Ingen registerstatus</div><div class="muted small">Ingen søk er kjørt ennå.</div>';
        return;
      }
      var person = result.person || {};
      var lastSeason = person.registered_date_display || person.last_registered_display || person.hummer_last_registered || person.last_registered_year || '';
      var seasonText = hummerSeasonText(lastSeason) || 'Registreringssesong ikke oppgitt';
      var sourceText = person.source || result.source || 'Hummerregister';
      var addressText = [person.address || '', person.post_place || ''].filter(Boolean).join(person.address && person.post_place ? ', ' : ' ');
      if (result.found) {
        hummerRegistryStatus.innerHTML = [
          '<div class="status-title status-ok">Treff i hummerregister</div>',
          person.name ? '<div><strong>Navn:</strong> ' + escapeHtml(person.name) + '</div>' : '',
          (person.participant_no || person.hummer_participant_no) ? '<div><strong>Deltakernummer:</strong> ' + escapeHtml(person.participant_no || person.hummer_participant_no) + '</div>' : '',
          '<div><strong>Status:</strong> ' + escapeHtml(seasonText) + '</div>',
          person.fisher_type ? '<div><strong>Type fiskar:</strong> ' + escapeHtml(person.fisher_type) + '</div>' : '',
          addressText ? '<div><strong>Adresse:</strong> ' + escapeHtml(addressText) + '</div>' : '',
          person.phone ? '<div><strong>Mobil:</strong> ' + escapeHtml(person.phone) + '</div>' : '',
          '<div class="muted small">Kilde: ' + escapeHtml(sourceText) + '</div>',
          result.message ? '<div class="muted small">' + escapeHtml(result.message) + '</div>' : ''
        ].join('');
      } else {
        hummerRegistryStatus.innerHTML = [
          '<div class="status-title status-warn">Ingen sikre treff i hummerregister</div>',
          person.name ? '<div><strong>Navn:</strong> ' + escapeHtml(person.name) + '</div>' : '',
          addressText ? '<div><strong>Adresse:</strong> ' + escapeHtml(addressText) + '</div>' : '',
          person.phone ? '<div><strong>Mobil:</strong> ' + escapeHtml(person.phone) + '</div>' : '',
          lastSeason ? '<div><strong>Siste registrerte sesong:</strong> ' + escapeHtml(lastSeason) + '</div>' : '',
          result.message ? '<div class="muted small">' + escapeHtml(result.message) + '</div>' : '<div class="muted small">Ingen treff i hummerregisteret for oppgitt navn eller deltakernummer.</div>'
        ].join('');
      }
    }

    function applyRegistryResult(result) {
      var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
      applyHints(result.hints || {});
      var fallbackLast = (result.hummer_check && result.hummer_check.person && (result.hummer_check.person.last_registered_display || result.hummer_check.person.last_registered_year)) || '';
      renderRegistryCandidates(result.candidates || []);
      var hummerStatusPayload = result.hummer_check || null;
      if (result.found && result.person && (result.person.hummer_participant_no || (result.hummer_check && result.hummer_check.found))) {
        hummerStatusPayload = {
          found: true,
          person: Object.assign({}, (result.hummer_check && result.hummer_check.person) || {}, result.person || {}),
          source: (result.hummer_check && result.hummer_check.source) || result.source || 'Hummerregister',
          message: (result.hummer_check && result.hummer_check.message) || ''
        };
      }
      renderHummerStatus(hummerStatusPayload);
      if (!result.found) {
        if (!isCommercial && hummerLastRegistered) hummerLastRegistered.value = fallbackLast;
        registryResult.innerHTML = '<strong>Ingen direkte treff</strong><div class="small muted">Prøv navn, deltakernummer eller annen identifikator. Eventuelle kandidat- og hummerregistertreff vises under.</div>';
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
      if (lastRegistered) messages.push('<div class="small muted">' + escapeHtml(hummerSeasonText(lastRegistered) || normalizedSeasonValue(lastRegistered)) + '</div>');
      if (result.vipps_message) messages.push('<div class="small muted">' + escapeHtml(result.vipps_message) + '</div>');
      registryResult.innerHTML = messages.join('');
      renderRegistryCandidates(result.candidates || []);
      updateExternalSearchLinks();
      loadGearSummary();
      scheduleAutosave('Registertreff oppdatert');
      if (person.source_url) mergeSources([{ name: person.source || 'Register', ref: 'Oppslag', url: person.source_url }]);
      else if (result.hummer_check && result.hummer_check.person && result.hummer_check.person.source_url) mergeSources([{ name: result.hummer_check.person.source || 'Register', ref: 'Hummerregister', url: result.hummer_check.person.source_url }]);
    }

    function currentRegistryLookupKey() {
      var parts = [
        String(controlType && controlType.value || '').trim().toLowerCase(),
        String(lookupName && lookupName.value || suspectName.value || suspectNameCommercial.value || '').trim().toLowerCase(),
        String(lookupIdentifier && lookupIdentifier.value || '').trim().toLowerCase(),
        String(lookupText && lookupText.value || '').trim().toLowerCase(),
        String(suspectAddress && suspectAddress.value || '').trim().toLowerCase(),
        String(suspectPostPlace && suspectPostPlace.value || '').trim().toLowerCase()
      ];
      return parts.join('||');
    }

    function hasRegistryLookupInput() {
      var key = currentRegistryLookupKey();
      var compact = key.replace(/\|/g, '').replace(/\s+/g, '');
      if (!compact) return false;
      if (lookupText && String(lookupText.value || '').trim().length >= 6) return true;
      if (lookupIdentifier && String(lookupIdentifier.value || '').trim().length >= 4) return true;
      if (lookupName && String(lookupName.value || '').trim().length >= 3) return true;
      if (suspectName && String(suspectName.value || '').trim().length >= 3) return true;
      if (hummerParticipantNo && String(hummerParticipantNo.value || '').trim().length >= 3) return true;
      if (vesselReg && String(vesselReg.value || '').trim().length >= 3) return true;
      return false;
    }

    function cleanPhoneLookupValue(value) {
      var digits = String(value || '').replace(/\D+/g, '');
      if (digits.length === 10 && digits.indexOf('47') === 0) digits = digits.slice(2);
      if (digits.length === 11 && digits.indexOf('047') === 0) digits = digits.slice(3);
      return /^\d{8}$/.test(digits) ? digits : '';
    }

    function applyPhoneLookupResult(result, phone) {
      result = result || {};
      renderRegistryCandidates(result.candidates || []);
      var person = result.person || (result.hummer_check && result.hummer_check.person) || null;
      if (!result.found || !person) {
        if (registryResult) registryResult.innerHTML = '<strong>Ingen treff på mobilnummer</strong><div class="small muted">Kontroller nummeret eller bruk vanlig Oppslag.</div>';
        return result;
      }
      var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
      if (phone && !isCommercial) autofillField(suspectPhone, phone, { allowOverwrite: true });
      if (phone && lookupIdentifier) autofillField(lookupIdentifier, phone, { allowOverwrite: true });
      if (person.name && !isBadPersonName(person.name)) {
        autofillField(suspectName, person.name, { allowOverwrite: true });
        autofillField(suspectNameCommercial, person.name, { allowOverwrite: true });
        autofillField(lookupName, person.name, { allowOverwrite: true });
      }
      if (!isCommercial && person.address && !isBadOcrFragment(person.address)) autofillField(suspectAddress, person.address, { allowOverwrite: true });
      if (!isCommercial && person.post_place && suspectPostPlace && !isBadOcrFragment(person.post_place)) autofillField(suspectPostPlace, person.post_place, { allowOverwrite: true });
      if (person.birthdate && suspectBirthdate) autofillField(suspectBirthdate, person.birthdate, { allowOverwrite: true });
      renderHummerStatus(result.hummer_check || { found: Boolean(person.hummer_participant_no || person.participant_no), person: person, source: person.source || result.source || 'Mobiloppslag' });
      if (registryResult) registryResult.innerHTML = '<strong>Mobiloppslag treff</strong><div class="small muted">Navn, adresse og poststed er hentet fra telefonoppslag.</div>';
      renderAutofillPreview({ source: 'Mobiloppslag', detail: person.source || result.source || '1881 / Gulesider' });
      updateExternalSearchLinks();
      loadGearSummary();
      scheduleAutosave('Mobiloppslag oppdatert persondata');
      if (person.source_url) mergeSources([{ name: person.source || 'Mobiloppslag', ref: phone || 'Telefonoppslag', url: person.source_url }]);
      return result;
    }

    function lookupPhoneNumber() {
      var phone = cleanPhoneLookupValue((suspectPhone && suspectPhone.value) || (lookupIdentifier && lookupIdentifier.value) || '');
      if (!phone) {
        if (registryResult) registryResult.innerHTML = '<strong>Oppgi mobilnummer</strong><div class="small muted">Skriv inn et 8-sifret mobilnummer i feltet Mobilnummer eller identifikator.</div>';
        return Promise.resolve(null);
      }
      if (suspectPhone) suspectPhone.value = phone;
      if (lookupIdentifier) lookupIdentifier.value = phone;
      if (registryResult) registryResult.innerHTML = 'Søker mobilnummer ...';
      var params = new URLSearchParams({
        phone: phone,
        vessel_reg: '',
        radio_call_sign: '',
        name: '',
        address: '',
        post_place: '',
        tag_text: '',
        hummer_participant_no: ''
      });
      return fetch(root.dataset.registryUrl + '?' + params.toString(), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (payload) { return applyPhoneLookupResult(payload || {}, phone); })
        .catch(function () {
          if (registryResult) registryResult.innerHTML = '<strong>Mobiloppslag feilet</strong><div class="small muted">Prøv igjen eller fyll inn manuelt.</div>';
          return null;
        });
    }

    function lookupRegistry(options) {
      options = options || {};
      var lookupKey = currentRegistryLookupKey();
      if (!hasRegistryLookupInput()) {
        if (registryResult) registryResult.innerHTML = 'Ta bilde eller oppgi navn, merketøy, telefonnummer eller deltakernummer. Bruk Oppslag manuelt ved behov.';
        return Promise.resolve(null);
      }
      if (registryLookupInFlight) {
        pendingRegistryLookup = true;
        return Promise.resolve(null);
      }
      if (!options.force && lookupKey && lookupKey === lastSuccessfulRegistryLookupKey) {
        return Promise.resolve(null);
      }
      registryLookupInFlight = true;
      lastRegistryLookupKey = lookupKey;
      var identifier = lookupIdentifier.value || '';
      var inferred = classifyLookupIdentifier(identifier);
      var isCommercial = String(controlType.value || '').toLowerCase().indexOf('kom') === 0;
      if (!isCommercial && inferred.phone) suspectPhone.value = inferred.phone;
      if (!isCommercial && inferred.hummer_participant_no) hummerParticipantNo.value = inferred.hummer_participant_no;
      if (inferred.vessel_reg) vesselReg.value = inferred.vessel_reg;
      if (inferred.radio_call_sign) radioCallSign.value = inferred.radio_call_sign;
      if (inferred.gear_marker_id && gearMarkerId) gearMarkerId.value = inferred.gear_marker_id;
      var params = new URLSearchParams({
        phone: (!isCommercial ? (suspectPhone.value || inferred.phone || '') : ''),
        vessel_reg: (vesselReg.value || inferred.vessel_reg || ''),
        radio_call_sign: (radioCallSign.value || inferred.radio_call_sign || ''),
        name: lookupName.value || suspectName.value || suspectNameCommercial.value || '',
        address: (!isCommercial ? (suspectAddress.value || '') : ''),
        post_place: (!isCommercial ? ((suspectPostPlace ? suspectPostPlace.value : '') || '') : ''),
        tag_text: lookupText.value || '',
        hummer_participant_no: (!isCommercial ? (hummerParticipantNo.value || inferred.hummer_participant_no || '') : '')
      });
      if (registryResult) registryResult.innerHTML = options.automatic === false ? 'Søker i hummerregister og 1881 / Gulesider ...' : 'Søker i hummerregister og offentlige kataloger (1881 / Gulesider) etter manuelt valg ...';
      updateExternalSearchLinks();
      return fetch(root.dataset.registryUrl + '?' + params.toString())
        .then(function (r) { return r.json(); })
        .then(function (payload) {
          applyRegistryResult(payload || {});
          lastSuccessfulRegistryLookupKey = lookupKey;
          return payload || {};
        })
        .catch(function () {
          if (registryResult) registryResult.innerHTML = '<strong>Ikke søkbar / ingen direkte treff</strong><div class="small muted">Prøv nytt bilde eller korriger navn, telefon, fiskerimerke eller deltakernummer.</div>';
          return null;
        })
        .finally(function () {
          registryLookupInFlight = false;
          if (pendingRegistryLookup) {
            pendingRegistryLookup = false;
            var nextKey = currentRegistryLookupKey();
            if (nextKey && nextKey !== lastSuccessfulRegistryLookupKey) lookupRegistry({ force: true });
          }
        });
    }

    function scheduleAutoRegistryLookup(reason, delay) {
      // Eksterne registeroppslag skal ikke starte automatisk eller overstyre OCR fra bilde.
      // Bruk Oppslag-knappen manuelt ved behov.
      if (registryLookupTimer) window.clearTimeout(registryLookupTimer);
    }

    if (btnPhoneLookup) btnPhoneLookup.addEventListener('click', function () {
      lookupPhoneNumber();
    });

    if (btnLookupPerson) btnLookupPerson.addEventListener('click', function () {
      lookupRegistry({ force: true, automatic: false });
    });

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
        var autoRows = ensureDeviationState(item);
        if (!autoRows.length) autoRows.push(defaultDeviationRow(item));
        syncDeviationDefaults(item);
        var btn = card.querySelector('.finding-evidence-btn');
        if (btn) btn.classList.remove('hidden');
      } else {
        item.auto_note = '';
      }
      findingsInput.value = JSON.stringify(findingsState);
    }

    function idleLater(callback, timeout) {
      if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(function () { try { callback(); } catch (e) {} }, { timeout: timeout || 800 });
      } else {
        setTimeout(function () { try { callback(); } catch (e) {} }, Math.max(120, Number(timeout) || 120));
      }
    }

    function hashString(value) {
      var hash = 2166136261;
      var input = String(value || '');
      for (var idx = 0; idx < input.length; idx += 1) {
        hash ^= input.charCodeAt(idx);
        hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
      }
      return (hash >>> 0).toString(16);
    }

    function buildSummaryPayload() {
      syncSeizureReportsFromDom();
      return {
        case_basis: caseBasis.value,
        control_type: controlType.value,
        species: species.value || fisheryType.value || '',
        fishery_type: fisheryType.value,
        gear_type: gearType.value,
        gear_marker_id: gearMarkerId ? gearMarkerId.value : '',
        location_name: locationName.value,
        area_name: areaName.value,
        area_status: areaStatus.value,
        suspect_name: suspectName.value || suspectNameCommercial.value,
        basis_details: basisDetails.value,
        start_time: startTime.value,
        latitude: latitude.value,
        longitude: longitude.value,
        persons: personsState || [],
        seizure_reports: seizureReportsState || [],
        findings: findingsState
      };
    }

    function summaryCacheKey(payload) {
      return 'kv-summary-draft:' + String(root.dataset.caseId || '') + ':' + hashString(JSON.stringify(payload || {}));
    }

    function loadCachedSummaryDraft(key) {
      if (!key) return null;
      if (summaryDraftCache[key]) return summaryDraftCache[key];
      var parsed = null;
      try {
        parsed = JSON.parse(localStorage.getItem(key) || 'null');
      } catch (e) { parsed = null; }
      if (!parsed || !parsed.drafts) return null;
      summaryDraftCache[key] = parsed;
      return parsed;
    }

    function storeCachedSummaryDraft(key, drafts) {
      if (!key || !drafts) return;
      var payload = { ts: Date.now(), drafts: drafts };
      summaryDraftCache[key] = payload;
      try { localStorage.setItem(key, JSON.stringify(payload)); } catch (e) {}
    }

    function localSummaryFromFindings(payload) {
      var findings = payload && payload.findings ? payload.findings : [];
      var avvik = findings.filter(function (item) {
        return item && String(item.status || '').toLowerCase() === 'avvik';
      });
      var place = String(payload && payload.location_name || '').trim() || 'kontrollstedet';
      if (place.indexOf(' - ') !== -1) place = place.split(' - ')[0].trim() || place;
      var areaNameText = String(payload && payload.area_name || '').trim();
      var areaStatusText = String(payload && payload.area_status || '').trim();
      var gearText = String(payload && payload.gear_type || '').trim();
      var speciesText = String(payload && (payload.species || payload.fishery_type) || '').trim();
      var controlText = String(payload && payload.control_type || '').trim();
      var subject = String(payload && payload.suspect_name || '').trim() || 'kontrollert person/fartøy';
      var when = String(payload && payload.start_time || '').trim().replace('T', ' ').slice(0, 16) || currentControlDateLabel();
      var topic = [controlText, speciesText, gearText].filter(function (item) { return String(item || '').trim(); }).join(' / ') || 'fiskerikontroll';

      function sentenceize(text) {
        var clean = String(text || '').trim().replace(/\s+/g, ' ');
        clean = clean.replace(/\bi aktuelt kontrollområde\b/ig, 'ved ' + place);
        clean = clean.replace(/\bved kontrollposisjonen\b/ig, 'ved ' + place);
        clean = clean.replace(/\bved kontrollposisjon\b/ig, 'ved ' + place);
        clean = clean.replace(/\bkontrollposisjonen\b/ig, place);
        clean = clean.replace(/ved ved /ig, 'ved ');
        if (!clean) return '';
        if (!/[.!?]$/.test(clean)) clean += '.';
        return clean;
      }

      function findingLine(item, idx) {
        var label = String(item && (item.label || item.key) || ('Avvik ' + idx)).trim();
        var note = String(item && (item.summary_text || item.notes || item.auto_note || '') || '').trim();
        var ref = [item && (item.source_name || item.law_name), item && (item.source_ref || item.section)].filter(function (x) { return String(x || '').trim(); }).join(' - ');
        return String(idx) + '. ' + sentenceize(label + (note ? ' - ' + note : '') + (ref ? ' (' + ref + ')' : ''));
      }

      var basis = String(payload && payload.basis_details || '').trim();
      if (!basis) {
        basis = 'Den ' + when + ' ble det gjennomført stedlig fiskerikontroll ved ' + place + '. Kontrollen gjaldt ' + topic.toLowerCase() + '. Formålet var å kontrollere faktiske forhold på stedet og sikre notoritet rundt observasjoner, bevis og eventuelle beslag.';
      } else {
        basis = sentenceize(basis);
      }

      var lines = [
        'Oppsummering / anmeldelsesgrunnlag',
        '',
        '1. Tid, sted og kontrolltema',
        'Den ' + when + ' ble det gjennomført kontroll ved ' + place + '. Kontrollen gjaldt ' + topic.toLowerCase() + ' og omfattet ' + subject + '.',
      ];
      if (areaNameText || (areaStatusText && areaStatusText.toLowerCase() !== 'ingen treff')) {
        lines.push('Kontrollstedet er vurdert mot registrert områdestatus/verneområde: ' + [areaNameText, areaStatusText].filter(Boolean).join(' - ') + '.');
      }
      lines = lines.concat(['', '2. Bakgrunn og gjennomføring', basis, '', '3. Registrerte funn og avvik']);
      if (!avvik.length) {
        lines.push('Det er ikke registrert avvik i kontrollpunktene på tidspunktet for tekstutkastet.');
      } else {
        avvik.forEach(function (item, idx) { lines.push(findingLine(item, idx + 1)); });
      }
      lines = lines.concat(['', '4. Beslag, bildebevis og dokumentasjon']);
      if (payload && payload.seizure_reports && payload.seizure_reports.length) {
        payload.seizure_reports.forEach(function (row, idx) {
          var ref = String(row.seizure_ref || row.gear_ref || ('Beslag ' + (idx + 1))).trim();
          var desc = String(row.description || row.violation_reason || row.type || 'registrert beslag/avvik').trim();
          lines.push((idx + 1) + '. ' + sentenceize(ref + ': ' + desc));
        });
      } else {
        lines.push('Det er ikke registrert beslag i saken.');
      }
      lines = lines.concat(['', '5. Dokumentgrunnlag', 'Utkastet beskriver faktum, kontrollobservasjoner, beslag/bildebevis og forklaringer slik de er registrert i saken. Endelig vurdering av skyld og reaksjon ligger til påtalemyndigheten.']);
      var summaryText = lines.join('\n').trim();
      return {
        basis_details: basis,
        notes: avvik.length ? 'Egenrapport bør beskrive egne observasjoner, hvem som observerte hva, og hvilke beslag/bilder som dokumenterer funnene.' : 'Ingen avvik er registrert i kontrollpunktene ennå.',
        summary: summaryText,
        complaint_preview: summaryText,
        source_label: 'rask straffesaksmal'
      };
    }

    function renderSummaryDraftPreview(drafts, sourceLabel) {
      if (!summaryPreview) return;
      var label = sourceLabel || drafts.source_label || 'generert utkast';
      summaryPreview.innerHTML = '<strong>' + escapeHtml(String(label || 'Generert utkast')) + '</strong>'
        + '<div class="small muted">Teksten bygges raskt lokalt først og oppdateres automatisk når ferdig utkast er klart.</div>'
        + '<div class="preview-text">' + escapeHtml(drafts.complaint_preview || drafts.summary || '') + '</div>';
    }

    function applySummaryDrafts(drafts, sourceLabel, options) {
      options = options || {};
      if (!drafts) return;
      if (drafts.basis_details) basisDetails.value = drafts.basis_details;
      if (drafts.notes) notes.value = drafts.notes;
      if (drafts.summary) summary.value = drafts.summary;
      renderSummaryDraftPreview(drafts, sourceLabel);
      if (!options.silent) scheduleAutosave('Oppsummeringsutkast oppdatert');
    }

    function fetchSummaryDrafts(payload, options) {
      options = options || {};
      var cacheKey = summaryCacheKey(payload);
      var cached = loadCachedSummaryDraft(cacheKey);
      var now = Date.now();
      if (cached && cached.drafts && (now - Number(cached.ts || 0)) < 5 * 60 * 1000 && !options.forceRefresh) {
        return Promise.resolve(cached.drafts);
      }
      if (summaryRequestInFlight && summaryRequestInFlight.key === cacheKey) return summaryRequestInFlight.promise;
      var controller = typeof AbortController === 'function' ? new AbortController() : null;
      var timer = controller ? setTimeout(function () { try { controller.abort(); } catch (e) {} }, 12000) : null;
      var promise = fetch(root.dataset.summaryUrl, Object.assign(secureFetchOptions({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }), controller ? { signal: controller.signal } : {})).then(function (r) {
        if (!r.ok) throw new Error('Kunne ikke generere tekst akkurat nå.');
        return r.json();
      }).then(function (drafts) {
        storeCachedSummaryDraft(cacheKey, drafts);
        return drafts;
      }).finally(function () {
        if (timer) clearTimeout(timer);
        if (summaryRequestInFlight && summaryRequestInFlight.key === cacheKey) summaryRequestInFlight = null;
      });
      summaryRequestInFlight = { key: cacheKey, promise: promise };
      return promise;
    }

    var summaryWarmupTimer = null;
    function scheduleSummaryWarmup() {
      clearTimeout(summaryWarmupTimer);
      summaryWarmupTimer = setTimeout(function () {
        var payload = buildSummaryPayload();
        var cacheKey = summaryCacheKey(payload);
        if (loadCachedSummaryDraft(cacheKey)) return;
        idleLater(function () {
          fetchSummaryDrafts(payload, { forceRefresh: false }).catch(function () {});
        }, 900);
      }, 700);
    }

    function generateBasisText() {
      var basis = String((caseBasis && caseBasis.value) || 'patruljeobservasjon');
      var presetEl = document.getElementById('basis_preset');
      var preset = String((presetEl && presetEl.value) || 'auto');
      var speciesLabel = String((species && species.value) || (fisheryType && fisheryType.value) || 'aktuelt fiskeri').trim();
      var gearLabel = String((gearType && gearType.value) || 'redskap').trim();
      var controlTypeLabel = String((controlType && controlType.value) || 'fiskerikontroll').trim();
      var dateLabel = currentControlDateLabel();
      var area = areaContextForNarrative();
      var zonePlace = normalizedNearestPlaceText(latestZoneResult);
      var rawLocation = zonePlace || String((locationName && locationName.value) || '').trim();
      var placeLabel = rawLocation ? ('ved ' + rawLocation) : 'ved kontrollstedet';
      var themeParts = [controlTypeLabel, speciesLabel, gearLabel].filter(function (item) { return String(item || '').trim(); });
      var theme = themeParts.join(' / ') || 'fiskerikontroll';

      function autoPreset() {
        var gearLower = gearLabel.toLowerCase();
        var speciesLower = speciesLabel.toLowerCase();
        if (speciesLower.indexOf('hummer') !== -1) return 'patrol-hummer';
        if (gearLower.indexOf('samleteine') !== -1 || gearLower.indexOf('sanketeine') !== -1) return 'patrol-samleteine';
        if (gearLower.indexOf('garn') !== -1 || gearLower.indexOf('lenke') !== -1) return 'patrol-garnlenke';
        if (gearLower.indexOf('teine') !== -1 || gearLower.indexOf('ruse') !== -1) return 'patrol-fixed';
        return 'patrol-general';
      }

      if (preset === 'auto') preset = autoPreset();
      var opening = 'Den ' + dateLabel + ' gjennomførte patruljen stedlig fiskerikontroll ' + placeLabel + '.';
      var purposeBase = 'Formålet med patruljen var å kontrollere faktiske forhold på stedet og etterlevelse av regelverket for ' + theme.toLowerCase() + ', med særlig vekt på redskap, merking, fangst eller oppbevaring, involverte personer/fartøy og relevante område- eller redskapsbestemmelser.';
      var controlArea = area ? (' Kontrollen ble gjennomført i tilknytning til registrert område: ' + area + '.') : '';
      var basisNote = '';
      if (basis === 'tips') {
        basisNote = ' Patruljen ble rettet mot observerbare forhold på stedet. Teksten beskriver kontrollens formål, faktiske observasjoner, bevis og gjennomførte kontrollhandlinger.';
      } else if (basis === 'anmeldelse') {
        basisNote = ' Patruljen ble gjennomført som oppfølging av registrerte opplysninger, med formål å klarlegge faktum og sikre notoritet rundt observasjoner og bevis.';
      }
      var texts = {
        'patrol-general': opening + ' Patruljen var rettet mot ' + theme.toLowerCase() + '. ' + purposeBase + controlArea + basisNote,
        'patrol-fixed': opening + ' Patruljen var rettet mot kontroll av faststående fiskeredskap. Kontrollformålet var å dokumentere plassering, merking, røktingsforhold, fangst/oppbevaring, ansvarlig person/fartøy og om redskapen var brukt i samsvar med gjeldende område- og redskapsbestemmelser.' + controlArea + basisNote,
        'patrol-hummer': opening + ' Patruljen var rettet mot kontroll av hummerfiske. Kontrollformålet var å dokumentere deltakelse/påmelding der dette var relevant, deltakernummer, merking av vak og redskap, antall teiner, fluktåpninger/rømningshull, lengdemål, oppbevaring og eventuelle område- eller tidsbegrensninger.' + controlArea + basisNote,
        'patrol-samleteine': opening + ' Patruljen var rettet mot kontroll av samleteine/sanketeine. Kontrollformålet var å dokumentere merking, plassering, oppbevaring av hummer i sjø, lengdemåling og om vilkår for bruk av redskapen var oppfylt.' + controlArea + basisNote,
        'patrol-garnlenke': opening + ' Patruljen var rettet mot kontroll av garnlenke/lenkefiske. Kontrollformålet var å dokumentere start- og sluttposisjon, merking, ansvarlig person eller fartøy og om redskapen sto i samsvar med gjeldende område- og redskapsbestemmelser.' + controlArea + basisNote
      };

      basisDetails.value = texts[preset] || (opening + ' ' + purposeBase + controlArea + basisNote);
      scheduleAutosave('Standardtekst satt inn');
    }
    var btnGenerateBasis = document.getElementById('btn-generate-basis');
    if (btnGenerateBasis) btnGenerateBasis.addEventListener('click', function () {
      if (latitude && longitude && latitude.value && longitude.value && locationName && !String(locationName.value || '').trim()) {
        try {
          checkZone({ force: true }).then(generateBasisText).catch(generateBasisText);
          return;
        } catch (e) {}
      }
      generateBasisText();
    });
    var polishBasisBtn = document.getElementById('btn-polish-basis');
    if (polishBasisBtn) polishBasisBtn.addEventListener('click', function () {
      fetch('/api/text/polish', secureFetchOptions({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'basis', text: basisDetails.value, case_basis: caseBasis.value, source_name: basisSourceName.value || '', location: (normalizedNearestPlaceText(latestZoneResult) || (locationName && locationName.value) || '') })
      })).then(function (r) { return r.json(); }).then(function (payload) {
        if (payload && payload.text) { basisDetails.value = payload.text; scheduleAutosave('Rettet grunnlagstekst'); }
      }).catch(function () {});
    });


    var signatureModal = document.getElementById('signature-modal');
    var signatureCanvas = document.getElementById('signature-canvas');
    var signatureCtx = signatureCanvas ? signatureCanvas.getContext('2d') : null;
    var signatureCurrentField = '';
    var signatureDrawing = false;

    function signatureNameForWidget(widget) {
      var sourceId = widget ? widget.getAttribute('data-signature-name-source') : '';
      var source = sourceId ? document.getElementById(sourceId) : null;
      return String((source && source.value) || '').trim();
    }

    function signatureValue(field) {
      var input = field ? document.getElementById(field) : null;
      return input ? String(input.value || '').trim() : '';
    }

    function signatureDisplayText(value, fallbackName) {
      if (!value) return fallbackName ? (fallbackName + ' - ikke signert') : 'Ikke signert';
      try {
        var parsed = JSON.parse(value);
        if (parsed && parsed.signed_at) return (parsed.name || fallbackName || 'Signatur') + ' - signert ' + new Date(parsed.signed_at).toLocaleString('nb-NO');
        if (parsed && parsed.name) return parsed.name + ' - signert';
      } catch (e) {}
      return value;
    }

    function refreshSignatureWidgets() {
      Array.prototype.forEach.call(document.querySelectorAll('.signature-widget'), function (widget) {
        var field = widget.getAttribute('data-signature-field');
        var status = widget.querySelector('.signature-status');
        if (!status) return;
        status.textContent = signatureDisplayText(signatureValue(field), signatureNameForWidget(widget));
      });
    }

    function clearSignatureCanvas() {
      if (!signatureCtx || !signatureCanvas) return;
      signatureCtx.clearRect(0, 0, signatureCanvas.width, signatureCanvas.height);
      signatureCtx.fillStyle = '#ffffff';
      signatureCtx.fillRect(0, 0, signatureCanvas.width, signatureCanvas.height);
      signatureCtx.lineWidth = 3;
      signatureCtx.lineCap = 'round';
      signatureCtx.strokeStyle = '#10273d';
    }

    function signaturePoint(event) {
      var rect = signatureCanvas.getBoundingClientRect();
      var source = event.touches && event.touches.length ? event.touches[0] : event;
      return { x: (source.clientX - rect.left) * (signatureCanvas.width / rect.width), y: (source.clientY - rect.top) * (signatureCanvas.height / rect.height) };
    }

    function startSignature(event) {
      if (!signatureCtx) return;
      event.preventDefault();
      signatureDrawing = true;
      var pt = signaturePoint(event);
      signatureCtx.beginPath();
      signatureCtx.moveTo(pt.x, pt.y);
    }

    function moveSignature(event) {
      if (!signatureDrawing || !signatureCtx) return;
      event.preventDefault();
      var pt = signaturePoint(event);
      signatureCtx.lineTo(pt.x, pt.y);
      signatureCtx.stroke();
    }

    function endSignature(event) {
      if (!signatureDrawing) return;
      if (event) event.preventDefault();
      signatureDrawing = false;
    }

    function openSignatureWidget(widget) {
      signatureCurrentField = widget.getAttribute('data-signature-field') || '';
      if (!signatureCurrentField || !signatureModal || !signatureCanvas) return;
      var name = signatureNameForWidget(widget) || 'Navn ikke angitt';
      var nameLine = document.getElementById('signature-name-line');
      if (nameLine) nameLine.textContent = 'Navn: ' + name;
      clearSignatureCanvas();
      signatureModal.classList.remove('hidden');
      signatureModal.setAttribute('aria-hidden', 'false');
    }

    if (signatureCanvas) {
      signatureCanvas.addEventListener('mousedown', startSignature);
      signatureCanvas.addEventListener('mousemove', moveSignature);
      window.addEventListener('mouseup', endSignature);
      signatureCanvas.addEventListener('touchstart', startSignature, { passive: false });
      signatureCanvas.addEventListener('touchmove', moveSignature, { passive: false });
      signatureCanvas.addEventListener('touchend', endSignature, { passive: false });
      clearSignatureCanvas();
    }
    document.addEventListener('click', function (event) {
      var btn = event.target.closest('[data-signature-open]');
      if (!btn) return;
      var widget = btn.closest('.signature-widget');
      if (widget) openSignatureWidget(widget);
    });
    var closeSignatureBtn = document.getElementById('btn-signature-close');
    if (closeSignatureBtn) closeSignatureBtn.addEventListener('click', function () { if (signatureModal) { signatureModal.classList.add('hidden'); signatureModal.setAttribute('aria-hidden', 'true'); } });
    var clearSignatureBtn = document.getElementById('btn-signature-clear');
    if (clearSignatureBtn) clearSignatureBtn.addEventListener('click', clearSignatureCanvas);
    var saveSignatureBtn = document.getElementById('btn-signature-save');
    if (saveSignatureBtn) saveSignatureBtn.addEventListener('click', function () {
      if (!signatureCurrentField || !signatureCanvas) return;
      var widget = document.querySelector('.signature-widget[data-signature-field="' + signatureCurrentField + '"]');
      var input = document.getElementById(signatureCurrentField);
      if (!input) return;
      input.value = JSON.stringify({ name: signatureNameForWidget(widget) || '', signed_at: new Date().toISOString(), image: signatureCanvas.toDataURL('image/png'), method: 'touch' });
      refreshSignatureWidgets();
      if (signatureModal) { signatureModal.classList.add('hidden'); signatureModal.setAttribute('aria-hidden', 'true'); }
      scheduleAutosave('Signatur lagret');
    });
    refreshSignatureWidgets();

    var autosaveStatus = document.getElementById('autosave-status');
    function setAutosaveStatus(textLabel, mode) {
      if (!autosaveStatus) return;
      autosaveStatus.textContent = textLabel;
      autosaveStatus.classList.remove('is-saving', 'is-saved', 'is-error');
      if (mode) autosaveStatus.classList.add(mode);
    }

    function formFingerprint() {
      return JSON.stringify({
        case_basis: caseBasis.value || '', basis_source_name: basisSourceName.value || '', basis_details: basisDetails.value || '',
        control_type: controlType.value || '', fishery_type: fisheryType.value || '', species: species.value || '', gear_type: gearType.value || '',
        lat: latitude.value || '', lng: longitude.value || '', area_status: areaStatus.value || '', area_name: areaName.value || '', location_name: locationName.value || '',
        suspect_name: suspectName.value || '', suspect_address: suspectAddress.value || '', suspect_post_place: (suspectPostPlace ? suspectPostPlace.value : '') || '', suspect_phone: suspectPhone.value || '',
        hummer_participant_no: hummerParticipantNo.value || '', vessel_reg: vesselReg.value || '', radio_call_sign: radioCallSign.value || '',
        findings: findingsState, crew: crewState, external: externalActorsState, persons: personsState, interviews: interviewState, seizure_reports: seizureReportsState, notes: notes ? notes.value : '', summary: summary ? summary.value : '', hearing: hearingText ? hearingText.value : ''
      });
    }

    function scheduleAutosaveRetryIfPending() {
      if (!autosavePending || suspendAutosave) return;
      autosavePending = false;
      if (formFingerprint() === lastAutosaveFingerprint) return;
      if (autosaveTimer) window.clearTimeout(autosaveTimer);
      autosaveTimer = window.setTimeout(function () { performAutosave('kø'); }, 150);
    }

    function performAutosave(reason) {
      if (!root.dataset.autosaveUrl || suspendAutosave) return;
      if (autosaveInFlight) {
        autosavePending = true;
        persistLocalCaseDraft({ silent: true });
        return;
      }
      var fingerprint = formFingerprint();
      if (fingerprint === lastAutosaveFingerprint) return;
      autosaveInFlight = true;
      setAutosaveStatus('Lagrer …', 'is-saving');
      persistLocalCaseDraft({ silent: true });
      var formData = serializeCaseFormData();
      fetch(root.dataset.autosaveUrl, secureFetchOptions({ method: 'POST', body: formData }))
        .then(function (r) { return parseJsonResponse(r, 'Kunne ikke autosynke saken.'); })
        .then(function (payload) {
          applyServerSaveMeta(payload || {});
          lastAutosaveFingerprint = fingerprint;
          setAutosaveStatus('Synket', 'is-saved');
          markLocalCaseSynced(payload && payload.saved_at ? payload.saved_at : new Date().toISOString());
        })
        .catch(function (error) {
          if (isMissingServerCaseError(error) && createCaseUrl) {
            updateLocalCaseStatus('Serveren finner ikke saken. Oppretter ny serverkopi ...', true, { forceShow: true, showSync: true, syncing: true, showDiscard: true });
            createServerCaseFromLocalDraft({ force: true, redirectAfterCreate: false, silent: true });
            return;
          }
          if (error && Number(error.status || 0) === 409) {
            var payload = error.payload || {};
            if (payload.current_version) root.dataset.caseConflictVersion = String(payload.current_version);
            if (payload.current_updated_at) root.dataset.caseConflictUpdatedAt = String(payload.current_updated_at);
            autosavePending = false;
            persistLocalCaseDraft({ silent: true });
            updateLocalCaseStatus('Konflikt. Last inn eller behold lokal kopi.', true, { forceShow: true, showSync: true, showDiscard: true });
            setAutosaveStatus('Konflikt', 'is-error');
            return;
          }
          persistLocalCaseDraft({ silent: true });
          updateLocalCaseStatus('Lokalt. Ikke synket.', true, { forceShow: true, showSync: true, showDiscard: true });
          setAutosaveStatus('Lokalt', 'is-saved');
        })
        .finally(function () {
          autosaveInFlight = false;
          scheduleAutosaveRetryIfPending();
        });
    }

    function scheduleAutosave(reason) {
      if (suspendAutosave) {
        scheduleSummaryWarmup();
        return;
      }
      scheduleLocalCaseDraftSave(reason);
      if (autosaveTimer) window.clearTimeout(autosaveTimer);
      autosaveTimer = window.setTimeout(function () { performAutosave(reason); }, 900);
      scheduleSummaryWarmup();
    }

    var ruleRefreshTimer = null;
    function scheduleRuleRefresh(delay) {
      if (ruleRefreshTimer) window.clearTimeout(ruleRefreshTimer);
      ruleRefreshTimer = window.setTimeout(function () {
        loadRules();
      }, Math.max(0, Number(delay || 0)));
    }

    document.addEventListener('input', function (event) {
      var target = event.target;
      if (!target) return;
      if (target === latitude || target === longitude) syncPositionCoordinateSummary();
      if (target.form === form || target.getAttribute('form') === 'case-form' || target.closest('#case-form')) scheduleAutosave('Skjemadata endret');
    });
    document.addEventListener('change', function (event) {
      var target = event.target;
      if (!target) return;
      if (target.form === form || target.getAttribute('form') === 'case-form' || target.closest('#case-form')) scheduleAutosave('Skjemadata endret');
    });

    controlType.addEventListener('change', function () { syncOptions(); syncMapSelectionStatus(); updateCaseMap(); if (latitude.value && longitude.value) scheduleZoneCheck({ force: true }, 250); scheduleRuleRefresh(0); loadGearSummary(); });
    fisheryType.addEventListener('change', function () { if (!species.value || species.value === fisheryType.dataset.lastValue) species.value = fisheryType.value; fisheryType.dataset.lastValue = fisheryType.value; syncMapSelectionStatus(); updateCaseMap(); if (latitude.value && longitude.value) scheduleZoneCheck({ force: true }, 250); scheduleRuleRefresh(0); loadGearSummary(); });
    gearType.addEventListener('change', function () { syncMapSelectionStatus(); updateCaseMap(); if (latitude.value && longitude.value) scheduleZoneCheck({ force: true }, 250); scheduleRuleRefresh(0); loadGearSummary(); });
    species.addEventListener('input', function () { scheduleRuleRefresh(160); });
    species.addEventListener('change', function () { syncMapSelectionStatus(); updateCaseMap(); if (latitude.value && longitude.value) scheduleZoneCheck({ force: true }, 250); scheduleRuleRefresh(0); loadGearSummary(); });
    startTime.addEventListener('change', function () { scheduleRuleRefresh(0); });
    suspectNameCommercial.addEventListener('input', function () { suspectName.value = suspectNameCommercial.value; lookupName.value = suspectNameCommercial.value; updateExternalSearchLinks(); loadGearSummary(); });
    suspectName.addEventListener('input', function () { suspectNameCommercial.value = suspectName.value; lookupName.value = suspectName.value; updateExternalSearchLinks(); loadGearSummary(); });
    suspectAddress.addEventListener('input', function () { updateExternalSearchLinks(); loadGearSummary(); });
    suspectPhone.addEventListener('input', function () { updateExternalSearchLinks(); loadGearSummary(); });
    if (observedGearCount) observedGearCount.addEventListener('input', loadGearSummary);

    [lookupName, lookupIdentifier, lookupText, suspectPhone, suspectAddress, suspectPostPlace, hummerParticipantNo, vesselReg, radioCallSign, gearMarkerId].forEach(function (field) {
      if (!field) return;
      field.addEventListener('input', updateExternalSearchLinks);
      field.addEventListener('change', updateExternalSearchLinks);
    });

    if (controlLinkToolbar) {
      controlLinkToolbar.addEventListener('change', function (event) {
        if (event.target && event.target.id === 'control-link-mode') {
          controlLinkModeEnabled = Boolean(event.target.checked);
          setActiveControlLinkIndex(controlLinkActiveIndex);
          findingsInput.value = JSON.stringify(findingsState);
          renderFindings();
          scheduleAutosave(controlLinkModeEnabled ? 'Lenke aktivert' : 'Lenke deaktivert');
        }
      });
      controlLinkToolbar.addEventListener('click', function (event) {
        var tab = event.target.closest('.control-link-tab');
        if (tab) {
          event.preventDefault();
          setActiveControlLinkIndex(Number(tab.dataset.linkIndex || 0));
          findingsInput.value = JSON.stringify(findingsState);
          renderFindings();
          scheduleAutosave('Lenke valgt');
          return;
        }
        if (event.target && event.target.id === 'control-link-add') {
          event.preventDefault();
          controlLinkModeEnabled = true;
          controlLinkPageCount = Math.max(1, controlLinkPageCount || 1) + 1;
          setActiveControlLinkIndex(controlLinkPageCount - 1);
          findingsInput.value = JSON.stringify(findingsState);
          renderFindings();
          scheduleAutosave('Ny lenke lagt til');
        }
      });
    }

    findingsList.addEventListener('change', function (event) {
      var card = event.target.closest('.finding-card');
      if (!card) return;
      var idx = Number(card.dataset.index);
      var item = findingsState[idx];
      if (event.target.classList.contains('finding-status')) {
        findingsState[idx].status = event.target.value;
        if (event.target.value === 'avvik') {
          findingsState[idx].active_deviation_link_index = controlLinkModeEnabled ? controlLinkActiveIndex : Number(findingsState[idx].active_deviation_link_index || 0);
          var autoRows = ensureDeviationState(findingsState[idx]);
          if (!autoRows.length) autoRows.push(defaultDeviationRow(findingsState[idx]));
          autoRows.forEach(function (row) { if (row && (!isFinite(Number(row.link_group_index)) || Number(row.link_group_index) < 0)) row.link_group_index = findingsState[idx].active_deviation_link_index || 0; });
          normalizeDeviationLinkGroups(findingsState[idx]);
          syncDeviationDefaults(findingsState[idx]);
          selectedInlineEvidenceTarget = { finding_key: findingsState[idx].key || '', seizure_ref: (autoRows[0] && autoRows[0].seizure_ref) || '' };
          inlineEvidenceFeedback = 'Avvik valgt. Legg til eller koble redskap/beslag.';
        } else {
          findingsState[idx].deviation_units = findingsState[idx].deviation_units || [];
        }
        findingsInput.value = JSON.stringify(findingsState);
        renderFindings();
        if (event.target.value === 'avvik') flashActiveDeviationRow();
        scheduleAutosave('Kontrollpunktstatus endret');
        return;
      }
      if (event.target.classList.contains('measurement-existing-gear')) {
        var mRowElChange = event.target.closest('.measurement-row');
        if (!mRowElChange) return;
        var mIdxChange = Number(mRowElChange.dataset.measureIndex);
        var mRowsChange = ensureMeasurementState(item);
        mRowsChange[mIdxChange] = mRowsChange[mIdxChange] || defaultMeasurementRow();
        var mRowChange = mRowsChange[mIdxChange];
        var selectedMeasurementRef = String(event.target.value || '').trim();
        mRowChange.linked_seizure_ref = selectedMeasurementRef;
        if (selectedMeasurementRef) {
          var measurementLinked = findDeviationUnitByRef(selectedMeasurementRef, mRowChange);
          mRowChange.seizure_ref = selectedMeasurementRef;
          mRowChange.reference = selectedMeasurementRef;
          if (measurementLinked && measurementLinked.position && !mRowChange.position) mRowChange.position = measurementLinked.position;
        } else {
          mRowChange.linked_seizure_ref = '';
          mRowChange.seizure_ref = '';
          mRowChange.reference = '';
        }
        syncMeasurementDefaults(item);
        findingsInput.value = JSON.stringify(findingsState);
        renderFindings();
        scheduleAutosave('Måling koblet til beslag/redskap');
        return;
      }
      if (event.target.classList.contains('marker-is-linked')) {
        var posChange = ensureMarkerState(item);
        posChange.is_linked = Boolean(event.target.checked);
        if (!posChange.is_linked) { posChange.start = ''; posChange.end = ''; }
        item.marker_summary = markerSummaryText(item);
        findingsInput.value = JSON.stringify(findingsState);
        renderFindings();
        scheduleAutosave('Lenkestatus for redskap endret');
        return;
      }
      if (event.target.classList.contains('deviation-existing-gear') || event.target.classList.contains('deviation-gear-kind')) {
        var dRowElChange = event.target.closest('.deviation-row');
        if (!dRowElChange) return;
        var dIdxChange = Number(dRowElChange.dataset.devIndex);
        var dRowsChange = ensureDeviationState(item);
        dRowsChange[dIdxChange] = dRowsChange[dIdxChange] || defaultDeviationRow(item);
        var rowChange = dRowsChange[dIdxChange];
        var previousSeizureRef = rowChange.seizure_ref || '';
        if (event.target.classList.contains('deviation-existing-gear')) {
          var selectedRef = String(event.target.value || '').trim();
          rowChange.linked_seizure_ref = selectedRef;
          if (selectedRef) {
            var linkedUnit = findDeviationUnitByRef(selectedRef, rowChange);
            rowChange.seizure_ref = selectedRef;
            if (linkedUnit && linkedUnit.gear_kind) rowChange.gear_kind = normalizeDeviationGearKind(linkedUnit.gear_kind);
            if (linkedUnit && linkedUnit.gear_ref) rowChange.gear_ref = linkedUnit.gear_ref;
          } else {
            rowChange.linked_seizure_ref = '';
            rowChange.seizure_ref = '';
          }
        }
        if (event.target.classList.contains('deviation-gear-kind')) {
          rowChange.gear_kind = normalizeDeviationGearKind(event.target.value || rowChange.gear_kind || defaultDeviationGearKind());
        }
        syncDeviationDefaults(item);
        if (selectedInlineEvidenceTarget && String(selectedInlineEvidenceTarget.finding_key || '') === String(item.key || '') && String(selectedInlineEvidenceTarget.seizure_ref || '') === String(previousSeizureRef || '')) {
          selectedInlineEvidenceTarget.seizure_ref = rowChange.seizure_ref || previousSeizureRef || '';
          evidenceCaption.value = rowChange.violation || evidenceCaption.value;
          evidenceReason.value = rowChange.violation || evidenceReason.value;
          updateSelectedFinding(item, rowChange, { showStepFive: false });
        }
        findingsInput.value = JSON.stringify(findingsState);
        renderFindings();
        scheduleAutosave(event.target.classList.contains('deviation-existing-gear') ? 'Redskap koblet til tidligere avvik' : 'Redskapstype oppdatert');
        return;
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
      if (event.target.classList.contains('measurement-reference') || event.target.classList.contains('measurement-length') || event.target.classList.contains('measurement-note') || event.target.classList.contains('measurement-position')) {
        var rowEl = event.target.closest('.measurement-row');
        if (!rowEl) return;
        var mIdx = Number(rowEl.dataset.measureIndex);
        var rows = ensureMeasurementState(item);
        rows[mIdx] = rows[mIdx] || defaultMeasurementRow();
        rows[mIdx].reference = (rowEl.querySelector('.measurement-reference') || {}).value || rows[mIdx].reference || '';
        rows[mIdx].length_cm = (rowEl.querySelector('.measurement-length') || {}).value || '';
        rows[mIdx].position = (rowEl.querySelector('.measurement-position') || {}).value || '';
        rows[mIdx].note = (rowEl.querySelector('.measurement-note') || {}).value || '';
        syncMeasurementDefaults(item);
        var currentMeasurement = rows[mIdx] || {};
        var preview = card.querySelector('.finding-measurements .structured-preview');
        if (preview) preview.textContent = item.measurement_summary || measurementSummaryText(item);
        var refInput = rowEl.querySelector('.measurement-reference');
        if (refInput) refInput.value = currentMeasurement.reference || currentMeasurement.seizure_ref || '';
        var posInput = rowEl.querySelector('.measurement-position');
        if (posInput) posInput.value = currentMeasurement.position || '';
        var evalBox = rowEl.querySelector('.measurement-evaluation');
        if (evalBox) {
          evalBox.textContent = currentMeasurement.delta_text || 'Legg inn måling i cm for automatisk vurdering.';
          evalBox.classList.remove('is-alert', 'is-ok');
          if (currentMeasurement.measurement_state === 'under_min' || currentMeasurement.measurement_state === 'over_max') evalBox.classList.add('is-alert');
          else if (currentMeasurement.measurement_state === 'ok') evalBox.classList.add('is-ok');
        }
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
      if (event.target.classList.contains('deviation-link-start') || event.target.classList.contains('deviation-link-end') || event.target.classList.contains('deviation-link-note')) {
        var linkInputRow = event.target.closest('.deviation-row');
        var linkInputTab = event.target.closest('.deviation-link-tab');
        if (!linkInputRow || !linkInputTab) return;
        var linkInputDevIdx = Number(linkInputRow.dataset.devIndex);
        var linkInputIdx = Number(linkInputTab.dataset.linkIndex);
        var linkInputRows = ensureDeviationState(item);
        linkInputRows[linkInputDevIdx] = linkInputRows[linkInputDevIdx] || defaultDeviationRow(item);
        var linkInputEntry = ensureDeviationLinks(linkInputRows[linkInputDevIdx])[linkInputIdx] || defaultDeviationLink();
        linkInputEntry.start = (linkInputTab.querySelector('.deviation-link-start') || {}).value || '';
        linkInputEntry.end = (linkInputTab.querySelector('.deviation-link-end') || {}).value || '';
        linkInputEntry.note = (linkInputTab.querySelector('.deviation-link-note') || {}).value || '';
        ensureDeviationLinks(linkInputRows[linkInputDevIdx])[linkInputIdx] = linkInputEntry;
        syncDeviationDefaults(item);
        item.deviation_summary = deviationSummaryText(item);
        var linkPreview = card.querySelector('.finding-deviations .structured-preview');
        if (linkPreview) linkPreview.textContent = item.deviation_summary;
        findingsInput.value = JSON.stringify(findingsState);
        scheduleAutosave('Lenke oppdatert');
        return;
      }
      if (event.target.classList.contains('deviation-quantity') || event.target.classList.contains('deviation-position') || event.target.classList.contains('deviation-violation') || event.target.classList.contains('deviation-note')) {
        var dRowEl = event.target.closest('.deviation-row');
        if (!dRowEl) return;
        var dIdx = Number(dRowEl.dataset.devIndex);
        var dRows = ensureDeviationState(item);
        dRows[dIdx] = dRows[dIdx] || defaultDeviationRow(item);
        var currentRow = dRows[dIdx];
        var prevSeizureRef = currentRow.seizure_ref || '';
        currentRow.quantity = (dRowEl.querySelector('.deviation-quantity') || {}).value || '';
        currentRow.position = (dRowEl.querySelector('.deviation-position') || {}).value || '';
        currentRow.violation = (dRowEl.querySelector('.deviation-violation') || {}).value || '';
        currentRow.note = (dRowEl.querySelector('.deviation-note') || {}).value || '';
        syncDeviationDefaults(item);
        if (selectedInlineEvidenceTarget && String(selectedInlineEvidenceTarget.finding_key || '') === String(item.key || '') && String(selectedInlineEvidenceTarget.seizure_ref || '') === String(prevSeizureRef || '')) {
          selectedInlineEvidenceTarget.seizure_ref = currentRow.seizure_ref || prevSeizureRef || '';
          evidenceCaption.value = currentRow.violation || evidenceCaption.value;
          evidenceReason.value = currentRow.violation || evidenceReason.value;
          updateSelectedFinding(item, currentRow, { showStepFive: false });
        }
        item.deviation_summary = deviationSummaryText(item);
        var dp = card.querySelector('.finding-deviations .structured-preview');
        if (dp) dp.textContent = item.deviation_summary;
        findingsInput.value = JSON.stringify(findingsState);
        scheduleAutosave('Avviksrad oppdatert');
      }
    });
    findingsList.addEventListener('click', function (event) {
      var rawTarget = event.target;
      var actionTarget = rawTarget && rawTarget.closest ? rawTarget.closest('button, input, select, textarea, a') : rawTarget;
      if (actionTarget) event.target = actionTarget;
      var card = rawTarget && rawTarget.closest ? rawTarget.closest('.finding-card') : null;
      if (!card) return;
      var idx = Number(card.dataset.index);
      var item = findingsState[idx];
      if (!item) return;
      if (event.target.classList.contains('help-toggle')) {
        var box = card.querySelector('.help-text');
        if (box) box.classList.toggle('hidden');
      }
      if (event.target.classList.contains('finding-evidence-btn')) {
        updateSelectedFinding(item);
      }
      if (event.target.classList.contains('measurement-add')) {
        var measurementRows = ensureMeasurementState(item);
        measurementRows.push(defaultMeasurementRow());
        syncMeasurementDefaults(item);
        renderFindings();
        scheduleAutosave('Ny lengdemåling lagt til');
      }
      if (event.target.classList.contains('measurement-position-fill')) {
        var measurePosRow = event.target.closest('.measurement-row');
        var measureIdx = Number(measurePosRow.dataset.measureIndex);
        var measureRows = ensureMeasurementState(item);
        measureRows[measureIdx] = measureRows[measureIdx] || defaultMeasurementRow();
        measureRows[measureIdx].position = currentCoordText();
        syncMeasurementDefaults(item);
        renderFindings();
        scheduleAutosave('Måleposisjon satt');
        return;
      }
      if (event.target.classList.contains('measurement-remove')) {
        var rowEl = event.target.closest('.measurement-row');
        var mIdx = Number(rowEl.dataset.measureIndex);
        ensureMeasurementState(item).splice(mIdx, 1);
        syncMeasurementDefaults(item);
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
      if (event.target.classList.contains('deviation-group-tab')) {
        event.preventDefault();
        item.status = 'avvik';
        findingsState[idx].status = 'avvik';
        item.active_deviation_link_index = Number(event.target.dataset.linkIndex || 0);
        normalizeDeviationLinkGroups(item);
        findingsInput.value = JSON.stringify(findingsState);
        renderFindings();
        scheduleAutosave('Aktiv lenke valgt');
        return;
      }
      if (event.target.classList.contains('deviation-group-add')) {
        event.preventDefault();
        item.status = 'avvik';
        findingsState[idx].status = 'avvik';
        var groupRows = ensureDeviationState(item);
        var groupState = normalizeDeviationLinkGroups(item);
        item.active_deviation_link_index = groupState.count;
        var groupRow = defaultDeviationRow(item);
        groupRow.link_group_index = item.active_deviation_link_index;
        groupRows.push(groupRow);
        syncDeviationDefaults(item);
        item.deviation_summary = deviationSummaryText(item);
        findingsInput.value = JSON.stringify(findingsState);
        setInlineEvidenceTarget(item, groupRow, 'Ny lenke er opprettet med egen avviksrad.');
        scheduleAutosave('Ny lenke lagt til avvik');
        return;
      }
      if (event.target.classList.contains('deviation-add-group')) {
        event.preventDefault();
        item.status = 'avvik';
        findingsState[idx].status = 'avvik';
        normalizeDeviationLinkGroups(item);
        var activeGroup = Number(item.active_deviation_link_index || 0);
        var rowsForGroup = ensureDeviationState(item);
        var rowForGroup = defaultDeviationRow(item);
        rowForGroup.link_group_index = activeGroup;
        rowsForGroup.push(rowForGroup);
        syncDeviationDefaults(item);
        item.deviation_summary = deviationSummaryText(item);
        findingsInput.value = JSON.stringify(findingsState);
        setInlineEvidenceTarget(item, rowForGroup, 'Nytt avvik er lagt til på valgt lenke.');
        scheduleAutosave('Nytt avvik lagt til lenke');
        return;
      }
      if (event.target.classList.contains('deviation-add') || event.target.classList.contains('deviation-add-top') || event.target.classList.contains('deviation-add-body')) {
        event.preventDefault();
        item.status = 'avvik';
        findingsState[idx].status = 'avvik';
        var addState = normalizeDeviationLinkGroups(item);
        var addRows = ensureDeviationState(item);
        var activeLinkGroup = Number(controlLinkModeEnabled ? controlLinkActiveIndex : (item.active_deviation_link_index || addState.activeIndex || 0));
        if (!isFinite(activeLinkGroup) || activeLinkGroup < 0) activeLinkGroup = 0;
        var newRow = defaultDeviationRow(item);
        newRow.link_group_index = activeLinkGroup;
        addRows.push(newRow);
        syncDeviationDefaults(item);
        item.deviation_summary = deviationSummaryText(item);
        findingsInput.value = JSON.stringify(findingsState);
        setInlineEvidenceTarget(item, newRow, 'Redskap/beslag lagt til. Fyll korttekst, merknad og bilde ved behov.');
        scheduleAutosave('Ny avviksrad lagt til');
        return;
      }
      if (event.target.classList.contains('deviation-remove')) {
        var dRow = event.target.closest('.deviation-row');
        var dIdx = Number(dRow.dataset.devIndex);
        var rows = ensureDeviationState(item);
        var removed = rows[dIdx] || null;
        var removedWasSelected = removed ? selectedInlineTargetMatches(item, removed) : false;
        rows.splice(dIdx, 1);
        syncDeviationDefaults(item);
        item.deviation_summary = deviationSummaryText(item);
        if (removedWasSelected) {
          var replacement = rows[Math.min(dIdx, rows.length - 1)] || null;
          if (replacement) setInlineEvidenceTarget(item, replacement, 'Valgt rad ble fjernet. Neste rad er valgt for bildebevis.');
          else {
            selectedInlineEvidenceTarget = null;
            inlineEvidenceFeedback = '';
            resetSelectedFinding();
            renderFindings();
          }
        } else {
          renderFindings();
        }
        scheduleAutosave('Avviksrad fjernet');
        return;
      }
      if (event.target.classList.contains('deviation-link-tab-btn')) {
        var linkTabRow = event.target.closest('.deviation-row');
        var linkTabIdx = Number(linkTabRow.dataset.devIndex);
        var linkTabRows = ensureDeviationState(item);
        linkTabRows[linkTabIdx] = linkTabRows[linkTabIdx] || defaultDeviationRow(item);
        linkTabRows[linkTabIdx].active_link_index = Number(event.target.dataset.linkIndex || 0);
        findingsInput.value = JSON.stringify(findingsState);
        renderFindings();
        return;
      }
      if (event.target.classList.contains('deviation-link-add')) {
        var linkAddRow = event.target.closest('.deviation-row');
        var linkAddIdx = Number(linkAddRow.dataset.devIndex);
        var linkAddRows = ensureDeviationState(item);
        linkAddRows[linkAddIdx] = linkAddRows[linkAddIdx] || defaultDeviationRow(item);
        var newLinks = ensureDeviationLinks(linkAddRows[linkAddIdx]);
        newLinks.push(defaultDeviationLink());
        linkAddRows[linkAddIdx].active_link_index = newLinks.length - 1;
        syncDeviationDefaults(item);
        renderFindings();
        scheduleAutosave('Lenke lagt til avvik');
        return;
      }
      if (event.target.classList.contains('deviation-link-remove')) {
        var linkRemoveRow = event.target.closest('.deviation-row');
        var linkRemoveTab = event.target.closest('.deviation-link-tab');
        var linkRemoveDevIdx = Number(linkRemoveRow.dataset.devIndex);
        var linkRemoveIdx = Number(linkRemoveTab.dataset.linkIndex);
        var linkRemoveRows = ensureDeviationState(item);
        linkRemoveRows[linkRemoveDevIdx] = linkRemoveRows[linkRemoveDevIdx] || defaultDeviationRow(item);
        ensureDeviationLinks(linkRemoveRows[linkRemoveDevIdx]).splice(linkRemoveIdx, 1);
        var remainingLinks = ensureDeviationLinks(linkRemoveRows[linkRemoveDevIdx]);
        linkRemoveRows[linkRemoveDevIdx].active_link_index = Math.min(linkRemoveIdx, Math.max(0, remainingLinks.length - 1));
        syncDeviationDefaults(item);
        renderFindings();
        scheduleAutosave('Lenke fjernet fra avvik');
        return;
      }
      if (event.target.classList.contains('deviation-link-start-fill') || event.target.classList.contains('deviation-link-end-fill')) {
        var linkFillRow = event.target.closest('.deviation-row');
        var linkFillTab = event.target.closest('.deviation-link-tab');
        var linkFillDevIdx = Number(linkFillRow.dataset.devIndex);
        var linkFillIdx = Number(linkFillTab.dataset.linkIndex);
        var linkFillRows = ensureDeviationState(item);
        linkFillRows[linkFillDevIdx] = linkFillRows[linkFillDevIdx] || defaultDeviationRow(item);
        var linkEntry = ensureDeviationLinks(linkFillRows[linkFillDevIdx])[linkFillIdx] || defaultDeviationLink();
        if (event.target.classList.contains('deviation-link-start-fill')) linkEntry.start = currentCoordText();
        else linkEntry.end = currentCoordText();
        ensureDeviationLinks(linkFillRows[linkFillDevIdx])[linkFillIdx] = linkEntry;
        syncDeviationDefaults(item);
        renderFindings();
        scheduleAutosave('Lenkeposisjon satt');
        return;
      }
      if (event.target.classList.contains('deviation-position-fill')) {
        var devPosRow = event.target.closest('.deviation-row');
        var devPosIdx = Number(devPosRow.dataset.devIndex);
        var devPosRows = ensureDeviationState(item);
        devPosRows[devPosIdx] = devPosRows[devPosIdx] || defaultDeviationRow(item);
        devPosRows[devPosIdx].position = currentCoordText();
        syncDeviationDefaults(item);
        item.deviation_summary = deviationSummaryText(item);
        findingsInput.value = JSON.stringify(findingsState);
        renderFindings();
        scheduleAutosave('Beslagsposisjon satt');
        return;
      }
      if (event.target.classList.contains('deviation-evidence-link')) {
        var dRow2 = event.target.closest('.deviation-row');
        var dIdx2 = Number(dRow2.dataset.devIndex);
        var chosen = ensureDeviationState(item)[dIdx2] || null;
        setInlineEvidenceTarget(item, chosen, 'Valgt avviksrad er klar for bilde.');
        return;
      }
      if (event.target.classList.contains('deviation-camera') || event.target.classList.contains('deviation-file')) {
        var photoRow = event.target.closest('.deviation-row');
        var photoIdx = Number(photoRow.dataset.devIndex);
        var photoTarget = ensureDeviationState(item)[photoIdx] || null;
        setInlineEvidenceTarget(item, photoTarget, event.target.classList.contains('deviation-camera') ? 'Kamera \u00e5pnes for valgt beslag.' : 'Velg bilde for valgt beslag.');
        if (event.target.classList.contains('deviation-camera')) {
          openCameraCapture({
            title: 'Kamera for bildebevis',
            description: 'Ta bilde for valgt beslag.',
            fallbackInput: inlineEvidenceCameraInput,
            filenamePrefix: 'bildebevis',
            onFile: function (file) { uploadInlineEvidenceFile(file); }
          });
        } else if (inlineEvidenceFileInput) {
          inlineEvidenceFileInput.click();
        }
        return;
      }
      if (event.target.classList.contains('inline-evidence-camera')) {
        var activeRow = preferredDeviationRow(item);
        setInlineEvidenceTarget(item, activeRow, 'Kamera åpnes for valgt avviksrad.');
        openCameraCapture({
          title: 'Kamera for bildebevis',
          description: 'Ta bildebevis direkte for valgt teine / redskap. Bildet lagres i illustrasjonsrapporten uten at du forlater kontrollpunktet.',
          fallbackInput: inlineEvidenceCameraInput,
          filenamePrefix: 'bildebevis',
          onFile: function (file) { uploadInlineEvidenceFile(file); }
        });
        return;
      }
      if (event.target.classList.contains('inline-evidence-file')) {
        var activeRow2 = preferredDeviationRow(item);
        setInlineEvidenceTarget(item, activeRow2, 'Velg bildefil for valgt avviksrad.');
        if (inlineEvidenceFileInput) inlineEvidenceFileInput.click();
        return;
      }
    });

    document.getElementById('btn-clear-evidence-target').addEventListener('click', function () {
      selectedInlineEvidenceTarget = null;
      inlineEvidenceFeedback = '';
      evidenceCaption.value = '';
      evidenceReason.value = '';
      resetSelectedFinding();
      renderFindings();
    });

    if (btnSyncLocalMedia) {
      btnSyncLocalMedia.addEventListener('click', function () {
        updateLocalMediaStatus('Starter synk av lokale vedlegg ...');
        syncLocalMediaQueue({ force: true });
      });
    }

    function bindLocalMediaActions(container, kindLabel) {
      if (!container) return;
      container.addEventListener('click', function (event) {
        var syncButton = event.target.closest('[data-local-sync]');
        if (syncButton) {
          updateLocalMediaStatus('Starter synk av valgt ' + kindLabel + ' ...');
          syncLocalMediaQueue({ force: true, onlyId: syncButton.getAttribute('data-local-sync') || '' });
          return;
        }
        var deleteButton = event.target.closest('[data-local-delete]');
        if (deleteButton) {
          var entryId = deleteButton.getAttribute('data-local-delete') || '';
          if (!window.confirm('Fjerne denne lokale ' + kindLabel + ' fra enheten?')) return;
          removeEvidenceStateEntry(entryId);
          if (localMediaSupported()) {
            LocalMedia.remove(entryId).catch(function () { return true; }).then(function () {
              updateLocalMediaStatus();
            });
          }
        }
      });
    }

    bindLocalMediaActions(evidenceGrid, 'bildefilen');
    bindLocalMediaActions(audioList, 'lydfilen');

    if (evidenceUploadForm) {
      evidenceUploadForm.addEventListener('submit', function (event) {
        event.preventDefault();
        if (!evidenceFileInput || !evidenceFileInput.files || !evidenceFileInput.files[0]) {
          updateLocalMediaStatus('Velg et bilde først.', true);
          return;
        }
        var chosenFile = evidenceFileInput.files[0];
        queueLocalEvidenceUpload(chosenFile, {
          caption: evidenceCaption.value || 'Illustrasjon',
          finding_key: evidenceFindingKey.value || '',
          law_text: evidenceLawText.value || '',
          violation_reason: evidenceReason.value || '',
          seizure_ref: evidenceSeizureRef ? (evidenceSeizureRef.value || '') : ''
        }, {
          sourceKind: 'illustration',
          statusMessage: 'Illustrasjon lokalt. Synk venter.',
          autosaveMessage: 'Illustrasjonsbilde lagret lokalt'
        }).then(function (entry) {
          if (!entry) return;
          evidenceFileInput.value = '';
          if (!entry.local_pending) {
            updateLocalMediaStatus('Illustrasjonsbildet er lagret i saken.');
          }
        }).catch(function (err) {
          updateLocalMediaStatus(err && err.message ? err.message : 'Kunne ikke lagre illustrasjonsbildet.', true);
        });
      });
    }

    function serializeInterviews() {
      if (interviewInput) interviewInput.value = JSON.stringify(interviewState);
    }

    function interviewNotConductedReasonText() {
      return String((interviewNotConductedReason && interviewNotConductedReason.value) || 'Ikke fått kontakt med vedkommende.').trim() || 'Ikke fått kontakt med vedkommende.';
    }

    function syncInterviewDisabledState() {
      var disabled = !!(interviewNotConducted && interviewNotConducted.checked);
      var list = document.getElementById('interview-list');
      var addBtn = document.getElementById('btn-add-interview');
      var syncBtn = document.getElementById('btn-sync-interviews');
      if (interviewNotConductedReason && disabled && !String(interviewNotConductedReason.value || '').trim()) interviewNotConductedReason.value = 'Ikke fått kontakt med vedkommende.';
      if (list) list.classList.toggle('muted-disabled', disabled);
      if (addBtn) addBtn.disabled = disabled;
      if (syncBtn) syncBtn.disabled = disabled;
      if (hearingText && disabled) hearingText.value = '';
      serializeInterviews();
    }

    function buildInterviewCombinedText() {
      if (interviewNotConducted && interviewNotConducted.checked) return '';
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
        syncInterviewDisabledState();
        return;
      }
      wrap.innerHTML = interviewState.map(function (entry, idx) {
        return [
          '<article class="interview-card" data-index="' + idx + '">',
          '<div class="grid-two compact-grid-form">',
          '<label><span>Navn</span><input class="interview-name" value="' + escapeHtml(entry.name || '') + '" /></label>',
          '<label><span>Rolle</span><select class="interview-role">' + ['Mistenkt', 'Vitne', 'Annen forklaring'].map(function (role) { return '<option value="' + role + '" ' + (role === (entry.role || 'Mistenkt') ? 'selected' : '') + '>' + role + '</option>'; }).join('') + '</select></label>',
          '<label><span>Avhørsmåte</span><input class="interview-method" value="' + escapeHtml(entry.method || 'Telefon / på stedet') + '" /></label>',
          '<label><span>Sted</span><input class="interview-place" value="' + escapeHtml(entry.place || locationName.value || '') + '" /></label>',
          '<label><span>Start</span><input class="interview-start" type="datetime-local" value="' + escapeHtml(entry.start || startTime.value || '') + '" /></label>',
          '<label><span>Slutt</span><input class="interview-end" type="datetime-local" value="' + escapeHtml(entry.end || endTime.value || '') + '" /></label>',
          '<label class="span-2"><span>Transkripsjon / forklaring</span><textarea class="interview-transcript" rows="6">' + escapeHtml(entry.transcript || '') + '</textarea></label>',
          '<label class="span-2"><span>Sammendrag</span><textarea class="interview-summary" rows="3">' + escapeHtml(entry.summary || '') + '</textarea></label>',
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
      syncInterviewDisabledState();
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
      syncInterviewDisabledState();
    }


    function avvikItemsForInterview() {
      return (findingsState || []).filter(function (item) {
        return item && String(item.status || '').toLowerCase() === 'avvik';
      });
    }

    function describeFindingForInterview(item, idx) {
      var label = item.label || item.key || ('avvik ' + idx);
      var law = item.law_text || item.help_text || item.source_ref || '';
      var note = item.notes || item.auto_note || item.summary_text || '';
      var rows = [];
      rows.push('Lenke ' + idx + ': ' + label);
      if (note) rows.push('   - Observasjon som skal avklares: ' + note);
      if (law) rows.push('   - Aktuelt regelgrunnlag i saken: ' + law);
      var deviations = ensureDeviationState(item) || [];
      if (deviations.length) {
        rows.push('   - Tilknyttede beslag/redskap:');
        deviations.forEach(function (row) {
          var ref = row.seizure_ref || row.gear_ref || 'uten beslagnummer';
          var violation = row.violation || 'avvik registrert';
          var position = row.position ? (' Posisjon: ' + row.position + '.') : '';
          rows.push('     * ' + ref + ': ' + violation + '.' + position);
        });
      }
      rows.push('   - Forklar tilknytning til redskap, fangst, fartøy, person eller aktivitet.');
      rows.push('   - Forklar når, hvor og av hvem redskapet ble satt, brukt, røktet eller tatt opp.');
      rows.push('   - Forklar hvilken kunnskap vedkommende hadde om område, fredning, redskapskrav, merkekrav, minstemål/maksimalmål eller andre relevante regler.');
      rows.push('   - Avklar om det finnes kvittering, tillatelse, bilder, sporingsdata, vitner eller annen dokumentasjon som bør sikres.');
      return rows.join('\n');
    }

    function buildInterviewGuidanceText() {
      var persons = [];
      if (suspectName.value || suspectNameCommercial.value) persons.push('Mistenkt/hovedperson: ' + (suspectName.value || suspectNameCommercial.value));
      (personsState || []).forEach(function (p) { if (p && p.name) persons.push((p.role || 'Person') + ': ' + p.name); });
      var avvik = avvikItemsForInterview();
      var place = String((normalizedNearestPlaceText(latestZoneResult) || (locationName && locationName.value) || 'kontrollstedet')).trim();
      if (place.indexOf(' - ') !== -1) place = place.split(' - ')[0].trim() || place;
      var topic = [controlType && controlType.value, species && species.value || fisheryType && fisheryType.value, gearType && gearType.value].filter(function (x) { return String(x || '').trim(); }).join(' / ') || 'fiskerikontroll';
      var lines = [];
      lines.push('KREATIV-basert avhørsdisposisjon');
      lines.push('');
      lines.push('1. Forberedelser');
      lines.push('- Avklar bevistema for ' + topic.toLowerCase() + ' ved ' + place + '.');
      lines.push('- Gjør klar aktuelle bilder, kart, beslag, målinger og dokumenter som kan forevises ved behov.');
      lines.push('- Avklar hypoteser og hvilke objektive opplysninger som både taler for og mot mulig lovbrudd.');
      lines.push('');
      lines.push('2. Kontaktetablering og formalia');
      lines.push('- Start lydopptak og noter tid, sted/metode, avhører og hvem som avhøres.');
      lines.push('- Gjør kjent hva saken gjelder og hvilket forhold personen avhøres om.');
      lines.push('- Gjør kjent retten til ikke å forklare seg for Kystvakten/politiet.');
      lines.push('- Gjør kjent retten til forsvarer på ethvert trinn, også under Kystvaktens avhør.');
      lines.push('- Avklar behov for tolk og noter om rettighetene er forstått.');
      lines.push('- Orienter om at en uforbeholden tilståelse kan få betydning ved straffeutmålingen.');
      lines.push('- Orienter om at falsk anklage eller uriktig forklaring som kan medføre straffeforfølgelse av en annen person, er straffbart.');
      lines.push('');
      lines.push('3. Fri forklaring');
      lines.push('- Be personen forklare med egne ord hva som skjedde, hvilken rolle vedkommende hadde, og hva vedkommende mener er relevant for saken.');
      lines.push('- La forklaringen komme før detaljerte kontrollspørsmål og før eventuell bevispresentasjon.');
      lines.push('');
      lines.push('4. Sondering / tema for kontrollpunkt');
      if (!avvik.length) {
        lines.push('- Ingen avvik er registrert. Vurder likevel spørsmål om identitet, eierskap, ansvar for redskap/fangst og kontrollsted dersom forklaring er nødvendig.');
      } else {
        avvik.forEach(function (item, idx) { lines.push(describeFindingForInterview(item, idx + 1)); lines.push(''); });
      }
      lines.push('5. Avslutning');
      lines.push('- Spør om det er etterforskingsskritt, dokumentasjon eller personer den avhørte mener Kystvakten bør følge opp.');
      lines.push('- Gå gjennom sammendraget og noter om forklaringen godtas, korrigeres eller ikke ønskes signert.');
      lines.push('- Avklar straffeskyld bare der dette er naturlig og etter at saken/faktum er gjennomgått.');
      lines.push('- Avklar samtykke til fortsatt beslag og eventuell inndragning der dette er aktuelt.');
      lines.push('');
      lines.push('6. Evaluering');
      lines.push('- Noter kort om avhøret fulgte planen, om nye opplysninger må kontrolleres, og om det er behov for supplerende bevis eller avhør.');
      lines.push('');
      lines.push('Personer som bør vurderes for forklaring:');
      if (persons.length) persons.forEach(function (row) { lines.push('- ' + row); });
      else lines.push('- Ingen ekstra personer er registrert. Vurder eier, fører/skipper, eksternt vitne eller andre involverte.');
      return lines.join('\n');
    }

    var generateInterviewGuidanceBtn = document.getElementById('btn-generate-interview-guidance');
    if (generateInterviewGuidanceBtn) generateInterviewGuidanceBtn.addEventListener('click', function () {
      if (interviewGuidanceText) interviewGuidanceText.value = buildInterviewGuidanceText();
      scheduleAutosave('Avhørspunkter generert');
    });
    var copyGuidanceBtn = document.getElementById('btn-copy-guidance-to-hearing');
    if (copyGuidanceBtn) copyGuidanceBtn.addEventListener('click', function () {
      if (!hearingText || !interviewGuidanceText) return;
      var base = String(hearingText.value || '').trim();
      var add = String(interviewGuidanceText.value || buildInterviewGuidanceText()).trim();
      if (!add) return;
      hearingText.value = [base, add].filter(Boolean).join('\n\n');
      scheduleAutosave('Avhørspunkter lagt inn');
    });
    var openGuidancePageBtn = document.getElementById('btn-open-guidance-page');
    if (openGuidancePageBtn) openGuidancePageBtn.addEventListener('click', function () {
      var text = String((interviewGuidanceText && interviewGuidanceText.value) || buildInterviewGuidanceText() || '').trim();
      if (interviewGuidanceText && !interviewGuidanceText.value) interviewGuidanceText.value = text;
      var page = window.open('', '_blank');
      if (!page) return;
      page.document.open();
      page.document.write('<!doctype html><html lang="no"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Avhørsmomenter</title><style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:18px;line-height:1.45;background:#f8fafc;color:#0f172a}pre{white-space:pre-wrap;background:#fff;border:1px solid #dbe3ec;border-radius:14px;padding:16px;font-size:15px}.toolbar{position:sticky;top:0;background:#f8fafc;padding-bottom:10px}button{border:0;border-radius:12px;padding:10px 14px;background:#17365d;color:#fff;font-weight:700}</style></head><body><div class="toolbar"><h1>Avhørsmomenter</h1><button onclick="window.print()">Skriv ut / lagre PDF</button></div><pre>' + escapeHtml(text) + '</pre></body></html>');
      page.document.close();
    });
    if (interviewGuidanceText) interviewGuidanceText.addEventListener('input', function () { scheduleAutosave('Avhørspunkter oppdatert'); });
    if (interviewNotConducted) interviewNotConducted.addEventListener('change', function () { syncInterviewDisabledState(); scheduleAutosave('Avhørsstatus oppdatert'); });
    if (interviewNotConductedReason) interviewNotConductedReason.addEventListener('input', function () { scheduleAutosave('Avhørsstatus oppdatert'); });

    function activeInterviewTranscript() {
      var focused = document.activeElement;
      if (focused && focused.classList && focused.classList.contains('interview-transcript')) return focused;
      var first = document.querySelector('#interview-list .interview-transcript');
      return first || hearingText;
    }

    var interviewHead = document.querySelector('#interview-list') ? document.querySelector('#interview-list').parentNode : null;
    if (interviewHead && !document.getElementById('interview-person-source')) {
      var sourceWrap = document.createElement('label');
      sourceWrap.className = 'block margin-top-s';
      sourceWrap.innerHTML = '<span>Opprett avhør for</span><select id="interview-person-source"></select>';
      interviewHead.insertBefore(sourceWrap, document.getElementById('interview-list'));
      syncInterviewPersonOptions();
    }
    var addInterviewBtn = document.getElementById('btn-add-interview');
    if (addInterviewBtn) addInterviewBtn.addEventListener('click', function () {
      if (interviewNotConducted && interviewNotConducted.checked) return;
      var selectedPerson = null;
      var sourceSelect = document.getElementById('interview-person-source');
      if (sourceSelect && sourceSelect.value !== '') {
        if (sourceSelect.value === 'main') selectedPerson = { role: 'Mistenkt', name: suspectName.value || suspectNameCommercial.value || '', phone: suspectPhone.value || '', birthdate: suspectBirthdate.value || '', address: suspectAddress.value || '' };
        else selectedPerson = personsState[Number(sourceSelect.value)] || null;
      }
      interviewState.push(makeInterviewFromPerson(selectedPerson || { role: 'Mistenkt', name: suspectName.value || suspectNameCommercial.value || '' }));
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
        fetch('/api/text/polish', secureFetchOptions({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: mode, text: sourceText, subject: entry.name || '' })
        })).then(function (r) { return r.json(); }).then(function (payload) {
          if (mode === 'interview_summary') entry.summary = payload.text || entry.summary;
          else entry.transcript = payload.text || entry.transcript;
          renderInterviews();
          hearingText.value = buildInterviewCombinedText();
        }).catch(function () {});
      }
    });

    function currentAudioStatusEl() {
      return document.getElementById('audio-status');
    }

    function setAudioStatus(message, isError) {
      var audioStatus = currentAudioStatusEl();
      if (!audioStatus) return;
      audioStatus.innerHTML = escapeHtml(String(message || ''));
      audioStatus.classList.toggle('alert-error', !!isError);
    }

    function currentInterviewLabelName() {
      var activeTranscript = activeInterviewTranscript();
      var activeCard = activeTranscript && activeTranscript.closest ? activeTranscript.closest('.interview-card') : null;
      return activeCard ? (activeCard.querySelector('.interview-name').value || 'ukjent') : (suspectName.value || suspectNameCommercial.value || 'ukjent');
    }

    function audioFilenameBase() {
      var stamp = new Date().toISOString().replace(/[:.]/g, '-');
      return 'avhor-' + stamp;
    }

    function audioExtensionForMime(mimeType) {
      var mime = String(mimeType || '').toLowerCase();
      if (mime.indexOf('audio/mp4') === 0) return '.m4a';
      if (mime.indexOf('audio/mpeg') === 0) return '.mp3';
      if (mime.indexOf('audio/ogg') === 0) return '.ogg';
      if (mime.indexOf('audio/wav') === 0) return '.wav';
      return '.webm';
    }

    function preferredRecordingMimeType() {
      if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') return '';
      var candidates = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/mp4',
        'audio/ogg;codecs=opus'
      ];
      for (var i = 0; i < candidates.length; i += 1) {
        try {
          if (MediaRecorder.isTypeSupported(candidates[i])) return candidates[i];
        } catch (e) {}
      }
      return '';
    }

    function queueAudioFileLocally(file, options) {
      options = options || {};
      if (!file) return Promise.reject(new Error('Velg eller ta opp en lydfil først.'));
      var labelName = currentInterviewLabelName();
      var baseCaption = 'Lydopptak avhør - ' + labelName;
      var caption = buildAudioCaption(baseCaption, Number(options.segmentIndex || 0));
      setAudioStatus('Lagrer lyd lokalt ...');
      return queueLocalAudioUpload(file, {
        caption: caption,
        finding_key: '',
        law_text: '',
        violation_reason: '',
        seizure_ref: ''
      }, {
        sourceKind: 'audio',
        segmentIndex: Number(options.segmentIndex || 0),
        groupId: options.groupId || '',
        statusMessage: 'Lyd lokalt. Synk venter.',
        autosaveMessage: 'Lydfil lagret lokalt'
      }).then(function (entry) {
        if (entry) appendAudioCard(entry);
        setAudioStatus('Lyd lagret lokalt.');
        return entry;
      }).catch(function (err) {
        setAudioStatus(err && err.message ? err.message : 'Kunne ikke lagre lydfil lokalt.', true);
        throw err;
      });
    }

    function uploadAudioFile(file, options) {
      return queueAudioFileLocally(file, options || {});
    }

    function stopRecordingStream(stream) {
      if (!stream || !stream.getTracks) return;
      try { stream.getTracks().forEach(function (track) { track.stop(); }); } catch (e) {}
    }

    function clearRecordingRotationTimer() {
      if (!recordingSegmentTimer) return;
      clearTimeout(recordingSegmentTimer);
      recordingSegmentTimer = null;
    }

    function scheduleRecordingRotation(stream) {
      clearRecordingRotationTimer();
      recordingSegmentTimer = setTimeout(function () {
        if (!mediaRecorder || mediaRecorder.state === 'inactive') return;
        recordingPausedByRotation = true;
        try { mediaRecorder.stop(); } catch (e) {}
      }, 5 * 60 * 1000);
    }

    function beginAudioSegment(stream) {
      var mimeType = preferredRecordingMimeType();
      mediaChunks = [];
      mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType: mimeType }) : new MediaRecorder(stream);
      mediaRecorder._kvStream = stream;
      mediaRecorder.ondataavailable = function (event) {
        if (event.data && event.data.size) mediaChunks.push(event.data);
      };
      mediaRecorder.onstop = function () {
        clearRecordingRotationTimer();
        var recorder = mediaRecorder;
        var chunkMime = (recorder && recorder.mimeType) || mimeType || 'audio/webm';
        var chunkCount = mediaChunks.length;
        var currentIndex = recordingSegmentIndex;
        var localChunks = mediaChunks.slice();
        mediaChunks = [];
        var filePromise = Promise.resolve(null);
        if (chunkCount) {
          var blob = new Blob(localChunks, { type: chunkMime });
          if (blob && blob.size) {
            var extension = audioExtensionForMime(chunkMime);
            var filename = audioFilenameBase() + '-del-' + currentIndex + extension;
            var file = new File([blob], filename, { type: blob.type || chunkMime, lastModified: Date.now() });
            filePromise = queueAudioFileLocally(file, { segmentIndex: currentIndex, groupId: recordingSessionId });
          }
        }
        Promise.resolve(filePromise).finally(function () {
          if (recordingPausedByRotation && stream && stream.active) {
            recordingPausedByRotation = false;
            recordingSegmentIndex += 1;
            beginAudioSegment(stream);
            return;
          }
          stopRecordingStream(stream);
          mediaRecorder = null;
          mediaChunks = [];
          recordingSessionId = '';
          recordingSegmentIndex = 0;
          recordingElapsedStart = 0;
          setAudioStatus('Lydopptak stoppet. Synk venter.');
        });
      };
      mediaRecorder.start(30000);
      scheduleRecordingRotation(stream);
      var minutes = Math.floor(Math.max(0, Date.now() - recordingElapsedStart) / 60000);
      setAudioStatus('Lydopptak pågår. Segment ' + recordingSegmentIndex + ' lagres lokalt fortløpende. Lengde hittil: ca. ' + minutes + ' min.');
    }

    document.getElementById('btn-start-recording').addEventListener('click', function () {
      var audioStatus = currentAudioStatusEl();
      if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        setAudioStatus('Lydopptak pågår allerede.');
        return;
      }
      if (typeof MediaRecorder === 'undefined') {
        if (audioStatus) audioStatus.innerHTML = 'Nettleseren støtter ikke lydopptak. Bruk «Velg fil» for å legge ved lyd.';
        return;
      }
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (audioStatus) audioStatus.innerHTML = 'Nettleseren støtter ikke lydopptak.';
        return;
      }
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
        recordingSessionId = LocalMedia && typeof LocalMedia.generateId === 'function' ? LocalMedia.generateId() : ('rec-' + Date.now());
        recordingSegmentIndex = 1;
        recordingElapsedStart = Date.now();
        recordingPausedByRotation = false;
        beginAudioSegment(stream);
      }).catch(function (err) {
        setAudioStatus('Kunne ikke starte lydopptak: ' + escapeHtml(err.message || err), true);
      });
    });

    document.getElementById('btn-stop-recording').addEventListener('click', function () {
      recordingPausedByRotation = false;
      clearRecordingRotationTimer();
      if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        try { mediaRecorder.stop(); } catch (e) {}
      } else {
        setAudioStatus('Ingen aktive lydopptak å stoppe.');
      }
    });

    var btnUploadAudio = document.getElementById('btn-upload-audio');
    if (btnUploadAudio) btnUploadAudio.addEventListener('click', function () {
      var input = document.getElementById('audio-upload-input');
      if (!input.files || !input.files[0]) { setAudioStatus('Velg en lydfil først.'); return; }
      uploadAudioFile(input.files[0]).finally(function () { input.value = ''; });
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

    var btnOcrCamera = document.getElementById('btn-ocr-camera');
    if (btnOcrCamera) btnOcrCamera.addEventListener('click', function () {
      openCameraCapture({
        title: 'Kamera for OCR-søk',
        description: 'Ta bilde av merketøy, dokument eller annen tekst. Bildet leses og brukes direkte i norsk registersøk.',
        fallbackInput: ocrCameraInput,
        filenamePrefix: 'ocr',
        onFile: function (file) {
          setSelectedOcrFile(file, 'Bilde tatt med kamera. OCR kjøres automatisk.');
          runOcrFromFile(file);
        }
      });
    });

    var btnOcrFile = document.getElementById('btn-ocr-file');
    if (btnOcrFile) btnOcrFile.addEventListener('click', function () {
      if (ocrFileInput) ocrFileInput.click();
    });

    if (ocrCameraInput) ocrCameraInput.addEventListener('change', function () {
      var file = this.files && this.files[0] ? this.files[0] : null;
      if (!file) return;
      setSelectedOcrFile(file, 'Bilde hentet fra enhetskamera. OCR kjøres automatisk.');
      runOcrFromFile(file);
      this.value = '';
    });

    if (ocrFileInput) ocrFileInput.addEventListener('change', function () {
      var file = this.files && this.files[0] ? this.files[0] : null;
      if (!file) return;
      setSelectedOcrFile(file, 'Bildefil valgt. OCR kjøres automatisk.');
      runOcrFromFile(file);
      this.value = '';
    });

    if (inlineEvidenceCameraInput) inlineEvidenceCameraInput.addEventListener('change', function () {
      var file = this.files && this.files[0] ? this.files[0] : null;
      if (!file) return;
      uploadInlineEvidenceFile(file);
      this.value = '';
    });

    if (inlineEvidenceFileInput) inlineEvidenceFileInput.addEventListener('change', function () {
      var file = this.files && this.files[0] ? this.files[0] : null;
      if (!file) return;
      uploadInlineEvidenceFile(file);
      this.value = '';
    });

    var btnCameraClose = document.getElementById('btn-camera-close');
    if (btnCameraClose) btnCameraClose.addEventListener('click', closeCameraCapture);
    var btnCameraCapture = document.getElementById('btn-camera-capture');
    if (btnCameraCapture) btnCameraCapture.addEventListener('click', captureCameraFile);
    var btnCameraRetry = document.getElementById('btn-camera-retry');
    if (btnCameraRetry) btnCameraRetry.addEventListener('click', function () {
      if (!cameraCaptureState) return;
      openCameraCapture(cameraCaptureState);
    });
    if (cameraCaptureModal) cameraCaptureModal.addEventListener('click', function (event) {
      if (event.target === cameraCaptureModal) closeCameraCapture();
    });

    var btnRunOcr = document.getElementById('btn-run-ocr');
    if (btnRunOcr) btnRunOcr.addEventListener('click', function () {
      if (!selectedOcrFile) {
        registryResult.innerHTML = 'Velg eller ta et bilde først.';
        return;
      }
      runOcrFromFile(selectedOcrFile);
    });

    renderInterviews();
    hearingText.value = buildInterviewCombinedText() || hearingText.value;
    if (LocalMedia && typeof LocalMedia.requestPersistence === 'function') { LocalMedia.requestPersistence().catch(function () { return false; }); }
    startLocationWatch();
    document.getElementById('btn-generate-summary').addEventListener('click', function () {
      var payload = buildSummaryPayload();
      var cacheKey = summaryCacheKey(payload);
      var cached = loadCachedSummaryDraft(cacheKey);
      var fastDraft = localSummaryFromFindings(payload);
      applySummaryDrafts(fastDraft, 'Raskt lokalt utkast', { silent: true });
      if (cached && cached.drafts) {
        applySummaryDrafts(cached.drafts, 'Lagret utkast fra enheten', { silent: true });
      }
      fetchSummaryDrafts(payload, { forceRefresh: !cached }).then(function (drafts) {
        applySummaryDrafts(drafts, 'Generert utkast', { silent: false });
      }).catch(function () {
        renderSummaryDraftPreview(fastDraft, 'Raskt lokalt utkast');
      });
    });

    function performManualSave() {
      if (caseMap && caseMap._kvLeafletMap) {
        try {
          var center = caseMap._kvLeafletMap.getCenter();
          sessionStorage.setItem('kv-map-view:' + (caseMap.id || 'case-map'), JSON.stringify({ lat: center.lat, lng: center.lng, zoom: caseMap._kvLeafletMap.getZoom() }));
        } catch (e) {}
      }
      try { sessionStorage.setItem(stepStorageKey, String(currentStep)); } catch (e) {}
      persistLocalCaseDraft({ silent: true });
      if (isLocalOnlyCase()) {
        setAutosaveStatus('Lagret lokalt', 'is-saved');
        updateLocalCaseStatus('Ny sak lagret lokalt.', false, { forceShow: true, showSync: true, showDiscard: true });
        return;
      }
      if (!root.dataset.autosaveUrl) return;
      var formData = serializeCaseFormData();
      setAutosaveStatus('Lagrer manuelt …', 'is-saving');
      fetch(root.dataset.autosaveUrl, secureFetchOptions({ method: 'POST', body: formData }))
        .then(function (r) { return parseJsonResponse(r, 'Kunne ikke lagre saken manuelt.'); })
        .then(function (payload) {
          lastAutosaveFingerprint = formFingerprint();
          setAutosaveStatus('Lagret manuelt ' + new Date().toLocaleTimeString('nb-NO', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), 'is-saved');
          markLocalCaseSynced(payload && payload.saved_at ? payload.saved_at : new Date().toISOString());
          syncLocalMediaQueue({ force: true, silent: true });
        })
        .catch(function (error) {
          if (isMissingServerCaseError(error) && createCaseUrl) {
            updateLocalCaseStatus('Serveren finner ikke saken lenger. Oppretter ny serverkopi fra utfylt kladd ...', true, { forceShow: true, syncing: true, showSync: true, showDiscard: true });
            createServerCaseFromLocalDraft({ force: true, redirectAfterCreate: false, silent: true });
            return;
          }
          updateLocalCaseStatus('Lagret lokalt. Synk når nett er tilbake.', true, { forceShow: true, showSync: true, showDiscard: true });
          setAutosaveStatus('Lagret lokalt', 'is-saved');
        });
    }

    var manualSaveBtn = document.getElementById('btn-manual-save');
    if (manualSaveBtn) manualSaveBtn.addEventListener('click', function(event){
      event.preventDefault();
      performManualSave();
    });

    form.addEventListener('submit', function (event) {
      if (event) event.preventDefault();
      serializeCaseFormData();
      if (caseMap && caseMap._kvLeafletMap) {
        try {
          var center = caseMap._kvLeafletMap.getCenter();
          sessionStorage.setItem('kv-map-view:' + (caseMap.id || 'case-map'), JSON.stringify({ lat: center.lat, lng: center.lng, zoom: caseMap._kvLeafletMap.getZoom() }));
        } catch (e) {}
      }
      performManualSave();
    });

    Array.prototype.forEach.call(document.querySelectorAll('a[href$="/preview"], form[action$="/bundle"], form[action$="/pdf"], form[action$="/interview-pdf"]'), function (node) {
      if (node.tagName === 'A') {
        node.addEventListener('click', function (event) {
          event.preventDefault();
          ensureLocalCaseSyncedBeforeAction().then(function (caseAllowed) {
            if (!caseAllowed) return;
            ensureLocalMediaSyncedBeforeAction().then(function (allowed) {
              if (!allowed) return;
              var href = node.getAttribute('href') || '';
              if (href) window.open(href, '_blank', 'noopener');
            });
          });
        });
        return;
      }
      node.addEventListener('submit', function (event) {
        event.preventDefault();
        ensureLocalCaseSyncedBeforeAction().then(function (caseAllowed) {
          if (!caseAllowed) return;
          ensureLocalMediaSyncedBeforeAction().then(function (allowed) {
            if (!allowed) return;
            if (window.KVCommon && typeof window.KVCommon.injectCsrfField === 'function') window.KVCommon.injectCsrfField(node);
            HTMLFormElement.prototype.submit.call(node);
          });
        });
      });
    });

    if (btnSyncCaseDraft) {
      btnSyncCaseDraft.addEventListener('click', function () {
        syncLocalCaseDraft({ force: true, silent: false }).then(function (ok) {
          if (ok) syncLocalMediaQueue({ force: true, silent: true });
        });
      });
    }
    if (btnDiscardLocalCase) {
      btnDiscardLocalCase.addEventListener('click', function () {
        discardLocalCaseDraft();
      });
    }
    window.addEventListener('online', function () {
      syncLocalCaseDraft({ force: true, silent: false }).then(function (ok) {
        if (ok) syncLocalMediaQueue({ force: true, silent: true });
      });
      autoRefreshStalePackages();
    });

    syncOptions();
    updateCaseMap();
    if (latitude.value && longitude.value) {
      window.setTimeout(function () { scheduleNearestPlaceResolve({ force: true }, 0); }, 120);
      window.setTimeout(function () { checkZone({ force: true, skipMapUpdate: true }); }, 350);
    }
    maintainOfflinePackages(true).then(function () { return refreshOfflinePackageList(); }).then(function () { return autoRefreshStalePackages(); });
    setTimeout(function () { if (currentStep === 2) maybeAutoStartLocation(); }, 250);
    renderFindings();
    scheduleSummaryWarmup();
    loadLocalEvidenceFromDevice().then(function () { updateLocalMediaStatus(); });
    if (sourcesState.length) sourceList.innerHTML = sourcesState.map(sourceChip).join('');
    if (controlType.value && (species.value || fisheryType.value)) loadRules();
    syncStepNavigation();
    var forcedInitialStep = Number(root.dataset.startStep || '0');
    var shouldForceInitialStep = root.dataset.forceStartStep === '1' && forcedInitialStep >= 1 && forcedInitialStep <= panes.length;
    if (shouldForceInitialStep) {
      try { sessionStorage.removeItem(stepStorageKey); } catch (e) {}
      showStep(forcedInitialStep, { scroll: false });
    } else {
      try {
        var storedStep = Number(sessionStorage.getItem(stepStorageKey) || '1');
        if (storedStep >= 1 && storedStep <= panes.length) showStep(storedStep, { scroll: false });
        else if (forcedInitialStep >= 1 && forcedInitialStep <= panes.length) showStep(forcedInitialStep, { scroll: false });
      } catch (e) {
        if (forcedInitialStep >= 1 && forcedInitialStep <= panes.length) showStep(forcedInitialStep, { scroll: false });
      }
    }
    requestLocalPersistence();
    ensureInitialOfflineDraft().then(function () {
      return restoreLocalCaseDraft();
    }).then(function () {
      loadLocalEvidenceFromDevice().then(function () { updateLocalMediaStatus(); });
    });
  }

  ready(initMapOverview);
  ready(initRulesOverview);
  ready(initCaseApp);
})();
