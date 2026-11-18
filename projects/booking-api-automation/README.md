# Booking API automation (portfolio demo)

Playwright API tests against the public [Restful Booker](https://restful-booker.herokuapp.com) training API.

**Purpose:** demonstrate automation skill — auth, critical booking lifecycle, unique test data, reporting/traces, and CI — with **synthetic** data only (no company systems).

## Problem

Manual API checks (auth → create → get → delete) are slow and easy to skip. This suite automates that critical path with isolated data so tests can run in parallel and in CI.

## Setup

```bash
cd projects/booking-api-automation
npm install
npx playwright test
npx playwright test --workers=2
npx playwright show-report
```

## What it covers

| Area | How |
|---|---|
| Auth | Valid token; bad credentials |
| Critical flow | Create → get → delete booking |
| Data isolation | Unique first/last name per run/worker |
| Cleanup | Delete after assert; expect 404 |
| Reliability evidence | `trace: retain-on-failure`; HTML report |

## Design choices

- **API-first** (Playwright `request`) — faster feedback than UI for this skill demo.
- **Unique names** — avoids parallel collisions (Week 4 lesson).
- **Public demo API** — safe to publish; credentials are the vendor’s documented training values.

## Debugging story

Week 6 practice: force a wrong assertion, open the HTML report / trace, classify **real product failure** vs **bad test expectation** (Expected vs Received).

## AI assistance

Mentor scaffolded the project layout and first tests; learner runs, explains, extends, and owns evidence in the journey portfolio.

## Limitations

- Depends on a third-party heroku demo (can be slow/flaky/down).
- Not a company CIP result; no production metrics claimed.
- No UI coverage yet.
- Auth “failure” shape follows Restful Booker’s quirky responses.

## Interview line

“I built a Playwright API suite against a public booking API to practice auth, create/get/delete with unique data, cleanup, and CI reporting — and I can show a failure trace distinguishing a wrong assertion from a real API defect.”
