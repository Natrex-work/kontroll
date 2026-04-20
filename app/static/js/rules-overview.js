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
    var trigger = document.getElementById('overview_fetch_rules') || document.getElementById('btn-overview-load-rules');
    var autoTimer = null;

    function currentLawSection() {
      var key = String(controlType.value || '').toLowerCase().indexOf('kom') === 0 ? 'kommersiell' : 'fritidsfiske';
      return lawBrowser.filter(function (item) { return item.key === key; })[0] || null;
    }

    function setSummaryPlaceholder(text) {
      meta.innerHTML = text || '';
      findings.innerHTML = '';
      sources.innerHTML = '';
    }

    function syncOptions() {
      var section = currentLawSection();
      var fisheryValue = fisheryType.value;
      var gearValue = gearType.value;
      var speciesValue = species.value;
      if (!section) {
        setSummaryPlaceholder('Velg kontrolltype for å få arts- og redskapsvalg.');
        return;
      }
      fisheryType.innerHTML = '<option value="">Velg</option>' + section.species.map(function (item) { return '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'; }).join('');
      gearType.innerHTML = '<option value="">Velg</option>' + section.gear.map(function (item) { return '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'; }).join('');
      speciesList.innerHTML = section.species.map(function (item) { return '<option value="' + escapeHtml(item) + '"></option>'; }).join('');
      if (fisheryValue) fisheryType.value = fisheryValue;
      if (gearValue) gearType.value = gearValue;
      if (speciesValue) species.value = speciesValue;
      if (!species.value && fisheryType.value) species.value = fisheryType.value;
      meta.innerHTML = '<strong>' + escapeHtml(section.label || 'Regelverk') + '</strong><div class="small muted">' + escapeHtml(section.intro || 'Velg art og redskap for å se relevant regelverk og kontrollpunkter.') + '</div>';
      sources.innerHTML = (section.sources || []).map(sourceChip).join('');
      findings.innerHTML = '';
    }

    function renderBundle(bundle) {
      var title = bundle.title || 'Relevant regelverk og kontrollpunkter';
      var description = bundle.description || 'Kontrollpunkter og regelgrunnlag for valget ditt.';
      meta.innerHTML = '<strong>' + escapeHtml(title) + '</strong><div class="small muted">' + escapeHtml(description) + '</div>';
      findings.innerHTML = buildReadonlyFindingsHtml(bundle.items || []);
      sources.innerHTML = (bundle.sources || []).map(sourceChip).join('');
      if (!(bundle.items || []).length) {
        findings.innerHTML = '<div class="callout">Ingen spesifikke kontrollpunkter funnet for dette valget ennå. Prøv et annet art-/redskapsvalg.</div>';
      }
    }

    function canLoad() {
      var speciesVal = (species.value || fisheryType.value || '').trim();
      return !!(controlType.value && speciesVal && gearType.value);
    }

    function loadBundle() {
      var speciesVal = (species.value || fisheryType.value || '').trim();
      if (!controlType.value || !speciesVal || !gearType.value) {
        setSummaryPlaceholder('Velg kontrolltype, art/fiskeri og redskap først.');
        return;
      }
      var params = new URLSearchParams({
        control_type: controlType.value,
        species: speciesVal,
        gear_type: gearType.value,
        area_status: '',
        control_date: ''
      });
      meta.innerHTML = 'Henter relevant regelverk og kontrollpunkter ...';
      findings.innerHTML = '';
      fetch(root.dataset.rulesUrl + '?' + params.toString(), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(renderBundle)
        .catch(function () { setSummaryPlaceholder('Kunne ikke hente relevant regelverk akkurat nå.'); });
    }

    function scheduleAutoLoad() {
      clearTimeout(autoTimer);
      if (!canLoad()) return;
      autoTimer = setTimeout(loadBundle, 250);
    }

    controlType.addEventListener('change', function () {
      syncOptions();
      scheduleAutoLoad();
    });
    fisheryType.addEventListener('change', function () {
      if (!species.value || species.value === fisheryType.dataset.lastValue || species.value.trim() === '') species.value = fisheryType.value;
      fisheryType.dataset.lastValue = fisheryType.value;
      scheduleAutoLoad();
    });
    species.addEventListener('input', scheduleAutoLoad);
    gearType.addEventListener('change', scheduleAutoLoad);
    if (trigger) trigger.addEventListener('click', loadBundle);
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
