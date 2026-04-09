from __future__ import annotations

from typing import Any

from backend.app.rule_engine.evaluator import evaluate_expression


def evaluate_eligibility(
    method_rule: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    matched: list[dict[str, Any]] = []

    for rule in method_rule.get("eligibility", []):
        if evaluate_expression(rule["when"], context):
            matched.append(rule)

    if not matched:
        return {
            "status": "NOT_ELIGIBLE",
            "reasons": ["No eligibility rule matched for this migration request."],
        }

    statuses = [rule["status"] for rule in matched]
    reasons = [rule["reason"] for rule in matched]

    if "NOT_ELIGIBLE" in statuses:
        return {"status": "NOT_ELIGIBLE", "reasons": reasons}
    if "CONDITIONALLY_ELIGIBLE" in statuses:
        return {"status": "CONDITIONALLY_ELIGIBLE", "reasons": reasons}
    return {"status": "ELIGIBLE", "reasons": reasons}
