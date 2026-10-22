import { defineConfig, devices } from '@playwright/test';

// E2E against the REAL app + REAL FastAPI backend in demo mode (no cloud creds
// needed): uvicorn (:8000) + Vite dev server (:5000) whose /py-api proxy wiring
// is exactly what production-minded deployments reverse-proxy.
//
// 127.0.0.1 is pinned everywhere (not localhost) — Node resolves localhost to
// IPv6 first, which has historically desynced Playwright's readiness probe
// from Vite's IPv4 bind (playwright#21227).

const FRONT_URL = 'http://127.0.0.1:5000';
const API_URL = 'http://127.0.0.1:8000';

const demoBackendEnv = {
  // Skip backend/.env re-loads so demo vars below win in every environment.
  CARBONX_SKIP_DOTENV: '1',
  // Empty strings intentionally DEGRADE the backend to labelled demo mode —
  // the same honest-offline stance the unit/CI suites exercise.
  SUPABASE_URL: '',
  SUPABASE_SERVICE_ROLE_KEY: '',
  SUPABASE_ANON_KEY: '',
  VITE_SUPABASE_URL: '',
  VITE_SUPABASE_ANON_KEY: '',
  CARBONX_PAYMENTS_PROVIDER: 'simulated',
  CARBONX_ALLOW_DEV_OTP: '1',
  // Keep the 5-day NDVI scheduler out of browser tests.
  CARBONX_AUTO_MONITOR: '0',
  CARBONX_ENVIRONMENT: 'development',
  JWT_SECRET_KEY: 'e2e-only-secret-key-not-for-production-random-32chars',
};

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: FRONT_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      name: 'backend',
      command: 'python -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: 'backend',
      url: `${API_URL}/health`,
      env: { ...process.env, ...demoBackendEnv },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      name: 'frontend',
      command: 'npx vite --host 127.0.0.1 --port 5000 --strictPort',
      url: FRONT_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
  ],
});
