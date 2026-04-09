from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def _to_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _to_namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_to_namespace(item) for item in value]
    return value


def evaluate_expression(expression: str, context: dict[str, Any]) -> bool:
    normalized = (
        expression.replace("&&", " and ")
        .replace("||", " or ")
        .replace("null", "None")
        .replace("true", "True")
        .replace("false", "False")
    )
    locals_dict = {key: _to_namespace(value) for key, value in context.items()}
    return bool(eval(normalized, {"__builtins__": {}}, locals_dict))
