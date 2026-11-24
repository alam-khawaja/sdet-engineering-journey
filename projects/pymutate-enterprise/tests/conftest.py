"""Builds throwaway ``toyshop`` projects so self-tests never touch the demo or the real repo."""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

PRICING_SOURCE = """\
def discount(total):
    if total >= 100:
        return total * 0.9
    return total
"""

STRONG_TESTS = """\
from toyshop.pricing import discount


def test_discount_applies_at_threshold():
    assert discount(100) == 90


def test_no_discount_below_threshold():
    assert discount(99) == 99


def test_discount_on_large_total():
    assert discount(200) == 180
"""

WEAK_TESTS = """\
from toyshop.pricing import discount


def test_large_totals_are_cheaper():
    assert discount(200) < 200


def test_small_totals_are_returned():
    assert discount(10) > 0
"""

PYPROJECT = """\
[tool.pymutate]
paths = ["toyshop"]
tests = ["toy_tests"]
default_min_score = {min_score}
exclude = ["**/__init__.py"]
workers = 2
cache_path = ".pymutate_cache.db"
html_report = "report.html"
sarif_report = "report.sarif"
"""

ProjectFactory = Callable[..., Path]


def write_files(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(content), encoding="utf-8")


@pytest.fixture
def make_project(tmp_path: Path) -> ProjectFactory:
    def factory(*, tests: str = STRONG_TESTS, min_score: float = 80.0, name: str = "proj") -> Path:
        root = tmp_path / name
        write_files(
            root,
            {
                "pyproject.toml": PYPROJECT.format(min_score=min_score),
                "toyshop/__init__.py": "",
                "toyshop/pricing.py": PRICING_SOURCE,
                "toy_tests/test_pricing.py": tests,
            },
        )
        return root

    return factory


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.name=pymutate", "-c", "user.email=pymutate@example.invalid", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
