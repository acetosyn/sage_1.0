// SAGE SERVICE WORKER — Phase 7
// Receives optional VAPID Web Push and keeps the PWA shell deliberately network-first so authenticated tenant pages are never cached across users.

self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
self.addEventListener('push', event => {
  let data = {}; try { data = event.data ? event.data.json() : {}; } catch (_) { data = {body: event.data?.text() || 'New SAGE notification'}; }
  const title = data.title || 'SAGE'; const options = {body:data.body || 'New activity requires your attention.', icon:data.icon || '/static/img/sage.png', badge:'/static/img/sage.png', tag:data.tag || 'sage-notification', data:{url:data.url || '/dashboard'}, requireInteraction:data.level === 'danger'};
  event.waitUntil(self.registration.showNotification(title, options));
});
self.addEventListener('notificationclick', event => {
  event.notification.close(); const target = event.notification.data?.url || '/dashboard';
  event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(clients => { for (const client of clients) { if ('focus' in client) { client.navigate(target); return client.focus(); } } return self.clients.openWindow ? self.clients.openWindow(target) : null; }));
});
