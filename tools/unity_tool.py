"""Unity TextAsset 提取/回封工具(M5,实验性;依赖 UnityPy)。

命令:
  export <input> <out_json>
      从 bundle/assets 提取全部 TextAsset,合并为 GalTransl 输入 JSON 数组:
      [{"_asset": <TextAsset名>, "name": <条目名>, "message": <文本>}, ...]
      TextAsset 内容支持两种格式(汉化场景最常见):
        - JSON 数组(元素为含 name/message 的对象)
        - TSV(每行"名称\\t文本",两列起取第一列为 name)
      其它格式 → 退出码非 0 并给出 E-UNITY-FORMAT 指引。

  import <input> <trans_json> <out>
      将译文 JSON 按 _asset 分组重组文本写回 TextAsset.m_Script,
      容器级保存(lz4)到 <out>。

  copy <input> <out_dir>
      将文件复制到 out_dir(UNPACK 步用,游戏目录保持只读)。

部署语义由流水线的 PACKAGE 步(deploy 策略)完成:先备份游戏目录原文件到
backup/,再以 workspace 副本替换;restore 通用步骤可从 backup/ 还原。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def _die(code: str, message: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"[{code}] {message}", file=sys.stderr)
    sys.exit(2)


def _decode_script(raw) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode("utf-8", errors="replace")
    return ""


def _parse_script(name: str, script: str) -> list[dict]:
    """TextAsset 文本 → GalTransl 条目列表;不支持的格式抛 ValueError。"""
    text = script.strip()
    if not text:
        return []
    # JSON 数组(元素含 message)
    if text.startswith("["):
        try:
            data = json.loads(text)
        except Exception:
            data = None
        if isinstance(data, list):
            entries = []
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("message"), str):
                    entries.append(
                        {
                            "name": item.get("name", ""),
                            "message": item["message"],
                        }
                    )
            if entries:
                return entries
    # TSV:第一列 name,其余合并为 message
    rows = []
    for line in script.splitlines():
        if "\t" not in line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name_col, message = parts[0], "\t".join(parts[1:])
        if message.strip():
            rows.append({"name": name_col, "message": message})
    if rows:
        return rows
    raise ValueError(
        f"TextAsset {name!r} 内容既非 JSON 数组也非 TSV;"
        "当前支持: [{name,message}...] JSON 或 名称\\t文本 制表符分隔"
    )


def _serialize_back(asset_name: str, entries: list[dict], original: str) -> str:
    """按原格式把译文条目重组为 TextAsset 文本。"""
    stripped = original.strip()
    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except Exception:
            data = None
        if isinstance(data, list):
            # 按原数组结构原位替换 message(保留未知字段与顺序)
            it = iter(entries)
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("message"), str):
                    entry = next(it, None)
                    if entry is None:
                        break
                    item["message"] = entry["message"]
                    if "name" in item:
                        item["name"] = entry.get("name", item["name"])
            return json.dumps(data, ensure_ascii=False, indent=1)
    lines = [f"{e.get('name', '')}\t{e['message']}" for e in entries]
    return "\n".join(lines)


def cmd_export(input_path: str, out_json: str) -> int:
    import UnityPy

    env = UnityPy.load(input_path)
    assets = []
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        data = obj.read()
        name = data.m_Name
        script = _decode_script(getattr(data, "m_Script", ""))
        try:
            entries = _parse_script(name, script)
        except ValueError as error:
            _die("E-UNITY-FORMAT", str(error))
        for entry in entries:
            assets.append({"_asset": name, "name": entry["name"], "message": entry["message"]})
    if not assets:
        _die(
            "E-EXTRACT-NO-SCRIPT",
            f"{Path(input_path).name} 中没有可提取的 TextAsset(或内容全部为空)",
        )
    out = Path(out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(assets, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"exported {len(assets)} entries from {len({a['_asset'] for a in assets})} TextAsset(s)")
    return 0


def cmd_import(input_path: str, trans_json: str, out_path: str) -> int:
    import UnityPy

    groups: dict[str, list[dict]] = {}
    for entry in json.loads(Path(trans_json).read_text(encoding="utf-8")):
        asset = entry.get("_asset")
        if asset is None:
            _die(
                "E-UNITY-FORMAT",
                f"译文 JSON 缺少 _asset 字段(必须由 unity_tool export 生成): {trans_json}",
            )
        groups.setdefault(asset, []).append(
            {"name": entry.get("name", ""), "message": entry.get("message", "")}
        )

    env = UnityPy.load(input_path)
    patched = 0
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        data = obj.read()
        if data.m_Name not in groups:
            continue
        script = _decode_script(getattr(data, "m_Script", ""))
        new_text = _serialize_back(data.m_Name, groups[data.m_Name], script)
        data.m_Script = new_text.encode("utf-8")
        data.save()
        patched += 1
    if patched == 0:
        _die(
            "E-UNITY-FORMAT",
            "没有任何 TextAsset 与译文 JSON 的 _asset 匹配;"
            "请确认译文文件由同一 bundle 的 export 产物翻译而来",
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = out.parent / f".unity_tmp_{out.stem}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        env.save(pack="lz4", out_path=str(tmp_dir))
        produced = list(tmp_dir.iterdir())
        if len(produced) != 1:
            _die("E-TOOL-PROCESS-CRASH", f"容器保存产物异常: {[p.name for p in produced]}")
        shutil.move(str(produced[0]), str(out))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"imported into {patched} TextAsset(s) → {out.name}")
    return 0


def cmd_copy(input_path: str, out_dir: str) -> int:
    src = Path(input_path)
    dst = Path(out_dir) / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"copied {src.name} → {dst}")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "export" and len(argv) == 3:
        return cmd_export(argv[1], argv[2])
    if len(argv) >= 2 and argv[0] == "import" and len(argv) == 4:
        return cmd_import(argv[1], argv[2], argv[3])
    if len(argv) >= 2 and argv[0] == "copy" and len(argv) == 3:
        return cmd_copy(argv[1], argv[2])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
