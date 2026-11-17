# Interview evidence index

| Project | Status | Concepts demonstrated | My contribution | Evidence | Limitations |
|---|---|---|---|---|---|
| [smoke/](smoke/) API smoke (JSONPlaceholder) | In progress (Week 3 done) | Playwright request API; status/body asserts; deliberate fail + trace; Expected vs Received | Ran install/tests; broke/restored assertion; explained limits | Local `npx playwright test` pass; fail with trace.zip; [smoke/README.md](smoke/README.md) | One endpoint; exact id only; no multi-valid ids; no timeout cases; no auth/UI; synthetic public API only — not company impact |

For each project add a README with problem, setup/run commands, architecture, decisions/trade-offs, meaningful checks, debugging story, measured results, AI assistance, and limitations. Link code and reproducible evidence.

Interview narrative: “I built a small Playwright API smoke against a public synthetic API to practice assertions and failure traces. I investigated a deliberate wrong assertion using Expected vs Received and a trace zip. Evidence shows the happy path passes locally. Limits: one call, no auth/UI/timeouts, not production impact.”

Suggested progression: critical-flow automation → CI/reports → evaluated requirement analyzer → read-only MCP tool. Prefer depth and reliability over project count.
