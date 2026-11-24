"""Loads and validates the ``[tool.pymutate]`` policy table from ``pyproject.toml``."""

from __future__ import annotations

import dataclasses
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pymutate.models import threshold_for

DEFAULT_PYPROJECT = "pyproject.toml"


class ConfigError(ValueError):
    """Raised when ``[tool.pymutate]`` is missing required keys or has invalid values."""


def _default_workers() -> int:
    return max(1, min(4, os.cpu_count() or 1))


@dataclass(frozen=True)
class PymutateConfig:
    project_root: Path
    paths: tuple[str, ...] = ("src",)
    tests: tuple[str, ...] = ("tests",)
    default_min_score: float = 80.0
    path_thresholds: dict[str, float] = field(default_factory=dict)
    exclude: tuple[str, ...] = ()
    mutators: tuple[str, ...] = ()
    workers: int = field(default_factory=_default_workers)
    timeout_multiplier: float = 3.0
    min_timeout_sec: float = 3.0
    cache_path: str = ".pymutate_cache.db"
    html_report: str = "mutation-report.html"
    sarif_report: str = "mutation-results.sarif"

    def threshold_for(self, rel_path: str) -> float:
        return threshold_for(rel_path, self.default_min_score, self.path_thresholds)

    def resolve(self, relative: str) -> Path:
        candidate = Path(relative)
        return candidate if candidate.is_absolute() else self.project_root / candidate

    @property
    def cache_file(self) -> Path:
        return self.resolve(self.cache_path)

    def with_overrides(self, **overrides: Any) -> PymutateConfig:
        """Return a copy with non-``None`` overrides applied (CLI flags win over pyproject)."""
        applicable = {key: value for key, value in overrides.items() if value is not None}
        for key in ("paths", "tests", "exclude", "mutators"):
            if key in applicable:
                applicable[key] = tuple(applicable[key])
        candidate = dataclasses.replace(self, **applicable)
        _validate(candidate)
        return candidate


def _as_str_tuple(table: dict[str, Any], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"[tool.pymutate].{key} must be a string or a list of strings")
    return tuple(value)


def _as_float(table: dict[str, Any], key: str, default: float) -> float:
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"[tool.pymutate].{key} must be a number")
    return float(value)


def _as_thresholds(table: dict[str, Any]) -> dict[str, float]:
    raw = table.get("path_thresholds", {})
    if not isinstance(raw, dict):
        raise ConfigError("[tool.pymutate].path_thresholds must be a table of path = score")
    thresholds: dict[str, float] = {}
    for path, score in raw.items():
        if isinstance(score, bool) or not isinstance(score, int | float):
            raise ConfigError(f"[tool.pymutate].path_thresholds.{path!r} must be a number")
        thresholds[str(path).replace("\\", "/").rstrip("/")] = float(score)
    return thresholds


def _validate(config: PymutateConfig) -> None:
    if not config.paths:
        raise ConfigError("[tool.pymutate].paths must list at least one source path")
    if not config.tests:
        raise ConfigError("[tool.pymutate].tests must list at least one test path")
    scores = {"default_min_score": config.default_min_score, **config.path_thresholds}
    for name, score in scores.items():
        if not 0.0 <= score <= 100.0:
            raise ConfigError(f"Mutation score threshold {name!r} must be between 0 and 100, got {score}")
    if config.workers < 1:
        raise ConfigError("[tool.pymutate].workers must be >= 1")
    if config.timeout_multiplier <= 0:
        raise ConfigError("[tool.pymutate].timeout_multiplier must be > 0")
    if config.min_timeout_sec <= 0:
        raise ConfigError("[tool.pymutate].min_timeout_sec must be > 0")


def load_config(project_root: Path, pyproject: Path | None = None) -> PymutateConfig:
    """Read ``[tool.pymutate]``; a missing file or table yields validated defaults."""
    root = project_root.resolve()
    pyproject_path = pyproject or root / DEFAULT_PYPROJECT
    table: dict[str, Any] = {}
    if pyproject_path.is_file():
        try:
            with pyproject_path.open("rb") as handle:
                document = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{pyproject_path} is not valid TOML: {exc}") from exc
        table = document.get("tool", {}).get("pymutate", {})
        if not isinstance(table, dict):
            raise ConfigError("[tool.pymutate] must be a table")

    workers_raw = table.get("workers", _default_workers())
    if isinstance(workers_raw, bool) or not isinstance(workers_raw, int):
        raise ConfigError("[tool.pymutate].workers must be an integer")

    for key in ("cache_path", "html_report", "sarif_report"):
        if key in table and not isinstance(table[key], str):
            raise ConfigError(f"[tool.pymutate].{key} must be a string")

    config = PymutateConfig(
        project_root=root,
        paths=_as_str_tuple(table, "paths", ("src",)),
        tests=_as_str_tuple(table, "tests", ("tests",)),
        default_min_score=_as_float(table, "default_min_score", 80.0),
        path_thresholds=_as_thresholds(table),
        exclude=_as_str_tuple(table, "exclude", ()),
        mutators=_as_str_tuple(table, "mutators", ()),
        workers=workers_raw,
        timeout_multiplier=_as_float(table, "timeout_multiplier", 3.0),
        min_timeout_sec=_as_float(table, "min_timeout_sec", 3.0),
        cache_path=table.get("cache_path", ".pymutate_cache.db"),
        html_report=table.get("html_report", "mutation-report.html"),
        sarif_report=table.get("sarif_report", "mutation-results.sarif"),
    )
    _validate(config)
    return config
