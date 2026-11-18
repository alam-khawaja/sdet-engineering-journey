# Week 3 — API smoke (personal)

Synthetic public API: [JSONPlaceholder](https://jsonplaceholder.typicode.com).  
No company credentials, tickets, or data.

## Run

```bash
cd smoke
npm install
npx playwright test
npx playwright test --workers=2
```

## Intent

- Week 3: one stable critical flow (`posts-smoke.spec.js`) + fail/trace drill.
- Week 4: parallel-safe cases (`posts-parallel-smoke.spec.js`) + GitHub Actions workflow with failure artifacts.

## CI

Workflow: `.github/workflows/smoke.yml`  
On failure it uploads `playwright-report/` and `test-results/` as artifacts.
