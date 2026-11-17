# Evidence checklist

Unchecked means pending, not failed. Every completed item needs dated evidence. Existing experience can satisfy a gate through a practical checkpoint.

## Initial diagnostic

- [x] Complete 15 practical questions. (2026-11-04 — Q1–Q13 answered; Q14 LLM + Q15 MCP deferred as major checkpoints, recorded in PROGRESS/LEARNING_PLAN)
- [x] Record area ratings and gaps. (2026-11-04 — LEARNING_PLAN.md)
- [x] Agree realistic first four weeks and first CIP. (2026-11-04 — weeks in LEARNING_PLAN; CIP Planned in CIP_TRACKER)

## Active topic

Topic: Week 3 — Playwright API smoke (started 2026-11-16).

- [x] Understand: API request smoke via Playwright `request` (2026-11-16).
- [x] Implement: `npx playwright test` — 1 passed `GET /posts/1` (2026-11-16, learner-reported).
- [x] Debug: deliberate expect 999 → Expected 999 / Received 1 + trace.zip; restored to 1 → passed again (2026-11-16).
- [x] Explain: asserts exact id 1 (fails other values); does not cover multi-valid-ids or timeout cases (2026-11-16). Also proves happy-path 200+shape for that one call.

Evidence: learner terminal pass/fail/pass; `smoke/tests/posts-smoke.spec.js`; Explain in PROGRESS journal.

### Week 2 (closed)

- [x] Auth 401/403 + idempotency design — journal 2026-11-16.

### Week 1 (closed)

- [x] Git + HTTP/DevTools — see journal 2026-11-16 / `fix/week1-demo` @ `83393db`.

## Major checkpoints (deferred from diagnostic)

- [ ] LLM / AI fundamentals (models, prompting, tuning, fine-tuning, RAG, eval).
- [ ] MCP fundamentals (host/client/server/tools; MCP vs direct API; later read-only tool).

## Major deliverables

- [ ] Reproducible API/UI automation project.
- [ ] Tests execute in CI with useful reports.
- [ ] Failure investigation and reliability evidence.
- [ ] AI workflow with evaluation cases and limitations.
- [ ] Useful MCP tool with input/access failure checks.
- [ ] Portfolio index and honest interview explanations.
