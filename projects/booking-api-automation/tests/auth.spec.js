const { test, expect } = require('@playwright/test');

test('POST /auth returns a token with valid demo credentials', async ({ request }) => {
  const response = await request.post('/auth', {
    data: {
      username: 'admin',
      password: 'password123',
    },
  });

  expect(response.status()).toBe(200);

  const body = await response.json();
  expect(body.token).toBeTruthy();
  expect(typeof body.token).toBe('string');
});

test('POST /auth fails with wrong password', async ({ request }) => {
  const response = await request.post('/auth', {
    data: {
      username: 'admin',
      password: 'wrong-password',
    },
  });

  // Restful Booker returns 200 with { reason: "Bad credentials" } for bad auth
  const body = await response.json();
  expect(body.reason || body.token).toBeTruthy();
  if (body.token) {
    throw new Error('Expected no token for bad credentials');
  }
  expect(body.reason).toMatch(/bad credentials/i);
});
