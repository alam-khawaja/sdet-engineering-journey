"""Report writers: self-contained interactive HTML, SARIF v2.1.0, JSON, and CLI summary."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymutate.models import MutantResult, MutantStatus, RunReport
from pymutate.mutators import ALL_MUTATORS

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
INFORMATION_URI = "https://github.com/alam-khawaja/sdet-engineering-journey/tree/main/projects/pymutate-enterprise"
SARIF_REPORTED_STATUSES = frozenset(
    {MutantStatus.SURVIVED, MutantStatus.CACHED_SURVIVED, MutantStatus.UNCOVERED}
)

STATUS_CLASS = {
    MutantStatus.KILLED: "killed",
    MutantStatus.CACHED_KILLED: "killed",
    MutantStatus.TIMEOUT: "timeout",
    MutantStatus.SURVIVED: "survived",
    MutantStatus.CACHED_SURVIVED: "survived",
    MutantStatus.UNCOVERED: "uncovered",
}


def _timestamp(epoch: float) -> str:
    if epoch <= 0:
        return "-"
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _diff_html(diff: str) -> str:
    rows: list[str] = []
    for line in diff.splitlines():
        css = ""
        if line.startswith("+++") or line.startswith("---"):
            css = "meta"
        elif line.startswith("@@"):
            css = "hunk"
        elif line.startswith("+"):
            css = "add"
        elif line.startswith("-"):
            css = "del"
        rows.append(f'<span class="{css}">{html.escape(line)}</span>')
    return "\n".join(rows)


def _mutant_card(result: MutantResult) -> str:
    mutant = result.mutant
    status_css = STATUS_CLASS[result.status]
    tests = "".join(f"<li><code>{html.escape(t)}</code></li>" for t in result.covering_tests[:25])
    if len(result.covering_tests) > 25:
        tests += f"<li>… {len(result.covering_tests) - 25} more</li>"
    tests_block = f"<ul class='tests'>{tests}</ul>" if tests else "<p class='muted'>No covering tests.</p>"
    detail = f"<p class='muted'>{html.escape(result.detail)}</p>" if result.detail else ""
    return f"""
<details class="mutant {status_css}" data-status="{status_css}" data-risk="{mutant.risk_level.value}"
         data-file="{html.escape(mutant.file_path)}">
  <summary>
    <span class="badge {status_css}">{result.status.value}</span>
    <span class="badge risk-{mutant.risk_level.value.lower()}">{mutant.risk_level.value}</span>
    <code>{html.escape(mutant.file_path)}:{mutant.lineno}</code>
    <span class="desc">{html.escape(mutant.description)}</span>
  </summary>
  <div class="body">
    <p class="muted">id <code>{html.escape(mutant.id)}</code> · mutator {html.escape(mutant.mutator_name)} ·
       {result.duration_sec:.2f}s{" · cached" if result.cached else ""}</p>
    {detail}
    <pre class="diff">{_diff_html(mutant.diff)}</pre>
    <h4>Covering tests ({len(result.covering_tests)})</h4>
    {tests_block}
  </div>
</details>"""


HTML_STYLE = """
:root { --bg:#0f172a; --panel:#111827; --text:#e5e7eb; --muted:#94a3b8; --line:#1f2937;
        --kill:#16a34a; --surv:#dc2626; --time:#d97706; --unc:#7c3aed; }
* { box-sizing: border-box; }
body { margin:0; font:14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif; background:var(--bg); color:var(--text); }
header, main { max-width:1200px; margin:0 auto; padding:16px 24px; }
h1 { margin:8px 0 4px; font-size:22px; } h2 { font-size:17px; margin:24px 0 8px; }
.muted { color:var(--muted); } code { font-family: ui-monospace, Menlo, monospace; font-size:12.5px; }
.verdict { display:inline-block; padding:4px 12px; border-radius:6px; font-weight:700; }
.verdict.pass { background:var(--kill); } .verdict.fail { background:var(--surv); }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:16px 0; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; }
.card .value { font-size:24px; font-weight:700; } .card .label { color:var(--muted); font-size:12px; }
table { width:100%; border-collapse:collapse; background:var(--panel); border-radius:8px; overflow:hidden; }
th, td { padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; }
th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; }
.bar { height:8px; background:#374151; border-radius:4px; overflow:hidden; min-width:120px; }
.bar span { display:block; height:100%; background:var(--kill); }
.pass-cell { color:#4ade80; font-weight:600; } .fail-cell { color:#f87171; font-weight:600; }
.filters { display:flex; gap:8px; flex-wrap:wrap; margin:12px 0; }
.filters button { background:var(--panel); color:var(--text); border:1px solid var(--line); border-radius:999px;
                  padding:4px 12px; cursor:pointer; }
.filters button.active { border-color:#60a5fa; color:#93c5fd; }
details.mutant { background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--line);
                 border-radius:6px; margin:6px 0; }
details.mutant.killed { border-left-color:var(--kill); } details.mutant.survived { border-left-color:var(--surv); }
details.mutant.timeout { border-left-color:var(--time); } details.mutant.uncovered { border-left-color:var(--unc); }
summary { cursor:pointer; padding:8px 12px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.body { padding:0 12px 12px; }
.badge { font-size:11px; font-weight:700; padding:2px 8px; border-radius:4px; background:#374151; }
.badge.killed { background:var(--kill); } .badge.survived { background:var(--surv); }
.badge.timeout { background:var(--time); } .badge.uncovered { background:var(--unc); }
.badge.risk-critical { background:#7f1d1d; } .badge.risk-high { background:#9a3412; } .badge.risk-medium { background:#1e3a8a; }
pre.diff { background:#020617; padding:10px; border-radius:6px; overflow-x:auto; font-size:12.5px; }
pre.diff .add { color:#4ade80; } pre.diff .del { color:#f87171; } pre.diff .hunk { color:#60a5fa; }
pre.diff .meta { color:var(--muted); } ul.tests { margin:4px 0; padding-left:18px; }
"""

HTML_SCRIPT = """
(function () {
  const buttons = document.querySelectorAll('.filters button');
  const cards = document.querySelectorAll('details.mutant');
  buttons.forEach(function (button) {
    button.addEventListener('click', function () {
      buttons.forEach(function (b) { b.classList.remove('active'); });
      button.classList.add('active');
      const filter = button.dataset.filter;
      cards.forEach(function (card) {
        const match = filter === 'all' || card.dataset.status === filter || card.dataset.risk === filter;
        card.style.display = match ? '' : 'none';
      });
    });
  });
})();
"""


def render_html(report: RunReport) -> str:
    summaries = report.file_summaries()
    file_rows = "".join(
        f"""<tr>
  <td><code>{html.escape(s.file_path)}</code></td>
  <td>{s.total}</td><td>{s.killed}</td><td>{s.timeout}</td><td>{s.survived}</td><td>{s.uncovered}</td>
  <td><div class="bar"><span style="width:{s.score:.1f}%"></span></div> {s.score:.2f}%</td>
  <td>{s.threshold:.1f}%{"" if s.threshold_is_explicit else " (default)"}</td>
  <td class="{"pass-cell" if s.passed else "fail-cell"}">{"PASS" if s.passed else "FAIL"}</td>
</tr>"""
        for s in summaries
    )
    ordered = report.survivors() + sorted(
        (r for r in report.results if r.status.is_killed),
        key=lambda r: (r.mutant.file_path, r.mutant.lineno),
    )
    cards = "".join(_mutant_card(result) for result in ordered)
    failures = "".join(f"<li>{html.escape(f)}</li>" for f in report.gate_failures())
    verdict = (
        '<span class="verdict pass">GATE PASSED</span>'
        if report.passed
        else f'<span class="verdict fail">GATE FAILED</span><ul>{failures}</ul>'
    )
    card_values = [
        ("Kill score", f"{report.kill_score:.2f}%"),
        ("Mutants", str(report.total)),
        ("Killed", str(report.count(MutantStatus.KILLED, MutantStatus.CACHED_KILLED))),
        ("Timeout", str(report.count(MutantStatus.TIMEOUT))),
        ("Survived", str(report.survived_count)),
        ("Uncovered", str(report.count(MutantStatus.UNCOVERED))),
        ("Baseline", f"{report.baseline_duration_sec:.2f}s"),
        ("Watchdog", f"{report.timeout_sec:.2f}s"),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="value">{html.escape(v)}</div><div class="label">{html.escape(k)}</div></div>'
        for k, v in card_values
    )
    filters = "".join(
        f'<button data-filter="{key}"{" class=active" if key == "all" else ""}>{label}</button>'
        for key, label in [
            ("all", "All"),
            ("survived", "Survived"),
            ("uncovered", "Uncovered"),
            ("timeout", "Timeout"),
            ("killed", "Killed"),
            ("CRITICAL", "Critical risk"),
            ("HIGH", "High risk"),
            ("MEDIUM", "Medium risk"),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pymutate report: {report.kill_score:.2f}%</title>
<style>{HTML_STYLE}</style>
</head>
<body>
<header>
  <h1>pymutate mutation report</h1>
  <p class="muted">pymutate {html.escape(report.tool_version)} · {_timestamp(report.started_at)} ·
     {report.duration_sec:.1f}s · target python <code>{html.escape(report.target_python)}</code>
     {"· git-diff scoped" if report.diff_filtered else ""}</p>
  {verdict}
</header>
<main>
  <div class="cards">{cards_html}</div>
  <h2>Files</h2>
  <table>
    <thead><tr><th>File</th><th>Mutants</th><th>Killed</th><th>Timeout</th><th>Survived</th>
      <th>Uncovered</th><th>Score</th><th>Threshold</th><th>Gate</th></tr></thead>
    <tbody>{file_rows}</tbody>
  </table>
  <h2>Mutants</h2>
  <div class="filters">{filters}</div>
  {cards}
</main>
<script>{HTML_SCRIPT}</script>
</body>
</html>
"""


def write_html(report: RunReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")
    return path


def _sarif_rules() -> list[dict[str, Any]]:
    rules = []
    for cls in ALL_MUTATORS:
        rules.append(
            {
                "id": cls.name,
                "name": cls.name,
                "shortDescription": {"text": f"[{cls.risk.value} - {cls.category}] mutant survived"},
                "fullDescription": {
                    "text": (
                        f"A {cls.name} mutation survived the test suite: no test fails when this code "
                        f"is changed. Category: {cls.category}."
                    )
                },
                "defaultConfiguration": {"level": cls.risk.sarif_level},
                "helpUri": INFORMATION_URI,
                "properties": {
                    "tags": ["mutation-testing", "test-gap", cls.category.lower()],
                    "precision": "high",
                    "problem.severity": "error" if cls.risk.sarif_level == "error" else "warning",
                },
            }
        )
    return rules


def build_sarif(report: RunReport) -> dict[str, Any]:
    rule_ids = [cls.name for cls in ALL_MUTATORS]
    results: list[dict[str, Any]] = []
    for result in report.results:
        if result.status not in SARIF_REPORTED_STATUSES:
            continue
        mutant = result.mutant
        verb = "is not executed by any test" if result.status is MutantStatus.UNCOVERED else "survived"
        results.append(
            {
                "ruleId": mutant.mutator_name,
                "ruleIndex": rule_ids.index(mutant.mutator_name),
                "level": mutant.risk_level.sarif_level,
                "message": {"text": f"Mutant {verb}: {mutant.description}"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": mutant.file_path, "uriBaseId": "%SRCROOT%"},
                            "region": {
                                "startLine": mutant.lineno,
                                "startColumn": mutant.col_offset + 1,
                            },
                        }
                    }
                ],
                "partialFingerprints": {"pymutateMutantId/v1": mutant.id},
                "properties": {
                    "status": result.status.value,
                    "riskLevel": mutant.risk_level.value,
                    "category": mutant.category,
                    "coveringTests": list(result.covering_tests),
                    "diff": mutant.diff,
                },
            }
        )
    root_uri = Path(report.project_root).resolve().as_uri().rstrip("/") + "/" if report.project_root else ""
    run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": "pymutate",
                "version": report.tool_version,
                "semanticVersion": report.tool_version,
                "informationUri": INFORMATION_URI,
                "rules": _sarif_rules(),
            }
        },
        "invocations": [
            {
                "executionSuccessful": True,
                "exitCode": 0 if report.passed else 1,
            }
        ],
        "results": results,
        "properties": {
            "killScore": report.kill_score,
            "totalMutants": report.total,
            "gatePassed": report.passed,
            "gateFailures": report.gate_failures(),
        },
    }
    if root_uri:
        run["originalUriBaseIds"] = {"%SRCROOT%": {"uri": root_uri}}
    return {"$schema": SARIF_SCHEMA, "version": SARIF_VERSION, "runs": [run]}


def write_sarif(report: RunReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_sarif(report), indent=2), encoding="utf-8")
    return path


def write_json(report: RunReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


def format_cli_summary(report: RunReport, max_survivors: int = 15) -> str:
    lines: list[str] = []
    rule = "=" * 78
    lines.append(rule)
    lines.append(
        f"pymutate {report.tool_version}  kill score {report.kill_score:.2f}%  "
        f"({report.killed_count}/{report.total} killed, {report.duration_sec:.1f}s)"
    )
    lines.append(
        f"baseline {report.baseline_duration_sec:.2f}s  watchdog {report.timeout_sec:.2f}s  "
        f"killed={report.count(MutantStatus.KILLED, MutantStatus.CACHED_KILLED)} "
        f"timeout={report.count(MutantStatus.TIMEOUT)} survived={report.survived_count} "
        f"uncovered={report.count(MutantStatus.UNCOVERED)} "
        f"cached={sum(1 for r in report.results if r.cached)}"
    )
    lines.append(rule)
    summaries = report.file_summaries()
    if summaries:
        width = max(len(s.file_path) for s in summaries)
        lines.append(f"{'file'.ljust(width)}  mutants  score    threshold  gate")
        for s in summaries:
            threshold = f"{s.threshold:.1f}%" + ("" if s.threshold_is_explicit else "*")
            lines.append(
                f"{s.file_path.ljust(width)}  {s.total:>7}  {s.score:>6.2f}%  {threshold:>9}  "
                f"{'PASS' if s.passed else 'FAIL'}"
            )
        lines.append("(* = default threshold)")
    survivors = report.survivors()
    if survivors:
        lines.append("")
        lines.append(f"Top surviving mutants ({min(len(survivors), max_survivors)} of {len(survivors)}):")
        for result in survivors[:max_survivors]:
            mutant = result.mutant
            lines.append(
                f"  {result.status.value:<16} {mutant.file_path}:{mutant.lineno}  {mutant.description}"
            )
    lines.append("")
    if report.passed:
        lines.append("GATE PASSED")
    else:
        lines.append("GATE FAILED")
        lines.extend(f"  - {failure}" for failure in report.gate_failures())
    return "\n".join(lines)
