(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  function syncPermissionPanel(panel) {
    if (!panel) return;
    var roleId = panel.getAttribute('data-role-select-id');
    if (!roleId) return;
    var select = document.getElementById(roleId);
    if (!select) return;
    var isAdmin = String(select.value || '').toLowerCase() === 'admin';
    var options = panel.querySelector('.permission-options');
    var callout = panel.querySelector('.admin-fixed-permissions');
    if (options) options.classList.toggle('hidden', isAdmin);
    if (callout) callout.classList.toggle('hidden', !isAdmin);
  }

  ready(function () {
    var panels = document.querySelectorAll('.permission-panel');
    Array.prototype.forEach.call(panels, function (panel) {
      syncPermissionPanel(panel);
      var roleId = panel.getAttribute('data-role-select-id');
      var select = roleId ? document.getElementById(roleId) : null;
      if (!select) return;
      select.addEventListener('change', function () { syncPermissionPanel(panel); });
    });
  });
})();
