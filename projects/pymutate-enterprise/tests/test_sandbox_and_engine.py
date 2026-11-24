from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pymutate.benchmark import BenchmarkError, run_benchmark
from pymutate.cache import ResultCache
from pymutate.cli import main
from pymutate.config import load_config
from pymutate.coverage_mapper import build_coverage_map
from pymutate.engine import EngineOptions, MutationEngine, parse_unified_zero_diff
from pymutate.models import Mutant, MutantStatus, RiskLevel
from pymutate.reporters import build_sarif, format_cli_summary, render_html
from pymutate.sandbox import (
    WORKER_SCRIPT,
    BaselineError,
    MutantJob,
    Sandbox,
    classify_exit_code,
    compute_timeout,
)
from tests.conftest import PRICING_SOURCE, WEAK_TESTS, ProjectFactory, git, requires_git, write_files

PRICING = "toyshop/pricing.py"
THRESHOLD_TEST = "toy_tests/test_pricing.py::test_discount_applies_at_threshold"
OFF_BY_ONE = PRICING_SOURCE.replace(">= 100", "> 100")
INFINITE_LOOP = "def discount(total):\n    while True:\n        pass\n"


def run_worker(root: Path, mutated_source: str, node_ids: list[str], payload_dir: Path) -> int:
    payload = payload_dir / "payload.json"
    payload.write_text(
        json.dumps(
            {
                "module_name": "toyshop.pricing",
                "file_path": str(root / PRICING),
                "is_package": False,
                "mutated_source": mutated_source,
                "node_ids": node_ids,
                "project_root": str(root),
                "import_root": str(root),
                "pytest_args": ["-x"],
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-B", str(WORKER_SCRIPT), str(payload)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return completed.returncode


def pricing_mutant(mutated_source: str, mutant_id: str = "Manual-L2-00000000") -> Mutant:
    return Mutant(
        id=mutant_id,
        file_path=PRICING,
        module_name="toyshop.pricing",
        lineno=2,
        mutator_name="Manual",
        risk_level=RiskLevel.HIGH,
        description="manual mutant",
        original_source=PRICING_SOURCE,
        mutated_source=mutated_source,
        diff="",
        end_lineno=2,
    )


def job_for(root: Path, mutant: Mutant, tests: tuple[str, ...] = (THRESHOLD_TEST,)) -> MutantJob:
    return MutantJob(
        mutant=mutant,
        covering_tests=tests,
        file_path=root / PRICING,
        import_root=root,
        is_package=False,
    )


class TestWorker:
    def test_mutant_is_injected_in_memory_and_disk_is_untouched(
        self, make_project: ProjectFactory, tmp_path: Path
    ) -> None:
        root = make_project()
        write_files(
            root,
            {
                "toy_tests/test_injection.py": """\
                import toyshop.pricing as pricing


                def test_sees_injected_source():
                    assert pricing.INJECTED is True
                """
            },
        )
        original = (root / PRICING).read_bytes()

        exit_code = run_worker(
            root, PRICING_SOURCE + "INJECTED = True\n", ["toy_tests/test_injection.py"], tmp_path
        )

        assert exit_code == 0
        assert (root / PRICING).read_bytes() == original
        assert not list((root / "toyshop").rglob("*.pyc"))

    def test_failing_tests_exit_one(self, make_project: ProjectFactory, tmp_path: Path) -> None:
        root = make_project()

        assert run_worker(root, OFF_BY_ONE, [THRESHOLD_TEST], tmp_path) == 1

    def test_unchanged_behaviour_exits_zero(self, make_project: ProjectFactory, tmp_path: Path) -> None:
        root = make_project()

        assert run_worker(root, PRICING_SOURCE, [THRESHOLD_TEST], tmp_path) == 0

    def test_tests_that_never_import_the_target_exit_97(
        self, make_project: ProjectFactory, tmp_path: Path
    ) -> None:
        root = make_project()
        write_files(root, {"toy_tests/test_unrelated.py": "def test_unrelated():\n    assert True\n"})

        assert run_worker(root, OFF_BY_ONE, ["toy_tests/test_unrelated.py"], tmp_path) == 97

    def test_bad_payload_exits_96(self, tmp_path: Path) -> None:
        payload = tmp_path / "payload.json"
        payload.write_text("{not json", encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, "-B", str(WORKER_SCRIPT), str(payload)], capture_output=True, check=False
        )

        assert completed.returncode == 96


class TestSandbox:
    @pytest.mark.parametrize(
        ("exit_code", "status", "detail_fragment"),
        [
            (0, MutantStatus.SURVIVED, ""),
            (1, MutantStatus.KILLED, ""),
            (2, MutantStatus.KILLED, ""),
            (3, MutantStatus.KILLED, ""),
            (4, MutantStatus.SURVIVED, "worker error"),
            (5, MutantStatus.SURVIVED, "worker error"),
            (96, MutantStatus.SURVIVED, "worker error"),
            (97, MutantStatus.SURVIVED, "never imported"),
            (-9, MutantStatus.KILLED, "signal 9"),
            (42, MutantStatus.KILLED, "code 42"),
        ],
    )
    def test_classify_exit_code(self, exit_code: int, status: MutantStatus, detail_fragment: str) -> None:
        actual_status, detail = classify_exit_code(exit_code)

        assert actual_status is status
        assert detail_fragment in detail

    @pytest.mark.parametrize(("baseline", "expected"), [(0.2, 3.0), (1.0, 3.0), (2.0, 6.0), (10.0, 30.0)])
    def test_watchdog_formula(self, baseline: float, expected: float) -> None:
        assert compute_timeout(baseline) == expected

    def test_infinite_loop_is_reported_as_timeout(self, make_project: ProjectFactory) -> None:
        root = make_project()
        sandbox = Sandbox(project_root=root, workers=1)
        sandbox.configure_timeout(0.1, multiplier=3.0, minimum=1.5)

        result = sandbox.run_mutant(job_for(root, pricing_mutant(INFINITE_LOOP)))

        assert result.status is MutantStatus.TIMEOUT
        assert result.status.is_killed
        assert 1.5 <= result.duration_sec < 30

    def test_uncovered_mutant_never_runs(self, make_project: ProjectFactory) -> None:
        root = make_project()
        sandbox = Sandbox(project_root=root)

        result = sandbox.run_mutant(job_for(root, pricing_mutant(OFF_BY_ONE), tests=()))

        assert result.status is MutantStatus.UNCOVERED

    def test_requires_configured_timeout(self, make_project: ProjectFactory) -> None:
        root = make_project()

        with pytest.raises(RuntimeError, match="configure_timeout"):
            Sandbox(project_root=root).run_mutant(job_for(root, pricing_mutant(OFF_BY_ONE)))

    def test_verdict_is_replayed_from_cache(self, make_project: ProjectFactory, tmp_path: Path) -> None:
        root = make_project()
        with ResultCache(tmp_path / "cache.db") as cache:
            sandbox = Sandbox(project_root=root, cache=cache)
            sandbox.configure_timeout(0.1, 3.0, 3.0)
            job = job_for(root, pricing_mutant(OFF_BY_ONE))

            first = sandbox.run_mutant(job)
            second = sandbox.run_mutant(job)

        assert first.status is MutantStatus.KILLED
        assert second.status is MutantStatus.CACHED_KILLED
        assert second.cached

    def test_run_all_keeps_input_order(self, make_project: ProjectFactory) -> None:
        root = make_project()
        sandbox = Sandbox(project_root=root, workers=3)
        sandbox.configure_timeout(0.1, 3.0, 3.0)
        mutants = [
            pricing_mutant(OFF_BY_ONE, "A-L2-00000001"),
            pricing_mutant(PRICING_SOURCE, "B-L2-00000002"),
            pricing_mutant(OFF_BY_ONE + "\n", "C-L2-00000003"),
        ]
        seen: list[int] = []

        results = sandbox.run_all(
            [job_for(root, m) for m in mutants], progress=lambda _result, done, _total: seen.append(done)
        )

        assert [r.mutant.id for r in results] == [m.id for m in mutants]
        assert [r.status for r in results] == [MutantStatus.KILLED, MutantStatus.SURVIVED, MutantStatus.KILLED]
        assert seen == [1, 2, 3]

    def test_failing_baseline_is_refused(self, make_project: ProjectFactory) -> None:
        root = make_project(tests="def test_broken():\n    assert False\n")

        with pytest.raises(BaselineError, match="must pass"):
            Sandbox(project_root=root).measure_baseline(["toy_tests"])


class TestCoverageMap:
    def test_maps_each_line_to_every_test_that_runs_it(self, make_project: ProjectFactory, tmp_path: Path) -> None:
        root = make_project()

        coverage_map = build_coverage_map(
            project_root=root,
            target_python=sys.executable,
            source_paths=("toyshop",),
            test_paths=("toy_tests",),
            work_dir=tmp_path / "work",
        )

        prefix = "toy_tests/test_pricing.py::"
        assert coverage_map.tests_for(PRICING, [2]) == (
            f"{prefix}test_discount_applies_at_threshold",
            f"{prefix}test_discount_on_large_total",
            f"{prefix}test_no_discount_below_threshold",
        )
        assert coverage_map.tests_for(PRICING, [3]) == (
            f"{prefix}test_discount_applies_at_threshold",
            f"{prefix}test_discount_on_large_total",
        )
        assert coverage_map.tests_for(PRICING, [4]) == (f"{prefix}test_no_discount_below_threshold",)
        assert coverage_map.tests_for(PRICING, [1]) == coverage_map.file_tests(PRICING)


class TestEngine:
    def test_strong_suite_kills_everything_and_passes(self, make_project: ProjectFactory, tmp_path: Path) -> None:
        root = make_project()

        report = MutationEngine(
            load_config(root), EngineOptions(target_python=sys.executable, cache_path=tmp_path / "c.db")
        ).run()

        assert report.total >= 5
        assert report.kill_score == 100.0
        assert report.passed
        assert report.timeout_sec == pytest.approx(max(3.0, report.baseline_duration_sec * 3.0))

    def test_weak_suite_leaves_boundary_survivors_and_fails(
        self, make_project: ProjectFactory, tmp_path: Path
    ) -> None:
        root = make_project(tests=WEAK_TESTS)

        report = MutationEngine(
            load_config(root), EngineOptions(target_python=sys.executable, cache_path=tmp_path / "c.db")
        ).run()

        survivors = {r.mutant.description for r in report.survivors()}
        assert report.kill_score < 80.0
        assert not report.passed
        assert any("Replace `>=` with `>`" in d for d in survivors)
        assert any("100 -> 101" in d for d in survivors)

        sarif = build_sarif(report)
        sarif_results = sarif["runs"][0]["results"]
        assert sarif["version"] == "2.1.0"
        assert len(sarif_results) == report.survived_count + report.count(MutantStatus.UNCOVERED)
        location = sarif_results[0]["locations"][0]["physicalLocation"]
        assert location["artifactLocation"]["uri"] == PRICING
        assert location["region"]["startLine"] >= 1

        html = render_html(report)
        assert html.lstrip().lower().startswith("<!doctype html")
        assert report.survivors()[0].mutant.id in html
        assert "GATE FAILED" in format_cli_summary(report)

    def test_changed_lines_scope_the_run(self, make_project: ProjectFactory, tmp_path: Path) -> None:
        root = make_project()

        report = MutationEngine(
            load_config(root),
            EngineOptions(
                target_python=sys.executable,
                use_cache=False,
                changed_lines={PRICING: frozenset({3})},
                cache_path=tmp_path / "c.db",
            ),
        ).run()

        assert report.diff_filtered
        assert report.total > 0
        assert {r.mutant.lineno for r in report.results} == {3}

    def test_parse_unified_zero_diff(self) -> None:
        diff = (
            "diff --git a/app/x.py b/app/x.py\n"
            "--- a/app/x.py\n"
            "+++ b/app/x.py\n"
            "@@ -3 +3 @@ def f():\n"
            "-    return 1\n"
            "+    return 2\n"
            "@@ -10,0 +11,3 @@\n"
            "+a\n+b\n+c\n"
            "--- a/gone.py\n"
            "+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n"
            "--- a/app/y.py\n"
            "+++ b/app/y.py\n"
            "@@ -5,2 +4,0 @@\n"
        )

        assert parse_unified_zero_diff(diff) == {"app/x.py": frozenset({3, 11, 12, 13})}


class TestCli:
    def test_weak_suite_fails_gate_writes_reports_and_replays_cache(
        self, make_project: ProjectFactory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_project(tests=WEAK_TESTS)
        args = ["run", "--project-root", str(root), "--target-python", sys.executable, "--quiet"]

        first = main([*args, "--json", str(root / "first.json")])
        second = main([*args, "--json", str(root / "second.json")])

        assert first == 1
        assert second == 1
        assert (root / "report.html").is_file()
        assert json.loads((root / "report.sarif").read_text())["version"] == "2.1.0"
        first_run = json.loads((root / "first.json").read_text())
        second_run = json.loads((root / "second.json").read_text())
        assert second_run["kill_score"] == first_run["kill_score"]
        assert all(r["cached"] for r in second_run["results"])
        assert "GATE FAILED" in capsys.readouterr().out

    def test_passing_gate_exits_zero(self, make_project: ProjectFactory) -> None:
        root = make_project()

        exit_code = main(
            [
                "run",
                "--project-root",
                str(root),
                "--target-python",
                sys.executable,
                "--mutators",
                "GuardClause",
                "--no-cache",
                "--quiet",
            ]
        )

        assert exit_code == 0

    def test_min_score_override_changes_verdict(self, make_project: ProjectFactory) -> None:
        root = make_project(tests=WEAK_TESTS)

        exit_code = main(
            ["run", "--project-root", str(root), "--min-score", "0", "--no-cache", "--quiet"]
        )

        assert exit_code == 0

    @pytest.mark.parametrize(
        "extra",
        [
            pytest.param(["--min-score", "150"], id="invalid-threshold"),
            pytest.param(["--paths", "missing_dir"], id="missing-source-path"),
        ],
    )
    def test_configuration_errors_exit_two(self, make_project: ProjectFactory, extra: list[str]) -> None:
        root = make_project()

        assert main(["run", "--project-root", str(root), "--quiet", *extra]) == 2

    def test_unknown_mutator_is_rejected_by_argument_parser(self, make_project: ProjectFactory) -> None:
        root = make_project()

        with pytest.raises(SystemExit) as exit_info:
            main(["run", "--project-root", str(root), "--mutators", "Nope"])

        assert exit_info.value.code == 2

    def test_failing_baseline_exits_two(self, make_project: ProjectFactory, capsys: pytest.CaptureFixture[str]) -> None:
        root = make_project(tests="def test_broken():\n    assert False\n")

        assert main(["run", "--project-root", str(root), "--quiet"]) == 2
        assert "must pass" in capsys.readouterr().err

    def test_cache_command_clears(self, make_project: ProjectFactory, capsys: pytest.CaptureFixture[str]) -> None:
        root = make_project()

        assert main(["cache", "--project-root", str(root), "--clear"]) == 0
        assert "0 cached verdicts" in capsys.readouterr().out


@requires_git
class TestBenchmark:
    @pytest.fixture
    def repo(self, make_project: ProjectFactory) -> Path:
        root = make_project(tests=WEAK_TESTS)
        (root / PRICING).write_text(OFF_BY_ONE, encoding="utf-8")
        write_files(root, {".gitignore": "__pycache__/\n.pytest_cache/\n*.db*\n"})
        git(root, "init", "-q", "-b", "main")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "buggy threshold")

        (root / PRICING).write_text(PRICING_SOURCE, encoding="utf-8")
        write_files(
            root,
            {
                "toy_tests/test_regression.py": """\
                from toyshop.pricing import discount


                def test_discount_starts_exactly_at_100():
                    assert discount(100) == 90
                """
            },
        )
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "fix: discount applies at 100")
        return root

    def test_fix_commit_is_validated_and_repo_is_restored(self, repo: Path) -> None:
        fix_sha = git(repo, "rev-parse", "HEAD")

        report = run_benchmark(repo=repo, commit="HEAD", target_python=sys.executable)

        assert report.validated
        assert report.changed_files == {PRICING: [2]}
        assert any("Replace `>=` with `>`" in d.description for d in report.detections)
        assert all(d.pre_fix_status is MutantStatus.SURVIVED for d in report.detections)
        assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
        assert git(repo, "rev-parse", "HEAD") == fix_sha
        assert git(repo, "status", "--porcelain") == ""
        assert (repo / "toy_tests/test_regression.py").is_file()
        assert "VALIDATED" in report.format_text()

    def test_dirty_tree_is_refused(self, repo: Path) -> None:
        (repo / PRICING).write_text(PRICING_SOURCE + "# edit\n", encoding="utf-8")

        with pytest.raises(BenchmarkError, match="not clean"):
            run_benchmark(repo=repo, commit="HEAD")

    def test_test_only_commit_is_refused(self, repo: Path) -> None:
        write_files(repo, {"toy_tests/test_more.py": "def test_more():\n    assert True\n"})
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "tests only")

        with pytest.raises(BenchmarkError, match="no non-test Python source"):
            run_benchmark(repo=repo, commit="HEAD", target_python=sys.executable)
        assert git(repo, "status", "--porcelain") == ""

    def test_non_repository_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BenchmarkError, match="not a git repository"):
            run_benchmark(repo=tmp_path, commit="HEAD")

    def test_cli_exit_code_reflects_verdict(self, repo: Path) -> None:
        assert main(["benchmark", "--repo", str(repo), "--commit", "HEAD", "--quiet"]) == 0
