from __future__ import annotations

from typing import Any


def derive_facts(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload["source"]
    target = payload["target"]
    scope = payload["scope"]
    business = payload["business"]
    features = payload["features"]

    database_size_gb = source.get("database_size_gb") or 0
    downtime_window_minutes = business.get("downtime_window_minutes") or 0

    return {
        "is_large_db": database_size_gb >= 5000,
        "is_huge_db": database_size_gb >= 10000,
        "is_low_downtime": downtime_window_minutes <= 30,
        "is_ultra_low_downtime": downtime_window_minutes <= 5,
        "same_version_family": source.get("oracle_version") == target.get("oracle_version"),
        "same_platform": source.get("platform") == target.get("platform"),
        "same_endian": target.get("same_endian", True),
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
