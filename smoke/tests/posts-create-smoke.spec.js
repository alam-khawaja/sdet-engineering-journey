const { test, expect } = require('@playwright/test');

/**
 * CIP deepen — create flow with unique data (no shared record).
 * JSONPlaceholder fakes creates (returns an id); good for learning data lifecycle.
 */
test('POST /posts creates a post with unique title', async ({ request }, testInfo) => {
  const uniqueTitle = `smoke-worker-${testInfo.workerIndex}-${Date.now()}`;

  const response = await request.post('/posts', {
    data: {
      title: uniqueTitle,
      body: 'week5 cip deepen',
      userId: 1,
    },
  });

  expect(response.status()).toBe(201);

  const body = await response.json();
  expect(body.title).toBe(uniqueTitle);
  expect(body).toHaveProperty('id');
});
