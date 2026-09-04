import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Separate from vite.config.ts so the dev-server proxy settings and the test
// runner cannot interfere with each other.
export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom, not node: useAuthStore.ts reads localStorage at module scope
    //   const SAVED_TOKEN = localStorage.getItem('auth_token');
    // so importing it under the node environment throws ReferenceError before a
    // single assertion runs.
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // Fail instead of silently passing if the suite ever ends up empty. The
    // whole point of this stage is that it can fail.
    passWithNoTests: false,
    restoreMocks: true,
    clearMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      reportsDirectory: 'coverage',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.{test,spec}.{ts,tsx}', 'src/main.tsx', 'src/types/**', 'src/**/*.d.ts'],
    },
  },
});
