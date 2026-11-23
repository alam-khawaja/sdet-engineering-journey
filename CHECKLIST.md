# Evidence checklist

Unchecked means pending, not failed. Every completed item needs dated evidence.

## Initial diagnostic

- [x] Complete 15 practical questions. (2026-11-04)
- [x] Record area ratings and gaps. (2026-11-04)
- [x] Agree realistic first four weeks and first CIP. (2026-11-04)

## Active topic

Topic: Week 7 — Docker refresh (light): image vs container, when Docker helps CI (started 2026-11-23).

- [x] Understand: image = blueprint, container = running instance; pinned image avoids version drift across machines for UI tests — learner 2026-11-23.
- [ ] Implement: run one suite inside the official Playwright Docker image.
- [ ] Debug: break one thing (port/env/mount) and read the error.
- [ ] Explain: when Docker helps a test suite and when it is overhead.

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
