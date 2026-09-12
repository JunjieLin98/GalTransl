"""缓存编辑库(M3 双语对照编辑器的后端核心)。

与上游 GalTransl/Cache.py 的关系:
- 读:只读快照 JSON(数组,每条含 index/name/pre_src/post_src/pre_dst/proofread_dst)。
  若存在 .append.jsonl(翻译中断未合并),读侧不做合并——统计区标 has_append,
  由用户先执行 compact(调上游 compact_cache_append_logs)再编辑,
  避免"编辑快照被 append 条目覆盖"的冲突。
- 写:tmp + os.replace 原子替换;定位条目用 (index, pre_src) 双校验。
  locked=True 要求 pre_dst 非空(锁定=人工终稿,不允许锁空译文)。
- 锁定语义由上游 Cache.py 受控改造实现:locked 条目在后续翻译/校对中强制命中。

增量重翻无需额外指纹:上游缓存键含前后句+当前句上下文(pre_src 三联键),
原文变化 → 键不匹配 → 自然进入重翻;locked 是唯一需要新增的语义。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import orjson

from .errors import PipelineError

APPEND_SUFFIX = ".append.jsonl"
PROBLEM_STATUS_FILE = "problem_status.json"
_VALID_PROBLEM_STATUS = ("", "confirmed", "ignored")


def _problem_status_path(project) -> Path:
    """问题状态表(独立文件,零上游侵入):{缓存文件名: {index: confirmed|ignored}}。"""
    return project.subdir("work/gt_project") / PROBLEM_STATUS_FILE


def load_problem_status(project) -> dict[str, dict[str, str]]:
    path = _problem_status_path(project)
    if not path.exists():
        return {}
    try:
        data = orjson.loads(path.read_bytes())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_problem_status(project, table: dict[str, dict[str, str]]) -> None:
    path = _problem_status_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(orjson.dumps(table, option=orjson.OPT_INDENT_2))
    os.replace(tmp, path)


def set_problem_status(project, name: str, index: int, status: str) -> dict[str, Any]:
    """设置问题状态:confirmed(确认有问题,待处理)/ ignored(忽略)/ ""(清除)。"""
    if status not in _VALID_PROBLEM_STATUS:
        raise PipelineError(
            "E-CACHE-EDIT-INVALID",
            f"非法问题状态: {status!r}(可用: confirmed / ignored / 空)",
        )
    table = load_problem_status(project)
    file_table = table.get(name) or {}
    if status:
        file_table[str(index)] = status
    else:
        file_table.pop(str(index), None)
    if file_table:
        table[name] = file_table
    else:
        table.pop(name, None)
    save_problem_status(project, table)
    return {"file": name, "index": index, "status": status}


def cache_dir(project) -> Path:
    """工程的翻译缓存目录(work/gt_project/transl_cache)。"""
    gt_dir = project.subdir("work/gt_project")
    return gt_dir / "transl_cache"


def _cache_file(project, name: str) -> Path:
    if not name or "/" in name or "\\" in name or ".." in name:
        raise PipelineError("E-CACHE-EDIT-INVALID", f"非法缓存文件名: {name!r}")
    path = cache_dir(project) / name
    if not path.suffix:
        path = path.with_name(path.name + ".json")
    if path.suffix != ".json" or not path.is_file():
        raise PipelineError(
            "E-CACHE-EDIT-INVALID", f"缓存文件不存在: {name}"
        )
    return path


def _load_snapshot(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if not raw:
        return []
    try:
        data = orjson.loads(raw)
    except Exception as error:
        raise PipelineError(
            "E-CACHE-EDIT-INVALID", f"缓存 JSON 解析失败({path.name}): {error}"
        )
    if not isinstance(data, list):
        raise PipelineError(
            "E-CACHE-EDIT-INVALID", f"缓存格式异常(非数组): {path.name}"
        )
    return data


def _save_snapshot(path: Path, data: list[dict[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
    os.replace(tmp, path)


def _append_path(path: Path) -> Path:
    return path.with_name(path.name + APPEND_SUFFIX)


def _entry_stats(entries: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "entries": len(entries),
        "locked": sum(1 for e in entries if e.get("locked")),
        "problems": sum(
            1
            for e in entries
            if isinstance(e.get("problem"), str) and e["problem"].strip()
        ),
        "untranslated": sum(1 for e in entries if not e.get("pre_dst")),
    }


def list_cache_files(project) -> list[dict[str, Any]]:
    """列出工程全部缓存文件及其统计。"""
    directory = cache_dir(project)
    result = []
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(APPEND_SUFFIX) or path.name.endswith(".tmp"):
            continue
        entries = _load_snapshot(path)
        stats = _entry_stats(entries)
        stats["name"] = path.name
        stats["has_append"] = _append_path(path).exists()
        result.append(stats)
    return result


def load_entries(
    project,
    name: str,
    query: str = "",
    locked: bool | None = None,
    problem: bool | None = None,
    untranslated: bool | None = None,
    page: int = 1,
    page_size: int = 200,
) -> dict[str, Any]:
    """分页读取缓存条目(按快照数组顺序;筛选全部内存过滤,单文件条目量级可接受)。"""
    path = _cache_file(project, name)
    entries = _load_snapshot(path)
    if _append_path(path).exists():
        raise PipelineError(
            "E-CACHE-BUSY",
            f"{name} 存在未合并的翻译日志(.append.jsonl),先执行合并日志再编辑。",
        )

    q = (query or "").strip().lower()

    def _hit(entry: dict[str, Any]) -> bool:
        if locked is not None and bool(entry.get("locked")) != locked:
            return False
        if problem is not None:
            has_p = isinstance(entry.get("problem"), str) and bool(entry["problem"].strip())
            if has_p != problem:
                return False
        if untranslated is not None and bool(entry.get("pre_dst")) != (not untranslated):
            return False
        if q:
            haystack = " ".join(
                str(entry.get(key, "") or "") for key in ("name", "pre_src", "pre_dst", "proofread_dst")
            ).lower()
            if q not in haystack:
                return False
        return True

    filtered = [e for e in entries if _hit(e)]
    total = len(filtered)
    page = max(1, int(page))
    page_size = min(1000, max(1, int(page_size)))
    start = (page - 1) * page_size
    status_table = load_problem_status(project).get(path.name, {})
    rows = [
        {
            "index": e.get("index"),
            "name": e.get("name", ""),
            "pre_src": e.get("pre_src", ""),
            "post_src": e.get("post_src", ""),
            "pre_dst": e.get("pre_dst", ""),
            "proofread_dst": e.get("proofread_dst", ""),
            "locked": bool(e.get("locked")),
            "problem": e.get("problem", ""),
            "problem_status": status_table.get(str(e.get("index")), ""),
        }
        for e in filtered[start : start + page_size]
    ]
    return {
        "file": path.name,
        "total": total,
        "page": page,
        "page_size": page_size,
        "stats": _entry_stats(entries),
        "entries": rows,
    }


def update_entry(
    project,
    name: str,
    index: int,
    pre_src: str,
    pre_dst: str | None = None,
    locked: bool | None = None,
) -> dict[str, Any]:
    """写回单条缓存条目(原子替换;定位=index+pre_src 双校验)。

    编辑器写回约定:改译文即人工接管,保存时由调用方把 locked 置 True
    (pre_dst 为空的条目拒绝锁定)。
    """
    path = _cache_file(project, name)
    if _append_path(path).exists():
        raise PipelineError(
            "E-CACHE-BUSY",
            f"{name} 存在未合并的翻译日志(.append.jsonl),先执行合并日志再编辑。",
        )
    entries = _load_snapshot(path)
    target = None
    for entry in entries:
        if entry.get("index") == index:
            target = entry
            break
    if target is None:
        raise PipelineError(
            "E-CACHE-EDIT-INVALID",
            f"未找到 index={index} 的条目(缓存可能已被重新生成,请刷新编辑器)。",
        )
    if pre_src is not None and target.get("pre_src", "") != pre_src:
        raise PipelineError(
            "E-CACHE-EDIT-INVALID",
            f"index={index} 原文不匹配(缓存可能已被重新生成,请刷新编辑器)。",
        )

    if pre_dst is not None:
        target["pre_dst"] = pre_dst
    if locked is not None:
        if locked and not target.get("pre_dst"):
            raise PipelineError(
                "E-CACHE-EDIT-INVALID",
                f"index={index} 译文为空,不能锁定(锁定=人工终稿)。",
            )
        target["locked"] = bool(locked)
    _save_snapshot(path, entries)
    return {
        "file": path.name,
        "index": index,
        "pre_dst": target.get("pre_dst", ""),
        "locked": bool(target.get("locked")),
        "stats": _entry_stats(entries),
    }


def compact_append_logs(project) -> int:
    """合并中断翻译遗留的 .append.jsonl 到快照(调上游公开函数)。"""
    directory = cache_dir(project)
    if not directory.is_dir():
        return 0
    try:
        from GalTransl.Cache import compact_cache_append_logs
    except ImportError:
        import sys

        repo_root = str(Path(__file__).resolve().parent.parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from GalTransl.Cache import compact_cache_append_logs
    import asyncio

    return asyncio.run(compact_cache_append_logs(str(directory)))


def rebuild_output(project) -> int:
    """用 rebuildr 模式从缓存重建 gt_output(不调 API、不改缓存)。

    前置:TRANSLATE 步曾成功运行过(config.yaml 与缓存均存在)。
    返回重建的输出文件数。
    """
    try:
        from GalTransl.Service import JobSpec, run_job
    except ImportError:
        import sys

        repo_root = str(Path(__file__).resolve().parent.parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from GalTransl.Service import JobSpec, run_job

    gt_dir = project.subdir("work/gt_project")
    config_path = gt_dir / "config.yaml"
    if not config_path.exists():
        raise PipelineError(
            "E-CACHE-EDIT-INVALID",
            f"缺少 {config_path},请先在补丁工作台跑过一次流水线(至少到翻译步)。",
        )
    spec = JobSpec(project_dir=str(gt_dir), translator="rebuildr")
    state = run_job(spec)
    if getattr(state, "error", None):
        raise PipelineError(
            "E-CACHE-EDIT-INVALID", f"重建输出失败: {state.error}"
        )
    outputs = [
        p for p in (gt_dir / "gt_output").glob("*.json") if p.stat().st_size > 2
    ]
    translated = project.subdir("work/translated")
    translated.mkdir(parents=True, exist_ok=True)
    import shutil

    for path in outputs:
        shutil.copy2(path, translated / path.name)
    return len(outputs)
