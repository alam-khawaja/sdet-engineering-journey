from __future__ import annotations

from pathlib import Path

import pytest

from pymutate.cache import ResultCache, cache_key, fingerprint_files
from pymutate.cache import tests_hash as hash_covering_tests
from pymutate.config import ConfigError, PymutateConfig, load_config
from pymutate.models import Mutant, MutantResult, MutantStatus, RiskLevel, RunReport, threshold_for
from pymutate.resolver import ResolutionError, discover_source_files, is_excluded, resolve_module_name
from tests.conftest import write_files


class TestResolver:
    def test_flat_module_at_root(self, tmp_path: Path) -> None:
        write_files(tmp_path, {"app.py": "X = 1\n"})

        resolved = resolve_module_name(tmp_path / "app.py", tmp_path)

        assert resolved.module_name == "app"
        assert resolved.import_root == tmp_path.resolve()
        assert resolved.rel_path == "app.py"
        assert not resolved.is_package

    def test_nested_package(self, tmp_path: Path) -> None:
        write_files(tmp_path, {"shop/__init__.py": "", "shop/billing/__init__.py": "", "shop/billing/tax.py": ""})

        resolved = resolve_module_name(Path("shop/billing/tax.py"), tmp_path)

        assert resolved.module_name == "shop.billing.tax"
        assert resolved.import_root == tmp_path.resolve()

    def test_package_init_resolves_to_package_name(self, tmp_path: Path) -> None:
        write_files(tmp_path, {"shop/__init__.py": ""})

        resolved = resolve_module_name(tmp_path / "shop/__init__.py", tmp_path)

        assert resolved.module_name == "shop"
        assert resolved.is_package

    def test_src_layout(self, tmp_path: Path) -> None:
        write_files(tmp_path, {"src/shop/__init__.py": "", "src/shop/cart.py": "", "src/loose.py": ""})

        packaged = resolve_module_name(tmp_path / "src/shop/cart.py", tmp_path)
        loose = resolve_module_name(tmp_path / "src/loose.py", tmp_path)

        assert packaged.module_name == "shop.cart"
        assert packaged.import_root == (tmp_path / "src").resolve()
        assert loose.module_name == "loose"

    @pytest.mark.parametrize(
        ("files", "target", "message"),
        [
            ({"notes.txt": ""}, "notes.txt", "not a .py file"),
            ({}, "missing.py", "does not exist"),
            ({"my-pkg/__init__.py": "", "my-pkg/mod.py": ""}, "my-pkg/mod.py", "not a valid Python identifier"),
        ],
    )
    def test_rejects_unimportable_files(
        self, tmp_path: Path, files: dict[str, str], target: str, message: str
    ) -> None:
        write_files(tmp_path, files)

        with pytest.raises(ResolutionError, match=message):
            resolve_module_name(tmp_path / target, tmp_path)

    def test_rejects_files_outside_project(self, tmp_path: Path) -> None:
        write_files(tmp_path, {"outside.py": "", "project/keep.py": ""})

        with pytest.raises(ResolutionError, match="not inside project root"):
            resolve_module_name(tmp_path / "outside.py", tmp_path / "project")

    def test_discovery_expands_directories_and_honours_exclude(self, tmp_path: Path) -> None:
        write_files(
            tmp_path,
            {
                "shop/__init__.py": "",
                "shop/a.py": "",
                "shop/sub/__init__.py": "",
                "shop/sub/b.py": "",
                "shop/__pycache__/junk.py": "",
                "extra.py": "",
            },
        )

        found = discover_source_files(("shop", "extra.py"), tmp_path, ("**/__init__.py",))

        assert [m.rel_path for m in found] == ["extra.py", "shop/a.py", "shop/sub/b.py"]

    def test_discovery_rejects_missing_path(self, tmp_path: Path) -> None:
        with pytest.raises(ResolutionError, match="does not exist"):
            discover_source_files(("nope",), tmp_path)

    @pytest.mark.parametrize(
        ("rel_path", "pattern", "expected"),
        [
            ("shop/__init__.py", "**/__init__.py", True),
            ("__init__.py", "**/__init__.py", True),
            ("shop/legacy/old.py", "shop/legacy/*", True),
            ("shop/cart.py", "**/__init__.py", False),
        ],
    )
    def test_is_excluded(self, rel_path: str, pattern: str, expected: bool) -> None:
        assert is_excluded(rel_path, (pattern,)) is expected


class TestConfig:
    def test_missing_pyproject_gives_defaults(self, tmp_path: Path) -> None:
        config = load_config(tmp_path)

        assert config.paths == ("src",)
        assert config.default_min_score == 80.0

    def test_reads_tool_table(self, tmp_path: Path) -> None:
        write_files(
            tmp_path,
            {
                "pyproject.toml": """\
                [tool.pymutate]
                paths = "lib"
                tests = ["t"]
                default_min_score = 75
                path_thresholds = { "lib/payments/" = 95 }
                workers = 3
                """
            },
        )

        config = load_config(tmp_path)

        assert config.paths == ("lib",)
        assert config.tests == ("t",)
        assert config.workers == 3
        assert config.path_thresholds == {"lib/payments": 95.0}
        assert config.threshold_for("lib/payments/card.py") == 95.0
        assert config.threshold_for("lib/other.py") == 75.0

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ("default_min_score = 120", "between 0 and 100"),
            ("workers = 0", "workers must be >= 1"),
            ("workers = true", "workers must be an integer"),
            ("paths = []", "at least one source path"),
            ("paths = [1]", "list of strings"),
            ("path_thresholds = { a = 'x' }", "must be a number"),
            ("timeout_multiplier = 0", "timeout_multiplier must be > 0"),
        ],
    )
    def test_rejects_invalid_values(self, tmp_path: Path, body: str, message: str) -> None:
        write_files(tmp_path, {"pyproject.toml": f"[tool.pymutate]\n{body}\n"})

        with pytest.raises(ConfigError, match=message):
            load_config(tmp_path)

    def test_rejects_invalid_toml(self, tmp_path: Path) -> None:
        write_files(tmp_path, {"pyproject.toml": "[tool.pymutate\n"})

        with pytest.raises(ConfigError, match="not valid TOML"):
            load_config(tmp_path)

    def test_overrides_ignore_none_and_validate(self, tmp_path: Path) -> None:
        config = PymutateConfig(project_root=tmp_path)

        overridden = config.with_overrides(paths=["app"], workers=None)

        assert overridden.paths == ("app",)
        assert overridden.workers == config.workers
        with pytest.raises(ConfigError):
            config.with_overrides(default_min_score=-1)


class TestCache:
    def test_miss_then_hit_and_replay_status(self, tmp_path: Path) -> None:
        with ResultCache(tmp_path / "c.db") as cache:
            assert cache.get("k") is None
            assert cache.put("k", MutantStatus.KILLED, 0.5, "m1")

            hit = cache.get("k")

            assert hit is not None
            assert hit.replay_status is MutantStatus.CACHED_KILLED
            assert cache.stats().hits == 1
            assert cache.stats().misses == 1

    def test_timeout_replays_as_killed_and_survivor_as_survived(self, tmp_path: Path) -> None:
        with ResultCache(tmp_path / "c.db") as cache:
            cache.put("t", MutantStatus.TIMEOUT, 3.0, "m1")
            cache.put("s", MutantStatus.SURVIVED, 0.1, "m2")

            assert cache.get("t").replay_status is MutantStatus.CACHED_KILLED
            assert cache.get("s").replay_status is MutantStatus.CACHED_SURVIVED

    def test_only_real_verdicts_are_stored(self, tmp_path: Path) -> None:
        with ResultCache(tmp_path / "c.db") as cache:
            assert not cache.put("u", MutantStatus.UNCOVERED, 0.0, "m1")
            assert not cache.put("c", MutantStatus.CACHED_KILLED, 0.0, "m2")
            assert cache.stats().entries == 0

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        with ResultCache(tmp_path / "c.db") as cache:
            cache.put("k", MutantStatus.SURVIVED, 0.2, "m1")

        with ResultCache(tmp_path / "c.db") as reopened:
            assert reopened.get("k").status is MutantStatus.SURVIVED

    def test_invalidate_and_clear(self, tmp_path: Path) -> None:
        with ResultCache(tmp_path / "c.db") as cache:
            cache.put("a", MutantStatus.KILLED, 0.1, "m1")
            cache.put("b", MutantStatus.KILLED, 0.1, "m2")

            cache.invalidate("a")
            assert cache.get("a") is None
            assert cache.get("b") is not None

            cache.clear()
            assert cache.stats().entries == 0

    def test_disabled_cache_never_hits(self, tmp_path: Path) -> None:
        cache = ResultCache(tmp_path / "c.db", enabled=False)

        cache.put("k", MutantStatus.KILLED, 0.1, "m1")

        assert cache.get("k") is None
        assert not (tmp_path / "c.db").exists()

    def test_key_changes_with_every_input(self) -> None:
        base = cache_key("a.py", 3, "src", "h")

        assert cache_key("a.py", 3, "src", "h") == base
        assert cache_key("b.py", 3, "src", "h") != base
        assert cache_key("a.py", 4, "src", "h") != base
        assert cache_key("a.py", 3, "src2", "h") != base
        assert cache_key("a.py", 3, "src", "h2") != base
        assert cache_key("a\\b.py", 3, "src", "h") == cache_key("a/b.py", 3, "src", "h")

    def test_tests_hash_is_order_insensitive_and_fingerprint_sensitive(self) -> None:
        assert hash_covering_tests(["t1", "t2"]) == hash_covering_tests(["t2", "t1"])
        assert hash_covering_tests(["t1"], "fp1") != hash_covering_tests(["t1"], "fp2")

    def test_fingerprint_changes_when_a_test_file_changes(self, tmp_path: Path) -> None:
        write_files(tmp_path, {"test_a.py": "def test(): pass\n"})
        before = fingerprint_files([tmp_path / "test_a.py", tmp_path / "missing.py"])

        (tmp_path / "test_a.py").write_text("def test(): assert 1\n", encoding="utf-8")

        assert fingerprint_files([tmp_path / "test_a.py"]) != before


def result(path: str, status: MutantStatus, line: int = 1) -> MutantResult:
    mutant = Mutant(
        id=f"M-L{line}-{status.value}",
        file_path=path,
        module_name="m",
        lineno=line,
        mutator_name="M",
        risk_level=RiskLevel.HIGH,
        description="d",
        original_source="",
        mutated_source="",
        diff="",
    )
    return MutantResult(mutant=mutant, status=status, duration_sec=0.0)


class TestScoreAndGate:
    def test_score_counts_timeouts_and_cached_kills_and_keeps_uncovered_in_denominator(self) -> None:
        report = RunReport(
            results=[
                result("a.py", MutantStatus.KILLED),
                result("a.py", MutantStatus.TIMEOUT),
                result("a.py", MutantStatus.CACHED_KILLED),
                result("a.py", MutantStatus.SURVIVED),
                result("a.py", MutantStatus.UNCOVERED),
            ],
            default_min_score=60.0,
        )

        assert report.kill_score == 60.0
        assert report.passed

    def test_empty_report_passes(self) -> None:
        assert RunReport().kill_score == 100.0
        assert RunReport().passed

    def test_per_path_threshold_fails_gate_even_when_overall_passes(self) -> None:
        report = RunReport(
            results=[
                result("core/pay.py", MutantStatus.KILLED),
                result("core/pay.py", MutantStatus.SURVIVED),
                *[result("ui.py", MutantStatus.KILLED, line) for line in range(8)],
            ],
            default_min_score=80.0,
            path_thresholds={"core": 90.0},
        )

        assert report.kill_score == 90.0
        assert not report.passed
        assert report.gate_failures() == ["core/pay.py: kill score 50.00% is below its threshold 90.00%"]

    def test_default_threshold_files_do_not_fail_individually(self) -> None:
        report = RunReport(
            results=[result("a.py", MutantStatus.SURVIVED), *[result("b.py", MutantStatus.KILLED, n) for n in range(9)]],
            default_min_score=80.0,
        )

        assert report.passed

    def test_survivors_are_ranked_by_risk(self) -> None:
        low = result("a.py", MutantStatus.SURVIVED, 1)
        critical = MutantResult(
            mutant=Mutant(**{**low.mutant.__dict__, "id": "c", "risk_level": RiskLevel.CRITICAL}),
            status=MutantStatus.SURVIVED,
            duration_sec=0.0,
        )

        report = RunReport(results=[low, critical])

        assert [r.mutant.id for r in report.survivors()] == ["c", low.mutant.id]

    @pytest.mark.parametrize(
        ("path", "expected"),
        [("core/pay.py", 95.0), ("core/payments/card.py", 99.0), ("core.py", 80.0), ("other/x.py", 80.0)],
    )
    def test_threshold_prefers_most_specific_match(self, path: str, expected: float) -> None:
        thresholds = {"core": 95.0, "core/payments": 99.0}

        assert threshold_for(path, 80.0, thresholds) == expected
