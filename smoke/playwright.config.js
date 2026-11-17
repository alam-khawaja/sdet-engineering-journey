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
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'https://jsonplaceholder.typicode.com',
    extraHTTPHeaders: {
      Accept: 'application/json',
    },
    trace: 'on-first-retry',
  },
});
