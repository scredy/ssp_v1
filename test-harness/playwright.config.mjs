import { defineConfig } from 'playwright/test';

export default defineConfig({
  testDir: './specs',
  outputDir: process.env.SSP_TEST_RESULTS_DIR ?? './artifacts/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: process.env.SSP_TEST_REPORT_DIR ?? './artifacts/html-report', open: 'never' }]],
  use: {
    baseURL: process.env.SSP_TEST_BASE_URL ?? 'http://localhost:3100',
    ignoreHTTPSErrors: true,
    browserName: 'chromium',
    headless: true,
    screenshot: 'on',
    trace: 'off',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
});
