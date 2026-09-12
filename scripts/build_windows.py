"""Windows 发布包构建脚本(M6)。

产出 release/app/ 目录(对齐上游 Tauri backend_executable_candidates 布局):
  release/app/
    backend/galtransl_backend.exe   ← PyInstaller onefile(run_backend.py)
    plugins/                        ← 上游 yapsy 插件(源码,动态发现)
    profiles/                       ← EngineProfile YAML
    tools/bin/                      ← msg-tool/Xp3Pack 等外部工具
    res/                            ← GenDic 分词模型(bccwj…model.xz)

用法:
  python scripts/build_windows.py            # PyInstaller + 组装
  python scripts/build_windows.py --skip-pyi # 仅重新组装(exe 已存在时)

Tauri 打包:desktop/src-tauri/tauri.conf.json 的 bundle.resources 已把
release/app 相对产物映射进安装包;tauri build 前(由 beforeBuildCommand 之外)
先跑本脚本。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RELEASE_APP = REPO / "release" / "app"
PYI_NAME = "galtransl_backend"

ASSEMBLE_MAP = [
    (REPO / "plugins", RELEASE_APP / "plugins"),
    (REPO / "profiles", RELEASE_APP / "profiles"),
    (REPO / "tools" / "bin", RELEASE_APP / "tools" / "bin"),
    (REPO / "res", RELEASE_APP / "res"),
]


def run_pyi() -> Path:
    dist_dir = REPO / "release" / "pyi"
    build_dir = REPO / "release" / "pyi_build"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", PYI_NAME,
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(build_dir),
        "--collect-submodules", "GalTransl",
        "--collect-submodules", "galtrans_pipeline",
        "--hidden-import", "GalTransl.server",
        "--hidden-import", "GalTransl.server_runtime",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        str(REPO / "run_backend.py"),
    ]
    print("[build]", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=REPO)
    exe = dist_dir / f"{PYI_NAME}.exe"
    if not exe.is_file():
        raise SystemExit(f"PyInstaller 产物缺失: {exe}")
    return exe


def assemble(exe: Path | None) -> None:
    RELEASE_APP.mkdir(parents=True, exist_ok=True)
    backend_dir = RELEASE_APP / "backend"
    backend_dir.mkdir(parents=True, exist_ok=True)
    if exe is not None:
        shutil.copy2(exe, backend_dir / f"{PYI_NAME}.exe")
    elif not (backend_dir / f"{PYI_NAME}.exe").is_file():
        raise SystemExit("未找到已有 galtransl_backend.exe,请先完整构建")
    for src, dst in ASSEMBLE_MAP:
        if not src.is_dir():
            print(f"[warn] 跳过不存在的目录: {src}")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(
            src,
            dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyd"),
        )
    print(f"[ok] 发布包就绪: {RELEASE_APP}")
    print("     Tauri bundle 经 tauri.conf.json 的 bundle.resources 引用该目录。")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-pyi", action="store_true", help="跳过 PyInstaller,仅组装")
    args = parser.parse_args()
    exe = None
    if not args.skip_pyi:
        exe = run_pyi()
    assemble(exe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
