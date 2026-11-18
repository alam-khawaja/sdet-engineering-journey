// @ts-check
const { defineConfig } = require('@playwright/test');

/**
 * Personal learning smoke config.
 * Uses a public synthetic API — no company credentials or data.
 */
module.exports = defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  fullyParallel: true,
  workers: process.env.CI ? 2 : undefined,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'https://jsonplaceholder.typicode.com',
    extraHTTPHeaders: {
      Accept: 'application/json',
    },
    // On CI failures, keep evidence for the artifact upload step
    trace: 'retain-on-failure',
  },
});
