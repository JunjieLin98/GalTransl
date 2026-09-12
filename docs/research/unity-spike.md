# M5 Spike 结论:UnityPy 定案(2026-09-12)

## 结论

**选型 UnityPy 1.25.3,AssetsTools.NET 不采用。** unity.yaml 以 TextAsset 最小版交付,能力等级 L2(实验性)。

## 实测记录

样本:K0lb3/UnityPy 测试样本 `char_118_yuki.ab`(704,951 字节,AssetBundle 容器 + SerializedFile,35 个 AudioClip;git-lfs media 直链下载)。

| 验证项 | 结果 |
|---|---|
| `UnityPy.load` 解析容器与对象 | ✓ 36 对象(AudioClip×35 + AssetBundle) |
| 对象字段修改(`read()` → 改 `m_Name` → `save()`) | ✓ `is_changed` 标记生效 |
| **容器级写回** `env.save(pack="lz4", out_path=…)` | ✓ 产物同名 .ab,704,974 字节(与原 704,951 基本一致) |
| **重载验证修改持久化** | ✓ PASS(改名后的 m_Name 在重载对象中出现) |
| 无 TextAsset 的 bundle 走 export | ✓ 正确报 E-EXTRACT-NO-SCRIPT |
| Python 脚本工具接入 profile(unity_tool.py) | ✓ `_run_tool` 以 sys.executable 驱动 .py |

## 关键 API 形态(1.25 重构版,与旧教程差异大)

```python
env = UnityPy.load(path)          # Environment;对象聚合在 env.objects
for obj in env.objects:
    data = obj.read()             # 类型化对象(UnityPy.classes.*)
    data.m_Name = "..."           # 直接改字段
    data.save()                   # 对象级重序列化(标记 changed)
env.save(pack="lz4", out_path=dir)  # 容器级保存;产物名保留原 bundle 名
```

注意:旧教程的 `env.file.save()` 在 1.25 不存在;`obj.assets_file.save()` 只保存
内层 SerializedFile(丢外层容器),必须用 `env.save()`。

## TextAsset 与 AudioClip 的关系

两者同为 SerializedFile 内的引擎对象,读改写路径完全相同;差异仅在字段
(`m_Script` 为 bytes/str)。容器级写回机制已实测,故 TextAsset 场景的
round-trip 置信度高。**未实测项**:真实游戏的 TextAsset 内容格式多样性——
unity_tool 当前只支持 JSON 数组(`[{name,message}]`)与 TSV 两类(汉化场景
最常见),其它格式给 E-UNITY-FORMAT 可行动指引,即 L2 "受限"的边界。

## AssetsTools.NET 不采用的依据(非 A/B 实测,基于调研+架构成本)

1. .NET 运行时依赖:需要自写 C# CLI 桥 + 随应用分发 .NET Runtime 或自包含
   二进制,与 Python 后端形成跨运行时胶水层(M3 已验证 Python 内联工具链成本
   远低于跨进程跨语言)。
2. UnityPy 已覆盖需求(见上),无功能缺口需要 AssetsTools.NET 补位。
3. 维护面:少一条工具链 = 少一份托管表条目/校验和/镜像。
   若未来遇到 UnityPy 处理不了的变体(如奇TypeTree 缺失的老版本),再评估。

## 交付物

- `tools/unity_tool.py`:export / import / copy 三命令
- `profiles/unity.yaml`:L2,detect(`*/resources.assets` 等)+ copy/export/import + deploy 策略
- `_package_deploy` 策略:**强制备份**(替换前原文件 → backup/,保留相对路径),
  restore 通用步骤可还原;同名多匹配拒绝部署(E-UNITY-DEPLOY-AMBIGUOUS)
- 单元测试:文本解析/重组/未知字段保留/CLI 契约(test_unity_tool.py)
- Il2Cpp 引导:docs/research/unity-il2cpp.md

## 后续(诚实边界)

- 真实 Unity 游戏全链路回归待样例(当前三款样例游戏均为 krkr/Yu-ris);
  取得后按 M1 的 per-game override 流程验证并回填本档案
- data.unity3d(容器型)需 override 扩 input_glob;含多 TextAsset 的大 bundle
  的 _asset 分组写回已在工具内支持但未经真实数据检验
