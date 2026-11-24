"""Standalone child-process entrypoint: run pytest against ONE in-memory mutant.

This file is executed by path with the *target* interpreter
(``<target-python> worker_bootstrap.py payload.json``). It imports only the
standard library plus ``pytest``, so pymutate does not have to be installed
in the target environment. The mutated module never touches disk: a
``MetaPathFinder`` at ``sys.meta_path[0]`` serves ``mutated_source`` whenever
``fullname`` equals the target module.

Exit codes:
    0              all selected tests passed      -> SURVIVED
    1, 2, 3        failures / collection errors    -> KILLED
    4, 5           pytest usage error / no tests   -> worker error
    96             invalid payload
    97             tests passed but never imported the mutated module
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import sys
from types import CodeType, ModuleType
from typing import Any

EXIT_BAD_PAYLOAD = 96
EXIT_NOT_LOADED = 97


class MutantLoader(importlib.abc.Loader):
    def __init__(self, fullname: str, file_path: str, source: str) -> None:
        self.fullname = fullname
        self.file_path = file_path
        self.source = source
        self.exec_count = 0

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType | None:
        return None

    def get_code(self) -> CodeType:
        return compile(self.source, self.file_path, "exec", dont_inherit=True)

    def exec_module(self, module: ModuleType) -> None:
        self.exec_count += 1
        module.__dict__["__pymutate_mutant__"] = True
        exec(self.get_code(), module.__dict__)


class MutantFinder(importlib.abc.MetaPathFinder):
    def __init__(self, fullname: str, file_path: str, source: str, is_package: bool) -> None:
        self.fullname = fullname
        self.file_path = file_path
        self.is_package = is_package
        self.loader = MutantLoader(fullname, file_path, source)

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname != self.fullname:
            return None
        search_locations = [os.path.dirname(self.file_path)] if self.is_package else None
        return importlib.util.spec_from_file_location(
            fullname,
            self.file_path,
            loader=self.loader,
            submodule_search_locations=search_locations,
        )


def _load_payload(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    required = ("module_name", "file_path", "mutated_source", "node_ids", "project_root", "import_root")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"payload is missing keys: {missing}")
    if not isinstance(payload["node_ids"], list) or not payload["node_ids"]:
        raise ValueError("payload node_ids must be a non-empty list")
    return payload


def _prepare_sys_path(project_root: str, import_root: str) -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = [entry for entry in sys.path if os.path.abspath(entry or ".") != script_dir]
    for entry in (project_root, import_root):
        if entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: worker_bootstrap.py <payload.json>", file=sys.stderr)
        return EXIT_BAD_PAYLOAD
    try:
        payload = _load_payload(argv[1])
    except (OSError, ValueError) as exc:
        print(f"pymutate worker: invalid payload: {exc}", file=sys.stderr)
        return EXIT_BAD_PAYLOAD

    sys.dont_write_bytecode = True
    os.chdir(payload["project_root"])
    _prepare_sys_path(payload["project_root"], payload["import_root"])
    sys.modules.pop(payload["module_name"], None)

    finder = MutantFinder(
        fullname=payload["module_name"],
        file_path=payload["file_path"],
        source=payload["mutated_source"],
        is_package=bool(payload.get("is_package", False)),
    )
    sys.meta_path.insert(0, finder)

    import pytest

    extra_args = [str(arg) for arg in payload.get("pytest_args", [])]
    exit_code = int(
        pytest.main(["-q", "--tb=no", "-p", "no:cacheprovider", *extra_args, *payload["node_ids"]])
    )

    if exit_code == 0 and finder.loader.exec_count == 0:
        print(
            f"pymutate worker: tests passed but {payload['module_name']} was never imported",
            file=sys.stderr,
        )
        return EXIT_NOT_LOADED
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
