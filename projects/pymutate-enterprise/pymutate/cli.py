"""Command-line interface.

    python -m pymutate.cli run        [--diff-base REF] [--no-cache] [--html F] [--sarif F] ...
    python -m pymutate.cli benchmark  --repo PATH --commit SHA [--target-python BIN]
    python -m pymutate.cli cache      --clear

Exit codes: 0 gate passed / benchmark validated, 1 gate failed / benchmark not
validated, 2 configuration, baseline, git, or other usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pymutate import __version__
from pymutate.benchmark import BenchmarkError, run_benchmark
from pymutate.cache import ResultCache
from pymutate.config import ConfigError, load_config
from pymutate.engine import EngineError, EngineOptions, MutationEngine
from pymutate.models import MutantResult
from pymutate.mutators import MUTATOR_REGISTRY
from pymutate.reporters import format_cli_summary, write_html, write_json, write_sarif
from pymutate.sandbox import ProgressCallback

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_ERROR = 2


def _stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymutate",
        description="In-memory AST mutation testing with coverage-targeted test selection.",
    )
    parser.add_argument("--version", action="version", version=f"pymutate {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Mutate configured sources and enforce score thresholds")
    run.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root (default: cwd)")
    run.add_argument("--config", type=Path, default=None, help="pyproject.toml path (default: <root>/pyproject.toml)")
    run.add_argument("--paths", nargs="+", default=None, help="Source files/dirs to mutate (overrides config)")
    run.add_argument("--tests", nargs="+", default=None, help="Test files/dirs (overrides config)")
    run.add_argument("--target-python", default=None, help="Interpreter of the target environment (default: this one)")
    run.add_argument("--workers", type=int, default=None, help="Parallel mutant subprocesses")
    run.add_argument("--min-score", type=float, default=None, help="Override default_min_score")
    run.add_argument(
        "--mutators",
        nargs="+",
        choices=sorted(MUTATOR_REGISTRY),
        default=None,
        help="Restrict to these mutators",
    )
    run.add_argument("--diff-base", default=None, help="Only mutate lines changed since this git ref")
    run.add_argument("--no-cache", action="store_true", help="Ignore and do not write the result cache")
    run.add_argument("--html", type=Path, default=None, help="HTML report path (default from config)")
    run.add_argument("--sarif", type=Path, default=None, help="SARIF report path (default from config)")
    run.add_argument("--json", type=Path, default=None, help="Also write a machine-readable JSON report")
    run.add_argument("--max-survivors", type=int, default=15, help="Survivors listed in the CLI summary")
    run.add_argument("--quiet", action="store_true", help="Suppress progress output")

    bench = sub.add_parser("benchmark", help="Validate against a historical bug-fix commit")
    bench.add_argument("--repo", type=Path, required=True, help="Path to a clean git checkout")
    bench.add_argument("--commit", required=True, help="Bug-fix commit SHA")
    bench.add_argument("--target-python", default=None, help="Interpreter with the repo's dependencies")
    bench.add_argument("--paths", nargs="+", default=None, help="Limit to these source paths")
    bench.add_argument("--tests", nargs="+", default=None, help="Test paths (default from repo config or 'tests')")
    bench.add_argument("--workers", type=int, default=None, help="Parallel mutant subprocesses")
    bench.add_argument("--json", type=Path, default=None, help="Write benchmark result JSON")
    bench.add_argument("--quiet", action="store_true", help="Suppress progress output")

    cache = sub.add_parser("cache", help="Inspect or clear the result cache")
    cache.add_argument("--project-root", type=Path, default=Path.cwd())
    cache.add_argument("--clear", action="store_true", help="Delete all cached verdicts")
    return parser


def _progress_printer(quiet: bool) -> ProgressCallback:
    def progress(result: MutantResult, done: int, total: int) -> None:
        if quiet:
            return
        mutant = result.mutant
        _stderr(f"  [{done:>4}/{total}] {result.status.value:<16} {mutant.file_path}:{mutant.lineno} {mutant.mutator_name}")

    return progress


def command_run(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    config = load_config(root, args.config).with_overrides(
        paths=args.paths,
        tests=args.tests,
        workers=args.workers,
        default_min_score=args.min_score,
        mutators=args.mutators,
    )
    log = None if args.quiet else _stderr
    engine = MutationEngine(
        config,
        EngineOptions(
            target_python=args.target_python,
            use_cache=not args.no_cache,
            diff_base=args.diff_base,
            progress=_progress_printer(args.quiet),
            log=log,
        ),
    )
    report = engine.run()

    html_path = args.html or config.resolve(config.html_report)
    sarif_path = args.sarif or config.resolve(config.sarif_report)
    write_html(report, html_path)
    write_sarif(report, sarif_path)
    if args.json is not None:
        write_json(report, args.json)

    print(format_cli_summary(report, max_survivors=args.max_survivors))
    print(f"HTML report : {html_path}")
    print(f"SARIF report: {sarif_path}")
    return EXIT_OK if report.passed else EXIT_GATE_FAILED


def command_benchmark(args: argparse.Namespace) -> int:
    report = run_benchmark(
        repo=args.repo,
        commit=args.commit,
        target_python=args.target_python,
        paths=tuple(args.paths) if args.paths else None,
        tests=tuple(args.tests) if args.tests else None,
        workers=args.workers,
        log=None if args.quiet else _stderr,
    )
    print(report.format_text())
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return EXIT_OK if report.validated else EXIT_GATE_FAILED


def command_cache(args: argparse.Namespace) -> int:
    config = load_config(args.project_root.resolve())
    with ResultCache(config.cache_file) as cache:
        if args.clear:
            cache.clear()
            print(f"Cleared {config.cache_file}")
        stats = cache.stats()
        print(f"{config.cache_file}: {stats.entries} cached verdicts")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handlers = {"run": command_run, "benchmark": command_benchmark, "cache": command_cache}
    try:
        return handlers[args.command](args)
    except (ConfigError, EngineError, BenchmarkError, ValueError) as exc:
        _stderr(f"pymutate: error: {exc}")
        return EXIT_ERROR
    except KeyboardInterrupt:
        _stderr("pymutate: interrupted")
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
