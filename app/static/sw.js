const CACHE = 'kv-kontroll-1-8-44-static';
const MAP_TILE_CACHE = 'kv-kontroll-1-8-44-map-tiles';
const STATIC_PREFIX = '/static/';
const API_CACHE_PREFIXES = ['/api/map/catalog', '/api/map/bundle', '/api/map/offline-package', '/api/map/features', '/api/map/identify'];
const NETWORK_ONLY_PREFIXES = ['/api/rules', '/api/zones/check', '/api/person-fartoy/analyze-image'];
const ASSETS = [
  '/static/styles.css?v=1.8.44',
  '/static/js/image-prep.js?v=1.8.44',
  '/static/js/local-media.js?v=1.8.44',
  '/static/js/local-cases.js?v=1.8.44',
  '/static/js/sync-orchestrator.js?v=1.8.44',
  '/static/js/local-map.js?v=1.8.44',
  '/static/js/common.js?v=1.8.44',
  '/static/js/case-app.js?v=1.8.44',
  '/static/js/map-overview.js?v=1.8.44',
  '/static/js/rules-overview.js?v=1.8.44',
  '/static/js/admin-users.js?v=1.8.44',
  '/static/logo.png?v=1.8.44',
  '/static/favicon-96.png?v=1.8.44',
  '/static/icon-192.png?v=1.8.44',
  '/static/icon-512.png?v=1.8.44'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE && key !== MAP_TILE_CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())
  );
});

function shouldHandleApi(url) {
  return API_CACHE_PREFIXES.some(prefix => url.pathname.startsWith(prefix));
}

function shouldBypassCache(url) {
  return NETWORK_ONLY_PREFIXES.some(prefix => url.pathname.startsWith(prefix));
}

function isHtmlNavigation(request, url) {
  if (request.mode === 'navigate') return true;
  const accept = request.headers.get('accept') || '';
  return request.method === 'GET' && accept.indexOf('text/html') !== -1 && !url.pathname.startsWith('/api/');
}

function isMapTileRequest(request, url) {
  if (request.method !== 'GET') return false;
  if (request.destination !== 'image') return false;
  return /(^|\.)tile\.openstreetmap\.org$/i.test(url.hostname) || /(^|\.)gis\.fiskeridir\.no$/i.test(url.hostname);
}

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  if (isMapTileRequest(event.request, url)) {
    event.respondWith(
      caches.open(MAP_TILE_CACHE).then(cache => cache.match(event.request).then(match => {
        if (match) return match;
        return fetch(event.request).then(response => {
          if (response && (response.ok || response.type === 'opaque')) cache.put(event.request, response.clone()).catch(() => {});
          return response;
        }).catch(() => match || new Response('', { status: 504 }));
      }))
    );
    return;
  }

  if (url.origin !== self.location.origin) return;

  if (shouldBypassCache(url)) {
    event.respondWith(fetch(event.request));
    return;
  }

  if (url.pathname.startsWith(STATIC_PREFIX)) {
    event.respondWith(
      fetch(event.request).then(networkRes => {
        const clone = networkRes.clone();
        caches.open(CACHE).then(cache => { cache.put(event.request, clone); if (url.search) cache.put(url.pathname, networkRes.clone()); }).catch(() => {});
        return networkRes;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  if (shouldHandleApi(url)) {
    event.respondWith(
      fetch(event.request).then(networkRes => {
        const clone = networkRes.clone();
        caches.open(CACHE).then(cache => { cache.put(event.request, clone); if (url.search) cache.put(url.pathname, networkRes.clone()); }).catch(() => {});
        return networkRes;
      }).catch(() => caches.match(event.request).then(match => match || new Response(JSON.stringify({ type: 'FeatureCollection', features: [], layers: [] }), { headers: { 'Content-Type': 'application/json' } })))
    );
    return;
  }

  if (isHtmlNavigation(event.request, url)) {
    event.respondWith(
      fetch(event.request).catch(() => new Response('<!doctype html><meta charset="utf-8"><title>Offline</title><body style="font-family:system-ui;padding:24px"><h1>Offline</h1><p>Ingen nettforbindelse.</p></body>', { headers: { 'Content-Type': 'text/html; charset=utf-8' } }))
    );
  }
});
