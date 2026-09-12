"""EngineProfile 加载/校验/覆盖优先级测试(需求 FR-A2/FR-A4)。"""

from pathlib import Path

import pytest

from galtrans_pipeline.errors import PipelineError
from galtrans_pipeline.profile import EngineProfile, deep_merge, load_profiles

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_DIR = REPO_ROOT / "profiles"


def test_load_repo_profiles():
    profiles = load_profiles(PROFILES_DIR)
    assert "kirikiri" in profiles
    assert "yuris" in profiles
    kirikiri = profiles["kirikiri"]
    assert kirikiri.capability == "L1"
    assert kirikiri.translator_mode == "ForGal-json"
    assert "*.xp3" in kirikiri.detect["archives"]


def test_invalid_capability_rejected():
    with pytest.raises(PipelineError):
        EngineProfile({"profile": "x", "capability": "L9"})


def test_l1_requires_steps():
    with pytest.raises(PipelineError):
        EngineProfile({"profile": "x", "capability": "L1"})


def test_deep_merge_override_priority():
    base = {
        "steps": {
            "unpack": {"tool": "msg-tool", "args": "a {archive}"},
            "extract": {"input_glob": "**/*.scn"},
        }
    }
    override = {"steps": {"extract": {"input_glob": "**/*", "magic_filter": "PSB"}}}
    merged = deep_merge(base, override)
    # 覆盖字段生效
    assert merged["steps"]["extract"]["input_glob"] == "**/*"
    assert merged["steps"]["extract"]["magic_filter"] == "PSB"
    # 未覆盖字段保留(非覆盖部分不被破坏)
    assert merged["steps"]["unpack"]["tool"] == "msg-tool"


def test_apply_override_keeps_original():
    base = EngineProfile(
        {
            "profile": "kirikiri",
            "capability": "L4",
            "steps": {"extract": {"input_glob": "**/*.scn"}},
        }
    )
    override_profile = base.apply_override(
        {"steps": {"extract": {"input_glob": "**/*", "magic_filter": "PSB"}}}
    )
    assert override_profile.step("extract")["input_glob"] == "**/*"
    # 原 profile 不被修改
    assert base.step("extract")["input_glob"] == "**/*.scn"
