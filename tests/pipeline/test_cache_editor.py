"""cache_editor(M3 缓存编辑库)单元测试。"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from galtrans_pipeline import cache_editor  # noqa: E402
from galtrans_pipeline.errors import PipelineError  # noqa: E402
from galtrans_pipeline.project import PatchProject  # noqa: E402


def make_entries() -> list[dict]:
    return [
        {
            "index": 0,
            "name": "Alice",
            "pre_src": "おはよう。",
            "post_src": "おはよう。",
            "pre_dst": "早上好。",
            "proofread_dst": "",
        },
        {
            "index": 1,
            "name": "Bob",
            "pre_src": "おやすみ。",
            "post_src": "おやすみ。",
            "pre_dst": "",
            "proofread_dst": "",
            "problem": "翻译失败 (Failed)",
        },
        {
            "index": 2,
            "name": "Alice",
            "pre_src": "また明日。",
            "post_src": "また明日。",
            "pre_dst": "明天见。",
            "proofread_dst": "",
            "locked": True,
        },
    ]


@pytest.fixture
def project(tmp_path):
    project = PatchProject(tmp_path / "proj", {"schema_version": 1, "profile": "kirikiri"})
    (project.subdir("work/gt_project") / "transl_cache").mkdir(parents=True)
    cache_file = cache_editor.cache_dir(project) / "sc.json"
    cache_file.write_text(
        json.dumps(make_entries(), ensure_ascii=False), encoding="utf-8"
    )
    return project


def test_list_cache_files_stats(project):
    files = cache_editor.list_cache_files(project)
    assert len(files) == 1
    stats = files[0]
    assert stats["name"] == "sc.json"
    assert stats["entries"] == 3
    assert stats["locked"] == 1
    assert stats["problems"] == 1
    assert stats["untranslated"] == 1
    assert stats["has_append"] is False


def test_load_entries_pagination_and_filters(project):
    page = cache_editor.load_entries(project, "sc.json", page=1, page_size=2)
    assert page["total"] == 3
    assert len(page["entries"]) == 2

    locked = cache_editor.load_entries(project, "sc.json", locked=True)
    assert [e["index"] for e in locked["entries"]] == [2]

    untranslated = cache_editor.load_entries(project, "sc.json", untranslated=True)
    assert [e["index"] for e in untranslated["entries"]] == [1]

    problems = cache_editor.load_entries(project, "sc.json", problem=True)
    assert [e["index"] for e in problems["entries"]] == [1]

    by_query = cache_editor.load_entries(project, "sc.json", query="bob")
    assert [e["index"] for e in by_query["entries"]] == [1]


def test_update_entry_writes_back(project):
    result = cache_editor.update_entry(
        project, "sc.json", index=1, pre_src="おやすみ。", pre_dst="晚安。", locked=True
    )
    assert result["locked"] is True
    saved = json.loads(
        (cache_editor.cache_dir(project) / "sc.json").read_text(encoding="utf-8")
    )
    assert saved[1]["pre_dst"] == "晚安。"
    assert saved[1]["locked"] is True
    # 其余条目不受影响
    assert saved[0]["pre_dst"] == "早上好。"


def test_update_entry_rejects_mismatch(project):
    with pytest.raises(PipelineError) as exc:
        cache_editor.update_entry(project, "sc.json", index=1, pre_src="错误原文")
    assert exc.value.code == "E-CACHE-EDIT-INVALID"


def test_update_entry_rejects_locking_empty_translation(project):
    with pytest.raises(PipelineError) as exc:
        cache_editor.update_entry(
            project, "sc.json", index=1, pre_src="おやすみ。", locked=True
        )
    assert exc.value.code == "E-CACHE-EDIT-INVALID"


def test_append_log_blocks_reads_and_writes(project):
    append_path = cache_editor.cache_dir(project) / "sc.json.append.jsonl"
    append_path.write_text("", encoding="utf-8")

    with pytest.raises(PipelineError) as exc:
        cache_editor.load_entries(project, "sc.json")
    assert exc.value.code == "E-CACHE-BUSY"

    with pytest.raises(PipelineError) as exc:
        cache_editor.update_entry(project, "sc.json", index=0, pre_src="おはよう。")
    assert exc.value.code == "E-CACHE-BUSY"


def test_compact_merges_append_log(project):
    # 模拟翻译中断遗留:append 里有 index=1 的补译(带 __cache_key)
    entries = make_entries()
    append_entry = dict(entries[1])
    append_entry["pre_dst"] = "晚安(补)。"
    append_entry["__cache_key"] = (
        f'Aliceおはよう。Bobおやすみ。Aliceまた明日。'  # prev+now+next 三联键
    )
    append_path = cache_editor.cache_dir(project) / "sc.json.append.jsonl"
    append_path.write_text(
        json.dumps(append_entry, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    merged = cache_editor.compact_append_logs(project)
    assert merged == 1
    assert not append_path.exists()

    saved = json.loads(
        (cache_editor.cache_dir(project) / "sc.json").read_text(encoding="utf-8")
    )
    by_index = {e["index"]: e for e in saved}
    assert by_index[1]["pre_dst"] == "晚安(补)。"
    # 合并后可编辑
    cache_editor.update_entry(project, "sc.json", index=0, pre_src="おはよう。")
