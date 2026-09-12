"""unity_tool(M5 Unity TextAsset 工具)单元测试。

round-trip 需要真实 Unity bundle(样本不入库),此处覆盖纯逻辑:
文本解析(TSV/JSON)、重组序列化、_asset 分组;bundle 级验证见 spike 记录。
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_spec = importlib.util.spec_from_file_location(
    "unity_tool", REPO_ROOT / "tools" / "unity_tool.py"
)
unity_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(unity_tool)


# ---------------------------------------------------------------- 解析

def test_parse_json_array():
    script = json.dumps(
        [{"name": "トワ", "message": "おはよう"}, {"message": "…"}],
        ensure_ascii=False,
    )
    rows = unity_tool._parse_script("story", script)
    assert rows == [
        {"name": "トワ", "message": "おはよう"},
        {"name": "", "message": "…"},
    ]


def test_parse_tsv():
    script = "名前1\tセリフ1\n名前2\tセリフ2\t続き"
    rows = unity_tool._parse_script("story", script)
    assert rows == [
        {"name": "名前1", "message": "セリフ1"},
        {"name": "名前2", "message": "セリフ2\t続き"},
    ]


def test_parse_unsupported_raises():
    with pytest.raises(ValueError):
        unity_tool._parse_script("story", "just a plain paragraph")


# ---------------------------------------------------------------- 重组

def test_serialize_back_json_preserves_structure():
    original = json.dumps(
        [
            {"name": "A", "message": "1", "extra": "keep"},
            {"message": "2"},
        ],
        ensure_ascii=False,
    )
    entries = [
        {"name": "甲", "message": "一"},
        {"name": "", "message": "二"},
    ]
    rebuilt = unity_tool._serialize_back("story", entries, original)
    data = json.loads(rebuilt)
    assert data[0]["message"] == "一"
    assert data[0]["extra"] == "keep", "未知字段必须原位保留"
    assert data[0]["name"] == "甲"
    assert data[1]["message"] == "二"


def test_serialize_back_tsv():
    entries = [{"name": "A", "message": "一"}, {"name": "B", "message": "二"}]
    rebuilt = unity_tool._serialize_back("story", entries, "A\t1\nB\t2")
    assert rebuilt == "A\t一\nB\t二"


# ---------------------------------------------------------------- 端到端(合成 bundle)

def test_cli_usage_on_bad_args(capsys):
    """bundle 级 round-trip 见 spike 文档;此处验证 CLI 契约(参数错误给非零)。"""
    assert unity_tool.main() == 1
    out = capsys.readouterr().out
    assert "export" in out and "import" in out
