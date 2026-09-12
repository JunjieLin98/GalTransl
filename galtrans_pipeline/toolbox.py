"""Toolbox:外部工具的定位/版本校验(E-EXTRACT-TOOL-MISSING 指引路径)。

查找顺序:GALTRANS_TOOLS_DIR 环境变量 → 仓库 tools/bin → PATH。
SHA-256 校验值已知的工具(见 docs/architecture.md §6)强制校验。
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import PipelineError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ToolSpec:
    name: str
    exe: str
    sha256: str | None = None  # 已知官方构建的锁定校验值;None 表示本地构建/未核实


# 版本锁定基准(2026-09-12 实测,来源见 docs/research/toolchain-verification.md)
TOOL_SPECS: dict[str, ToolSpec] = {
    "msg-tool": ToolSpec(
        "msg-tool",
        "msg_tool.exe",
        sha256="62fe396780468200cb50f287fe213e697a903f0a85a91153fa3692598ae8ab5d",
    ),
    "xp3pack": ToolSpec(
        "xp3pack",
        "Xp3Pack.exe",
        sha256="c6f4a6f4d74cd293777cd321cefdeae88ff4dd344c4f2a0bcbc88840aa717cb6",
    ),
    "xp3brute": ToolSpec("xp3brute", "xp3brute.exe", sha256=None),
    "sextractor": ToolSpec("sextractor", "run.py", sha256=None),
    # 本仓库自有 Python 工具(M5);由 _run_tool 以当前解释器驱动,无需校验和
    "unity_tool": ToolSpec("unity_tool", "unity_tool.py", sha256=None),
}


class ToolBox:
    def __init__(self, tools_dir: Path | None = None) -> None:
        self.tools_dir = self._resolve_tools_dir(tools_dir)

    @staticmethod
    def _resolve_tools_dir(explicit: Path | None) -> Path | None:
        if explicit is not None:
            return explicit
        env_dir = os.environ.get("GALTRANS_TOOLS_DIR")
        if env_dir:
            return Path(env_dir)
        # 从当前目录向上查找仓库的 tools/bin
        probe = Path.cwd().resolve()
        for candidate in [probe, *probe.parents]:
            tools_bin = candidate / "tools" / "bin"
            if tools_bin.is_dir():
                return tools_bin
        return None

    def locate(self, tool_name: str) -> Path:
        spec = TOOL_SPECS.get(tool_name)
        if spec is None:
            raise PipelineError("E-EXTRACT-TOOL-MISSING", f"未知工具: {tool_name}")
        candidates: list[Path] = []
        if self.tools_dir is not None:
            candidates.append(self.tools_dir / spec.exe)
        path_env = shutil.which(spec.exe)
        if path_env:
            candidates.append(Path(path_env))
        for candidate in candidates:
            if candidate.is_file():
                self._verify(spec, candidate)
                return candidate
        raise PipelineError(
            "E-EXTRACT-TOOL-MISSING",
            f"找不到 {tool_name}({spec.exe});搜索目录: {self.tools_dir or '未找到 tools/bin'}",
        )

    @staticmethod
    def _verify(spec: ToolSpec, path: Path) -> None:
        if spec.sha256 is None:
            return
        actual = _sha256(path)
        if actual != spec.sha256:
            raise PipelineError(
                "E-EXTRACT-TOOL-MISSING",
                f"{spec.exe} SHA-256 不匹配(期望 {spec.sha256[:16]}…,实际 {actual[:16]}…);"
                "请使用托管表锁定的版本",
            )
