/**
 * Admin user management — robust version uten kompliserte segmenterte kontroller.
 *
 * Bruker bare standard <select> og <input>-elementer som alltid fungerer.
 *
 * - Phone required toggle basert på rolle (select)
 * - Permissions panel show/hide basert på rolle
 * - Password generator (16-tegns sterkt passord)
 * - Show/hide passord-toggle
 * - Kopier passord til utklippstavlen
 * - Permissions visual highlight når avkrysset
 * - Confirm-dialog for delete
 */
(function () {
  'use strict';

  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  // --------------------------------------------------------------------
  // Rolle (select) — påvirker telefon-krav, hint-tekst og permissions
  // --------------------------------------------------------------------
  function applyCreateRole(role) {
    var phoneInput = document.getElementById('create-phone');
    var phoneReq = document.getElementById('phone-req');
    var phoneHint = document.getElementById('phone-hint');
    var permsWrap = document.getElementById('create-permissions');
    var permsInfo = document.getElementById('admin-permissions-info');
    var roleHint = document.getElementById('role-hint');

    var isAdmin = (role === 'admin');

    if (phoneInput) {
      phoneInput.required = !isAdmin;
      phoneInput.setAttribute('aria-required', isAdmin ? 'false' : 'true');
    }
    if (phoneReq) phoneReq.style.display = isAdmin ? 'none' : 'inline';
    if (phoneHint) {
      phoneHint.textContent = isAdmin
        ? 'Valgfritt for admin (admin er unntatt 2-trinnskravet).'
        : 'Norsk mobilnummer (8 siffer). SMS-kode sendes hit ved innlogging.';
    }
    if (permsWrap) permsWrap.classList.toggle('hidden', isAdmin);
    if (permsInfo) permsInfo.classList.toggle('hidden', !isAdmin);
    if (roleHint) {
      roleHint.textContent = isAdmin
        ? 'Admin har full tilgang til alle moduler og er unntatt 2-trinnskravet.'
        : 'Etterforsker logger inn med passord + SMS-kode. Admin er unntatt 2-trinn.';
    }
  }

  function initCreateRole() {
    var sel = document.getElementById('create-role');
    if (!sel) return;
    sel.addEventListener('change', function () { applyCreateRole(sel.value); });
    applyCreateRole(sel.value || 'investigator');
  }

  // --------------------------------------------------------------------
  // Passord-hjelpere
  // --------------------------------------------------------------------
  function generateStrongPassword() {
    var lower = 'abcdefghijkmnpqrstuvwxyz';
    var upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
    var digits = '23456789';
    var symbols = '!@#$%&*+-?';
    var all = lower + upper + digits + symbols;
    function pick(set) {
      var arr = new Uint32Array(1);
      window.crypto.getRandomValues(arr);
      return set[arr[0] % set.length];
    }
    var pwd = [pick(lower), pick(upper), pick(digits), pick(symbols)];
    while (pwd.length < 16) pwd.push(pick(all));
    for (var i = pwd.length - 1; i > 0; i--) {
      var rand = new Uint32Array(1);
      window.crypto.getRandomValues(rand);
      var j = rand[0] % (i + 1);
      var tmp = pwd[i]; pwd[i] = pwd[j]; pwd[j] = tmp;
    }
    return pwd.join('');
  }

  function initPasswordHelpers() {
    var pwd = document.getElementById('create-password');
    var genBtn = document.getElementById('generate-password-btn');
    var toggleBtn = document.getElementById('toggle-password');
    var copyBtn = document.getElementById('copy-password');
    var eyeShow = document.getElementById('eye-show');
    var eyeHide = document.getElementById('eye-hide');

    if (genBtn && pwd) {
      genBtn.addEventListener('click', function (e) {
        e.preventDefault();
        var newPwd = generateStrongPassword();
        pwd.value = newPwd;
        pwd.type = 'text';
        if (eyeShow) eyeShow.style.display = 'none';
        if (eyeHide) eyeHide.style.display = 'block';
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(newPwd).then(function () {
            showToast('Passord generert og kopiert til utklippstavlen', 'success');
          }).catch(function () {
            showToast('Passord generert. Kopier manuelt fra feltet.', 'success');
          });
        } else {
          showToast('Passord generert', 'success');
        }
      });
    }

    if (toggleBtn && pwd) {
      toggleBtn.addEventListener('click', function (e) {
        e.preventDefault();
        var isHidden = pwd.type === 'password';
        pwd.type = isHidden ? 'text' : 'password';
        if (eyeShow) eyeShow.style.display = isHidden ? 'none' : 'block';
        if (eyeHide) eyeHide.style.display = isHidden ? 'block' : 'none';
        toggleBtn.setAttribute('aria-label', isHidden ? 'Skjul passord' : 'Vis passord');
        toggleBtn.setAttribute('title', isHidden ? 'Skjul passord' : 'Vis passord');
      });
    }

    if (copyBtn && pwd) {
      copyBtn.addEventListener('click', function (e) {
        e.preventDefault();
        if (!pwd.value) {
          showToast('Ingen passord å kopiere', 'error');
          return;
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(pwd.value).then(function () {
            showToast('Passord kopiert', 'success');
          }).catch(function () {
            showToast('Kunne ikke kopiere automatisk', 'error');
          });
        } else {
          pwd.select();
          try { document.execCommand('copy'); showToast('Passord kopiert', 'success'); }
          catch (e) { showToast('Kunne ikke kopiere', 'error'); }
        }
      });
    }
  }

  // --------------------------------------------------------------------
  // Permissions visual feedback
  // --------------------------------------------------------------------
  function initPermissions() {
    var permLabels = document.querySelectorAll('.admin-permissions label, .permission-options label');
    permLabels.forEach(function (lbl) {
      var cb = lbl.querySelector('input[type="checkbox"]');
      if (!cb) return;
      function updateBg() {
        lbl.classList.toggle('is-checked', cb.checked);
      }
      cb.addEventListener('change', updateBg);
      updateBg();
    });
  }

  // --------------------------------------------------------------------
  // Phone required for existing-user edits
  // --------------------------------------------------------------------
  function initLegacyPhoneRequired() {
    var inputs = document.querySelectorAll('[data-phone-input-for-role-select]');
    inputs.forEach(function (input) {
      var roleId = input.getAttribute('data-phone-input-for-role-select');
      var select = roleId ? document.getElementById(roleId) : null;
      function sync() {
        if (!select) return;
        var isAdmin = String(select.value || '').toLowerCase() === 'admin';
        input.required = !isAdmin;
        input.setAttribute('aria-required', isAdmin ? 'false' : 'true');
      }
      sync();
      if (select) select.addEventListener('change', sync);
    });

    var panels = document.querySelectorAll('.permission-panel');
    panels.forEach(function (panel) {
      var roleId = panel.getAttribute('data-role-select-id');
      var select = roleId ? document.getElementById(roleId) : null;
      if (!select) return;
      function sync() {
        var isAdmin = String(select.value || '').toLowerCase() === 'admin';
        var options = panel.querySelector('.permission-options');
        var callout = panel.querySelector('.admin-fixed-permissions');
        if (options) options.classList.toggle('hidden', isAdmin);
        if (callout) callout.classList.toggle('hidden', !isAdmin);
      }
      sync();
      select.addEventListener('change', sync);
    });
  }

  // --------------------------------------------------------------------
  // Suksess-modal kopier-knapper
  // --------------------------------------------------------------------
  function initCopyButtons() {
    var btns = document.querySelectorAll('.admin-cred-copy');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var targetId = btn.getAttribute('data-copy-target');
        var target = targetId ? document.getElementById(targetId) : null;
        if (!target) return;
        var text = target.textContent.trim();
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () {
            showToast('Kopiert', 'success');
          });
        }
      });
    });
  }

  // --------------------------------------------------------------------
  // Confirm-dialog for delete buttons
  // --------------------------------------------------------------------
  function initConfirmDialogs() {
    var btns = document.querySelectorAll('[data-confirm]');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        var msg = btn.getAttribute('data-confirm');
        if (!confirm(msg)) e.preventDefault();
      });
    });
  }

  // --------------------------------------------------------------------
  // Toast helper
  // --------------------------------------------------------------------
  function getToastHost() {
    var host = document.getElementById('mk-toast-host');
    if (host) return host;
    host = document.createElement('div');
    host.id = 'mk-toast-host';
    host.className = 'mk-toast-host';
    document.body.appendChild(host);
    return host;
  }

  function showToast(message, kind) {
    var host = getToastHost();
    var toast = document.createElement('div');
    toast.className = 'mk-toast' + (kind ? ' mk-toast-' + kind : '');
    toast.textContent = message;
    host.appendChild(toast);
    setTimeout(function () {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'opacity 200ms, transform 200ms';
      setTimeout(function () { toast.remove(); }, 220);
    }, 2400);
  }

  ready(function () {
    initCreateRole();
    initPasswordHelpers();
    initPermissions();
    initLegacyPhoneRequired();
    initCopyButtons();
    initConfirmDialogs();
  });
})();
