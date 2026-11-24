"""Coordinates one mutation run.

Order: discover → (optional) git-diff filter → generate mutants → baseline
timing → per-test coverage map → parallel sandboxed execution → threshold gate.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from pymutate import __version__
from pymutate.cache import ResultCache, fingerprint_files
from pymutate.config import PymutateConfig
from pymutate.coverage_mapper import CoverageMap, build_coverage_map
from pymutate.models import Mutant, RunReport
from pymutate.mutators import generate_mutants, get_mutators
from pymutate.resolver import ResolvedModule, discover_source_files
from pymutate.sandbox import MutantJob, ProgressCallback, Sandbox

HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
PYTEST_CONFIG_FILES = ("conftest.py", "pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini")

LogCallback = Callable[[str], None]


class EngineError(RuntimeError):
    """A run could not be completed (git, discovery, baseline, or coverage failure)."""


def run_git(repo: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise EngineError("git executable not found") from exc
    if completed.returncode != 0:
        raise EngineError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout


def parse_unified_zero_diff(diff_text: str) -> dict[str, frozenset[int]]:
    """Parse ``git diff --unified=0`` output into ``{rel_path: added/changed line numbers}`` (new side)."""
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                current = None
            else:
                current = target[2:] if target.startswith("b/") else target
                changed.setdefault(current, set())
            continue
        if current is None:
            continue
        match = HUNK_HEADER.match(line)
        if match:
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) is not None else 1
            changed[current].update(range(start, start + count))
    return {path: frozenset(lines) for path, lines in changed.items() if lines}


def git_changed_lines(
    repo: Path, base: str, head: str | None = None, pathspecs: Iterable[str] = ("*.py",)
) -> dict[str, frozenset[int]]:
    """Lines added or modified between ``base`` and ``head`` (or the working tree when ``head`` is None)."""
    args = ["diff", "--unified=0", "--no-color", "--no-ext-diff", base]
    if head is not None:
        args.append(head)
    args.extend(["--", *pathspecs])
    return parse_unified_zero_diff(run_git(repo, *args))


@dataclass
class EngineOptions:
    target_python: str | None = None
    use_cache: bool = True
    diff_base: str | None = None
    changed_lines: dict[str, frozenset[int]] | None = None
    cache_path: Path | None = None
    work_dir: Path | None = None
    progress: ProgressCallback | None = None
    log: LogCallback | None = None


@dataclass
class PreparedRun:
    modules: dict[str, ResolvedModule] = field(default_factory=dict)
    mutants: list[Mutant] = field(default_factory=list)


class MutationEngine:
    def __init__(self, config: PymutateConfig, options: EngineOptions | None = None) -> None:
        self.config = config
        self.options = options or EngineOptions()
        self.target_python = self.options.target_python or sys.executable
        self.coverage_map: CoverageMap | None = None

    def _log(self, message: str) -> None:
        if self.options.log is not None:
            self.options.log(message)

    def _changed_lines(self) -> dict[str, frozenset[int]] | None:
        if self.options.changed_lines is not None:
            return self.options.changed_lines
        if self.options.diff_base:
            return git_changed_lines(self.config.project_root, self.options.diff_base)
        return None

    def tests_fingerprint(self) -> str:
        root = self.config.project_root
        files: list[Path] = [root / name for name in PYTEST_CONFIG_FILES]
        for entry in self.config.tests:
            target = root / entry
            if target.is_file():
                files.append(target)
            elif target.is_dir():
                files.extend(target.rglob("*.py"))
        return fingerprint_files(files)

    def prepare(self) -> PreparedRun:
        try:
            discovered = discover_source_files(
                self.config.paths, self.config.project_root, self.config.exclude
            )
        except ValueError as exc:
            raise EngineError(str(exc)) from exc
        changed = self._changed_lines()
        mutators = get_mutators(self.config.mutators)

        prepared = PreparedRun()
        for module in discovered:
            lines: frozenset[int] | None = None
            if changed is not None:
                lines = changed.get(module.rel_path)
                if not lines:
                    continue
            source = module.file_path.read_text(encoding="utf-8")
            try:
                mutants = generate_mutants(
                    source,
                    file_path=module.rel_path,
                    module_name=module.module_name,
                    mutators=mutators,
                    changed_lines=lines,
                )
            except SyntaxError as exc:
                raise EngineError(f"{module.rel_path} does not parse: {exc}") from exc
            prepared.modules[module.rel_path] = module
            prepared.mutants.extend(mutants)
            self._log(f"  {module.rel_path} ({module.module_name}): {len(mutants)} mutants")
        return prepared

    def run(self) -> RunReport:
        started = time.time()
        report = RunReport(
            project_root=str(self.config.project_root),
            target_python=self.target_python,
            default_min_score=self.config.default_min_score,
            path_thresholds=dict(self.config.path_thresholds),
            started_at=started,
            tool_version=__version__,
            diff_filtered=self.options.diff_base is not None or self.options.changed_lines is not None,
        )

        self._log("Generating mutants")
        prepared = self.prepare()
        if not prepared.mutants:
            self._log("No mutants generated; nothing to test")
            report.finished_at = time.time()
            return report

        with tempfile.TemporaryDirectory(prefix="pymutate-run-") as temp_dir:
            work_dir = self.options.work_dir or Path(temp_dir)
            cache = ResultCache(
                self.options.cache_path or self.config.cache_file, enabled=self.options.use_cache
            )
            try:
                sandbox = Sandbox(
                    project_root=self.config.project_root,
                    target_python=self.target_python,
                    cache=cache,
                    workers=self.config.workers,
                    tests_fingerprint=self.tests_fingerprint(),
                    work_dir=work_dir,
                )

                self._log("Measuring clean baseline")
                try:
                    baseline = sandbox.measure_baseline(self.config.tests)
                except RuntimeError as exc:
                    raise EngineError(str(exc)) from exc
                timeout = sandbox.configure_timeout(
                    baseline.duration_sec, self.config.timeout_multiplier, self.config.min_timeout_sec
                )
                report.baseline_duration_sec = baseline.duration_sec
                report.timeout_sec = timeout
                self._log(f"  baseline {baseline.duration_sec:.2f}s -> watchdog timeout {timeout:.2f}s")

                self._log("Mapping per-test coverage")
                try:
                    coverage_map = build_coverage_map(
                        project_root=self.config.project_root,
                        target_python=self.target_python,
                        source_paths=self.config.paths,
                        test_paths=self.config.tests,
                        work_dir=work_dir,
                    )
                except RuntimeError as exc:
                    raise EngineError(str(exc)) from exc
                self.coverage_map = coverage_map
                self._log(f"  {len(coverage_map.all_tests)} tests mapped to source lines")

                jobs = []
                for mutant in prepared.mutants:
                    module = prepared.modules[mutant.file_path]
                    jobs.append(
                        MutantJob(
                            mutant=mutant,
                            covering_tests=coverage_map.tests_for(mutant.file_path, mutant.line_range),
                            file_path=module.file_path,
                            import_root=module.import_root,
                            is_package=module.is_package,
                        )
                    )

                self._log(f"Running {len(jobs)} mutants on {self.config.workers} worker(s)")
                report.results = sandbox.run_all(jobs, progress=self.options.progress)
            finally:
                cache.close()

        report.finished_at = time.time()
        return report
