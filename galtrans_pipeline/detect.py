"""引擎检测:特征规则加权命中(需求 FR-A1,置信度排序)。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .profile import EngineProfile


def _glob_count(game_dir: Path, pattern: str) -> int:
    try:
        return sum(1 for _ in game_dir.glob(pattern) if _.is_file())
    except (OSError, ValueError):
        return 0


def detect_engine(
    game_dir: Path, profiles: dict[str, EngineProfile]
) -> list[dict[str, Any]]:
    """返回按得分排序的检测结果 [{profile, score, capability, matched}]。"""
    results: list[dict[str, Any]] = []
    for profile in profiles.values():
        spec = profile.detect
        matched: list[str] = []
        score = 0
        for pattern in spec.get("archives", []) or []:
            count = _glob_count(game_dir, pattern)
            if count:
                score += 2
                matched.append(f"{pattern}×{count}")
        for file_name in spec.get("files", []) or []:
            # glob 语义:字面名与旧版直查等价,同时支持 "*/xxx.assets" 一层通配
            count = _glob_count(game_dir, file_name)
            if count:
                score += 2
                matched.append(file_name)
        for hint in spec.get("hints", []) or []:
            pattern = hint.get("pattern", "") if isinstance(hint, dict) else hint
            if pattern and _glob_count(game_dir, pattern):
                score += 1
                matched.append(f"hint:{pattern}")
        min_score = int(spec.get("min_score", 1))
        if score >= min_score:
            results.append(
                {
                    "profile": profile.name,
                    "score": score,
                    "capability": profile.capability,
                    "matched": matched,
                }
            )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results
