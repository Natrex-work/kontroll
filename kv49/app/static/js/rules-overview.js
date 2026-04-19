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
      var params = new URLSearchParams({ control_type: controlType.value, species: speciesVal, gear_type: gearType.value, area_status: '', control_date: '' });
      meta.innerHTML = 'Henter kontrollpunkter ...';
      fetch(root.dataset.rulesUrl + '?' + params.toString())
        .then(function (r) { return r.json(); })
        .then(renderBundle)
        .catch(function () { meta.innerHTML = 'Kunne ikke hente kontrollpunkter akkurat nå.'; });
    }

    controlType.addEventListener('change', syncOptions);
    fisheryType.addEventListener('change', function () {
      if (!species.value || species.value === fisheryType.dataset.lastValue) species.value = fisheryType.value;
      fisheryType.dataset.lastValue = fisheryType.value;
    });
    document.getElementById('btn-overview-load-rules').addEventListener('click', loadBundle);
    findings.addEventListener('click', function (event) {
      if (!event.target.classList.contains('help-toggle')) return;
      var card = event.target.closest('.finding-card');
      var box = card && card.querySelector('.help-text');
      if (box) box.classList.toggle('hidden');
    });
    syncOptions();
  }

  ready(initRulesOverview);
})();
