"""Deterministic question generator API shared with Sage runners."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from numbers import Integral
from typing import Any

_registered_generator: Callable[[Context], None] | None = None


def generator(function: Callable[[Context], None]) -> Callable[[Context], None]:
    global _registered_generator
    if _registered_generator is not None:
        raise ValueError("a question may define only one generator")
    _registered_generator = function
    return function


def take_generator() -> Callable[[Context], None]:
    global _registered_generator
    result = _registered_generator
    _registered_generator = None
    if result is None:
        raise ValueError("generate.sage did not register a generator")
    return result


class Rejected(Exception):
    def __init__(self, name: str, detail: str | None = None) -> None:
        super().__init__(detail or name)
        self.name = name
        self.detail = detail


class CheckFailed(Exception):
    def __init__(self, evidence: dict[str, Any]) -> None:
        super().__init__(evidence["id"])
        self.evidence = evidence


class RandomContext:
    def __init__(self, seed: int) -> None:
        import numpy

        self._generator = numpy.random.Generator(numpy.random.PCG64(seed))

    def integer(self, low: int, high: int) -> int:
        return int(self._generator.integers(low, high, endpoint=True))

    def choice(self, values):
        return values[int(self._generator.integers(0, len(values)))]

    def rational(self, numerators, denominators):
        from sage.all import QQ

        return QQ(self.choice(numerators)) / QQ(self.choice(denominators))


def seed_for(root_seed: str, variant: str, question_id: str, attempt: int) -> int:
    fields = ("mathpub-mvp", root_seed, variant, question_id, str(attempt))
    digest = hashlib.sha256("\0".join(fields).encode()).digest()
    return int.from_bytes(digest, "big")


def serialize(value: Any) -> Any:
    if isinstance(value, (bool, str)) or value is None:
        return value
    if isinstance(value, Integral):
        return {"type": "integer", "value": int(value)}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize(value[key]) for key in sorted(value)}
    try:
        if value in (math.inf, -math.inf) or math.isnan(float(value)):
            raise ValueError("non-finite mathematical value")
    except (TypeError, ValueError):
        pass
    try:
        numerator = value.numerator()
        denominator = value.denominator()
        if denominator != 1:
            return {
                "type": "rational",
                "numerator": int(numerator),
                "denominator": int(denominator),
            }
        if str(value) == str(numerator):
            return {"type": "integer", "value": int(numerator)}
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        from sage.all import latex

        return {"type": "expression", "sage": str(value), "tex": str(latex(value))}
    except ImportError:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite mathematical value") from None
        return {"type": "real", "decimal": repr(number)}


@dataclass
class Context:
    random: RandomContext

    def __post_init__(self) -> None:
        self.parameters: dict[str, Any] = {}
        self.derived_values: dict[str, Any] = {}
        self.display_values: dict[str, dict[str, Any]] = {}
        self.checks: list[dict[str, Any]] = []

    def _put(self, target: dict[str, Any], name: str, value: Any) -> None:
        if name in target:
            raise ValueError(f"duplicate value: {name}")
        target[name] = value

    def parameter(self, name: str, value: Any) -> None:
        self._put(self.parameters, name, value)

    def derived(self, name: str, value: Any) -> None:
        self._put(self.derived_values, name, value)

    def require(self, name: str, condition: Any, detail: str | None = None) -> None:
        if not bool(condition):
            raise Rejected(name, detail)

    def _record(self, name: str, passed: bool, evidence: str, assumptions, detail=None) -> None:
        record = {
            "id": name,
            "status": "passed" if passed else "failed",
            "evidence": evidence,
            "backend": "sagemath",
            "assumptions": list(assumptions),
        }
        if detail is not None:
            record["detail"] = str(detail)
        self.checks.append(record)
        if not passed:
            raise CheckFailed(record)

    def check_equal(self, name: str, lhs: Any, rhs: Any, assumptions=()) -> None:
        try:
            difference = (lhs - rhs).simplify_full()
            passed = bool(difference == 0)
        except AttributeError:
            passed = bool(lhs == rhs)
        self._record(name, passed, "symbolic-check", assumptions, f"{lhs} == {rhs}")

    def check_close(
        self, name: str, lhs: Any, rhs: Any, atol: float, rtol: float = 0, assumptions=()
    ) -> None:
        left, right = float(lhs), float(rhs)
        residual = abs(left - right)
        passed = residual <= atol + rtol * abs(right)
        self._record(name, passed, "numerical-residual", assumptions, f"residual={residual}")

    def check_true(self, name: str, condition: Any, detail=None, assumptions=()) -> None:
        self._record(name, bool(condition), "exact-computation", assumptions, detail)

    def _display(self, name: str, kind: str, tex: str, *, trusted: bool = False) -> None:
        self._put(self.display_values, name, {"kind": kind, "tex": tex, "trusted": trusted})

    def display_text(self, name: str, value: Any) -> None:
        self._display(name, "text", str(value))

    def display_integer(self, name: str, value: Any) -> None:
        self._display(name, "integer", str(int(value)))

    def display_decimal(
        self, name: str, value: Any, places: int, trailing_zeros=True, unit=None
    ) -> None:
        rendered = f"{float(value):.{places}f}"
        if not trailing_zeros:
            rendered = rendered.rstrip("0").rstrip(".")
        if unit:
            rendered += rf"\,\unit{{{unit}}}"
        self._display(name, "decimal", rendered, trusted=bool(unit))

    def display_significant(self, name: str, value: Any, digits: int, unit=None) -> None:
        rendered = f"{float(value):.{digits}g}"
        if unit:
            rendered += rf"\,\unit{{{unit}}}"
        self._display(name, "significant", rendered, trusted=bool(unit))

    def display_math(self, name: str, value: Any) -> None:
        from sage.all import latex

        self._display(name, "math", str(latex(value)), trusted=True)

    def display_quantity(self, name: str, value: Any, unit: str) -> None:
        self._display(name, "quantity", rf"{value}\,\unit{{{unit}}}", trusted=True)

    def display_tex(self, name: str, trusted_tex: str) -> None:
        self._display(name, "tex", trusted_tex, trusted=True)

    class _DisplayProxy:
        def __init__(self, context: Context) -> None:
            self._context = context

        def __getattr__(self, name):
            return getattr(self._context, f"display_{name}")

    @property
    def display(self):
        return self._DisplayProxy(self)

    def instance(self) -> dict[str, Any]:
        return {
            "parameters": serialize(self.parameters),
            "derived": serialize(self.derived_values),
            "display": self.display_values,
            "checks": self.checks,
        }
