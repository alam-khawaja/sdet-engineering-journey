const { test, expect } = require('@playwright/test');

/**
 * Week 3 — one critical API smoke flow (synthetic data).
 * GET /posts/1 should succeed and return the expected post id.
 */
test('GET /posts/1 returns 200 and id 1', async ({ request }) => {
  const response = await request.get('/posts/1');

  expect(response.status()).toBe(200);

  const body = await response.json();
  expect(body.id).toBe(1);
  expect(body).toHaveProperty('title');
});
