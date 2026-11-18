const { test, expect } = require('@playwright/test');

/**
 * Week 4 — parallel-safe data: each test uses its own post id.
 * Layman: two workers, two different lockers — no shared key.
 */
const cases = [
  { postId: 1, titleHint: 'sunt' },
  { postId: 2, titleHint: 'qui' },
];

for (const { postId, titleHint } of cases) {
  test(`GET /posts/${postId} returns 200 and matching id`, async ({ request }) => {
    const response = await request.get(`/posts/${postId}`);

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body.id).toBe(postId);
    expect(String(body.title).toLowerCase()).toContain(titleHint);
  });
}
