# Interview evidence index

| Project | Status | Concepts demonstrated | My contribution | Evidence | Limitations |
|---|---|---|---|---|---|
| [projects/async-webhook-state-machine-qa](projects/async-webhook-state-machine-qa/) | **Built (AI-generated from my spec)** | Oversell race (25 vs stock 1); webhook replay 15×; illegal transitions; poison job → DLQ; HMAC + replay window; local + remote (`BASE_URL`) modes | Walk through each suite; break one assertion and classify; explain optimistic locking vs DB lock | 35 passed local (5× repeat, no flakes); 34 passed + 1 skipped remote | SQLite single-writer; single-process concurrency; not company impact |
| [projects/booking-api-automation](projects/booking-api-automation/) | **Active demo (Week 6)** | Auth; booking create/get/delete; unique data; cleanup; traces/HTML report; CI artifacts | Run suite; Week 6 failure classification; explain design | README + local/CI runs (after first green) | Public heroku demo may be slow/flaky; no UI; not company impact |
| [smoke/](smoke/) JSONPlaceholder API smoke | Week 3–5 done | Request API; parallel GETs; unique POST; baseline timing; GHA | Ran tests; baselines; explains | [Actions](https://github.com/alam-khawaja/sdet-engineering-journey/actions) smoke runs | Toy API; fake POST persistence; thin for interviews vs booking project |

Interview narrative (booking demo): “I built a Playwright API suite against a public booking API to practice auth, create/get/delete with unique data, cleanup, and CI reporting. I investigated failures using Expected vs Received and traces. Limits: third-party demo stability; no UI; not production metrics.”

Suggested progression: this booking demo → deeper reliability notes → LLM checkpoint → MCP tool.
