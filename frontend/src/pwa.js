/**
 * Register the offline shell, in production builds only.
 *
 * In development Vite serves modules straight from source and a service
 * worker would only get in the way of hot reload. Registration waits for
 * `load` so it never competes with the first paint.
 */
export function registerServiceWorker() {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // The app works without it; there is nothing useful to tell the user.
    })
  })
}
