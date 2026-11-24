"""Maps source files to the dotted module names the test suite will import.

The in-memory import hook only fires when ``fullname`` matches exactly, so getting
this right decides whether a mutant is actually exercised. Supported layouts:

- flat:       ``pkg/sub/mod.py``        -> ``pkg.sub.mod``   (import root = project root)
- src:        ``src/pkg/sub/mod.py``    -> ``pkg.sub.mod``   (import root = ``src/``)
- namespace:  ``pkg/mod.py`` without ``__init__.py`` -> ``pkg.mod``
- top-level:  ``mod.py`` / ``src/mod.py`` -> ``mod``
- packages:   ``pkg/__init__.py``       -> ``pkg``
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path


class ResolutionError(ValueError):
    """Raised when a file is outside the project or is not an importable Python module."""


@dataclass(frozen=True)
class ResolvedModule:
    module_name: str
    file_path: Path
    rel_path: str
    import_root: Path
    is_package: bool


def to_rel_posix(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        raise ResolutionError(f"{path} is not inside project root {project_root}") from exc


def _default_import_root(file_path: Path, root: Path) -> Path:
    src = root / "src"
    if src.is_dir() and file_path.is_relative_to(src):
        return src
    return root


def _package_import_root(file_path: Path, root: Path) -> Path | None:
    """Walk up while directories contain ``__init__.py``; return the first non-package parent."""
    directory = file_path.parent
    if not (directory / "__init__.py").is_file():
        return None
    while directory != root and (directory / "__init__.py").is_file():
        directory = directory.parent
    return directory


def resolve_module_name(file_path: Path, project_root: Path) -> ResolvedModule:
    root = project_root.resolve()
    path = (file_path if file_path.is_absolute() else root / file_path).resolve()

    if path.suffix != ".py":
        raise ResolutionError(f"{path} is not a .py file")
    if not path.is_file():
        raise ResolutionError(f"{path} does not exist")
    rel_path = to_rel_posix(path, root)

    import_root = _package_import_root(path, root) or _default_import_root(path, root)
    relative = path.relative_to(import_root).with_suffix("")
    parts = list(relative.parts)

    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    if not parts:
        raise ResolutionError(f"{rel_path} resolves to an empty module name")
    for part in parts:
        if not part.isidentifier():
            raise ResolutionError(f"{rel_path}: {part!r} is not a valid Python identifier")

    return ResolvedModule(
        module_name=".".join(parts),
        file_path=path,
        rel_path=rel_path,
        import_root=import_root,
        is_package=is_package,
    )


def is_excluded(rel_path: str, exclude: tuple[str, ...]) -> bool:
    name = rel_path.rsplit("/", 1)[-1]
    for pattern in exclude:
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(rel_path, pattern[3:]):
            return True
    return False


def discover_source_files(
    paths: tuple[str, ...], project_root: Path, exclude: tuple[str, ...] = ()
) -> list[ResolvedModule]:
    """Expand configured files/directories into resolved modules, sorted by relative path."""
    root = project_root.resolve()
    found: dict[str, ResolvedModule] = {}
    for entry in paths:
        target = (root / entry).resolve()
        if target.is_file():
            candidates = [target]
        elif target.is_dir():
            candidates = sorted(target.rglob("*.py"))
        else:
            raise ResolutionError(f"Configured source path {entry!r} does not exist under {root}")

        for candidate in candidates:
            if any(part in {"__pycache__", ".venv", "venv", ".git"} for part in candidate.parts):
                continue
            rel_path = to_rel_posix(candidate, root)
            if is_excluded(rel_path, exclude):
                continue
            found[rel_path] = resolve_module_name(candidate, root)
    return [found[key] for key in sorted(found)]
