from __future__ import annotations


def rank_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(
        candidates,
        key=lambda item: (item["score"], item["method"]),
        reverse=True,
    )
