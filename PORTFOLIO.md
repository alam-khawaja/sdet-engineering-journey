# Interview evidence index

| Project | Status | Concepts demonstrated | My contribution | Evidence | Limitations |
|---|---|---|---|---|---|
| [smoke/](smoke/) API smoke (JSONPlaceholder) | Week 3–4 done | Playwright request API; parallel-safe cases; GHA CI + failure artifacts; Expected vs Received debug | Ran local workers; explained isolation/CI; authorized personal push | Local 3 passed `--workers=2`; Actions success [run 44349942865](https://github.com/alam-khawaja/sdet-engineering-journey/actions/runs/44349942865); [smoke/README.md](smoke/README.md) | Synthetic API only; no auth/UI; CIP impact not measured; optional failure-artifact drill not run (CI green) |

For each project add a README with problem, setup/run commands, architecture, decisions/trade-offs, meaningful checks, debugging story, measured results, AI assistance, and limitations. Link code and reproducible evidence.

Interview narrative: “I built a small Playwright API smoke against a public synthetic API to practice assertions and failure traces. I investigated a deliberate wrong assertion using Expected vs Received and a trace zip. Evidence shows the happy path passes locally. Limits: one call, no auth/UI/timeouts, not production impact.”

Suggested progression: critical-flow automation → CI/reports → evaluated requirement analyzer → read-only MCP tool. Prefer depth and reliability over project count.
