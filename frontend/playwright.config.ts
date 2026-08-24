import { defineConfig } from '@playwright/test'

process.env.PWTEST_CHILD_PROCESS_TIMEOUT = '10000'
const e2ePython = process.env.E2E_PYTHON || (process.platform === 'win32' ? '..\\.venv\\Scripts\\python.exe' : 'python')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    channel: 'chrome',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `${e2ePython} ../scripts/run_e2e_backend.py`,
      cwd: '.',
      url: 'http://127.0.0.1:8001/ready',
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 4173',
      cwd: '.',
      url: 'http://127.0.0.1:4173/login',
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        VITE_API_BASE_URL: 'http://127.0.0.1:8001',
        VITE_API_TIMEOUT_MS: '15000',
      },
    },
  ],
})
