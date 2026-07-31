var CACHE = 'pingpilot-v1';
var OFFLINE_URL = '/static/offline.html';
var APP_SHELL = [
  '/',
  '/dashboard/',
  '/static/css/global.css',
  '/static/manifest.webmanifest',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/maskable-192.png',
  '/static/maskable-512.png',
  '/static/offline.html'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return Promise.all(
        APP_SHELL.map(function (url) {
          return cache.add(url).catch(function () {});
        })
      );
    }).then(function () { self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k !== CACHE) return caches.delete(k);
      }));
    }).then(function () { self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;

  var url = new URL(req.url);

  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req)
        .then(function (resp) {
          var copy = resp.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); });
          return resp;
        })
        .catch(function () {
          return caches.match(req)
            .then(function (cached) {
              return cached || caches.match('/');
            })
            .catch(function () { return caches.match(OFFLINE_URL); });
        })
    );
    return;
  }

  if (url.origin === self.location.origin) {
    e.respondWith(
      caches.match(req).then(function (cached) {
        var fetchPromise = fetch(req).then(function (resp) {
          if (resp && resp.status === 200) {
            var copy = resp.clone();
            caches.open(CACHE).then(function (c) { c.put(req, copy); });
          }
          return resp;
        }).catch(function () { return cached; });
        return cached || fetchPromise;
      })
    );
  }
});
