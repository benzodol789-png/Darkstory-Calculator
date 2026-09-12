// Service worker — ทำให้เปิดแอปได้แม้เน็ตไม่ดี และอัปเดตเองเมื่อมีของใหม่
//
// ขึ้นเลขนี้ทุกครั้งที่แก้ไฟล์ในเว็บ ไม่งั้นเครื่องที่เคยเปิดแล้วจะยังใช้ของเก่า
const VERSION = 'codex-v1';

const SHELL = [
  './',
  'index.html',
  'css/app.css',
  'js/app.js',
  'js/calc.js',
  'js/data.js',
  'js/search.js',
  'js/api.js',
  'js/config.js',
  'manifest.json',
  'icons/icon-192.png',
  'icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(VERSION)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)),
      ))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  // ข้อมูลจากชีตต้องสดเสมอ ห้ามแคช ไม่งั้นราคาที่เพื่อนอัปเดตจะไม่ขึ้น
  if (!request.url.startsWith(self.location.origin)) return;

  event.respondWith(
    // เอาของใหม่จากเน็ตก่อน ถ้าเน็ตล่มค่อยใช้ของที่แคชไว้
    fetch(request)
      .then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((cache) => cache.put(request, copy));
        return res;
      })
      .catch(() => caches.match(request).then((hit) => hit || caches.match('index.html'))),
  );
});
