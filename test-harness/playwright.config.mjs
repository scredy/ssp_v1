import { defineConfig } from 'playwright/test';

export default defineConfig({
  testDir: './specs',
  outputDir: './artifacts/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: './artifacts/html-report', open: 'never' }]],
  use: {
    baseURL: 'http://localhost:3100',
    browserName: 'chromium',
    headless: true,
    screenshot: 'on',
    trace: 'off',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
});
