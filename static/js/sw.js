const CACHE_NAME = 'rescuease-v1';
const urlsToCache = [
  '/',
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/js/socket.js',
  '/static/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request).catch(() => {
          // Return offline page for navigation requests
          if (event.request.mode === 'navigate') {
            return caches.match('/');
          }
        });
      })
  );
});

self.addEventListener('sync', event => {
  if (event.tag === 'sync-emergencies') {
    event.waitUntil(syncOfflineQueue());
  }
});

async function syncOfflineQueue() {
  // This will be handled by the main app
  const clients = await self.clients.matchAll();
  clients.forEach(client => {
    client.postMessage({type: 'sync-offline-queue'});
  });
}
