# Evidence checklist

Unchecked means pending, not failed. Every completed item needs dated evidence. Existing experience can satisfy a gate through a practical checkpoint.

## Initial diagnostic

- [x] Complete 15 practical questions. (2026-11-04 — Q1–Q13 answered; Q14 LLM + Q15 MCP deferred as major checkpoints, recorded in PROGRESS/LEARNING_PLAN)
- [x] Record area ratings and gaps. (2026-11-04 — LEARNING_PLAN.md)
- [x] Agree realistic first four weeks and first CIP. (2026-11-04 — weeks in LEARNING_PLAN; CIP Planned in CIP_TRACKER)

## Active topic

Topic: Week 2 — API auth (401/403) + idempotency (started 2026-11-16).

- [x] Understand: authn vs authz; 401 vs 403; same-key retry must not double-charge (2026-11-16).
- [x] Implement: 401/403 cases; idempotency sketch — same key → no duplicate (409/safe replay); new key → new process (2026-11-16).
- [ ] Debug: optional (later).
- [x] Explain: unique key per transaction → cannot debit/withdraw twice (2026-11-16).

Evidence: Week 2 answers in PROGRESS journal 2026-11-16.

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
