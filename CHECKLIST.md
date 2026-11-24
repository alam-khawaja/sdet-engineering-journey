# Evidence checklist

Unchecked means pending, not failed. Every completed item needs dated evidence.

## Initial diagnostic

- [x] Complete 15 practical questions. (2026-11-04)
- [x] Record area ratings and gaps. (2026-11-04)
- [x] Agree realistic first four weeks and first CIP. (2026-11-04)

## Active topic

Topic: Week 8 — Observability practice: Expected → Actual → Evidence chain on a failed API case (started 2026-11-23).

- [ ] Understand: logs vs metrics vs traces; what a request/correlation id is for.
- [ ] Implement: make one booking test fail and write a hypothesis → evidence note from the report/trace.
- [ ] Debug: find the exact request/response behind the failure in the trace.
- [ ] Explain: Expected → Actual → Evidence → Classification, in 3 lines.

### Week 7 (closed 2026-11-23)

- [x] Understand: image = blueprint, container = running instance; pinned image avoids version drift across machines for UI tests — learner 2026-11-23.
- [x] Implement: booking suite ran in CI inside `playwright:v1.65.1-noble` — 3 passed (935ms); host Ubuntu 26.04 vs container 24.04.5, Node v26.13.1, uid 1001 (run 45178015825) — 2026-11-23.
- [x] Debug: typo'd image tag (nobel) → "Initialize containers" failed with `not found` after 3 pull retries (run 45179958628); restored, green (run 45180375009) — 2026-11-23. Learner's own classification (setup vs test failure) carried into Explain.
- [x] Explain: image-tag failure = environment/setup (container could not be prepared, "could not resolve"), tests never ran; Docker helps when you need an isolated, pinned, stable environment, overkill when not required — learner 2026-11-23.

### Week 6 (closed 2026-11-23)

- [x] Understand: classified failure types (bad assertion vs real bug vs flaky) during Debug — 2026-11-19.
- [x] Implement: booking-api-automation 3 passed (2.8s, 3 workers) — learner run 2026-11-18.
- [x] Debug: expected 200, received 201 on delete → classified as bad assertion (API contract is 201), not a product bug or flake — learner 2026-11-19.
- [x] Explain: unique data + create→verify→cleanup keeps tests isolated so parallel delete/update can't break each other — 2026-11-23.

Evidence: booking-api CI green on 6a817cf; assertion restored to 201.

### Week 5 (closed)

- [x] CIP deepen unique POST + baseline — journal 2026-11-18.

### Weeks 1–4 (closed)

- [x] See PROGRESS journal / smoke CI runs.

## Major checkpoints

- [ ] LLM / AI fundamentals.
- [ ] MCP fundamentals.

## Major deliverables

- [~] Reproducible API automation project (booking demo in progress; smoke exists).
- [x] Tests execute in CI with reports (smoke; booking workflow added).
- [~] Failure investigation and reliability evidence (Week 6).
- [ ] AI workflow with evaluation cases and limitations.
- [ ] Useful MCP tool with input/access failure checks.
- [~] Portfolio index (booking + smoke rows).
