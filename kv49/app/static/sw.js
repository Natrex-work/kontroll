const CACHE = 'kv-kontroll-v49-fullskala';
const STATIC_PREFIX = '/static/';
const ASSETS = [
  '/static/styles.css',
  '/static/js/common.js',
  '/static/js/case-app.js',
  '/static/js/map-overview.js',
  '/static/js/rules-overview.js',
  '/static/js/admin-users.js',
  '/static/icon-192.png',
  '/static/icon-512.png'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(STATIC_PREFIX)) return;
  event.respondWith(
    fetch(event.request).then(networkRes => {
      const clone = networkRes.clone();
      caches.open(CACHE).then(cache => cache.put(event.request, clone)).catch(() => {});
      return networkRes;
    }).catch(() => caches.match(event.request))
  );
});
