"""Baseline timing, watchdog timeouts, cache lookups, and parallel isolated mutant execution.

Every mutant runs in a fresh ``<target-python> worker_bootstrap.py payload.json``
subprocess, so mutated module state can never leak between mutants and a
mutated infinite loop is killed by ``subprocess.run(..., timeout=...)``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from pymutate.cache import ResultCache, cache_key, tests_hash
from pymutate.models import Mutant, MutantResult, MutantStatus

WORKER_SCRIPT = Path(__file__).with_name("worker_bootstrap.py")
EXIT_BAD_PAYLOAD = 96
EXIT_NOT_LOADED = 97
KILL_EXIT_CODES = frozenset({1, 2, 3})
WORKER_ERROR_EXIT_CODES = frozenset({4, 5, EXIT_BAD_PAYLOAD})
DEFAULT_PYTEST_ARGS: tuple[str, ...] = ("-x",)

ProgressCallback = Callable[[MutantResult, int, int], None]


class BaselineError(RuntimeError):
    """The unmutated test suite failed or could not run, so no mutant verdict would be trustworthy."""


@dataclass(frozen=True)
class BaselineResult:
    duration_sec: float
    exit_code: int
    output_tail: str


@dataclass(frozen=True)
class MutantJob:
    mutant: Mutant
    covering_tests: tuple[str, ...]
    file_path: Path
    import_root: Path
    is_package: bool


def compute_timeout(baseline_sec: float, multiplier: float = 3.0, minimum: float = 3.0) -> float:
    """``timeout = max(minimum, T_base * multiplier)``."""
    return max(minimum, baseline_sec * multiplier)


def classify_exit_code(exit_code: int) -> tuple[MutantStatus, str]:
    """Map a worker exit code to a verdict.

    Worker errors are reported as SURVIVED with a detail message: an
    infrastructure problem must never inflate the kill score.
    """
    if exit_code == 0:
        return MutantStatus.SURVIVED, ""
    if exit_code == EXIT_NOT_LOADED:
        return MutantStatus.SURVIVED, "covering tests never imported the mutated module"
    if exit_code in WORKER_ERROR_EXIT_CODES:
        return MutantStatus.SURVIVED, f"worker error (exit {exit_code})"
    if exit_code in KILL_EXIT_CODES:
        return MutantStatus.KILLED, ""
    if exit_code < 0:
        return MutantStatus.KILLED, f"worker crashed with signal {-exit_code}"
    return MutantStatus.KILLED, f"mutant exited the interpreter with code {exit_code}"


class Sandbox:
    def __init__(
        self,
        *,
        project_root: Path,
        target_python: str | None = None,
        cache: ResultCache | None = None,
        workers: int = 1,
        tests_fingerprint: str = "",
        pytest_args: Sequence[str] = DEFAULT_PYTEST_ARGS,
        work_dir: Path | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.target_python = target_python or sys.executable
        self.cache = cache
        self.workers = max(1, workers)
        self.tests_fingerprint = tests_fingerprint
        self.pytest_args = tuple(pytest_args)
        self.work_dir = work_dir or Path(tempfile.mkdtemp(prefix="pymutate-"))
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_sec = 0.0

    def _env(self, mutant_id: str = "") -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if mutant_id:
            env["PYMUTATE_MUTANT_ID"] = mutant_id
        return env

    def measure_baseline(self, test_paths: Sequence[str], timeout_sec: float = 900.0) -> BaselineResult:
        command = [self.target_python, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider", *test_paths]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=self.project_root,
                env=self._env(),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise BaselineError(f"Baseline test run exceeded {timeout_sec:.0f}s") from exc
        except FileNotFoundError as exc:
            raise BaselineError(f"Target python not found: {self.target_python}") from exc
        duration = time.perf_counter() - started
        tail = (completed.stdout + completed.stderr)[-3000:]
        if completed.returncode != 0:
            raise BaselineError(
                f"Baseline test suite must pass before mutation testing "
                f"(exit {completed.returncode}).\n{tail}"
            )
        return BaselineResult(duration_sec=duration, exit_code=completed.returncode, output_tail=tail)

    def configure_timeout(self, baseline_sec: float, multiplier: float, minimum: float) -> float:
        self.timeout_sec = compute_timeout(baseline_sec, multiplier, minimum)
        return self.timeout_sec

    def _cache_key(self, job: MutantJob) -> str:
        return cache_key(
            job.mutant.file_path,
            job.mutant.lineno,
            job.mutant.mutated_source,
            tests_hash(job.covering_tests, self.tests_fingerprint),
        )

    def _write_payload(self, job: MutantJob) -> Path:
        payload = {
            "mutant_id": job.mutant.id,
            "module_name": job.mutant.module_name,
            "file_path": str(job.file_path),
            "is_package": job.is_package,
            "mutated_source": job.mutant.mutated_source,
            "node_ids": list(job.covering_tests),
            "project_root": str(self.project_root),
            "import_root": str(job.import_root),
            "pytest_args": list(self.pytest_args),
        }
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".json",
            prefix=f"{job.mutant.id}-",
            dir=self.work_dir,
            delete=False,
        )
        with handle:
            json.dump(payload, handle)
        return Path(handle.name)

    def run_mutant(self, job: MutantJob) -> MutantResult:
        if not job.covering_tests:
            return MutantResult(
                mutant=job.mutant,
                status=MutantStatus.UNCOVERED,
                duration_sec=0.0,
                detail="no test executes this line",
            )
        if self.timeout_sec <= 0:
            raise RuntimeError("configure_timeout() must be called before running mutants")

        key = self._cache_key(job)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                return MutantResult(
                    mutant=job.mutant,
                    status=hit.replay_status,
                    duration_sec=0.0,
                    covering_tests=job.covering_tests,
                    cached=True,
                    detail=f"cached {hit.status.value}",
                )

        payload_path = self._write_payload(job)
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [self.target_python, "-B", str(WORKER_SCRIPT), str(payload_path)],
                cwd=self.project_root,
                env=self._env(job.mutant.id),
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
            status, detail = classify_exit_code(completed.returncode)
            if detail.startswith("worker error"):
                detail = f"{detail}: {(completed.stdout + completed.stderr)[-500:].strip()}"
        except subprocess.TimeoutExpired:
            status = MutantStatus.TIMEOUT
            detail = f"exceeded watchdog timeout of {self.timeout_sec:.2f}s"
        finally:
            payload_path.unlink(missing_ok=True)
        duration = time.perf_counter() - started

        if self.cache is not None and not detail.startswith("worker error"):
            self.cache.put(key, status, duration, job.mutant.id)
        return MutantResult(
            mutant=job.mutant,
            status=status,
            duration_sec=duration,
            covering_tests=job.covering_tests,
            cached=False,
            detail=detail,
        )

    def run_all(
        self, jobs: Sequence[MutantJob], progress: ProgressCallback | None = None
    ) -> list[MutantResult]:
        """Run jobs in parallel; results come back in the same order as ``jobs``."""
        results: list[MutantResult | None] = [None] * len(jobs)
        total = len(jobs)
        done = 0
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="pymutate") as pool:
            futures = {pool.submit(self.run_mutant, job): index for index, job in enumerate(jobs)}
            for future in as_completed(futures):
                index = futures[future]
                result = future.result()
                results[index] = result
                done += 1
                if progress is not None:
                    progress(result, done, total)
        return [result for result in results if result is not None]
