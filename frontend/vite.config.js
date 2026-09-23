import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    // Forwarded unrewritten: the app sees `/api/auth/login` locally and behind
    // CloudFront alike, so no path middleware is needed anywhere.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    css: false,
    // Page tests drive several round trips through MUI; the default 5 s is
    // tight when eight workers share the machine.
    testTimeout: 15000,
    coverage: {
      provider: 'v8',
      // Every source file, not only the ones a test happened to import, so the
      // number T96 ratchets from is honest about untested screens.
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/main.jsx', 'src/test/**', 'src/**/*.test.{js,jsx}'],
      reporter: ['text', 'html'],
      reportsDirectory: './coverage',
    },
  },
})
