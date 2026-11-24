"""AST mutators with real-world noise filters.

Mutants are produced by splicing ``ast.unparse(replacement)`` into the exact
source span of the targeted node (positions from the AST, UTF-8 byte columns).
The rest of the file is untouched, so every mutant keeps the original line
numbers and the coverage map ``(file, line) -> tests`` stays valid for it.
Multi-line targets are padded with newlines inside parentheses for the same
reason. Every mutant is compiled before it is emitted; anything that does not
compile or shifts line numbers is discarded.

Never mutated:

- module / class / function docstrings
- ``if TYPE_CHECKING:`` bodies and ``if __name__ == "__main__":`` blocks
- functions decorated with ``@overload`` or ``@no_mutate``
- display dunders (``__repr__``, ``__str__``, ``__format__``)
- ``logger.*`` / ``logging.*`` / ``warnings.warn()`` calls, ``assert`` statements, f-strings
- any line carrying ``# pragma: no mutate`` (on a ``def``/``class`` line: the whole block)
"""

from __future__ import annotations

import ast
import copy
import difflib
import hashlib
import io
import tokenize
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, TypeVar

from pymutate.models import Mutant, RiskLevel

PRAGMA = "pragma: no mutate"
SKIP_DECORATORS = frozenset({"overload", "no_mutate"})
DISPLAY_DUNDERS = frozenset({"__repr__", "__str__", "__format__"})
LOGGER_NAMES = frozenset({"logger", "log", "logging", "_logger", "_log", "LOGGER", "LOG"})
MAX_SNIPPET = 60

NodeT = TypeVar("NodeT", bound=ast.AST)
F = TypeVar("F", bound=Callable[..., object])


def no_mutate(func: F) -> F:
    """Marker decorator: pymutate skips the decorated function entirely (matched by name)."""
    return func


def _snippet(node: ast.AST) -> str:
    text = " ".join(ast.unparse(node).split())
    return text if len(text) <= MAX_SNIPPET else text[: MAX_SNIPPET - 3] + "..."


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _is_main_guard(test: ast.expr) -> bool:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    operands = [test.left, test.comparators[0]]
    has_name = any(isinstance(o, ast.Name) and o.id == "__name__" for o in operands)
    has_main = any(isinstance(o, ast.Constant) and o.value == "__main__" for o in operands)
    return has_name and has_main


def _is_logging_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == "warn"
    if not isinstance(func, ast.Attribute):
        return False
    owner = func.value
    if isinstance(owner, ast.Name):
        if owner.id in LOGGER_NAMES:
            return True
        if owner.id == "warnings" and func.attr == "warn":
            return True
    if isinstance(owner, ast.Attribute) and owner.attr in LOGGER_NAMES:
        return True
    return False


def _docstring_node(node: ast.AST) -> ast.Expr | None:
    body = getattr(node, "body", None)
    if not body or not isinstance(body, list):
        return None
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first
    return None


def find_pragma_lines(source: str) -> frozenset[int]:
    """Line numbers whose *comment* contains ``pragma: no mutate`` (string literals do not count)."""
    lines: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and PRAGMA in token.string.lower():
                lines.add(token.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        for number, line in enumerate(source.split("\n"), start=1):
            if "#" in line and PRAGMA in line.split("#", 1)[1].lower():
                lines.add(number)
    return frozenset(lines)


def _mark_subtree(node: ast.AST, skipped: set[int]) -> None:
    for child in ast.walk(node):
        skipped.add(id(child))


def collect_skipped_nodes(tree: ast.AST, pragma_lines: frozenset[int]) -> set[int]:
    skipped: set[int] = set()
    for node in ast.walk(tree):
        docstring = _docstring_node(node) if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ) else None
        if docstring is not None:
            _mark_subtree(docstring, skipped)

        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            header_lines = {node.lineno, *(d.lineno for d in node.decorator_list)}
            if header_lines & pragma_lines:
                _mark_subtree(node, skipped)
                continue
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            decorators = {_decorator_name(d) for d in node.decorator_list}
            if decorators & SKIP_DECORATORS or node.name in DISPLAY_DUNDERS:
                _mark_subtree(node, skipped)
        elif isinstance(node, ast.If):
            if _is_type_checking(node.test):
                skipped.add(id(node))
                _mark_subtree(node.test, skipped)
                for statement in node.body:
                    _mark_subtree(statement, skipped)
            elif _is_main_guard(node.test):
                _mark_subtree(node, skipped)
        elif isinstance(node, ast.Assert | ast.JoinedStr):
            _mark_subtree(node, skipped)
        elif isinstance(node, ast.Call) and _is_logging_call(node):
            _mark_subtree(node, skipped)
    return skipped


class _LineIndex:
    """Converts AST (lineno, UTF-8 byte column) positions into ``str`` offsets."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.line_starts = [0]
        position = source.find("\n")
        while position != -1:
            self.line_starts.append(position + 1)
            position = source.find("\n", position + 1)

    def offset(self, lineno: int, col_bytes: int) -> int:
        start = self.line_starts[lineno - 1]
        end = self.source.find("\n", start)
        line = self.source[start : end if end != -1 else len(self.source)]
        return start + len(line.encode("utf-8")[:col_bytes].decode("utf-8", errors="ignore"))


@dataclass
class AnalysisContext:
    tree: ast.Module
    source: str
    skipped: set[int]
    parents: dict[int, ast.AST]
    pragma_lines: frozenset[int]

    def parent(self, node: ast.AST) -> ast.AST | None:
        return self.parents.get(id(node))

    def lines_clear(self, first: int, last: int) -> bool:
        return not any(line in self.pragma_lines for line in range(first, last + 1))

    def is_mutable(self, node: ast.AST) -> bool:
        if id(node) in self.skipped:
            return False
        lineno = getattr(node, "lineno", None)
        end_lineno = getattr(node, "end_lineno", None)
        if lineno is None or end_lineno is None:
            return False
        return self.lines_clear(lineno, end_lineno)

    def walk(self, node_type: type[NodeT]) -> Iterator[NodeT]:
        for node in ast.walk(self.tree):
            if isinstance(node, node_type) and id(node) not in self.skipped:
                yield node


def analyze(source: str, filename: str = "<unknown>") -> AnalysisContext:
    tree = ast.parse(source, filename=filename, type_comments=False)
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    pragma_lines = find_pragma_lines(source)
    return AnalysisContext(
        tree=tree,
        source=source,
        skipped=collect_skipped_nodes(tree, pragma_lines),
        parents=parents,
        pragma_lines=pragma_lines,
    )


@dataclass(frozen=True)
class MutationSite:
    target: ast.AST
    replacement: ast.AST
    description: str
    force_parens: bool = False
    anchor: ast.AST | None = None

    @property
    def report_node(self) -> ast.AST:
        return self.anchor or self.target


class Mutator(ABC):
    name: ClassVar[str]
    risk: ClassVar[RiskLevel]
    category: ClassVar[str]

    @property
    def label(self) -> str:
        return f"[{self.risk.value} - {self.category}]"

    @abstractmethod
    def sites(self, ctx: AnalysisContext) -> Iterator[MutationSite]:
        """Yield every single-point mutation this mutator can apply."""


_OPERATOR_PARENTS = (
    ast.BoolOp,
    ast.UnaryOp,
    ast.BinOp,
    ast.Compare,
    ast.Attribute,
    ast.Subscript,
    ast.Await,
)


def _is_number(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    )


def _shifted(value: int | float) -> list[int | float]:
    if isinstance(value, int):
        return [value + 1, value - 1]
    return [round(value + 0.01, 10), round(value - 0.01, 10)]


class NumericBoundaryMutator(Mutator):
    name = "NumericBoundary"
    risk = RiskLevel.HIGH
    category = "BOUNDARY GAP"

    def sites(self, ctx: AnalysisContext) -> Iterator[MutationSite]:
        for compare in ctx.walk(ast.Compare):
            for operand in (compare.left, *compare.comparators):
                constant = operand
                if (
                    isinstance(operand, ast.UnaryOp)
                    and isinstance(operand.op, ast.USub | ast.UAdd)
                    and _is_number(operand.operand)
                ):
                    constant = operand.operand
                if not _is_number(constant) or not ctx.is_mutable(constant):
                    continue
                assert isinstance(constant, ast.Constant)
                parent_is_unary = isinstance(ctx.parent(constant), ast.UnaryOp)
                for new_value in _shifted(constant.value):
                    yield MutationSite(
                        target=constant,
                        replacement=ast.Constant(new_value),
                        description=(
                            f"{self.label} Shift comparison boundary "
                            f"{constant.value!r} -> {new_value!r} in `{_snippet(compare)}`"
                        ),
                        force_parens=parent_is_unary and new_value < 0,
                    )


_COMPARE_SWAPS: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}

_SYMBOLS: dict[type[ast.AST], str] = {
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.And: "and",
    ast.Or: "or",
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
}


class ComparisonOperatorMutator(Mutator):
    name = "ComparisonOperator"
    risk = RiskLevel.HIGH
    category = "BOUNDARY GAP"

    def sites(self, ctx: AnalysisContext) -> Iterator[MutationSite]:
        for compare in ctx.walk(ast.Compare):
            if not ctx.is_mutable(compare):
                continue
            for index, operator in enumerate(compare.ops):
                swap = _COMPARE_SWAPS.get(type(operator))
                if swap is None:
                    continue
                mutated = copy.deepcopy(compare)
                mutated.ops[index] = swap()
                yield MutationSite(
                    target=compare,
                    replacement=mutated,
                    description=(
                        f"{self.label} Replace `{_SYMBOLS[type(operator)]}` with "
                        f"`{_SYMBOLS[swap]}` in `{_snippet(compare)}`"
                    ),
                )


class BooleanLogicMutator(Mutator):
    name = "BooleanLogic"
    risk = RiskLevel.CRITICAL
    category = "MC/DC LOGIC GAP"

    def sites(self, ctx: AnalysisContext) -> Iterator[MutationSite]:
        for bool_op in ctx.walk(ast.BoolOp):
            if not ctx.is_mutable(bool_op):
                continue
            swapped = copy.deepcopy(bool_op)
            swapped.op = ast.Or() if isinstance(bool_op.op, ast.And) else ast.And()
            yield MutationSite(
                target=bool_op,
                replacement=swapped,
                description=(
                    f"{self.label} Replace `{_SYMBOLS[type(bool_op.op)]}` with "
                    f"`{_SYMBOLS[type(swapped.op)]}` in `{_snippet(bool_op)}`"
                ),
                force_parens=isinstance(ctx.parent(bool_op), _OPERATOR_PARENTS),
            )
            for value in bool_op.values:
                if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.Not):
                    continue
                if not ctx.is_mutable(value):
                    continue
                yield MutationSite(
                    target=value,
                    replacement=ast.UnaryOp(op=ast.Not(), operand=copy.deepcopy(value)),
                    description=(
                        f"{self.label} Negate operand `{_snippet(value)}` of "
                        f"`{_SYMBOLS[type(bool_op.op)]}` condition"
                    ),
                )


class DefaultBooleanMutator(Mutator):
    name = "DefaultBoolean"
    risk = RiskLevel.CRITICAL
    category = "SECURITY/CONFIG DEFAULT"

    def sites(self, ctx: AnalysisContext) -> Iterator[MutationSite]:
        for function in ctx.walk(ast.FunctionDef):
            yield from self._function_sites(ctx, function, function.name)
        for function in ctx.walk(ast.AsyncFunctionDef):
            yield from self._function_sites(ctx, function, function.name)
        for function in ctx.walk(ast.Lambda):
            yield from self._function_sites(ctx, function, "lambda")

    def _function_sites(
        self,
        ctx: AnalysisContext,
        function: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        name: str,
    ) -> Iterator[MutationSite]:
        args = function.args
        positional = [*args.posonlyargs, *args.args]
        pairs: list[tuple[ast.arg, ast.expr]] = list(
            zip(positional[len(positional) - len(args.defaults) :], args.defaults, strict=True)
        )
        pairs.extend(
            (arg, default)
            for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True)
            if default is not None
        )
        for arg, default in pairs:
            if not (isinstance(default, ast.Constant) and isinstance(default.value, bool)):
                continue
            if not ctx.is_mutable(default):
                continue
            flipped = not default.value
            yield MutationSite(
                target=default,
                replacement=ast.Constant(flipped),
                description=(
                    f"{self.label} Flip default `{arg.arg}={default.value}` -> "
                    f"`{arg.arg}={flipped}` in `{name}()`"
                ),
            )


_ARITHMETIC_SWAPS: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mod,
    ast.Mod: ast.FloorDiv,
}


def _is_text_like(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return True
    return isinstance(node, ast.Constant) and isinstance(node.value, str | bytes)


class ArithmeticOperatorMutator(Mutator):
    name = "ArithmeticOperator"
    risk = RiskLevel.MEDIUM
    category = "CALCULATION BUG"

    def sites(self, ctx: AnalysisContext) -> Iterator[MutationSite]:
        for bin_op in ctx.walk(ast.BinOp):
            swap = _ARITHMETIC_SWAPS.get(type(bin_op.op))
            if swap is None or not ctx.is_mutable(bin_op):
                continue
            if _is_text_like(bin_op.left) or _is_text_like(bin_op.right):
                continue
            mutated = copy.deepcopy(bin_op)
            mutated.op = swap()
            yield MutationSite(
                target=bin_op,
                replacement=mutated,
                description=(
                    f"{self.label} Replace `{_SYMBOLS[type(bin_op.op)]}` with "
                    f"`{_SYMBOLS[swap]}` in `{_snippet(bin_op)}`"
                ),
            )
        for aug in ctx.walk(ast.AugAssign):
            swap = _ARITHMETIC_SWAPS.get(type(aug.op))
            if swap is None or not ctx.is_mutable(aug) or _is_text_like(aug.value):
                continue
            mutated_aug = copy.deepcopy(aug)
            mutated_aug.op = swap()
            yield MutationSite(
                target=aug,
                replacement=mutated_aug,
                description=(
                    f"{self.label} Replace `{_SYMBOLS[type(aug.op)]}=` with "
                    f"`{_SYMBOLS[swap]}=` in `{_snippet(aug)}`"
                ),
            )


class GuardClauseMutator(Mutator):
    name = "GuardClause"
    risk = RiskLevel.CRITICAL
    category = "GUARD CLAUSE BYPASSED"
    max_guard_body = 3

    def sites(self, ctx: AnalysisContext) -> Iterator[MutationSite]:
        for if_node in ctx.walk(ast.If):
            if if_node.orelse or not if_node.body:
                continue
            terminal = if_node.body[-1]
            if not isinstance(terminal, ast.Raise | ast.Return):
                continue
            if len(if_node.body) > self.max_guard_body:
                continue
            if isinstance(if_node.test, ast.Constant):
                continue
            if id(if_node.test) in ctx.skipped:
                continue
            if not ctx.lines_clear(if_node.lineno, if_node.test.end_lineno or if_node.lineno):
                continue
            kind = "raise" if isinstance(terminal, ast.Raise) else "return"
            yield MutationSite(
                target=if_node.test,
                replacement=ast.Constant(False),
                description=(
                    f"{self.label} Bypass guard clause `if {_snippet(if_node.test)}: {kind} ...`"
                ),
                anchor=if_node,
            )


ALL_MUTATORS: tuple[type[Mutator], ...] = (
    NumericBoundaryMutator,
    ComparisonOperatorMutator,
    BooleanLogicMutator,
    DefaultBooleanMutator,
    ArithmeticOperatorMutator,
    GuardClauseMutator,
)

MUTATOR_REGISTRY: dict[str, type[Mutator]] = {cls.name: cls for cls in ALL_MUTATORS}


def get_mutators(names: Sequence[str] = ()) -> list[Mutator]:
    """Instantiate the named mutators (all six when ``names`` is empty)."""
    if not names:
        return [cls() for cls in ALL_MUTATORS]
    unknown = [name for name in names if name not in MUTATOR_REGISTRY]
    if unknown:
        raise ValueError(
            f"Unknown mutator(s) {unknown}; available: {sorted(MUTATOR_REGISTRY)}"
        )
    return [MUTATOR_REGISTRY[name]() for name in names]


def make_diff(original: str, mutated: str, file_path: str, context: int = 2) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            mutated.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            n=context,
        )
    )


def _replacement_text(site: MutationSite) -> str:
    target = site.target
    text = ast.unparse(site.replacement)
    extra_lines = (target.end_lineno or target.lineno) - target.lineno
    padding = "\n" * extra_lines
    if isinstance(target, ast.stmt):
        return text + padding
    if site.force_parens or extra_lines:
        return "(" + text + padding + ")"
    return text


def apply_site(source: str, index: _LineIndex, site: MutationSite) -> str:
    target = site.target
    start = index.offset(target.lineno, target.col_offset)
    end = index.offset(target.end_lineno or target.lineno, target.end_col_offset or 0)
    return source[:start] + _replacement_text(site) + source[end:]


@dataclass
class _Candidate:
    order: tuple[int, int, int, int]
    mutator: Mutator
    site: MutationSite
    mutated_source: str = field(default="")


def generate_mutants(
    source: str,
    *,
    file_path: str,
    module_name: str,
    mutators: Sequence[Mutator] | None = None,
    changed_lines: frozenset[int] | None = None,
) -> list[Mutant]:
    """Generate every valid single-point mutant for ``source``.

    ``changed_lines`` restricts output to mutants whose reported line was touched
    (used for git-diff-scoped runs).
    """
    active = list(mutators) if mutators is not None else get_mutators()
    ctx = analyze(source, filename=file_path)
    index = _LineIndex(source)
    original_newlines = source.count("\n")

    candidates: list[_Candidate] = []
    for mutator_rank, mutator in enumerate(active):
        for sequence, site in enumerate(mutator.sites(ctx)):
            node = site.report_node
            candidates.append(
                _Candidate(
                    order=(node.lineno, node.col_offset, mutator_rank, sequence),
                    mutator=mutator,
                    site=site,
                )
            )
    candidates.sort(key=lambda candidate: candidate.order)

    mutants: list[Mutant] = []
    seen_sources: set[str] = set()
    for candidate in candidates:
        node = candidate.site.report_node
        if changed_lines is not None and node.lineno not in changed_lines:
            continue
        mutated = apply_site(source, index, candidate.site)
        if mutated == source or mutated in seen_sources:
            continue
        if mutated.count("\n") != original_newlines:
            continue
        try:
            compile(mutated, file_path, "exec", dont_inherit=True)
        except (SyntaxError, ValueError):
            continue
        seen_sources.add(mutated)

        digest = hashlib.sha256(
            f"{file_path}\0{node.lineno}\0{node.col_offset}\0{candidate.mutator.name}\0{mutated}".encode()
        ).hexdigest()
        mutants.append(
            Mutant(
                id=f"{candidate.mutator.name}-L{node.lineno}-{digest[:8]}",
                file_path=file_path,
                module_name=module_name,
                lineno=node.lineno,
                mutator_name=candidate.mutator.name,
                risk_level=candidate.mutator.risk,
                description=candidate.site.description,
                original_source=source,
                mutated_source=mutated,
                diff=make_diff(source, mutated, file_path),
                col_offset=node.col_offset,
                end_lineno=getattr(node, "end_lineno", None) or node.lineno,
                category=candidate.mutator.category,
            )
        )
    return mutants
