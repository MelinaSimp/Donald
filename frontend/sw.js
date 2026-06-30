// Service Worker — pass-through, no caching of shell
// This prevents stale PWA installs on iOS

self.addEventListener('install', event => {
    console.log('[SW] Install event');
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    console.log('[SW] Activate event');
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', event => {
    // Simple pass-through: all requests go to the network
    // No caching strategy — we want fresh assets on every load
    event.respondWith(fetch(event.request));
});
