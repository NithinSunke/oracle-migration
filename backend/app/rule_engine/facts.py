from __future__ import annotations

import re
from typing import Any


def _extract_major_version(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"(\d+)", value)
    if match is None:
        return None
    return int(match.group(1))


def derive_facts(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload["source"]
    target = payload["target"]
    scope = payload["scope"]
    business = payload["business"]
    features = payload["features"]

    database_size_gb = source.get("database_size_gb") or 0
    downtime_window_minutes = business.get("downtime_window_minutes") or 0
    source_major = _extract_major_version(source.get("oracle_version"))
    target_major = _extract_major_version(target.get("oracle_version"))
    version_gap_major = (
        (target_major - source_major)
        if source_major is not None and target_major is not None
        else 0
    )
    same_platform = source.get("platform") == target.get("platform")
    same_endian = target.get("same_endian", True)

    return {
        "source_major_version": source_major,
        "target_major_version": target_major,
        "version_gap_major": version_gap_major,
        "is_large_db": database_size_gb >= 5000,
        "is_huge_db": database_size_gb >= 10000,
        "is_medium_db": 500 <= database_size_gb < 5000,
        "is_small_db": database_size_gb < 500,
        "is_low_downtime": downtime_window_minutes <= 30,
        "is_ultra_low_downtime": downtime_window_minutes <= 5,
        "same_version_family": source_major == target_major,
        "same_platform": same_platform,
        "same_endian": same_endian,
        "cross_platform": not same_platform,
        "cross_platform_same_endian": (not same_platform) and same_endian,
        "upgrade_gap_present": version_gap_major > 0,
        "major_upgrade_gap": version_gap_major >= 2,
        "tde_enabled": bool(source.get("tde_enabled")),
        "tde_mismatch": bool(source.get("tde_enabled")) and not bool(target.get("tde_enabled")),
        "full_database_move": scope.get("migration_scope") == "FULL_DATABASE"
        and not scope.get("subset_only", False),
        "logical_transformation_needed": any(
            [
                scope.get("need_schema_remap", False),
                scope.get("need_tablespace_remap", False),
                scope.get("need_reorg", False),
                scope.get("subset_only", False),
            ]
        ),
        "physical_move_preferred": scope.get("migration_scope") == "FULL_DATABASE"
        and not any(
            [
                scope.get("need_schema_remap", False),
                scope.get("need_tablespace_remap", False),
                scope.get("need_reorg", False),
            ]
        ),
        "upgrade_in_scope": features.get("need_version_upgrade", False),
        "dg_candidate": scope.get("migration_scope") == "FULL_DATABASE"
        and not any(
            [
                scope.get("need_schema_remap", False),
                scope.get("need_reorg", False),
                scope.get("subset_only", False),
            ]
        ),
        "gg_candidate": features.get("goldengate_license_available", False),
        "zdm_candidate": target.get("target_is_exadata", False)
        and features.get("zdm_supported_target", False),
    }
