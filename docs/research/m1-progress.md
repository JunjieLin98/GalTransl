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

---

# M2 进度:GUI 工作台(后端 API + 前端)

## 已完成

### M2 后端(galtrans_pipeline/server_ext.py,commit 72ee405)
- 扩展上游 12333 后端(不另起服务),新增 10 个 REST 端点:
  - GET profiles / status / events(SSE 票据制)
  - POST sse-ticket / detect / projects / run / cancel / restore
- 安全层:
  - **Host 白名单**(localhost/127.0.0.1)——修复上游 DNS Rebinding 隐患(实测恶意 Host 返回 200+数据)
  - **本地 token 鉴权**:GUI 启动换取,hmac.compare_digest 校验,全部 POST 强制
  - **DPAPI 存储 API key**(ctypes,修复 c_char_p 堆损坏 0xc0000374 → create_string_buffer+cast)
- PipelineManager:后台线程跑 Pipeline,SSE 广播 job_started/log/job_done/job_failed
- 在线测试套件 tests/pipeline/test_server_ext_live.py:11 项全过

### CORS 精确收敛(commit 7d4f810)
- 上游 `send_header("Access-Control-Allow-Origin","*")` 全局放行与具体 Origin 并存时浏览器拒绝 →
  受控改造 end_headers:`handler._gt_cors_origin` 属性模式(白名单回显/外来置空抑制/None=上游原行为)
- server_ext 补 OPTIONS 预检放行 X-Local-Token;_reject_host 同样抑制 CORS
- npm run build 通过;live 套件 11/11 回归

### M2 前端(commit 7d4f810)
- desktop/src/lib/pipeline.ts:API 客户端(启动换 token 存 sessionStorage、EventSource+ticket 订阅)
- PatchWorkbenchPage:①选择游戏(文本框+浏览+检测+profile 下拉)②执行流水线
  (步骤徽章/运行全部/从翻译重跑/取消/还原 + SSE 日志区)+ 能力等级说明
- 路由 /patch + 侧边栏 🎮 入口 + patch.css

## 浏览器 E2E 冒烟(通过,2026-09-12)

Relirium 全流程在浏览器中验证:
1. 填入游戏目录 → 检测引擎 → yuris 自动选中(依据 yscfg.dat),profile 下拉同步
2. 创建工程 → 工程目录 `*_patch` 创建成功
3. ▶ 运行全部 → SSE 实时日志:DETECT(1 候选)→ UNPACK(sc.ypf,显示完整 msg-tool 命令行)
   → EXTRACT(242 文件逐个导出,空脚本"跳过(无可翻译文本)"容错正常)
4. TRANSLATE 步无 API key → **预期错误完整呈现**:`[E-TRANSLATE-API-AUTH]` + 可行动指引
   (提示 --api-key / 环境变量 / 直接编辑 config.yaml 三种途径)

## M2 剩余(按开发计划属 v0.1 范围,当前为功能子集)

- 首启向导/API 自检页、人性化错误聚合、只读问题列表(v0.1 完整门)
- Tauri 打包态(http://tauri.localhost)验证——dev 态已验证,打包态待 M6
- TRANSLATE 真实回归仍待 API key
