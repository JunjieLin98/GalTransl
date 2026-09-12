"""自建样例游戏的全链路回归(CLI alpha DoD 的 CI 形态)。

链路: pack fixture → UNPACK → EXTRACT → (桩翻译) → INJECT → PACKAGE → dist 产物校验。
不依赖 LLM API;msg-tool/Xp3Pack 缺失时跳过。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from galtrans_pipeline.orchestrator import Pipeline
from galtrans_pipeline.profile import load_profiles
from galtrans_pipeline.project import PatchProject
from galtrans_pipeline.toolbox import ToolBox

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "fixtures" / "sample_game"
MSG_TOOL = REPO_ROOT / "tools" / "bin" / "msg_tool.exe"
XP3PACK = REPO_ROOT / "tools" / "bin" / "Xp3Pack.exe"

pytestmark = pytest.mark.skipif(
    not (MSG_TOOL.is_file() and XP3PACK.is_file()),
    reason="tools/bin 缺少 msg_tool.exe / Xp3Pack.exe(需要本地工具)",
)


def _make_sample_game(tmp_path: Path) -> Path:
    """把 fixture 场景打包为 data.xp3,构造一个'游戏目录'。"""
    game = tmp_path / "sample_game"
    (game / "scenario_src").mkdir(parents=True)
    for ks in (FIXTURE / "scenario").glob("*.ks"):
        shutil.copy2(ks, game / "scenario_src" / ks.name)
    archive = game / "data.xp3"
    result = subprocess_run(
        [
            str(MSG_TOOL),
            "pack",
            "-t",
            "kirikiri-xp3",
            "-r",
            str(game / "scenario_src"),
            str(archive),
        ]
    )
    assert result.returncode == 0, result.stderr
    return game


def subprocess_run(args: list[str]):
    return subprocess.run(args, capture_output=True)


def test_sample_game_full_mechanical_chain(tmp_path: Path, monkeypatch):
    profiles = load_profiles(REPO_ROOT / "profiles")
    # 样例为 KS 脚本:per-game override 切换到 KS 链(FR-A4 覆盖机制的实证)
    profile = profiles["kirikiri"].apply_override(
        {
            "steps": {
                "extract": {
                    "input_glob": "**/*.ks",
                    "args": "export -t kirikiri {input} {out_file}",
                },
                "inject": {
                    "args": "import -t kirikiri --patched-encoding gbk {input} {trans_file} {patched}"
                },
            }
        }
    )
    game = _make_sample_game(tmp_path)
    project = PatchProject.create(tmp_path / "proj", game, "kirikiri")
    pipeline = Pipeline(project, profile, toolbox=ToolBox(REPO_ROOT / "tools" / "bin"))
    executor = pipeline.executor()

    # UNPACK + EXTRACT(真实 msg-tool)
    executor.step_unpack()
    extracted = executor.step_extract()
    assert extracted == 2
    manifest = json.loads(
        (project.project_dir / "work/extracted/_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest) == 2

    # 校验日文提取质量
    sample_json = project.project_dir / "work/extracted" / (
        sorted(manifest.keys())[0]
    )
    data = json.loads(sample_json.read_text(encoding="utf-8"))
    assert any("テスト" in entry.get("message", "") for entry in data)

    # 桩翻译:复制提取产物(内容不变,验证机械链路;真实翻译待 API key 回归)
    translated = project.project_dir / "work/translated"
    for path in (project.project_dir / "work/extracted").glob("*.json"):
        if path.name != "_manifest.json":
            shutil.copy2(path, translated / path.name)

    # INJECT + PACKAGE(真实 msg-tool/Xp3Pack)
    executor.step_inject()
    executor.step_package()

    dist = project.project_dir / "dist"
    archives = list(dist.glob("patch*.xp3"))
    assert len(archives) == 1, f"dist 应有补丁归档: {list(dist.iterdir())}"
    assert (dist / "TRANSLATION_NOTICE").is_file()
    assert (dist / "LICENSE-THIRD-PARTY.txt").is_file()
    assert (dist / "安装说明.txt").is_file()

    # 产物回解校验:补丁归档可被 msg-tool 读回
    unpacked_check = tmp_path / "check"
    result = subprocess_run(
        [
            str(MSG_TOOL),
            "unpack",
            "-t",
            "kirikiri-xp3",
            str(archives[0]),
            str(unpacked_check),
        ]
    )
    assert result.returncode == 0, result.stderr
    patched_files = list(unpacked_check.rglob("*"))
    assert any(p.suffix == ".ks" for p in patched_files if p.is_file())
