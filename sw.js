"use strict";
const CACHE = "kr-job-radar-public-v1";
const ROOT = new URL("./", self.location.href);
const ASSETS = ["./", "index.html", "style.css", "app.js", "insights.js", "install.js",
  "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png",
  "icons/icon-maskable.png", "icons/apple-touch-icon.png", "data/jobs.js"];
const URLS = new Set(ASSETS.map(path => new URL(path, ROOT).href));
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => key.startsWith("kr-job-radar-public-") && key !== CACHE)
    .map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  // Cache only this app's public assets. Never intercept decrypted pages,
  // encrypted snapshots, API requests, CVs or credentials.
  if (event.request.method !== "GET" || !URLS.has(event.request.url)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const response = await fetch(event.request, {cache: "no-cache"});
      if (response.ok) await cache.put(event.request, response.clone());
      return response;
    } catch (error) {
      const cached = await cache.match(event.request);
      if (cached) return cached;
      throw error;
    }
  })());
});
