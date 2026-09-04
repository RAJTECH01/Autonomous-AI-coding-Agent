import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev-server proxy target for /api.
//
// The app calls same-origin relative paths ('/api/v1/sessions'), so something
// has to map /api to the backend:
//   * running vite on the host  -> http://localhost:8000 (default below)
//   * running vite in Compose   -> http://backend:8000, because inside the
//     frontend container 'localhost' is the frontend itself
//   * production                -> no vite at all; the reverse proxy routes /api
//
// This file is not covered by tsconfig.json ("include": ["src"]), so `process`
// needs no @types/node.
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  build: {
    // Explicit so the Dockerfile's COPY --from=build path cannot drift.
    outDir: 'dist',
    sourcemap: false,
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
});
