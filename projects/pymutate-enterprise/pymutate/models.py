"""Shared dataclasses and enums used across the engine, sandbox, cache, and reporters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class MutantStatus(str, Enum):
    KILLED = "KILLED"
    SURVIVED = "SURVIVED"
    TIMEOUT = "TIMEOUT"
    CACHED_KILLED = "CACHED_KILLED"
    CACHED_SURVIVED = "CACHED_SURVIVED"
    UNCOVERED = "UNCOVERED"

    @property
    def is_killed(self) -> bool:
        """A timeout means the mutant changed behaviour (e.g. an infinite loop), so it counts as detected."""
        return self in {MutantStatus.KILLED, MutantStatus.TIMEOUT, MutantStatus.CACHED_KILLED}

    @property
    def is_cached(self) -> bool:
        return self in {MutantStatus.CACHED_KILLED, MutantStatus.CACHED_SURVIVED}


class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"

    @property
    def sarif_level(self) -> str:
        return {"CRITICAL": "error", "HIGH": "error", "MEDIUM": "warning"}[self.value]

    @property
    def rank(self) -> int:
        return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}[self.value]


def threshold_for(rel_path: str, default: float, path_thresholds: dict[str, float]) -> float:
    """Most specific matching threshold: exact file, else longest directory prefix, else ``default``."""
    normalized = rel_path.replace("\\", "/")
    if normalized in path_thresholds:
        return path_thresholds[normalized]
    best_key = ""
    for key in path_thresholds:
        prefix = key.rstrip("/") + "/"
        if normalized.startswith(prefix) and len(key) > len(best_key):
            best_key = key
    return path_thresholds[best_key] if best_key else default


def has_explicit_threshold(rel_path: str, path_thresholds: dict[str, float]) -> bool:
    sentinel = float("nan")
    value = threshold_for(rel_path, sentinel, path_thresholds)
    return value == value


@dataclass(frozen=True)
class Mutant:
    id: str
    file_path: str
    module_name: str
    lineno: int
    mutator_name: str
    risk_level: RiskLevel
    description: str
    original_source: str
    mutated_source: str
    diff: str
    col_offset: int = 0
    end_lineno: int = 0
    category: str = ""

    @property
    def line_range(self) -> range:
        return range(self.lineno, max(self.lineno, self.end_lineno) + 1)

    def to_dict(self, *, include_sources: bool = True) -> dict[str, Any]:
        data = asdict(self)
        data["risk_level"] = self.risk_level.value
        if not include_sources:
            data.pop("original_source")
            data.pop("mutated_source")
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mutant:
        return cls(
            id=data["id"],
            file_path=data["file_path"],
            module_name=data["module_name"],
            lineno=int(data["lineno"]),
            mutator_name=data["mutator_name"],
            risk_level=RiskLevel(data["risk_level"]),
            description=data["description"],
            original_source=data["original_source"],
            mutated_source=data["mutated_source"],
            diff=data["diff"],
            col_offset=int(data.get("col_offset", 0)),
            end_lineno=int(data.get("end_lineno", 0)),
            category=data.get("category", ""),
        )


@dataclass(frozen=True)
class MutantResult:
    mutant: Mutant
    status: MutantStatus
    duration_sec: float
    covering_tests: tuple[str, ...] = ()
    cached: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutant": self.mutant.to_dict(include_sources=False),
            "status": self.status.value,
            "duration_sec": round(self.duration_sec, 4),
            "covering_tests": list(self.covering_tests),
            "cached": self.cached,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class FileSummary:
    file_path: str
    total: int
    killed: int
    survived: int
    timeout: int
    uncovered: int
    cached: int
    threshold: float
    threshold_is_explicit: bool

    @property
    def score(self) -> float:
        if self.total == 0:
            return 100.0
        return round(100.0 * (self.killed + self.timeout) / self.total, 2)

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = self.score
        data["passed"] = self.passed
        return data


@dataclass
class RunReport:
    """Outcome of one mutation run.

    Kill score = (KILLED + TIMEOUT + CACHED_KILLED) / all mutants. UNCOVERED mutants
    stay in the denominator: a line no test executes is the weakest test gap of all.
    The gate passes when the overall score meets ``default_min_score`` and every file
    matched by ``path_thresholds`` meets its own threshold.
    """

    results: list[MutantResult] = field(default_factory=list)
    project_root: str = ""
    target_python: str = ""
    baseline_duration_sec: float = 0.0
    timeout_sec: float = 0.0
    default_min_score: float = 80.0
    path_thresholds: dict[str, float] = field(default_factory=dict)
    started_at: float = 0.0
    finished_at: float = 0.0
    tool_version: str = ""
    diff_filtered: bool = False

    @property
    def total(self) -> int:
        return len(self.results)

    def count(self, *statuses: MutantStatus) -> int:
        wanted = set(statuses)
        return sum(1 for result in self.results if result.status in wanted)

    @property
    def killed_count(self) -> int:
        return sum(1 for result in self.results if result.status.is_killed)

    @property
    def survived_count(self) -> int:
        return self.count(MutantStatus.SURVIVED, MutantStatus.CACHED_SURVIVED)

    @property
    def kill_score(self) -> float:
        if not self.results:
            return 100.0
        return round(100.0 * self.killed_count / self.total, 2)

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

    def survivors(self) -> list[MutantResult]:
        return sorted(
            (r for r in self.results if not r.status.is_killed),
            key=lambda r: (r.mutant.risk_level.rank, r.mutant.file_path, r.mutant.lineno),
        )

    def file_summaries(self) -> list[FileSummary]:
        by_file: dict[str, list[MutantResult]] = {}
        for result in self.results:
            by_file.setdefault(result.mutant.file_path, []).append(result)

        summaries: list[FileSummary] = []
        for file_path in sorted(by_file):
            results = by_file[file_path]
            summaries.append(
                FileSummary(
                    file_path=file_path,
                    total=len(results),
                    killed=sum(
                        1
                        for r in results
                        if r.status in {MutantStatus.KILLED, MutantStatus.CACHED_KILLED}
                    ),
                    survived=sum(
                        1
                        for r in results
                        if r.status in {MutantStatus.SURVIVED, MutantStatus.CACHED_SURVIVED}
                    ),
                    timeout=sum(1 for r in results if r.status is MutantStatus.TIMEOUT),
                    uncovered=sum(1 for r in results if r.status is MutantStatus.UNCOVERED),
                    cached=sum(1 for r in results if r.cached),
                    threshold=threshold_for(file_path, self.default_min_score, self.path_thresholds),
                    threshold_is_explicit=has_explicit_threshold(file_path, self.path_thresholds),
                )
            )
        return summaries

    def gate_failures(self) -> list[str]:
        failures: list[str] = []
        if self.kill_score < self.default_min_score:
            failures.append(
                f"Overall kill score {self.kill_score:.2f}% is below the minimum {self.default_min_score:.2f}%"
            )
        for summary in self.file_summaries():
            if summary.threshold_is_explicit and not summary.passed:
                failures.append(
                    f"{summary.file_path}: kill score {summary.score:.2f}% is below its threshold "
                    f"{summary.threshold:.2f}%"
                )
        return failures

    @property
    def passed(self) -> bool:
        return not self.gate_failures()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "project_root": self.project_root,
            "target_python": self.target_python,
            "baseline_duration_sec": round(self.baseline_duration_sec, 4),
            "timeout_sec": round(self.timeout_sec, 4),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_sec": round(self.duration_sec, 4),
            "diff_filtered": self.diff_filtered,
            "default_min_score": self.default_min_score,
            "path_thresholds": dict(self.path_thresholds),
            "total": self.total,
            "killed": self.killed_count,
            "survived": self.survived_count,
            "timeout": self.count(MutantStatus.TIMEOUT),
            "uncovered": self.count(MutantStatus.UNCOVERED),
            "kill_score": self.kill_score,
            "passed": self.passed,
            "gate_failures": self.gate_failures(),
            "files": [summary.to_dict() for summary in self.file_summaries()],
            "results": [result.to_dict() for result in self.results],
        }
