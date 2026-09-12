"""术语向导库(FR-D7):封装上游 GenDic 与草稿/正式字典文件。

数据流(全部上游原生格式,零 config 修改):
  gt_input/*.json → GenDic(投票去重)→ <project>/项目GPT字典-生成.txt(草稿)
  用户在 GUI 确认/删改条目 → confirm 写 <project>/项目GPT字典.txt(正式)
  两个文件都在上游默认 config 的 gpt.dict 引用链里,下次翻译自动带人设。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .errors import PipelineError

DRAFT_FILE = "项目GPT字典-生成.txt"
CONFIRMED_FILE = "项目GPT字典.txt"


def _import_upstream():
    try:
        from GalTransl.Service import JobSpec, run_job
    except ImportError:
        repo_root = str(Path(__file__).resolve().parent.parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from GalTransl.Service import JobSpec, run_job
    return JobSpec, run_job


def draft_path(project) -> Path:
    """GenDic 草稿:getProjectDir() 即 work/gt_project。"""
    return project.subdir("work/gt_project") / DRAFT_FILE


def confirmed_path(project) -> Path:
    """正式 GPT 字典:上游 config 的 (project_dir)项目GPT字典.txt。"""
    return project.subdir("work/gt_project") / CONFIRMED_FILE


def _parse_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    entries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        src, dst = parts[0].strip(), parts[1].strip()
        note = parts[2].strip() if len(parts) > 2 else ""
        if not src or not dst or src == "NULL":
            continue
        entries.append({"src": src, "dst": dst, "note": note})
    return entries


def read_draft(project) -> list[dict[str, str]]:
    return _parse_tsv(draft_path(project))


def read_confirmed(project) -> list[dict[str, str]]:
    return _parse_tsv(confirmed_path(project))


def confirm_entries(project, entries: list[dict[str, str]]) -> int:
    """把用户确认的词条写入正式 GPT 字典(TSV,上游 CGptDict 原生格式)。"""
    lines = []
    seen = set()
    for entry in entries:
        src = str(entry.get("src", "")).strip()
        dst = str(entry.get("dst", "")).strip()
        note = str(entry.get("note", "")).strip()
        if not src or not dst or (src, dst, note) in seen:
            continue
        seen.add((src, dst, note))
        lines.append(f"{src}\t{dst}\t{note}" if note else f"{src}\t{dst}")
    if not lines:
        raise PipelineError(
            "E-CACHE-EDIT-INVALID", "没有可确认的词条(至少需要 原文+译文)。"
        )
    path = confirmed_path(project)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def run_gendic(project) -> int:
    """跑上游 GenDic(translator 模式),返回草稿词条数。"""
    JobSpec, run_job = _import_upstream()
    gt_dir = project.subdir("work/gt_project")
    if not (gt_dir / "config.yaml").exists():
        raise PipelineError(
            "E-CACHE-EDIT-INVALID",
            f"缺少 {gt_dir / 'config.yaml'},请先在补丁工作台跑过一次流水线。",
        )
    spec = JobSpec(project_dir=str(gt_dir), translator="GenDic")
    state = run_job(spec)
    if getattr(state, "error", None):
        raise PipelineError("E-CACHE-EDIT-INVALID", f"术语提取失败: {state.error}")
    return len(read_draft(project))
