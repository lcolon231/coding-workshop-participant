import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end runs: a real browser, the real Vite proxy, and a real backend.
 *
 * The backend is a throwaway one: `tools/e2e_backend.py` creates its own
 * database, migrates and seeds it with a known password, and serves every
 * service on one port until the run ends. Vite starts on its own port too,
 * proxying `/api` there, so a `make serve` and `npm run dev` already running
 * for development are neither reused nor disturbed.
 *
 * Needs a local PostgreSQL (the same one `make test` uses) and the Python
 * `.venv`. Run with `npm run test:e2e`.
 */
const BACKEND_PORT = 8100
const FRONTEND_PORT = 3100

export const E2E_PASSWORD = process.env.E2E_PASSWORD || 'e2e-password-not-a-secret'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `../.venv/bin/python ../tools/e2e_backend.py --port ${BACKEND_PORT}`,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/auth/readyz`,
      reuseExistingServer: false,
      timeout: 90_000,
      env: { ACME_SEED_PASSWORD: E2E_PASSWORD },
    },
    {
      command: `npx vite --port ${FRONTEND_PORT} --strictPort`,
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_API_PROXY: `http://127.0.0.1:${BACKEND_PORT}` },
    },
  ],
})
