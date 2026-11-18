// @ts-check
const { defineConfig } = require('@playwright/test');

/**
 * Interview demo project — public Restful Booker API only.
 * No company credentials or data.
 */
module.exports = defineConfig({
  testDir: './tests',
  timeout: 45_000,
  retries: process.env.CI ? 1 : 0,
  fullyParallel: true,
  workers: process.env.CI ? 2 : undefined,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  use: {
    baseURL: 'https://restful-booker.herokuapp.com',
    extraHTTPHeaders: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    // Week 6: keep evidence when something fails
    trace: 'retain-on-failure',
  },
});
