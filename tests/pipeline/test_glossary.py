"""术语向导(glossary.py)与问题状态(cache_editor)单元测试。"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from galtrans_pipeline import cache_editor, glossary  # noqa: E402
from galtrans_pipeline.errors import PipelineError  # noqa: E402
from galtrans_pipeline.project import PatchProject  # noqa: E402


@pytest.fixture
def project(tmp_path):
    project = PatchProject(tmp_path / "proj", {"schema_version": 1, "profile": "kirikiri"})
    gt = project.subdir("work/gt_project")
    (gt / "transl_cache").mkdir(parents=True)
    cache_file = gt / "transl_cache" / "sc.json"
    cache_file.write_text(
        json.dumps(
            [
                {
                    "index": 0,
                    "name": "Alice",
                    "pre_src": "おはよう。",
                    "post_src": "おはよう。",
                    "pre_dst": "早上好。",
                    "proofread_dst": "",
                    "problem": "翻译失败 (Failed)",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project


# ---------------------------------------------------------------- 问题状态

def test_problem_status_roundtrip(project):
    assert cache_editor.load_problem_status(project) == {}
    cache_editor.set_problem_status(project, "sc.json", 0, "confirmed")
    cache_editor.set_problem_status(project, "sc.json", 1, "ignored")
    table = cache_editor.load_problem_status(project)
    assert table["sc.json"] == {"0": "confirmed", "1": "ignored"}

    cache_editor.set_problem_status(project, "sc.json", 0, "")
    table = cache_editor.load_problem_status(project)
    assert table["sc.json"] == {"1": "ignored"}


def test_problem_status_invalid_value(project):
    with pytest.raises(PipelineError):
        cache_editor.set_problem_status(project, "sc.json", 0, "bogus")


def test_entries_include_problem_status(project):
    cache_editor.set_problem_status(project, "sc.json", 0, "ignored")
    page = cache_editor.load_entries(project, "sc.json")
    assert page["entries"][0]["problem_status"] == "ignored"


# ---------------------------------------------------------------- 术语向导

def test_glossary_confirm_and_read(project):
    entries = [
        {"src": "トワ", "dst": "远夜", "note": "女主"},
        {"src": "リゼット", "dst": "莉泽", "note": ""},
        {"src": "", "dst": "空词条应被忽略"},
    ]
    count = glossary.confirm_entries(project, entries)
    assert count == 2
    text = glossary.confirmed_path(project).read_text(encoding="utf-8")
    assert "トワ\t远夜\t女主" in text
    assert glossary.read_confirmed(project)[0] == {"src": "トワ", "dst": "远夜", "note": "女主"}


def test_glossary_confirm_dedup_and_empty(project):
    with pytest.raises(PipelineError):
        glossary.confirm_entries(project, [{"src": "x", "dst": ""}])
    count = glossary.confirm_entries(
        project,
        [
            {"src": "A", "dst": "1", "note": ""},
            {"src": "A", "dst": "1", "note": ""},  # 重复
        ],
    )
    assert count == 1


def test_glossary_draft_parse(project):
    glossary.draft_path(project).write_text(
        "カグヤ\t辉夜\t配角\n\nトワ\t远夜\nNULL\tNULL\n", encoding="utf-8"
    )
    draft = glossary.read_draft(project)
    assert draft == [
        {"src": "カグヤ", "dst": "辉夜", "note": "配角"},
        {"src": "トワ", "dst": "远夜", "note": ""},
    ]


def test_glossary_confirm_requires_project_config(project):
    """run_gendic 在缺 config 时给出可行动错误(不实际调 LLM)。"""
    with pytest.raises(PipelineError) as exc:
        glossary.run_gendic(project)
    assert "config.yaml" in str(exc.value)
