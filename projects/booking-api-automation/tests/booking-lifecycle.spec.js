const { test, expect } = require('@playwright/test');
const { getAuthToken } = require('./helpers/auth');

/**
 * Critical flow: create → read → delete with unique guest names (parallel-safe).
 */
test('booking lifecycle: create, get, delete', async ({ request }, testInfo) => {
  const stamp = `${testInfo.workerIndex}-${Date.now()}`;
  const firstname = `Auto${stamp}`;
  const lastname = `Demo${stamp}`;

  const createResponse = await request.post('/booking', {
    data: {
      firstname,
      lastname,
      totalprice: 120,
      depositpaid: true,
      bookingdates: {
        checkin: '2026-12-01',
        checkout: '2026-12-05',
      },
      additionalneeds: 'Breakfast',
    },
  });

  expect(createResponse.status()).toBe(200);

  const created = await createResponse.json();
  expect(created.bookingid).toBeTruthy();
  expect(created.booking.firstname).toBe(firstname);
  expect(created.booking.lastname).toBe(lastname);

  const bookingId = created.bookingid;

  const getResponse = await request.get(`/booking/${bookingId}`);
  expect(getResponse.status()).toBe(200);

  const fetched = await getResponse.json();
  expect(fetched.firstname).toBe(firstname);
  expect(fetched.lastname).toBe(lastname);

  const token = await getAuthToken(request);
  const deleteResponse = await request.delete(`/booking/${bookingId}`, {
    headers: {
      Cookie: `token=${token}`,
    },
  });

  expect(deleteResponse.status()).toBe(201);

  const afterDelete = await request.get(`/booking/${bookingId}`);
  expect(afterDelete.status()).toBe(404);
});
