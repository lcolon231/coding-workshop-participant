/*
 * The offline shell.
 *
 * Three rules, chosen by URL:
 *   - `/api/...` is never cached. Incident data must be fresh, and a cached
 *     answer to a mutation would be a lie.
 *   - `/assets/...` are Vite's hashed bundles: immutable, so cache-first and
 *     kept until a new shell version sweeps them.
 *   - a navigation (any page load) is network-first, falling back to the
 *     cached `index.html` so the app still opens with no connection. The app
 *     then shows its own offline state instead of the browser's error page.
 *
 * `VERSION` changes whenever the shell's shape changes; activation deletes
 * every other cache.
 */
const VERSION = 'acme-shell-v3'
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png']

/**
 * The bundles the shell needs, read off `index.html` itself: Vite names them
 * by content hash, so the worker cannot know them ahead of time. Without
 * this the first page load, which happens before the worker controls the
 * page, would leave the scripts uncached and the offline shell empty.
 */
async function bundleUrls() {
  const html = await (await fetch('/index.html', { cache: 'no-cache' })).text()
  const urls = new Set()
  for (const match of html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)) urls.add(match[1])
  // The stylesheet pulls in the font; it is not in the HTML.
  for (const url of [...urls].filter((u) => u.endsWith('.css'))) {
    const css = await (await fetch(url, { cache: 'no-cache' })).text()
    for (const match of css.matchAll(/url\((\/assets\/[^)]+\.woff2?)\)/g)) urls.add(match[1])
  }
  return [...urls]
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(VERSION)
      await cache.addAll(SHELL)
      await cache.addAll(await bundleUrls())
      await self.skipWaiting()
    })(),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  )
})

async function networkFirstShell(request) {
  try {
    const response = await fetch(request)
    if (response.ok) {
      const cache = await caches.open(VERSION)
      cache.put('/index.html', response.clone())
    }
    return response
  } catch {
    const cached = await caches.match('/index.html', { ignoreVary: true })
    return cached ?? Response.error()
  }
}

// `ignoreVary`: the server varies on Accept-Encoding, and a worker's lookup
// does not carry the same header the page's request did; the bytes are the same.
async function cacheFirst(request) {
  const cached = await caches.match(request, { ignoreVary: true })
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) {
    const cache = await caches.open(VERSION)
    cache.put(request, response.clone())
  }
  return response
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) return
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstShell(request))
    return
  }
  if (url.pathname.startsWith('/assets/') || SHELL.includes(url.pathname)) {
    event.respondWith(cacheFirst(request))
  }
})
