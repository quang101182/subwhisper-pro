var CACHE = 'subwhisper-pro-v1.1.9';
var FILES = ['./', './index.html', './prompts.js'];

self.addEventListener('install', function(e) {
  e.waitUntil(caches.open(CACHE).then(function(c) { return c.addAll(FILES); }));
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      var old = keys.filter(function(k) { return k !== CACHE; });
      return Promise.all(old.map(function(k) { return caches.delete(k); })).then(function() {
        if (old.length > 0) {
          self.clients.matchAll().then(function(clients) {
            clients.forEach(function(c) { c.postMessage({ type: 'SW_UPDATED', version: CACHE }); });
          });
        }
      });
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  // Skip cross-origin requests (PostHog, analytics, APIs, fonts, etc.)
  if (!e.request.url.startsWith(self.location.origin)) return;
  // Only cache same-origin navigation/page requests
  if (e.request.mode === 'navigate' || e.request.url.endsWith('index.html')) {
    e.respondWith(
      fetch(e.request).then(function(r) {
        var clone = r.clone();
        caches.open(CACHE).then(function(c) { c.put(e.request, clone); });
        return r;
      }).catch(function() {
        return caches.match(e.request);
      })
    );
    return;
  }
});
