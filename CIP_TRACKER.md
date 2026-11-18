# Continuous improvement tracker

Public-safe summaries only. Keep sensitive company evidence elsewhere.

## Candidate: critical API smoke validation

Status: **Measuring** (2026-11-18 — baseline estimated; suite expanded with unique POST).
Problem: repeatable validation lacks scalable automation.
Baseline (estimated, learner-reported 2026-11-18):
- Scope: Postman — (1) GET check post exists/status/body (2) if needed POST create (3) confirm create value via GET
- Time: ~**5–10 minutes** once (includes header/auth setup friction when AI/helpers not set)
- Denominator: one full manual pass of that checklist
- Label: **estimated** (not stopwatched in session)
Automated comparison (same session):
- `posts-create-smoke.spec.js` alone: **~3.5s** wall time (1 passed)
- Broader suite also runs GET smokes + CI (~17s historically for earlier job)
Proposed solution: Playwright API smoke (GET + parallel GET + unique POST), reports, GitHub Actions + failure artifacts.
Technologies: Playwright + GitHub Actions on personal `sdet-engineering-journey`.
Learning: assertions, unique data lifecycle, workers, CI artifacts, baseline honesty.
KPI mapping: time to run comparable smoke scope (manual vs automated); **proposed** for personal learning — confirm team CIP definitions before company claims.
Expected impact: hypothesis — automation much faster/more repeatable for this scope.
Actual impact: **preliminary** — estimated manual 5–10 min vs create automated ~3.5s (not identical steps; JSONPlaceholder POST is fake/non-persistent so GET-after-create verify is limited here).
Evidence:
- Suite: `smoke/`
- Local create: 1 passed 2026-11-18
- Local workers: 3 passed earlier
- CI: https://github.com/alam-khawaja/sdet-engineering-journey/actions/runs/44349942865
Review value: demonstrate reproducible validation and honest measurement limits.
Priority: high for learning + portfolio; company CIP only with sanitized/approved metrics.

For each initiative define comparable baseline scope, measurement period, denominator, maintenance/triage cost, result, evidence links, and contribution. Statuses: Idea, Planned, In Progress, Measuring, Completed. Count CIPs according to team criteria.
