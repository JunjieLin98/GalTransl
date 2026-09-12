# galTrans 开发计划

| 项 | 内容 |
|---|---|
| 版本 | v1.0(基准,经独立审查修订) |
| 日期 | 2026-09-12 |
| 状态 | 独立审查通过,作为 M0 正式开工依据 |
| 估算口径 | 单人开发者 + AI 辅助编程,兼职节奏;诚实估算,不为赶工压缩 |
| 总周期 | **约 21 周**(文档 1 + M0 2 + M1 4 + M2 4 + M3 3 + M4 1.5 + M5 2 + M6 3) |

---

## 1. 里程碑总览

| 阶段 | 周数 | 累计 | 交付物 |
|---|---|---|---|
| 文档阶段 | 1 | W1 | requirements / architecture / development-plan 三份文档评审通过 |
| M0 工程启动 | 2 | W3 | fork 就绪、工具链验证报告、开源样例游戏、上游协议调研 |
| M1 编排层+Kirikiri | 4 | W7 | **CLI alpha 发布** |
| M2 GUI 工作台 | 4 | W11 | **v0.1 发布**(krkr 端到端 GUI) |
| M3 质量与编辑 | 3 | W14 | 缓存锁定+增量重翻、双语编辑器 MVP |
| M4 智能化集成 | 1.5 | W15.5 | 上游字典人设(FR-D4)/问题状态管理(FR-D6)/术语向导(FR-D7)/任务队列与通知(FR-F7);TEaR 与成本包移出 v1.0 |
| M5 Unity 最小版 | 2 | W17.5 | unity.yaml + TextAsset 回封(含备份/恢复) |
| M6 发布 | 3 | W20.5 | **v1.0 发布**(安装器/自动更新/审计/CI/文档) |

发布节奏:**CLI alpha(M1 末)→ v0.1(W11)→ v1.0(W20.5)**;每个发布点都可用,不攒大招。

---

## 2. 文档阶段(W1,当前阶段)

- [x] 复核上游 issue 引用(14 条,`gh api`,核查日期 2026-09-12,见 requirements §8)
- [x] requirements.md / architecture.md / development-plan.md 初稿
- [ ] **用户评审三份文档**(评审通过才进入 M0)
- [ ] 用户决策确认:M0 本地回归样例游戏清单(2-3 款合法持有的 krkr 游戏)

---

## 3. 里程碑详情

### M0 工程启动(2 周)

**目标**:消除全部"未实测"假设,开工即踩在实地上。

任务:
1. Fork GalTransl → clone;本地跑通上游 CLI 与 v7 桌面端各一次;
2. **上游后端协议调研**:run_backend.py/server.py 的路由风格、SSE 事件格式、CORS 实现;**确认打包态 WebView 真实 Origin(Tauri v2 Windows 预期 `http://tauri.localhost`,以实测为准)并回填 CORS 白名单**(产出《上游后端协议笔记》,architecture §4 据此修订);
3. **工具链验证报告**(核心任务):msg-tool xp3 unpack/pack + .ks/.scn export/import round-trip 实测;SExtractor 命令行调用方式与 BIN 导入实测;KirikiriTools Xp3Pack/version.dll 实测;固化所有 profile 参数模板(替换文档中的"M0 实测"占位);
4. **GalTransl_DumpInjector 调研**:license 矛盾澄清(README MIT vs 仓库 GPL-3.0,以 LICENSE 文件与作者确认为准)、代码可复用性评估 → 托管表定稿;
5. **自建开源样例游戏**:直接基于 KAG3 官方开源模版(如 `kag3_blank`)裁剪(保留 1 个背景图、1 首 BGM、5 条对话脚本),总包体控制在 <5MB,严禁从零手写 TJS 系统脚本;制作加密/未加密两种 xp3 配置,入库供 CI/E2E 快速回归;
6. 选定 2-3 款真实 krkr 游戏作本地手动回归样例(用户合法持有,不入库不分发);
7. CI 骨架:GitHub Actions(pytest + 前端 build);
8. **PatchProject 路径语义与 schema_version 定稿**(architecture §3.4,含游戏目录缺失校验 E-PROJECT-GAME-MISSING)。

**DoD**:工具链验证报告 + 协议笔记入库;样例游戏在 CI 可跑;全部"M0 实测"占位被实际参数替换。

风险:krkrz 样例游戏制作耗时超预期 → 先做未加密配置,加密配置顺延至 M1。

### M1 编排层+Kirikiri 端到端(4 周)

任务:galtrans_pipeline 包(profile/detect/orchestrator/jobs/toolbox/project/errors/steps);kirikiri.yaml(L1 主链 + L2 SExtractor 兜底);CLI 入口 `galtrans patch <游戏目录>`(检测→提取→翻译→注入→打包,`--from-step` 重跑);错误码目录全量实现于 CLI 输出;pytest(状态机/解析/覆盖优先级/合约测试)。

**DoD(= CLI alpha 发布)**:自建样例 + 1 款真实游戏全流程通过;每步幂等可重跑;断点续翻验证;dist 产物检查含 LICENSE-THIRD-PARTY.txt(FR-E1)与 TRANSLATION_NOTICE(FR-E2);性能基线记录(NFR-2:同工程同模型同并发与上游 CLI 各跑一次,差 ≤10%);README 发布 alpha 使用说明 + 种子用户反馈渠道(issue 模板)。

### M2 GUI 补丁工作台(4 周)

任务:扩展上游 12333 后端(新增 REST 端点 + SSE 事件类型 + **Host 白名单拦截 + 本地 token 鉴权 + CORS 精确白名单**);React 向导页(拖入目录→检测(等级展示)→提取预览→翻译配置→注入打包);首启向导 + API 连接自检(真实小请求);**设置页(API/工具箱/镜像/实验开关,FR-F6)**;翻译进度页(进度/Token/ETA/暂停取消);只读问题列表(类型筛选/跳转,FR-F4);DPAPI 存储 API key;工程文件持久化;错误提示人话化(错误码→文案映射复用 CLI)。
*注:v0.1 聚焦交付端到端流水线可用性(FR-A/B/C/E/F/G 的基础能力),上游字典深度定制(FR-D4)与问题状态管理(FR-D6)明确排入 M4 作为 v1.0 特性交付。*

**DoD(= v0.1 发布)**:P2 画像用户(1 名未参与开发的测试者,无协助)按向导完成样例游戏全流程,卡点记录归档;首启向导+连接自检与错误码指引全量(GUI 侧);样例游戏加载补丁显示中文(含字体指引场景验证);产物含 TRANSLATION_NOTICE 与安装说明(及 LICENSE-THIRD-PARTY.txt);产品文案能力承诺评审通过(FR-B2);打包为可运行桌面程序(允许未签名,提供绕过 SmartScreen 说明)。

### M3 质量与编辑(3 周;专注于数据闭环与体验)

任务:
1. (前 2 周)**缓存锁定+增量重翻**:缓存条目新增 locked 字段;编辑器/CLI 写回 = 改 pre_zh + 锁定;增量重翻范围 = 非锁定且指纹变化;**缓存 schema 变更以向上游 PR 为第一交付形态**,PR 合入前本地 overlay;
2. (后 1 周)**双语对照编辑器 MVP**:句对网格(虚拟滚动)、按问题类型筛选、修改写回(经缓存)、只读问题跳转。

**DoD**:#113/#151/#154/#65 场景复现用例全部通过(改缓存不被覆写、输出同步、字典变更不触发全量重翻);编辑器修改后重翻不覆盖已改行。

### M4 智能化集成(1.5 周)

任务:集成/扩展上游条件字典与 GPT 字典人设能力(称呼/代词场景,#120/#179 方向,**不重造**,FR-D4);**问题状态管理**(确认/忽略/白名单,与缓存行双向联动,#205,FR-D6);**术语一键提取向导**(FR-D7);**任务队列与完成通知**(前端轻量调度器排队 + Tauri 原生通知,FR-F7)。
*范围调整(第三轮审查 MAJ-D 方案 A):TEaR 闭环与 prompt 缓存分层**默认移出 v1.0**(FR-H1/H2),作为 v1.0 后首个实验版交付,有余力回填;prompt 分层实现载体限定为上游 PR 或上游 prompt 插件扩展点(MAJ-E),不直改。*

**DoD**:集成功能在上游原生入口同样可用;术语向导按 FR-D7 AC 通过;≥2 项目排队顺序执行且完成触发系统通知;TEaR/成本包不在 v1.0 验收范围。

### M5 Unity 最小版(2 周)

任务:**spike:UnityPy(首选)vs AssetsTools.NET 实测定案**(同一样例游戏:TextAsset 定位/读取/修改/save 写回/重打包验证);unity.yaml(TextAsset+TypeTree,L3 起步,spike 通过后升 L1)含 **Unity 检测规则与 Il2Cpp 识别→XUAT 引导文案(FR-A5)**;**写回前强制自动备份 + restore 步骤**;AssetRipper 定位链接入;Il2Cpp→XUAT 引导文档;Unity 样例游戏(用户合法持有)端到端。

**DoD**:Unity 样例端到端(或明确降级 L3 并产出指引);破坏性操作前备份存在且 restore 验证通过;不支持场景文档化。

### M6 发布(3 周)

任务:PyInstaller(后端,以 Tauri sidecar 托管、退出级联结束;启动自检 12333 端口占用→E-BACKEND-PORT-BUSY)+ Tauri bundler(前端)一键安装器;自动更新(Tauri Updater + latest.json;NSIS/MSI 清单一致性检查);**THIRD-PARTY-NOTICES 与工具 license 审计收尾**(GARBro/KrkrExtract 等标注"未核实"者核实;DumpInjector 澄清结论落地);新手文档(图文向导)+ 示例工程 + FAQ(杀软误报/缺字/加密游戏);CI 完善(E2E 样例游戏流水线);版本策略落地(详见 §4)。

**DoD(= v1.0 发布)**:干净 Windows 虚拟机从安装到产出补丁全程无障碍;requirements §10 全部版本级 AC 通过;license 审计表 100% 有结论;**允许无签名发布**,发布说明公示 SmartScreen 风险与绕过方法(签名证书列入后续规划)。

---

## 4. 运营流程与版本策略

### 4.1 版本策略
- 分支:`main`(发布)+ `develop`;里程碑末从 develop 切 release;
- 版本号(semver):CLI alpha 里程碑发布 = `0.1.x`;v0.1 里程碑发布 = `0.2.0`;v1.0 里程碑发布 = `1.0.0`;对外沟通一律使用 semver,"v0.1/v1.0"仅为内部里程碑代号(避免 0.2.0 发布物被称为 v0.1 的混淆);
- 上游基线 tag 记录于仓库 `UPSTREAM.md`(当前:GalTransl v7.4.0)。

### 4.2 上游同步与贡献
- 每里程碑末检查上游 release;升级 = 评估 diff + overlay 回放;
- 计划向上游提交的 PR:缓存锁定位与增量重翻、CORS 收敛、错误指引增强、(若接受)EngineProfile 机制;
- PR 合入上游后移除对应 overlay,并在 UPSTREAM.md 记录。

### 4.3 社区运营
- issue 模板:引擎适配请求(强制附引擎特征信息)/ 报错(强制附错误码)/ 功能建议;
- 引擎适配请求处理路径:查 msg-tool 覆盖 → SExtractor 预设 → 引导社区按 profile schema 贡献(文档提供模板与教程)→ L4 兜底;
- 发布渠道:GitHub Releases + 文档站(新手向导为主页)。

---

## 5. 风险登记册

| 风险 | 概率 | 影响 | 对策 | 责任里程碑 |
|---|---|---|---|---|
| 加密 xp3/引擎变体提取失败 | 高 | 中 | per-game 覆盖;SExtractor L2 兜底;L4 手动接 JSON;等级如实告知 | M0–M1 |
| SExtractor 导入编码限制 | 中 | 中 | L2 预检;失败明确降级 L3;限制文档化 | M1 |
| msg-tool 参数与预期不符 | 低 | 高 | M0 round-trip 实测先行;必要时 fork 工具 | M0 |
| 上游后端协议与假设不符 | 中 | 中 | M0 协议调研;architecture §4 预留修订 | M0 |
| 缓存改造与上游冲突 | 中 | 中 | PR 优先+overlay;后端锁 tag | M3 |
| v7 前端 churn | 中 | 低 | 前端不 merge;选择性摘取修复 | 持续 |
| Unity 场景碎片化 | 高 | 中 | 收敛 TextAsset+TypeTree;备份可恢复;XUAT 兜底;spike 降低押注 | M5 |
| 杀软误报 version.dll | 高 | 低 | 误报指引随产物输出;文档说明 | M1/M6 |
| 工具下载国内不可达 | 中 | 中 | 镜像+校验和;GPL 镜像附源码;离线模式(自备) | M1 |
| 无签名发布被 SmartScreen 拦 | 高 | 低 | 发布说明公示+绕过指引;签名证书列入后续规划 | M6 |
| 单人兼职进度滑期 | 中 | 中 | 诚实估算已含缓冲;Unity 可降级 L3;TEaR/成本包可裁;每发布点可用 | 全程 |
| DumpInjector license 矛盾 | 低 | 低 | M0 澄清;不可用则自研薄封装(msg-tool 本身能力足够) | M0 |

---

## 6. 需用户提供 / 决策的事项

| 事项 | 说明 | 截止 |
|---|---|---|
| 三份文档评审 | requirements / architecture / development-plan | M0 开工前 |
| 本地回归样例游戏 | 2-3 款合法持有的 Kirikiri 游戏(M1/M2 用;不入库不分发) | M0 期间 |
| L2 验证用长尾引擎样例 | 1 款 SExtractor 预设/BIN 覆盖范围内的非 Kirikiri 引擎游戏(FR-C5 用;不入库不分发) | M1 末前 |
| Unity 样例游戏 | 1-2 款合法持有的 Mono/TextAsset 类游戏(M5 用) | M4 末前 |
| 模型偏好 | 首发默认适配的 API(DeepSeek/OpenRouter/Sakura 本地端点等)与示例 key | M2 前 |

---

## 7. 排期备忘

- 文档中所有外部工具 CLI 参数在 M0 实测前均为占位,不得照抄进代码;
- "周"为兼职人周的近似单位;每里程碑末做一次 re-baseline,滑期时按序裁剪:TEaR/成本包(已默认移出 v1.0)→ M5 Unity 降级 L3 → 编辑器 MVP 收窄,**不裁 M2/M3/M6 的验收标准**;
- v0.1(W11)与 v1.0(W20.5)之间 9.5 周装载 M3+M4+M5+M6;M4 经第三轮审查按方案 A 收敛(FR-D4/D6/D7 + FR-F7 共 4 项,TEaR/成本包移出),M5 为 Unity 最小版,若再滑期按上条裁剪。
