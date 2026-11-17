# Week 3 — API smoke (personal)

Synthetic public API: [JSONPlaceholder](https://jsonplaceholder.typicode.com).  
No company credentials, tickets, or data.

## Run

```bash
cd smoke
npm install
npx playwright test
```

## Intent

One stable critical flow: fetch a post and assert status + id.  
Later: deliberate failure + Playwright trace (Week 3 debug gate).
