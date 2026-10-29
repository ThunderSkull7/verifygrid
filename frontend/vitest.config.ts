import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Component tests only. The existing zero-dependency logic suite continues to
// run under `node --test tests/*.test.ts` and is intentionally not picked up
// here (it uses the node:test API).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.tsx'],
    clearMocks: true,
    restoreMocks: true,
  },
});
