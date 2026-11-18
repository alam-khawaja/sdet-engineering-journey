# Evidence checklist

Unchecked means pending, not failed. Every completed item needs dated evidence. Existing experience can satisfy a gate through a practical checkpoint.

## Initial diagnostic

- [x] Complete 15 practical questions. (2026-11-04 — Q1–Q13 answered; Q14 LLM + Q15 MCP deferred as major checkpoints, recorded in PROGRESS/LEARNING_PLAN)
- [x] Record area ratings and gaps. (2026-11-04 — LEARNING_PLAN.md)
- [x] Agree realistic first four weeks and first CIP. (2026-11-04 — weeks in LEARNING_PLAN; CIP Planned in CIP_TRACKER)

## Active topic

Topic: Week 4 — parallel data + GitHub Actions CI (started 2026-11-18).

- [x] Understand: shared mutable data → race/order dependency (update vs delete) → flaky; tests must be independent/isolated (2026-11-18).
- [~] Implement: local `--workers=2` → 3 passed (2026-11-18). CI Actions run pending push.
- [ ] Debug: optional CI failure artifact inspection.
- [x] Explain: CI pipeline checks new commits before deploy; shared repo for team access/contribute (2026-11-18). Also: runs off laptop, same machine for everyone, failure artifacts.

Evidence: learner terminal — 3 passed (2.9s) with 2 workers; CI pending push.

### Week 3 (closed)

- [x] Playwright API smoke + fail/trace — journal 2026-11-16 / `smoke/`.

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
