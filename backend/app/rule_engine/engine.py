from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.app.rule_engine.eligibility import evaluate_eligibility
from backend.app.rule_engine.explainer import build_response
from backend.app.rule_engine.facts import derive_facts
from backend.app.rule_engine.loader import load_rules
from backend.app.rule_engine.normalizer import normalize_request
from backend.app.rule_engine.ranking import rank_candidates
from backend.app.rule_engine.scoring import score_method
from backend.app.schemas.migration import MigrationCreate
from backend.app.schemas.recommendation import RecommendationResponse


class RecommendationEngine:
    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._config = load_rules(config_path)
        self._cache: dict[str, RecommendationResponse] = {}

    @property
    def rules_version(self) -> str:
        return str(self._config["rules_version"])

    def recommend(self, request: MigrationCreate) -> RecommendationResponse:
        payload = normalize_request(request)
        cache_key = json.dumps(payload, sort_keys=True, default=str)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return deepcopy(cached)

        facts = derive_facts(payload)
        context = {**payload, "facts": facts}

        candidates: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for method_rule in self._config["methods"]:
            eligibility = evaluate_eligibility(method_rule, context)
            if eligibility["status"] == "NOT_ELIGIBLE":
                rejected.append(
                    {
                        "approach": method_rule["name"],
                        "score": 0,
                        "reason": "; ".join(eligibility["reasons"]),
                    }
                )
                continue

            score = score_method(method_rule, context)
            why = []
            why.extend(eligibility["reasons"])
            why.extend(score["positive_reasons"])
            if not score["positive_reasons"]:
                why.append("Base score and eligibility rules favored this method.")

            candidates.append(
                {
                    "method": method_rule["name"],
                    "score": score["score"],
                    "eligibility_status": eligibility["status"],
                    "eligibility_reasons": eligibility["reasons"],
                    "positive_reasons": score["positive_reasons"],
                    "negative_reasons": score["negative_reasons"],
                    "prerequisites": score["prerequisites"],
                    "why": why,
                }
            )

        ranked = rank_candidates(candidates)
        companion_tools = self._derive_companion_tools(context)
        manual_review_flags = self._derive_manual_review_flags(payload, facts, ranked)

        response = build_response(
            request_id=request.request_id,
            rules_version=self.rules_version,
            candidates=ranked,
            rejected=rejected,
            companion_tools=companion_tools,
            manual_review_flags=manual_review_flags,
        )
        self._cache[cache_key] = response
        return deepcopy(response)

    def _derive_companion_tools(self, context: dict[str, Any]) -> list[str]:
        tools: list[str] = []
        for tool_rule in self._config.get("companion_tools", []):
            from backend.app.rule_engine.evaluator import evaluate_expression

            if evaluate_expression(tool_rule["when"], context):
                tools.append(tool_rule["name"])

        tools.extend(["Assessment Checklist", "Compatibility Review"])
        return list(dict.fromkeys(tools))

    def _derive_manual_review_flags(
        self,
        payload: dict[str, Any],
        facts: dict[str, Any],
        ranked: list[dict[str, Any]],
    ) -> list[str]:
        flags: list[str] = []

        if payload["features"].get("need_non_cdb_to_pdb_conversion"):
            flags.append("Validate Non-CDB to PDB conversion steps before production use.")
        if payload["features"].get("need_cross_platform_move"):
            flags.append("Confirm cross-platform migration compatibility and fallback path.")
        if not ranked:
            flags.append("No eligible method matched; manual review is required.")
        elif ranked[0]["eligibility_status"] == "CONDITIONALLY_ELIGIBLE":
            flags.append("Top recommendation is only conditionally eligible.")
        if facts["is_huge_db"] and facts["is_low_downtime"]:
            flags.append("Large database with tight downtime requires rehearsal and capacity review.")

        return flags
