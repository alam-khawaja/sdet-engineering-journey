# Learning plan

Target: June 2027 review and demonstrable SDET capability. Capacity assumption: three 45-minute learning sessions and one 60-minute practical session weekly. Adjust after assessment.

## Diagnostic

Status: **complete for routing** (2026-11-04). Q1–Q13 answered with gaps; Q14 (LLM) and Q15 (MCP) deferred to major checkpoints (unfamiliar). Area ratings and first four weeks below. First CIP: critical API smoke (see CIP_TRACKER.md).

## Area ratings (diagnostic evidence only — not mastery)

| Area | Rating | Notes |
|---|---|---|
| Git | Emerging | Branch/commit/push OK; gaps: stash/WIP isolation, revert vs reset, verify with diff |
| HTTP | Emerging | Path OK after teach; TCP vs UDP, pre-HTTP failures |
| API (authn/authz) | Emerging+ | Roles/403 OK; clarify 401 vs authn wording |
| Backend | Emerging+ | Idempotency + single-winner booking solid; deepen race evidence |
| Database | Emerging | Transactions OK; EXPLAIN/index selectivity gaps |
| Playwright | Emerging | Logs/locators/auth storage OK; avoid sleeps; parallel data isolation |
| CI/CD | Emerging | Acceptable after teach; deepen workflows |
| Docker | Emerging | Acceptable after teach; host vs container ports |
| Observability | Emerging+ | Strong request-ID triage instincts |
| LLMs | Unassessed | Deferred — major checkpoint |
| MCP | Unassessed | Deferred — major checkpoint |

## Milestones

1. Git/Linux and environment variables (revision: stash, revert).
2. HTTP/APIs, browser DevTools, basic TypeScript.
3. Backend/SQL: transactions, concurrency, retries, idempotency.
4. Reliable Playwright API/UI flow, fixtures and test data.
5. CI execution, reporting, Docker where needed.
6. Failure triage, observability, reliability metrics.
7. **LLM / AI fundamentals (major checkpoint):** models, prompting, tuning, fine-tuning, RAG, eval of generated tests.
8. Evaluated local-LLM QA workflow (after #7).
9. **MCP fundamentals (major checkpoint):** host/client/server/tools; when MCP vs direct API; then a read-only tool with bad-input/access checks.
10. Optional agents after tool calling and core systems.

## LLM checkpoint (major)

Status: Planned — deferred from diagnostic Q14. Study cores in depth before any adoption claims.

Concepts: what LLMs do; prompting vs fine-tuning vs RAG; hallucinations; evaluate generated tests with a rubric.

Gate: explain prompting/fine-tuning/RAG; score sample generated cases; document limitations.

## MCP checkpoint (major)

Status: Planned — deferred from diagnostic Q15 (learner unfamiliar; requested as major checkpoint 2026-11-04).

Prerequisites: solid HTTP/API + some automation; LLM basics helpful but not required for MCP concepts.

Concepts:
1. Host (e.g. Cursor) vs client vs MCP server vs tools.
2. Tools/resources/prompts; schemas; auth/access boundaries.
3. When MCP helps (reusable tool surface for assistants) vs plain API calls (deterministic scripts/tests).

Practical exercise (later): one read-only MCP tool with invalid input and unauthorized access checks.

Gate: explain host/client/server/tools in own words; justify MCP vs direct API for one QA use case; show failure-path checks.

## First four weeks (agreed direction)

Capacity: ~3×45 min + 1×60 min practical / week. Adjust if needed.

| Week | Focus | Exercise | Gate signal |
|---|---|---|---|
| 1 | Git revision + HTTP/DevTools | Stash WIP → bugfix branch; `diff`/`log` verify; trace one HTTPS request in Network | Explain stash vs commit; classify one failed request |
| 2 | API auth + idempotency | Design 401 vs 403 cases; sketch idempotent payment retry test | Name 401/403; same-key retry → one effect |
| 3 | Playwright critical flow start | One API or UI smoke on a **personal sample** app (synthetic data); stable locators; no fixed sleeps | Test runs locally; one failure investigated with trace |
| 4 | Test data + CI intro | Isolate data for parallel; minimal GitHub Actions smoke job + artifacts | Job runs off laptop; failure uploads log/screenshot/trace |

Then: deepen automation → Docker as needed → observability practice → **LLM major checkpoint** → **MCP major checkpoint**.

## First CIP

Critical API smoke validation — Status: **Planned** (see CIP_TRACKER.md). Personal/synthetic scope first; company CIP only with permitted metrics later.
