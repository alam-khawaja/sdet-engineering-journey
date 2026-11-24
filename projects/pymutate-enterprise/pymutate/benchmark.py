"""Time-machine validator: does a historical bug-fix commit's test change kill mutants it should?

For a fix commit ``<sha>``:

1. Require a clean working tree; remember the current HEAD.
2. Check out ``<sha>``; take the lines it changed (``git diff <sha>~1 <sha>``).
3. Mutate only those lines and run the **post-fix** tests (no cache).
4. Roll the test paths back to ``<sha>~1`` (``git checkout <sha>~1 -- <tests>``),
   delete test files the fix added, and run the same mutants (no cache).
5. Report mutants KILLED post-fix but not killed pre-fix: proof that the
   fix's tests close the gap the mutation engine pointed at.

The original HEAD is always restored in ``finally``. All scratch state (cache,
coverage data, payloads) lives in a temp dir outside the repository.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pymutate.config import PymutateConfig, load_config
from pymutate.engine import EngineError, EngineOptions, LogCallback, MutationEngine, git_changed_lines, run_git
from pymutate.models import MutantResult, MutantStatus, RunReport


class BenchmarkError(RuntimeError):
    """The repository is not in a state where the benchmark can run safely."""


@dataclass(frozen=True)
class FixDetection:
    mutant_id: str
    file_path: str
    lineno: int
    description: str
    pre_fix_status: MutantStatus
    post_fix_status: MutantStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutant_id": self.mutant_id,
            "file_path": self.file_path,
            "lineno": self.lineno,
            "description": self.description,
            "pre_fix_status": self.pre_fix_status.value,
            "post_fix_status": self.post_fix_status.value,
        }


@dataclass
class BenchmarkReport:
    repo: str
    commit: str
    parent: str
    changed_files: dict[str, list[int]]
    post_fix: RunReport
    pre_fix: RunReport
    detections: list[FixDetection] = field(default_factory=list)

    @property
    def validated(self) -> bool:
        return bool(self.detections)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "commit": self.commit,
            "parent": self.parent,
            "changed_files": self.changed_files,
            "validated": self.validated,
            "post_fix": {"kill_score": self.post_fix.kill_score, "total": self.post_fix.total},
            "pre_fix": {"kill_score": self.pre_fix.kill_score, "total": self.pre_fix.total},
            "detections": [detection.to_dict() for detection in self.detections],
        }

    def format_text(self) -> str:
        lines = [
            f"Time-machine benchmark: {self.repo} @ {self.commit[:12]} (parent {self.parent[:12]})",
            f"  changed source files : {', '.join(sorted(self.changed_files)) or '(none)'}",
            f"  pre-fix  kill score  : {self.pre_fix.kill_score:.2f}% of {self.pre_fix.total} mutants",
            f"  post-fix kill score  : {self.post_fix.kill_score:.2f}% of {self.post_fix.total} mutants",
            f"  fix-detected mutants : {len(self.detections)}",
        ]
        for detection in self.detections:
            lines.append(
                f"    {detection.file_path}:{detection.lineno} {detection.pre_fix_status.value} -> "
                f"{detection.post_fix_status.value}  {detection.description}"
            )
        lines.append("  verdict: " + ("VALIDATED" if self.validated else "NOT VALIDATED"))
        return "\n".join(lines)


def compare_runs(pre_fix: RunReport, post_fix: RunReport) -> list[FixDetection]:
    """Mutants (matched by stable id) killed post-fix but not killed pre-fix."""
    pre_by_id: dict[str, MutantResult] = {result.mutant.id: result for result in pre_fix.results}
    detections: list[FixDetection] = []
    for post in post_fix.results:
        pre = pre_by_id.get(post.mutant.id)
        if pre is None or not post.status.is_killed or pre.status.is_killed:
            continue
        detections.append(
            FixDetection(
                mutant_id=post.mutant.id,
                file_path=post.mutant.file_path,
                lineno=post.mutant.lineno,
                description=post.mutant.description,
                pre_fix_status=pre.status,
                post_fix_status=post.status,
            )
        )
    return sorted(detections, key=lambda d: (d.file_path, d.lineno, d.mutant_id))


def _is_test_path(rel_path: str, test_paths: tuple[str, ...]) -> bool:
    name = rel_path.rsplit("/", 1)[-1]
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True
    return any(rel_path == p or rel_path.startswith(p.rstrip("/") + "/") for p in test_paths)


def _current_ref(repo: Path) -> str:
    branch = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch and branch != "HEAD":
        return branch
    return run_git(repo, "rev-parse", "HEAD").strip()


def run_benchmark(
    *,
    repo: Path,
    commit: str,
    target_python: str | None = None,
    paths: tuple[str, ...] | None = None,
    tests: tuple[str, ...] | None = None,
    workers: int | None = None,
    log: LogCallback | None = None,
) -> BenchmarkReport:
    repo = repo.resolve()
    if not (repo / ".git").exists():
        raise BenchmarkError(f"{repo} is not a git repository")
    status = run_git(repo, "status", "--porcelain").strip()
    if status:
        raise BenchmarkError(f"Working tree of {repo} is not clean:\n{status}")

    sha = run_git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
    parent = run_git(repo, "rev-parse", "--verify", f"{sha}~1").strip()
    original_ref = _current_ref(repo)

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    try:
        emit(f"Checking out fix commit {sha[:12]}")
        run_git(repo, "checkout", "--quiet", sha)

        base_config = load_config(repo)
        test_paths = tests or base_config.tests
        changed_all = git_changed_lines(repo, parent, sha)
        changed_source = {
            path: lines for path, lines in changed_all.items() if not _is_test_path(path, test_paths)
        }
        if paths is not None:
            changed_source = {
                path: lines
                for path, lines in changed_source.items()
                if any(path == p or path.startswith(p.rstrip("/") + "/") for p in paths)
            }
        if not changed_source:
            raise BenchmarkError(f"Commit {sha[:12]} changes no non-test Python source lines")

        config: PymutateConfig = base_config.with_overrides(
            paths=tuple(sorted(changed_source)),
            tests=test_paths,
            workers=workers,
            exclude=(),
            default_min_score=0.0,
            path_thresholds={},
        )

        with tempfile.TemporaryDirectory(prefix="pymutate-bench-") as scratch:
            scratch_dir = Path(scratch)

            def options(label: str) -> EngineOptions:
                return EngineOptions(
                    target_python=target_python,
                    use_cache=False,
                    changed_lines=changed_source,
                    cache_path=scratch_dir / f"{label}.db",
                    work_dir=scratch_dir / label,
                    log=log,
                )

            emit("Post-fix run (fix commit tests)")
            post_fix = MutationEngine(config, options("post")).run()

            emit(f"Rolling test paths back to {parent[:12]}")
            added_tests = run_git(
                repo, "diff", "--name-only", "--diff-filter=A", parent, sha, "--", *test_paths
            ).split()
            existing_in_parent = [
                p
                for p in test_paths
                if run_git(repo, "ls-tree", "--name-only", parent, "--", p).strip()
            ]
            if existing_in_parent:
                run_git(repo, "checkout", "--quiet", parent, "--", *existing_in_parent)
            for added in added_tests:
                (repo / added).unlink(missing_ok=True)

            emit("Pre-fix run (parent commit tests, --no-cache)")
            pre_fix = MutationEngine(config, options("pre")).run()
    except EngineError as exc:
        raise BenchmarkError(str(exc)) from exc
    finally:
        run_git(repo, "checkout", "--quiet", "--force", original_ref)
        emit(f"Restored {original_ref}")

    return BenchmarkReport(
        repo=str(repo),
        commit=sha,
        parent=parent,
        changed_files={path: sorted(lines) for path, lines in changed_source.items()},
        post_fix=post_fix,
        pre_fix=pre_fix,
        detections=compare_runs(pre_fix, post_fix),
    )
