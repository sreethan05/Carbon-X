import { defineConfig } from 'vitest/config';

// Unit tests cover pure frontend logic only (services, lib, utils).
// Browser-journey coverage lives in Playwright (npm run test:e2e, `e2e/`).
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.test.{js,jsx}'],
    environmentOptions: {
      jsdom: {
        url: 'http://localhost:5000/',
      },
    },
  },
});
