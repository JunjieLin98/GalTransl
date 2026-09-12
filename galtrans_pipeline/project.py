"""PatchProject:工程文件与 workspace 目录规范(架构 §3.4)。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .errors import PipelineError

SCHEMA_VERSION = 1

WORKSPACE_DIRS = (
    "work/unpacked",
    "work/extracted",
    "work/translated",
    "work/injected",
    "work/package",
    "cache",
    "backup",
    "dist",
    "logs",
    "dict",
)

STEPS = ("DETECT", "UNPACK", "EXTRACT", "TRANSLATE", "INJECT", "PACKAGE")


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PatchProject:
    """工程:游戏路径/profile/覆盖项/步骤快照;workspace 产物一律相对 project_dir。"""

    def __init__(self, project_dir: Path, data: dict[str, Any]) -> None:
        self.project_dir = project_dir
        self.data = data

    # -- 创建/加载 -------------------------------------------------------
    @classmethod
    def create(
        cls,
        project_dir: Path,
        game_dir: Path,
        profile_name: str,
        overrides: dict[str, Any] | None = None,
    ) -> "PatchProject":
        project_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": SCHEMA_VERSION,
            "game_dir": str(game_dir.resolve()),
            "profile": profile_name,
            "created_at": _utcnow(),
            "overrides": overrides or {},
            "steps": {},
        }
        project = cls(project_dir, data)
        project.ensure_dirs()
        project.save()
        return project

    @classmethod
    def load(cls, project_dir: Path) -> "PatchProject":
        path = project_dir / "project.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"工程文件不存在: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        project = cls(project_dir, data)
        project.ensure_dirs()
        project.check_game_dir()
        return project

    # -- 路径与目录 -------------------------------------------------------
    def check_game_dir(self) -> Path:
        game_dir = Path(str(self.data.get("game_dir", "")))
        if not game_dir.is_dir():
            raise PipelineError(
                "E-PROJECT-GAME-MISSING", f"游戏目录不存在: {game_dir}"
            )
        return game_dir

    @property
    def game_dir(self) -> Path:
        return Path(str(self.data["game_dir"]))

    @property
    def profile_name(self) -> str:
        return str(self.data.get("profile", ""))

    @property
    def overrides(self) -> dict[str, Any]:
        return self.data.get("overrides", {}) or {}

    def subdir(self, relative: str) -> Path:
        path = self.project_dir / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_dirs(self) -> None:
        for relative in WORKSPACE_DIRS:
            self.subdir(relative)

    # -- 步骤快照(幂等重跑的依据) ----------------------------------------
    def mark_step(self, step: str, status: str, note: str = "") -> None:
        steps = self.data.setdefault("steps", {})
        steps[step] = {"status": status, "finished_at": _utcnow(), "note": note}
        self.save()

    def step_status(self, step: str) -> str:
        entry = (self.data.get("steps", {}) or {}).get(step, {})
        return str(entry.get("status", ""))

    def reset_step(self, step: str) -> None:
        """restore 等运维操作后,把该步及之后步骤快照重置为未执行(架构 §3.3)。"""
        index = STEPS.index(step) if step in STEPS else 0
        for name in STEPS[index:]:
            (self.data.setdefault("steps", {})).pop(name, None)
        self.save()

    # -- 持久化 -----------------------------------------------------------
    def save(self) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        path = self.project_dir / "project.yaml"
        path.write_text(
            yaml.safe_dump(self.data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
