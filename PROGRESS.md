# Progress

## Current state

Current focus: initial diagnostic.
Current topic: CI/CD (diagnostic Q11) — teach + restate.
Current phase: assessment.
Next diagnostic question: 11 of 15.
Completed topics: none verified (areas assessed with gaps — revision noted).
Blocked topics: CI/CD pipelines unfamiliar (self-reported).
Next action: learner restates minimum smoke pipeline (trigger, install, run, artifacts) in own words; then Q12.

## Workspace and project state

Learning repository path: `/Users/alam/sdet-engineering-journey`
Active project path: `/Users/alam/sdet-engineering-journey`
Work context: personal learning.
Mode: Teach.
Current milestone: initial diagnostic.
Pending gates: assessment (15 questions); area ratings; first four weeks + CIP agreement.
Evidence paths: `PROGRESS.md` (diagnostic record + session journal).
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
| 11 | CI/CD | Learner: doesn't know pipelines yet (2026-11-02). Mentor teaching minimum smoke CI | Not familiar — awaiting restate | Restate trigger/install/run/artifacts |

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
