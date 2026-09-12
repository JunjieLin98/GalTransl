# M1 进度报告(编排层 + CLI alpha)

| 项 | 内容 |
|---|---|
| 日期 | 2026-09-12 |
| 交付 | `galtrans_pipeline` 包 + kirikiri/yuris profiles + `galtrans` CLI + 17 项测试 + 三款真实游戏 E2E |

---

## 已交付

| 模块 | 文件 | 实测状态 |
|---|---|---|
| 错误码目录 | galtrans_pipeline/errors.py | 14 个错误码,全部带可行动指引;E2E 中 E-EXTRACT-TOOL-MISSING/E-TRANSLATE-API-AUTH 实际触发并给出正确指引 |
| EngineProfile | galtrans_pipeline/profile.py | 加载/校验/深合并覆盖(override 优先);18 项断言覆盖 |
| 引擎检测 | galtrans_pipeline/detect.py | **三款真实游戏全部正确检出**(マガルミナ→kirikiri、Relirium→yuris、とける風花→kirikiri) |
| ProcessRunner | galtrans_pipeline/runner.py | 子进程树管理;E2E 中发现并修复管道死锁(xp3brute 大量状态输出填满 64KB 缓冲) |
| ToolBox | galtrans_pipeline/toolbox.py | tools/bin 定位 + SHA-256 校验(msg-tool/Xp3Pack 已锁版本) |
| PatchProject | galtrans_pipeline/project.py | schema_version/workspace 目录/步骤快照/游戏目录校验 |
| 步骤实现 | galtrans_pipeline/steps.py | unpack/extract/translate(复用上游 run_job)/inject/package(patch_xp3+repack_archive)/restore |
| Orchestrator | galtrans_pipeline/orchestrator.py | 状态机 + --from-step 幂等重跑 + L3/L4 裁剪;restore 运维语义 |
| CLI | galtrans_pipeline/cli.py | detect/profiles/init/run/patch/restore 六命令 |
| profiles | profiles/kirikiri.yaml、yuris.yaml | 参数全部来自 M0 实测固化 |

## 真实游戏 E2E 结果(非 LLM 步骤全通过)

| 游戏 | 检测 | 解包 | 提取 | 注入+打包 |
|---|---|---|---|---|
| Relirium(Yu-ris) | ✅ yuris | ✅ sc.ypf | ✅ 242 JSON(日文 name-message) | ✅ **dist/sc.ypf 回解字节一致**(DIST_ROUNDTRIP_OK) |
| マガルミナ(krkrz+PSB) | ✅ kirikiri | ✅ data+append | ✅ 452 JSON(242 日文 PSB + 210 补丁中文) | M1.5(PSB 真名恢复) |
| とける風花(强加密) | ✅ kirikiri | ✅ xp3brute override(826 全解) | ✅ 42 scn JSON(760 条日文对话;另有 68 ks 可选) | M1.5(脚本集选择调优) |

TRANSLATE 步骤:代码链路验证完成(上游 run_job 调用、配置生成含全部段落、断点续翻由上游缓存承担);**真实翻译回归待用户提供 API key**(`--api-key` 或 `GALTRANS_API_KEY`)。

## E2E 发现并修复的缺陷(价值记录)

1. **参数模板空格切断**:`_render_args` 先 format 后 split,含空格路径被拆散 → 改为先分词后替换;
2. **管道死锁**:runner 轮询不读 stdout,xp3brute 大量输出填满 64KB 缓冲导致子进程永久阻塞 → 后台线程持续读取;
3. **配置模板降级**:上游导入失败时静默降级 10 行残缺模板(缺 common 段)→ 导入提前 + 显式传入上游模板;
4. **yuris ypf 版本字段**:pack 需 `--yuris-ypf-version`(Relirium=500,读原包头 dword 判定),已写入 profile 并注明 per-game;
5. **空脚本容错**:msg-tool 对无可翻译文本不产输出 → 提取步骤跳过而非报错。

## M1 剩余(下一段)

- 自建 krkrz/KAG 样例游戏 + 用户提供 API key 后的全流程回归(CLI alpha 发布门)
- マガルミナ PSB 真名恢复(利用已有 append.xp3 文件名/msg-tool file-list)+ とける風花脚本集选择调优
- 性能基线记录(NFR-2)
