/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { mockApiPlugin } from './mock/vitePlugin';

// The `mock` mode boots the app with an in-process POST /api/chat middleware
// (same core mock the vitest suite drives through MSW) so the agent-driven E2E
// and local dev run fully offline. No real backend wiring exists in Phase 1.
export default defineConfig(({ mode }) => ({
  plugins: [react(), ...(mode === 'mock' ? [mockApiPlugin()] : [])],
  server: { port: 5178 },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./test/setup.ts'],
    css: true,
    include: ['test/**/*.test.{ts,tsx}'],
  },
}));
