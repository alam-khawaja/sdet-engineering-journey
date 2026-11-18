/**
 * Restful Booker demo credentials are public (training API).
 * @param {import('@playwright/test').APIRequestContext} request
 */
async function getAuthToken(request) {
  const response = await request.post('/auth', {
    data: {
      username: 'admin',
      password: 'password123',
    },
  });

  if (response.status() !== 200) {
    throw new Error(`Auth failed with status ${response.status()}`);
  }

  const body = await response.json();
  if (!body.token) {
    throw new Error('Auth response missing token');
  }

  return body.token;
}

module.exports = { getAuthToken };
