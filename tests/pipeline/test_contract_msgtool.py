"""msg-tool 合约测试(Kirikiri 链 round-trip;M0 实测行为的回归保护)。

依赖本地 tools/bin/msg_tool.exe;缺失则跳过(CI 无工具时)。
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from galtrans_pipeline.toolbox import ToolBox

REPO_ROOT = Path(__file__).resolve().parents[2]
MSG_TOOL = REPO_ROOT / "tools" / "bin" / "msg_tool.exe"

pytestmark = pytest.mark.skipif(
    not MSG_TOOL.is_file(), reason="tools/bin/msg_tool.exe 不存在(合约测试需要本地工具)"
)

SAMPLE_KS_SJIS = (
    "*page1|\n[clean]\nこれはテストメッセージです。\n"
    "二行目のメッセージです。\n*page2|\n最後のメッセージ。\n"
).encode("shift-jis")


def _msg_tool(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(MSG_TOOL), *args], capture_output=True, cwd=str(cwd) if cwd else None
    )


def test_ks_export_produces_message_json(tmp_path: Path):
    source = tmp_path / "sample.ks"
    source.write_bytes(SAMPLE_KS_SJIS)
    out = tmp_path / "out.json"
    result = _msg_tool("export", "-t", "kirikiri", str(source), str(out))
    assert result.returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert any("テスト" in entry.get("message", "") for entry in data)


def test_ks_import_gbk_roundtrip(tmp_path: Path):
    source = tmp_path / "sample.ks"
    source.write_bytes(SAMPLE_KS_SJIS)
    extracted = tmp_path / "extracted.json"
    _msg_tool("export", "-t", "kirikiri", str(source), str(extracted))
    data = json.loads(extracted.read_text(encoding="utf-8"))
    data[0]["message"] = "这是注入的中文消息。"
    translated = tmp_path / "translated.json"
    translated.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    patched = tmp_path / "patched.ks"
    result = _msg_tool(
        "import",
        "-t",
        "kirikiri",
        "--patched-encoding",
        "gbk",
        str(source),
        str(translated),
        str(patched),
    )
    assert result.returncode == 0
    content = patched.read_bytes().decode("gbk")
    assert "这是注入的中文消息。" in content
    # 指令保留:页标签不被破坏
    assert content.startswith("*page1|")


def test_xp3_pack_unpack_byte_identical(tmp_path: Path):
    src = tmp_path / "patch"
    src.mkdir()
    (src / "script.txt").write_bytes("中文内容确认".encode("gbk"))
    # Xp3Pack 需要目录名为 patch 才产出 patch.xp3;此处用 msg-tool 等价验证
    archive = tmp_path / "test.xp3"
    result = _msg_tool("pack", "-t", "kirikiri-xp3", str(src), str(archive))
    assert result.returncode == 0
    unpacked = tmp_path / "unpacked"
    result = _msg_tool("unpack", "-t", "kirikiri-xp3", str(archive), str(unpacked))
    assert result.returncode == 0
    assert (unpacked / "script.txt").read_bytes() == "中文内容确认".encode("gbk")
