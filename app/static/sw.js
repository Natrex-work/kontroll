const CACHE = 'kv-kontroll-demo-v40';
const ASSETS = [
  '/static/styles.css',
  '/static/js/common.js',
  '/static/js/case-app.js',
  '/static/js/map-overview.js',
  '/static/js/rules-overview.js',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/login'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(caches.match(event.request).then(res => res || fetch(event.request)));
});
