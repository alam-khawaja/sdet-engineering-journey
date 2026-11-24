from __future__ import annotations

import re
import textwrap

import pytest

from pymutate.models import Mutant, RiskLevel
from pymutate.mutators import (
    ArithmeticOperatorMutator,
    BooleanLogicMutator,
    ComparisonOperatorMutator,
    DefaultBooleanMutator,
    GuardClauseMutator,
    NumericBoundaryMutator,
    generate_mutants,
    get_mutators,
)


def mutate(source: str, *mutators: object) -> list[Mutant]:
    return generate_mutants(
        textwrap.dedent(source),
        file_path="pkg/mod.py",
        module_name="pkg.mod",
        mutators=list(mutators) if mutators else None,
    )


def mutated_lines(mutants: list[Mutant], lineno: int) -> set[str]:
    return {m.mutated_source.splitlines()[lineno - 1].strip() for m in mutants}


class TestNumericBoundary:
    def test_shifts_integer_constant_both_ways(self) -> None:
        mutants = mutate("def f(x):\n    return x > 10\n", NumericBoundaryMutator())

        assert mutated_lines(mutants, 2) == {"return x > 11", "return x > 9"}
        assert all(m.risk_level is RiskLevel.HIGH for m in mutants)
        assert all(m.description.startswith("[HIGH - BOUNDARY GAP]") for m in mutants)

    def test_shifts_float_constant(self) -> None:
        mutants = mutate("def f(x):\n    return x <= 0.43\n", NumericBoundaryMutator())

        assert mutated_lines(mutants, 2) == {"return x <= 0.44", "return x <= 0.42"}

    def test_ignores_constants_outside_comparisons(self) -> None:
        assert mutate("RATE = 10\n", NumericBoundaryMutator()) == []


class TestComparisonOperator:
    @pytest.mark.parametrize(
        ("original", "expected"),
        [("<", "<="), ("<=", "<"), (">", ">="), (">=", ">"), ("==", "!="), ("!=", "==")],
    )
    def test_swaps_each_operator(self, original: str, expected: str) -> None:
        mutants = mutate(f"def f(a, b):\n    return a {original} b\n", ComparisonOperatorMutator())

        assert mutated_lines(mutants, 2) == {f"return a {expected} b"}

    def test_ignores_identity_and_membership(self) -> None:
        assert mutate("def f(a, b):\n    return a is b or a in b\n", ComparisonOperatorMutator()) == []


class TestBooleanLogic:
    def test_swaps_operator_and_negates_each_operand(self) -> None:
        mutants = mutate("def f(a, b):\n    return a and b\n", BooleanLogicMutator())

        assert mutated_lines(mutants, 2) == {
            "return a or b",
            "return not a and b",
            "return a and not b",
        }
        assert all(m.risk_level is RiskLevel.CRITICAL for m in mutants)
        assert all("MC/DC LOGIC GAP" in m.description for m in mutants)

    def test_does_not_double_negate(self) -> None:
        mutants = mutate("def f(a, b):\n    return not a or b\n", BooleanLogicMutator())

        assert "return not not a or b" not in mutated_lines(mutants, 2)


class TestDefaultBoolean:
    def test_flips_positional_and_keyword_only_defaults(self) -> None:
        source = "def f(x, strict=True, *, verify=False):\n    return x\n"
        mutants = mutate(source, DefaultBooleanMutator())

        assert mutated_lines(mutants, 1) == {
            "def f(x, strict=False, *, verify=False):",
            "def f(x, strict=True, *, verify=True):",
        }
        assert all("SECURITY/CONFIG DEFAULT" in m.description for m in mutants)

    def test_ignores_non_boolean_defaults(self) -> None:
        assert mutate("def f(x=1, y=None):\n    return x\n", DefaultBooleanMutator()) == []


class TestArithmeticOperator:
    @pytest.mark.parametrize(
        ("original", "expected"),
        [("+", "-"), ("-", "+"), ("*", "/"), ("/", "*"), ("//", "%"), ("%", "//")],
    )
    def test_swaps_each_operator(self, original: str, expected: str) -> None:
        mutants = mutate(f"def f(a, b):\n    return a {original} b\n", ArithmeticOperatorMutator())

        assert mutated_lines(mutants, 2) == {f"return a {expected} b"}
        assert all(m.risk_level is RiskLevel.MEDIUM for m in mutants)

    def test_mutates_augmented_assignment(self) -> None:
        mutants = mutate("def f(a):\n    a += 1\n    return a\n", ArithmeticOperatorMutator())

        assert mutated_lines(mutants, 2) == {"a -= 1"}

    def test_skips_string_concatenation(self) -> None:
        assert mutate("def f(name):\n    return 'hi ' + name\n", ArithmeticOperatorMutator()) == []


class TestGuardClause:
    def test_bypasses_raise_guard(self) -> None:
        source = """\
        def f(x):
            if x < 0:
                raise ValueError("negative")
            return x
        """
        mutants = mutate(source, GuardClauseMutator())

        assert mutated_lines(mutants, 2) == {"if False:"}
        assert mutants[0].description.startswith("[CRITICAL - GUARD CLAUSE BYPASSED]")
        assert mutants[0].lineno == 2

    def test_bypasses_early_return_guard(self) -> None:
        source = "def f(x):\n    if not x:\n        return None\n    return x[0]\n"

        assert mutated_lines(mutate(source, GuardClauseMutator()), 2) == {"if False:"}

    def test_ignores_if_with_else(self) -> None:
        source = "def f(x):\n    if x:\n        return 1\n    else:\n        return 2\n"

        assert mutate(source, GuardClauseMutator()) == []

    def test_ignores_long_bodies(self) -> None:
        source = "def f(x):\n    if x:\n        a = 1\n        b = 2\n        c = 3\n        return a + b + c\n    return 0\n"

        assert mutate(source, GuardClauseMutator()) == []


class TestNoiseSuppression:
    @pytest.mark.parametrize(
        "source",
        [
            pytest.param('def f():\n    """Limit is x > 10."""\n    return 1\n', id="docstring"),
            pytest.param("def f(x):\n    logger.info('n=%s', x + 1)\n", id="logger-call"),
            pytest.param("import warnings\ndef f(x):\n    warnings.warn(str(x + 1))\n", id="warnings-warn"),
            pytest.param("def f(x):\n    assert x > 0\n", id="assert"),
            pytest.param("def f(x):\n    return f'{x + 1}'\n", id="f-string"),
            pytest.param("def f(x):\n    return x > 10  # pragma: no mutate\n", id="pragma-line"),
            pytest.param("def f(x):  # pragma: no mutate\n    return x > 10\n", id="pragma-def"),
            pytest.param("@no_mutate\ndef f(x):\n    return x > 10\n", id="no-mutate-decorator"),
            pytest.param("@overload\ndef f(x=True):\n    return x > 1\n", id="overload"),
            pytest.param(
                "class A:\n    def __repr__(self):\n        return str(self.x + 1)\n", id="repr"
            ),
            pytest.param("if TYPE_CHECKING:\n    LIMIT = 1 + 2\n", id="type-checking"),
            pytest.param("if __name__ == '__main__':\n    print(1 + 2)\n", id="main-guard"),
        ],
    )
    def test_generates_no_mutants(self, source: str) -> None:
        assert mutate(source) == []

    def test_pragma_inside_string_literal_is_not_a_pragma(self) -> None:
        source = "def f(x):\n    return x > 10, '# pragma: no mutate'\n"

        assert mutate(source, NumericBoundaryMutator())


class TestGeneration:
    SOURCE = """\
    def price(units, unit_price, *, member=False):
        if units < 0:
            raise ValueError("units")
        total = (
            units
            * unit_price
        )
        if member and total > 100:
            return total - 10
        return total
    """

    def test_every_mutant_compiles_and_keeps_line_count(self) -> None:
        source = textwrap.dedent(self.SOURCE)
        mutants = mutate(self.SOURCE)

        assert len(mutants) > 10
        for mutant in mutants:
            compile(mutant.mutated_source, mutant.file_path, "exec")
            assert mutant.mutated_source.count("\n") == source.count("\n")
            assert mutant.mutated_source != source

    def test_multiline_expression_is_padded_in_place(self) -> None:
        mutants = mutate(self.SOURCE, ArithmeticOperatorMutator())
        multiplication = next(m for m in mutants if "`*` with `/`" in m.description)

        assert multiplication.lineno == 5
        assert multiplication.end_lineno == 6
        assert "return total - 10" in multiplication.mutated_source.splitlines()[8]

    def test_mutants_are_unique(self) -> None:
        mutants = mutate(self.SOURCE)

        assert len({m.mutated_source for m in mutants}) == len(mutants)
        assert len({m.id for m in mutants}) == len(mutants)

    def test_ids_are_stable_and_well_formed(self) -> None:
        first = [m.id for m in mutate(self.SOURCE)]
        second = [m.id for m in mutate(self.SOURCE)]

        assert first == second
        assert all(re.fullmatch(r"[A-Za-z]+-L\d+-[0-9a-f]{8}", mutant_id) for mutant_id in first)

    def test_diff_shows_the_single_change(self) -> None:
        mutant = next(m for m in mutate(self.SOURCE) if "Bypass guard" in m.description and m.lineno == 2)

        assert "-    if units < 0:" in mutant.diff
        assert "+    if False:" in mutant.diff
        assert mutant.diff.startswith("--- a/pkg/mod.py")

    def test_changed_lines_restricts_output(self) -> None:
        mutants = generate_mutants(
            textwrap.dedent(self.SOURCE),
            file_path="pkg/mod.py",
            module_name="pkg.mod",
            changed_lines=frozenset({8}),
        )

        assert mutants
        assert {m.lineno for m in mutants} == {8}

    def test_mutants_are_sorted_by_position(self) -> None:
        linenos = [m.lineno for m in mutate(self.SOURCE)]

        assert linenos == sorted(linenos)

    def test_invalid_source_raises_syntax_error(self) -> None:
        with pytest.raises(SyntaxError):
            mutate("def broken(:\n")

    def test_mutant_round_trips_through_dict(self) -> None:
        mutant = mutate(self.SOURCE)[0]

        assert Mutant.from_dict(mutant.to_dict()) == mutant


class TestRegistry:
    def test_all_six_mutators_by_default(self) -> None:
        assert [m.name for m in get_mutators()] == [
            "NumericBoundary",
            "ComparisonOperator",
            "BooleanLogic",
            "DefaultBoolean",
            "ArithmeticOperator",
            "GuardClause",
        ]

    def test_selects_by_name(self) -> None:
        assert [m.name for m in get_mutators(["GuardClause"])] == ["GuardClause"]

    def test_unknown_name_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown mutator"):
            get_mutators(["Nope"])
