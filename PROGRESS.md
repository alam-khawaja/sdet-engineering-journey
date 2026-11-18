# Progress

## Current state

Current focus: Week 6 — portfolio booking API demo + reporting/reliability.
Current topic: Debug drill — deliberate failure in booking lifecycle, read HTML report/trace, classify failure.
Current phase: Debug (Week 6).
Next diagnostic question: n/a.
Completed topics: Week 1–5.
Blocked topics: LLM + MCP deferred as major checkpoints.
Next action: change lifecycle delete expectation 201 → 200, run tests, open report, classify failure; then restore 201.

## Workspace and project state

Learning repository path: `/Users/alam/sdet-engineering-journey`
Active project path: `/Users/alam/sdet-engineering-journey/projects/booking-api-automation`
Work context: personal learning.
Mode: Teach.
Current milestone: Week 6 booking API demo + reliability reporting.
Pending gates: Week 6 Understand/Implement/Debug/Explain; LLM + MCP major checkpoints.
Evidence paths: `projects/booking-api-automation/`, `PROGRESS.md`, `PORTFOLIO.md`.
Personal GitHub repository URLs: https://github.com/alam-khawaja/sdet-engineering-journey
Standing publication authorization: initial bootstrap push authorized by learner request to set up personal GitHub with this journey (2026-10-07). Further milestone pushes on request unless standing auth is expanded.

## Diagnostic record

| Question | Area | Answer summary | Feedback/evidence | Revision |
|---|---|---|---|---|
| 1 | Git | Create/checkout bugfix branch, work there; said unfinished changes stay off that branch because not pushed; then add/commit/push | Incomplete/partially incorrect (2026-10-19): uncommitted changes usually follow you on checkout; push is unrelated to isolating WIP. Missed verify-only-intended-changes (`status`/`diff`/`log`). Better: stash or commit WIP on current branch, then new branch for fix, then compare against main | Practice stash; verify with diff/log vs main |
| 2 | Git | Suggested `git reset HEAD~` to undo merged bad commit on shared branch | Incomplete for shared branches (2026-10-19): reset rewrites history; after merge/push prefer `git revert` (new undo commit). Syntax is `HEAD~` not `HEAD ~`. Reset OK only on private unpushed commits | Read revert vs reset |
| 3 | HTTP | Restate (2026-10-19): domain → DNS → host IP → TCP/UDP → TLS → communication; failures via HTTP status (401/400/403/404), JS console, CORS | Acceptable after teach: path mostly right; HTTPS uses TCP (not UDP for normal page load); good to include status + console/CORS. Still light on pre-HTTP failures (DNS/TLS) | Optional: Network tab timing + failed request type |
| 4 | API | Authn ≈ valid user/token; authz ≈ privileges/roles; agent vs admin → 403 (2026-10-19) | Mostly correct roles idea; authn is “who are you”, not “can you reach area”. Missing explicit 401 (missing/invalid token) vs 403 (valid identity, forbidden action) | Practice naming 401 vs 403 test cases |
| 5 | Backend | Idempotency keys; same payload twice → only first succeeds / duplicates blocked (2026-10-21) | Correct prevention idea. Light on *how* duplicates happen (timeout after server already charged, client retries). Test: same key → one charge + same response; new key → new charge; concurrent same-key retries still one effect | Optional: inspect DB/ledger for single payment row |
| 6 | Backend | Only one checkout; other gets “already booked”; no duplicate slot IDs; FE shows booked if race; one slot ≠ two users (2026-10-21) | Correct invariant. FE is UX only — enforce with DB unique constraint and/or transactional lock on server. Evidence: concurrent API test, one booking row, second 409/400 + message | Note: race must be safe even if both never refreshed UI |
| 7 | Database | Transaction all-or-nothing (one or none); on mid-fail rollback to original; verify by interrupting mid-way (2026-10-21) | Correct (meant rollback, not rollout). Verify both tables unchanged after forced failure; success path updates both | Optional: assert API error + DB row counts/state |
| 8 | Database | Check WHERE columns, joins, filter indexed cols first, confirm index exists; claimed non-unique WHERE means index won’t work (2026-10-21) | Good instincts on filters/joins/indexes. Incorrect: indexes work on non-unique columns (selectivity affects usefulness). Main tool: EXPLAIN/query plan — seq scan vs index scan as data grows | Learn EXPLAIN; unique ≠ required for index use |
| 9 | Playwright | Check error logs/fail point, console, resource load/render, deploys; try small waits + async/await; long XPaths flaky (2026-11-02) | Good on logs/console/locators. Prefer Playwright auto-wait + assert visible/enabled over sleep waits. Use trace/screenshot/video; CI slower/env diffs. Prefer role/test-id over long XPath | Avoid fixed sleeps; use trace |
| 10 | Playwright | Same auth → store session and reuse; different auth levels → separate preserved states/scenarios (2026-11-02) | Correct storageState/role idea. Light on data isolation for parallel: unique users/records per worker, no shared mutable data, cleanup/fixtures | Add unique test data per parallel worker |
| 11 | CI/CD | Restate (2026-11-02): CI runs smoke script (Playwright/bash) with its config; on fail capture runtime errors, network failures, logs, screenshots for UI | Acceptable after teach. Add: trigger on push/PR, checkout, install deps, env/secrets, fail the job. Artifacts idea correct | Optional skim GitHub Actions workflow file |
| 12 | Docker | Restate (2026-11-02): image≈class, container≈instance; unique ports or start fails (port in use); env points tests/app at stage vs prod DB/URL | Acceptable after teach. Class/object analogy works. Nuance: containers can share *internal* port if *host* mappings differ. Env for correct target env is right | Optional: try docker run -p and -e once |
| 13 | Observability | Use request/correlation ID in logs to find fail point; match error to checks (pool exhaustion→DB connections, thread leak, unique constraint, NPE→null value) (2026-11-04) | Strong practical triage. Good link of log error → DB/system evidence. Light on stating a hypothesis first and confirming across services with same ID | Optional: timeline of one ID across services |
| 14 | LLMs | Skipped for now by learner (2026-11-04); will learn in detail with core LLM checkpoint (models, tuning, fine-tuning, RAG, eval) | Deferred — not assessed as complete; not a pass | Major LLM checkpoint in LEARNING_PLAN.md |
| 15 | MCP | Not familiar (2026-11-04); requested as major checkpoint | Deferred — not assessed as complete; not a pass | Major MCP checkpoint in LEARNING_PLAN.md |

## Session journal

### 2026-10-07 — Personal GitHub setup + diagnostic resume

- Topic: local learning repo bootstrap; personal GitHub wiring; diagnostic Q1.
- External study: none yet (at session start).
- Understanding demonstrated: none yet (assessment not started).
- Learner implementation: none yet.
- AI assistance: mentor installed `gh`, authenticated personal account `alam-khawaja`, created/pushed journey repo; will not invent learner diagnostic answers.
- Remaining gaps: full diagnostic unassessed.
- Current level: unassessed.
- Exact next action: learner answers diagnostic Git Q1 in chat.

### 2026-10-07 — Git starter study before Q1

- Topic: Git fundamentals (learner stated no prior Git knowledge).
- External study assigned:
  - https://docs.github.com/en/get-started/using-git/about-git
  - https://docs.github.com/en/get-started/git-basics/git-workflows
  - https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository (status, add, commit)
  - https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging
  - https://git-scm.com/docs/git-stash
  - https://git-scm.com/docs/git-diff
- Understanding demonstrated: not yet — study in progress.
- Exact next action: after reading, answer diagnostic Git Q1 in chat; mentor will give feedback and advance.

### 2026-10-19 — Git basics self-report before Q1

- Topic: Git fundamentals review.
- External study: learner reported completing basics (add/commit/status/branch/merge/diff); stash not practiced.
- Understanding demonstrated (self-reported): VCS purpose; stage/commit/remote flow; branches as parallel lines of work; merge combines branches; diff compares changes. Gaps: commit vs push; status vs merge conflicts; stash for unfinished work.
- Learner implementation: practiced listed commands except stash (self-reported).
- AI assistance: mentor feedback only; no answers invented for Q1 scenario.
- Exact next action: learner answers diagnostic Git Q1 scenario in chat.

### 2026-10-19 — Diagnostic Q1 answered; advance to Q2

- Topic: Git Q1 — preserve WIP + isolate bug fix.
- Understanding demonstrated: knows create branch, checkout, add/commit/push sequence.
- Wrong / incomplete: believed unfinished work stays off new branch because it was not pushed; did not verify fix-only changes.
- Correction given: uncommitted changes usually move with you; use stash or commit WIP first; verify with status/diff/log vs main.
- Exact next action: answer diagnostic Git Q2.

### 2026-10-19 — Diagnostic Q2 answered; advance to Q3

- Topic: Git Q2 — undo merged commit on shared branch.
- Understanding demonstrated: knows reset moves HEAD back.
- Wrong / incomplete: reset on shared/published history is unsafe; prefer revert.
- Exact next action: answer diagnostic HTTP Q3.

### 2026-10-19 — Diagnostic Q3: not familiar; teach mode

- Topic: HTTPS request path and failure investigation.
- Understanding demonstrated: none yet (explicit unfamiliar).
- AI assistance: mentor short explanation provided; learner must restate.
- Exact next action: learner restates Q3 in own words, then Q4.

### 2026-10-19 — Diagnostic Q3 restated; advance to Q4

- Topic: HTTPS path + failure checks.
- Understanding demonstrated: DNS resolution, host reachability, TLS, then client/server communication; investigates HTTP status codes, JS console, CORS.
- Gaps: UDP not the usual transport for HTTPS; pre-HTTP failures (DNS/TLS) less explicit.
- Exact next action: answer diagnostic API Q4.

### 2026-10-19 — Diagnostic Q4 answered; advance to Q5

- Topic: authentication vs authorization; 401/403.
- Understanding demonstrated: valid identity/token vs role privileges; agent cannot do admin → 403.
- Gaps: “reach area” phrasing blurs authn/authz; 401 case not stated.
- Exact next action: answer diagnostic Backend Q5.

### 2026-10-21 — Diagnostic Q5 answered; advance to Q6

- Topic: payment timeout/retry duplicates and prevention.
- Understanding demonstrated: idempotency keys; duplicate same request should not create second success.
- Gaps: mechanism of duplicate (processed then timeout then retry) not stated; evidence (DB/ledger) light.
- Exact next action: answer diagnostic Backend Q6.

### 2026-10-21 — Diagnostic Q6 answered; advance to Q7

- Topic: concurrent booking same slot.
- Understanding demonstrated: single-winner invariant; graceful failure message; DB uniqueness idea; FE booked state.
- Gaps: server/DB as source of truth vs FE; locking/transactions not named; evidence plan light.
- Exact next action: answer diagnostic Database Q7.

### 2026-10-21 — Diagnostic Q7 answered; advance to Q8

- Topic: two-table update fails halfway.
- Understanding demonstrated: transactional atomicity; rollback restores prior state; interrupt mid-flow to verify.
- Gaps: worded “rollout”; explicit check of both tables lightly implied.
- Exact next action: answer diagnostic Database Q8.

### 2026-10-21 — Diagnostic Q8 answered; advance to Q9

- Topic: API slow as data grows — query vs index.
- Understanding demonstrated: WHERE/join review; prefer filtering on indexed columns; check indexes exist.
- Gaps: uniqueness myth about indexes; EXPLAIN/plan not named.
- Exact next action: answer diagnostic Playwright Q9.

### 2026-11-02 — Diagnostic Q9 answered; advance to Q10

- Topic: flaky click CI vs local.
- Understanding demonstrated: inspect fail logs/console; resource/render/deploy; long XPaths as flake risk.
- Gaps: sleep waits vs auto-wait; traces/CI env not named.
- Exact next action: answer diagnostic Playwright Q10.

### 2026-11-02 — Diagnostic Q10 answered; advance to Q11

- Topic: parallel auth + data isolation.
- Understanding demonstrated: reuse stored auth for same role; separate states for different privilege levels.
- Gaps: unique test data per parallel worker / shared mutable data risk not covered.
- Exact next action: answer diagnostic CI/CD Q11.

### 2026-11-02 — Diagnostic Q11: not familiar; teach mode

- Topic: minimum CI smoke pipeline.
- Understanding demonstrated: none yet (explicit unfamiliar).
- AI assistance: mentor short explanation; learner must restate.
- Exact next action: learner restates Q11, then Q12.

### 2026-11-02 — Diagnostic Q11 restated; advance to Q12

- Topic: minimum CI smoke pipeline.
- Understanding demonstrated: remote run of smoke suite with config; keep logs/screenshots/network/runtime errors on failure.
- Gaps: trigger/checkout/install/secrets/fail-job less explicit.
- Exact next action: answer diagnostic Docker Q12.

### 2026-11-02 — Progress pushed to personal GitHub

- Commit `212d0c0` on `alam-khawaja/sdet-engineering-journey` (PROGRESS through Q11 teach). Credential helper set to personal `gh` account for this repo.

### 2026-11-02 — Diagnostic Q12: not familiar; teach mode

- Topic: Docker image vs container; ports and env for tests.
- Understanding demonstrated: none yet (explicit unfamiliar).
- AI assistance: mentor short explanation; learner must restate.
- Exact next action: learner restates Q12, then Q13.

### 2026-11-02 — Diagnostic Q12 restated; advance to Q13

- Topic: Docker basics for test runs.
- Understanding demonstrated: image vs running instance; port conflicts; env selects stage vs prod targets.
- Gaps: host vs container port mapping nuance.
- Exact next action: answer diagnostic Observability Q13.

### 2026-11-04 — Diagnostic Q13 answered; advance to Q14

- Topic: 500 across services — logs, correlation ID, DB state.
- Understanding demonstrated: follow request ID in logs; map error type to concrete checks (pool, threads, constraints, NPE).
- Gaps: explicit hypothesis + multi-service timeline lightly implied.
- Exact next action: answer diagnostic LLM Q14.

### 2026-11-04 — Diagnostic Q14: not familiar; LLM main checkpoint added

- Topic: evaluate LLM-generated tests; learner requested LLM/AI fundamentals (models, tuning, fine-tuning, RAG) as main checkpoint.
- Understanding demonstrated: none yet on LLMs.
- Plan update: LEARNING_PLAN.md milestone + LLM checkpoint detail added (Planned).
- AI assistance: short teach on evaluation-before-adoption; full LLM curriculum deferred to dedicated checkpoint after diagnostic.
- Exact next action: learner restates Q14 evaluation idea, then Q15.

### 2026-11-04 — Q14 skipped; advance to Q15

- Learner chose skip LLM detail for now; keep as major post-diagnostic checkpoint with cores.
- Q14 left deferred (unchecked / not passed).
- Exact next action: answer diagnostic MCP Q15.

### 2026-11-04 — Q15 not familiar; MCP major checkpoint; diagnostic closed for routing

- Topic: MCP host/client/server/tools.
- Understanding demonstrated: none (explicit unfamiliar).
- Plan update: MCP added as major checkpoint in LEARNING_PLAN; area ratings + first four weeks + CIP Planned recorded.
- Exact next action: Week 1 Git stash + bug-fix branch verification exercise.

### 2026-11-04 — Week 1 started (Git stash exercise)

- Topic: preserve WIP with stash; isolate bug fix on branch; verify with diff/log.
- Mode: Teach — learner runs commands.
- Exact next action: Step 1 — create unfinished edit in journey repo and paste `git status` output.

### 2026-11-04 — Week 1 Step 1 done (git status)

- Evidence: learner showed modified CHECKLIST, CIP_TRACKER, LEARNING_PLAN, PROGRESS (unstaged).
- Exact next action: `git stash push -m "week1-wip"` then `git status` (should be clean).

### 2026-11-16 — Week 1 Git Implement complete; Explain pending

- Evidence: stash week1-wip; branch fix/week1-demo; commit 83393db README only; diff/log vs main showed only that fix; on main with plan WIP restored (stash already empty when pop re-run — WIP already on desk).
- Exact next action: learner Explain in 2–3 sentences; then HTTP/DevTools.

### 2026-11-16 — Week 1 Git Explain done; start HTTP

- Explain: stash keeps unsaved changes safe when switching branches; diff compares branches so you can check what’s unique on your branch.
- Correction: that check is usually *before* merge (`git diff main` / `git log main..HEAD`), not “after merge.”
- Exact next action: Network tab exercise — one HTTPS request report.

### 2026-11-16 — Week 1 HTTP success trace

- Evidence: GET XHR `nova-api/listings/filters?...` → 200 (learner-reported from Network tab).
- Understanding: can read method/status/type for a successful API call.
- Exact next action: classify one failed (4xx/5xx or red) request.

### 2026-11-16 — Week 1 HTTP failure captured; Week 1 HTTP done

- Evidence: GET `https://github.com/github-copilot/chat/repositories_search?limit=10` → **404**; learner asked if URL is “right.”
- Feedback: 404 means that path wasn’t found for this call (feature/path/access)—good capture for learning; “right URL” = whatever the app requested; tester checks path/params/feature availability next.
- Exact next action: push journey docs if asked; or start Week 2.

### 2026-11-16 — Week 2 started (401/403 + idempotency)

- Topic: design auth failure cases; then payment retry idempotency sketch.
- Exact next action: learner writes 3 cases (no token, bad token, agent→admin).

### 2026-11-16 — Week 2 auth cases correct

- Evidence: 1) no token → 401  2) bad token → 401  3) agent→admin → 403.
- Exact next action: idempotency retry sketch.

### 2026-11-16 — Week 2 idempotency sketch

- Evidence: same key → 409 / no duplicate txn; different key → process as new.
- Feedback: Correct no-duplicate invariant. Note: some APIs return 200 with original result on replay (also valid); 409 is fine if documented. “Already in process” fits concurrent in-flight; completed retry often replays success.
- Exact next action: Explain gate (2 sentences).

### 2026-11-16 — Week 2 Explain done; Week 2 closed

- Explain: idempotency key unique per transaction so money isn’t debited twice.
- Exact next action: push if asked; or start Week 3 Playwright.

### 2026-11-16 — Week 3 started (Playwright API smoke)

- Scaffolded personal `smoke/` against JSONPlaceholder (synthetic).
- AI assistance: mentor created project skeleton; learner must install and run.
- Exact next action: learner runs npm install + playwright test; paste output.

### 2026-11-16 — Week 3 Implement passed

- Evidence (learner-reported): 1 passed — GET /posts/1 returns 200 and id 1 (849ms).
- Exact next action: deliberate fail + trace debug.

### 2026-11-16 — Week 3 Debug done

- Failure: Expected 999 Received 1; trace.zip produced; restored assertion; 1 passed again (743ms).
- Exact next action: Explain what smoke proves / does not prove.

### 2026-11-16 — Week 3 Explain done; Week 3 closed

- Explain: proves failure when id ≠ 1; does not prove multi-valid-value cases or timeouts.
- Feedback: also positively proves GET /posts/1 → 200 + id 1 + has title; limits also include no auth/UI/company system coverage.
- Exact next action: push if asked; or start Week 4 CI + data isolation.

### 2026-11-18 — Week 4 started (parallel data + CI)

- Added `posts-parallel-smoke.spec.js`, workers config, `.github/workflows/smoke.yml` (artifacts on failure).
- AI assistance: mentor scaffolded CI/parallel files; learner must explain + run + authorize push for Actions.
- Exact next action: learner explains shared-data risk; runs `npx playwright test --workers=2`.

### 2026-11-18 — Week 4 local workers run passed

- Evidence: `npx playwright test --workers=2` → 3 passed (2.9s): posts/1, posts/2, original posts-smoke.
- Exact next action: Understand answer (shared data risk); then push for Actions.

### 2026-11-18 — Week 4 Understand done

- Evidence: shared data creates test dependency (e.g. delete before update) → flakiness; tests should be independent/isolated.
- Exact next action: push for GitHub Actions CI.

### 2026-11-18 — Week 4 Explain drafted

- Explain: pipelines check new commits before deployment; shared repo for collaboration.
- Feedback: good. Also emphasize: automated run on a clean server (not “works on my machine”), PR/push trigger, save failure artifacts.
- Exact next action: push for Actions evidence.

### 2026-11-18 — Week 4 CI green; first four weeks closed

- Push as personal `alam-khawaja` (needed `workflow` scope refresh).
- Actions run `44349942865` **success** (~17s) for smoke workflow on main.
- Exact next action: pick next learning focus (CIP deepen / LLM / more Playwright).

### 2026-11-18 — Week 5 started (CIP deepen)

- CIP → In Progress; added `posts-create-smoke.spec.js` (unique title per run).
- Next four weeks sketched in LEARNING_PLAN (CIP → reporting → Docker light → observability → LLM/MCP).
- Exact next action: learner runs create smoke; records manual baseline checklist + time.

### 2026-11-18 — Week 5 create smoke + baseline

- Evidence: POST create 1 passed (3.5s). Manual checklist (estimated 5–10 min): Postman GET check → POST create → verify via GET; auth/header setup adds friction.
- Feedback: solid baseline thinking. Note: JSONPlaceholder fakes POST (may not persist for real GET-after-create); still valid learning for unique data + status asserts. Label impact preliminary/estimated.
- Exact next action: Explain what improved vs GET-only; then push.

### 2026-11-18 — Week 5 Explain done; Week 5 closed

- Explain: adds create option previous GET-only lagged; create if missing and verify.
- Exact next action: push if asked; Week 6 reporting/reliability next.

### 2026-11-18 — Week 6 started: booking API portfolio project

- Scaffolded `projects/booking-api-automation` (Restful Booker): auth, lifecycle create/get/delete, unique data, CI workflow with always-upload report artifacts.
- Why: stronger interview demo than JSONPlaceholder GET/POST alone; Week 6 reporting/reliability rides on this project.
- AI assistance: mentor scaffold; learner must install, run, debug, explain.
- Exact next action: learner runs npm install + playwright test in booking project.

### 2026-11-18 — Week 6 Implement passed

- Evidence (learner-reported): 3 passed in 2.8s with 3 workers — lifecycle create/get/delete, bad auth, valid auth.
- Exact next action: Debug drill on delete status assertion.

