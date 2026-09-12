"""Orchestrator 状态机测试:幂等标记/断点重跑/能力等级裁剪(需求 FR-B1/NFR-3)。"""

import threading
from pathlib import Path

import pytest

from galtrans_pipeline.orchestrator import Pipeline
from galtrans_pipeline.profile import EngineProfile
from galtrans_pipeline.project import PatchProject


def _profile(capability: str = "L1") -> EngineProfile:
    return EngineProfile(
        {
            "profile": "fake",
            "capability": capability,
            "translator_mode": "ForGal-json",
            "detect": {"archives": ["*.xp3"], "min_score": 2},
            "steps": {
                "unpack": {"tool": "fake", "args": "x {archive} {out_dir}",
                           "archives": ["*.xp3"]},
                "extract": {"tool": "fake", "args": "x", "input_glob": "**/*"},
                "inject": {"tool": "fake", "args": "x"},
                "package": {"strategy": "patch_xp3", "tool": "fake"},
            },
        }
    )


def _project(tmp_path: Path) -> PatchProject:
    game = tmp_path / "game"
    game.mkdir()
    (game / "data.xp3").write_bytes(b"x")
    return PatchProject.create(tmp_path / "proj", game, "fake")


def test_all_steps_recorded_in_order(tmp_path, monkeypatch):
    project = _project(tmp_path)
    pipeline = Pipeline(project, _profile())
    calls = []

    def fake_step(name):
        def _impl(*a, **k):
            calls.append(name)
            return 1

        return _impl

    executor = pipeline.executor()
    monkeypatch.setattr(executor, "step_unpack", fake_step("UNPACK"))
    monkeypatch.setattr(executor, "step_extract", fake_step("EXTRACT"))
    monkeypatch.setattr(executor, "step_translate", fake_step("TRANSLATE"))
    monkeypatch.setattr(executor, "step_inject", fake_step("INJECT"))
    monkeypatch.setattr(executor, "step_package", fake_step("PACKAGE"))
    monkeypatch.setattr(Pipeline, "executor", lambda self, cancel_event=None: executor)

    pipeline.run()
    assert calls == ["UNPACK", "EXTRACT", "TRANSLATE", "INJECT", "PACKAGE"]
    for step in ("DETECT", "UNPACK", "EXTRACT", "TRANSLATE", "INJECT", "PACKAGE"):
        assert project.step_status(step) == "done"


def test_from_step_skips_earlier_steps(tmp_path, monkeypatch):
    project = _project(tmp_path)
    pipeline = Pipeline(project, _profile())
    calls = []

    def fake_step(name):
        def _impl(*a, **k):
            calls.append(name)
            return 1

        return _impl

    executor = pipeline.executor()
    monkeypatch.setattr(executor, "step_unpack", fake_step("UNPACK"))
    monkeypatch.setattr(executor, "step_extract", fake_step("EXTRACT"))
    monkeypatch.setattr(executor, "step_translate", fake_step("TRANSLATE"))
    monkeypatch.setattr(executor, "step_inject", fake_step("INJECT"))
    monkeypatch.setattr(executor, "step_package", fake_step("PACKAGE"))
    monkeypatch.setattr(Pipeline, "executor", lambda self, cancel_event=None: executor)

    pipeline.run(from_step="INJECT")
    assert calls == ["INJECT", "PACKAGE"]
    # 前序步骤快照不被伪造
    assert project.step_status("UNPACK") == ""


def test_l3_capability_stops_after_translate(tmp_path, monkeypatch):
    project = _project(tmp_path)
    pipeline = Pipeline(project, _profile("L3"))
    executed = []

    def fake_step(name):
        def _impl(*a, **k):
            executed.append(name)
            return 1

        return _impl

    executor = pipeline.executor()
    monkeypatch.setattr(executor, "step_unpack", fake_step("UNPACK"))
    monkeypatch.setattr(executor, "step_extract", fake_step("EXTRACT"))
    monkeypatch.setattr(executor, "step_translate", fake_step("TRANSLATE"))
    monkeypatch.setattr(executor, "step_inject", fake_step("INJECT"))
    monkeypatch.setattr(executor, "step_package", fake_step("PACKAGE"))
    monkeypatch.setattr(Pipeline, "executor", lambda self, cancel_event=None: executor)

    pipeline.run()
    assert "INJECT" not in executed and "PACKAGE" not in executed


def test_failure_marks_step_failed(tmp_path, monkeypatch):
    project = _project(tmp_path)
    pipeline = Pipeline(project, _profile())

    def boom(*a, **k):
        from galtrans_pipeline.errors import PipelineError

        raise PipelineError("E-TOOL-PROCESS-CRASH", "boom")

    executor = pipeline.executor()
    monkeypatch.setattr(executor, "step_unpack", boom)
    monkeypatch.setattr(Pipeline, "executor", lambda self, cancel_event=None: executor)

    with pytest.raises(Exception):
        pipeline.run()
    assert project.step_status("UNPACK") == "failed"
    assert project.step_status("EXTRACT") == ""


def test_cancel_event_propagates(tmp_path):
    project = _project(tmp_path)
    pipeline = Pipeline(project, _profile())
    cancel_event = threading.Event()
    cancel_event.set()
    executor = pipeline.executor(cancel_event)
    assert executor.cancel_event.is_set()
