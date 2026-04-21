(function () {
  var Common = window.KVCommon || {};
  var ready = Common.ready || function (fn) { if (document.readyState !== 'loading') fn(); else document.addEventListener('DOMContentLoaded', fn); };
  var escapeHtml = Common.escapeHtml || function (value) { return String(value || ''); };
  var parseJson = Common.parseJson || function (value, fallback) { try { return JSON.parse(value || ''); } catch (e) { return fallback; } };
  var buildReadonlyFindingsHtml = Common.buildReadonlyFindingsHtml || function () { return ''; };
  var sourceChip = Common.sourceChip || function () { return ''; };

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
    var trigger = document.getElementById('overview_fetch_rules');
    var autoTimer = null;
    var cache = {};

    function sectionKey() {
      return String(controlType.value || '').toLowerCase().indexOf('kom') === 0 ? 'kommersiell' : 'fritidsfiske';
    }

    function currentLawSection() {
      var key = sectionKey();
      return lawBrowser.filter(function (item) { return item.key === key; })[0] || null;
    }

    function selectionSpecies() {
      return String((species.value || fisheryType.value || '')).trim();
    }

    function setPlaceholder(text, keepSources) {
      meta.innerHTML = text || '';
      findings.innerHTML = '';
      if (!keepSources) sources.innerHTML = '';
    }

    function syncOptions(preserveValues) {
      preserveValues = preserveValues !== false;
      var section = currentLawSection();
      if (!section) {
        setPlaceholder('Velg kontrolltype for å hente relevant regelverk og kontrollpunkter.', false);
        return;
      }
      var currentFishery = preserveValues ? fisheryType.value : '';
      var currentGear = preserveValues ? gearType.value : '';
      var currentSpecies = preserveValues ? species.value : '';
      fisheryType.innerHTML = '<option value="">Velg</option>' + (section.species || []).map(function (item) { return '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'; }).join('');
      gearType.innerHTML = '<option value="">Velg</option>' + (section.gear || []).map(function (item) { return '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'; }).join('');
      speciesList.innerHTML = (section.species || []).map(function (item) { return '<option value="' + escapeHtml(item) + '"></option>'; }).join('');
      if (currentFishery) fisheryType.value = currentFishery;
      if (currentGear) gearType.value = currentGear;
      if (currentSpecies) species.value = currentSpecies;
      if (!species.value && fisheryType.value) species.value = fisheryType.value;
      meta.innerHTML = '<strong>' + escapeHtml(section.label || 'Regelverk') + '</strong><div class="small muted">' + escapeHtml(section.intro || 'Velg art/fiskeri og redskap for å hente samme kontrollpunkter som brukes under kontroll.') + '</div>';
      sources.innerHTML = (section.sources || []).map(sourceChip).join('');
      findings.innerHTML = '';
    }

    function canLoad() {
      return !!(controlType.value && selectionSpecies());
    }

    function cacheKey() {
      return [sectionKey(), selectionSpecies(), gearType.value || ''].join('|');
    }

    function renderBundle(bundle) {
      var title = bundle.title || 'Relevant regelverk og kontrollpunkter';
      var description = bundle.description || 'Kontrollpunkter og regelgrunnlag for valget ditt.';
      meta.innerHTML = '<strong>' + escapeHtml(title) + '</strong><div class="small muted">' + escapeHtml(description) + '</div>';
      findings.innerHTML = buildReadonlyFindingsHtml(bundle.items || []);
      sources.innerHTML = (bundle.sources || []).map(sourceChip).join('');
      if (!(bundle.items || []).length) {
        findings.innerHTML = '<div class="callout">Ingen spesifikke kontrollpunkter ble funnet for dette valget. Prøv et annet art-/redskapsvalg.</div>';
      }
    }

    function loadBundle() {
      if (!canLoad()) {
        setPlaceholder('Velg kontrolltype og art/fiskeri først. Redskap kan legges til for mer presis filtrering.', true);
        return;
      }
      var key = cacheKey();
      if (cache[key]) {
        renderBundle(cache[key]);
        return;
      }
      var params = new URLSearchParams({
        control_type: controlType.value,
        species: selectionSpecies(),
        area_status: '',
        control_date: ''
      });
      if (gearType.value) params.set('gear_type', gearType.value);
      meta.innerHTML = 'Henter relevant regelverk og kontrollpunkter ...';
      findings.innerHTML = '';
      fetch(root.dataset.rulesUrl + '?' + params.toString(), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (bundle) {
          cache[key] = bundle || {};
          renderBundle(bundle || {});
        })
        .catch(function () {
          setPlaceholder('Kunne ikke hente relevant regelverk akkurat nå.', true);
        });
    }

    function scheduleAutoLoad() {
      clearTimeout(autoTimer);
      if (!canLoad()) {
        setPlaceholder('Velg kontrolltype og art/fiskeri først. Redskap kan legges til for mer presis filtrering.', true);
        return;
      }
      autoTimer = setTimeout(loadBundle, 200);
    }

    controlType.addEventListener('change', function () {
      syncOptions(true);
      scheduleAutoLoad();
    });
    fisheryType.addEventListener('change', function () {
      species.value = fisheryType.value || species.value;
      scheduleAutoLoad();
    });
    species.addEventListener('input', scheduleAutoLoad);
    species.addEventListener('change', scheduleAutoLoad);
    gearType.addEventListener('change', scheduleAutoLoad);
    if (trigger) trigger.addEventListener('click', loadBundle);
    findings.addEventListener('click', function (event) {
      if (!event.target.classList.contains('help-toggle')) return;
      var card = event.target.closest('.finding-card');
      var box = card && card.querySelector('.help-text');
      if (box) box.classList.toggle('hidden');
    });

    syncOptions(false);
  }

  ready(initRulesOverview);
})();
