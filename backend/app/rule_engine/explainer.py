from __future__ import annotations

from typing import Any

from backend.app.schemas.recommendation import (
    RankedApproach,
    RecommendationResponse,
    SecondaryOption,
)


def _confidence(ranked: list[dict[str, Any]], manual_review_flags: list[str]) -> str:
    if not ranked:
        return "LOW"

    leader = ranked[0]["score"]
    runner_up = ranked[1]["score"] if len(ranked) > 1 else 0
    gap = leader - runner_up

    if gap >= 20 and not manual_review_flags:
        return "HIGH"
    if gap >= 10:
        return "MEDIUM"
    return "LOW"


def build_response(
    request_id: str,
    rules_version: str,
    candidates: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    companion_tools: list[str],
    manual_review_flags: list[str],
) -> RecommendationResponse:
    if not candidates:
        return RecommendationResponse(
            request_id=request_id,
            recommended_approach="MANUAL_REVIEW",
            confidence="LOW",
            score=0,
            why=["No eligible migration approach matched the current request."],
            companion_tools=companion_tools,
            prerequisites=[],
            risk_flags=["Manual intervention is required before recommendation."],
            secondary_option=None,
            rejected_approaches=[
                RankedApproach(
                    approach=item["approach"],
                    score=item.get("score", 0),
                    reason=item["reason"],
                )
                for item in rejected
            ],
            manual_review_flags=manual_review_flags
            or ["Review eligibility rules and source/target compatibility."],
            rules_version=rules_version,
        )

    winner = candidates[0]
    secondary_option = None
    if len(candidates) > 1:
        runner_up = candidates[1]
        secondary_option = SecondaryOption(
            approach=runner_up["method"],
            score=runner_up["score"],
            why=runner_up["why"][:3] or ["Secondary approach remained eligible."],
        )

    risk_flags = winner["negative_reasons"][:]
    if winner["eligibility_status"] == "CONDITIONALLY_ELIGIBLE":
        risk_flags.extend(winner["eligibility_reasons"])

    return RecommendationResponse(
        request_id=request_id,
        recommended_approach=winner["method"],
        confidence=_confidence(candidates, manual_review_flags),
        score=winner["score"],
        why=winner["why"][:5] or ["Recommendation selected by rule evaluation."],
        companion_tools=companion_tools,
        prerequisites=winner["prerequisites"],
        risk_flags=risk_flags,
        secondary_option=secondary_option,
        rejected_approaches=[
            RankedApproach(
                approach=item["approach"],
                score=item.get("score", 0),
                reason=item["reason"],
            )
            for item in rejected
        ],
        manual_review_flags=manual_review_flags,
        rules_version=rules_version,
    )
