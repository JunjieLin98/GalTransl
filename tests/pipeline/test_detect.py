"""引擎检测测试(需求 FR-A1)。"""

from pathlib import Path

from galtrans_pipeline.detect import detect_engine
from galtrans_pipeline.profile import EngineProfile


def _make_profile(name: str, detect: dict) -> EngineProfile:
    # 检测测试只关心 detect 规则;L4 不要求 steps 定义
    return EngineProfile({"profile": name, "capability": "L4", "detect": detect})


def test_kirikiri_style_detection(tmp_path: Path):
    (tmp_path / "data.xp3").write_bytes(b"x")
    (tmp_path / "video.xp3").write_bytes(b"x")
    profiles = {"kirikiri": _make_profile("kirikiri", {"archives": ["*.xp3"], "min_score": 2})}
    results = detect_engine(tmp_path, profiles)
    assert results and results[0]["profile"] == "kirikiri"
    assert results[0]["score"] >= 2


def test_yuris_file_signature(tmp_path: Path):
    (tmp_path / "yscfg.dat").write_bytes(b"x")
    profiles = {"yuris": _make_profile("yuris", {"files": ["yscfg.dat"], "min_score": 1})}
    results = detect_engine(tmp_path, profiles)
    assert results and results[0]["profile"] == "yuris"


def test_unknown_engine_returns_empty(tmp_path: Path):
    (tmp_path / "game.exe").write_bytes(b"x")
    profiles = {"kirikiri": _make_profile("kirikiri", {"archives": ["*.xp3"], "min_score": 2})}
    assert detect_engine(tmp_path, profiles) == []


def test_min_score_filters_weak_match(tmp_path: Path):
    (tmp_path / "readme.txt").write_bytes(b"x")
    profiles = {
        "strict": _make_profile("strict", {"files": ["Config.tjs"], "min_score": 2})
    }
    assert detect_engine(tmp_path, profiles) == []
