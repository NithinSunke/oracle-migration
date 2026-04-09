from __future__ import annotations

from typing import Any

from backend.app.rule_engine.evaluator import evaluate_expression


def _collect_matches(
    rules: list[dict[str, Any]],
    context: dict[str, Any],
) -> tuple[int, list[str]]:
    points = 0
    reasons: list[str] = []

    for rule in rules:
        if evaluate_expression(rule["when"], context):
            points += int(rule["points"])
            reasons.append(rule["reason"])

    return points, reasons


def score_method(method_rule: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    base_score = int(method_rule["base_score"])
    positive_points, positive_reasons = _collect_matches(
        method_rule.get("positive_weights", []),
        context,
    )
    negative_points, negative_reasons = _collect_matches(
        method_rule.get("negative_weights", []),
        context,
    )

    raw_score = base_score + positive_points - negative_points
    final_score = max(0, min(100, raw_score))

    return {
        "score": final_score,
        "positive_reasons": positive_reasons,
        "negative_reasons": negative_reasons,
        "prerequisites": method_rule.get("prerequisites", []),
    }
