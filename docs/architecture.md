# galTrans 架构设计

| 项 | 内容 |
|---|---|
| 版本 | v1.0(基准,经独立审查修订) |
| 日期 | 2026-09-12 |
| 关联 | [requirements.md](requirements.md) · [development-plan.md](development-plan.md) |
| 状态 | 独立审查通过,作为 M0 正式开工依据 |
| 上游基线 | GalTransl v7.4.0(GPL-3.0) |

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│ 桌面 GUI(Tauri + React,fork 自上游 v7 desktop/)          │
│ fork 自有资产,不随上游 merge                              │
│ 本项目增量:补丁工作台向导 / 双语编辑器 / 只读问题列表 / 设置页 │
├─────────────────────────────────────────────────────────┤
│ 本地后端 = 扩展上游 12333 后端进程(禁止另起第二个服务)        │
│ 上游现状:stdlib http.server 手写 REST,已含 SSE 通道,       │
│ 无 WebSocket,CORS *;本项目新增端点沿用其风格并强化安全:     │
│   · 后端第一道中间件强制校验 HTTP Host 头等于               │
│     localhost:12333 或 127.0.0.1:12333(彻底防御 DNS Rebind) │
│   · 所有新增"写操作"端点强制本地鉴权 token(X-Local-Token)   │
│   · CORS 允许 Origin=M0 实测白名单(dev:127.0.0.1:1420;打包:tauri.localhost)               │
├─────────────────────────────────────────────────────────┤
│ 编排层 galtrans_pipeline(本项目核心新增 Python 包)          │
│   EngineProfile 注册表 · Orchestrator 状态机 · JobRegistry  │
│   Toolbox(托管表/校验/下载/镜像) · PatchProject · restore   │
├──────────────────────────┬──────────────────────────────┤
│ profiles/(声明式 YAML)    │ GalTransl 翻译核心(上游代码)    │
│   kirikiri.yaml (L1/L2)  │ 算法层:零侵入                  │
│   unity.yaml   (L3 起步)  │ 缓存/存储层:受控改造(PR 优先     │
│   per-game override       │ + 本地 overlay 维持可 merge)    │
├──────────────────────────┴──────────────────────────────┤
│ 外部工具箱 tools/(不随仓库分发:按需下载+SHA-256+国内镜像)     │
│ msg-tool(骨干) · SExtractor(兜底) · VNTextPatch ·         │
│ KirikiriTools(可选) · DumpInjector(许可澄清后定) ·         │
│ UnityPy/AssetsTools.NET(M5 spike) · AssetRipper ·         │
│ GARBro:自备或托管下载 · KrkrExtract/xp3-brute 自备(解密)     │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 与上游 GalTransl 的关系(三层边界策略)

| 层 | 策略 | 理由 |
|---|---|---|
| **翻译算法层**(LLMTranslate/后端/提示词/词典逻辑) | **零侵入**:只调用,不修改;通用性改进向上游提 PR;实验性 prompt 缓存分层仅可经上游 PR 或上游 prompt 插件扩展点实现,不直改 | 保持可 merge 性 |
| **缓存/存储层**(Cache.py 及序列化格式) | **受控改造**:缓存锁定位与增量重翻指纹是本项目核心增量,改动以"向上游 PR"为第一交付形态;PR 合入前以本地 overlay 补丁叠加,并锁上游 tag 保证 overlay 不漂移 | 直改不可避免,但必须可回溯、可上游化 |
| **前端(desktop/ Tauri+React)** | **fork 自有资产,不做上游 merge**:本项目在 fork 初始即建立自己的前端分支线,只选择性摘取上游 GUI 修复 | 上游 v7 刚发布、churn 大,前端 merge 成本远超收益 |

版本策略:
- Python 后端与核心:**锁定上游版本 tag**(v7.4.0 起步),升级 = 显式评估 + overlay 回放,不跟踪 main;
- 定期(每里程碑末)检查上游 release 与安全修复;
- 向上游贡献的 PR 列表在 development-plan.md §4 维护。

---

## 3. 模块设计(galtrans_pipeline 包)

```
galtrans_pipeline/
  __init__.py
  profile.py        # EngineProfile 加载/校验/注册表
  detect.py         # 引擎检测(特征规则引擎)
  orchestrator.py   # 流水线状态机
  jobs.py           # JobRegistry:任务注册/取消/进度广播
  toolbox.py        # 外部工具定位/校验/下载/镜像
  project.py        # PatchProject 工程文件
  steps/            # 各步骤实现(unpack/extract/inject/package)
  errors.py         # 错误码与指引文案
profiles/           # 引擎适配 YAML(数据,非代码)
  kirikiri.yaml
  unity.yaml
```

### 3.1 EngineProfile Schema

```yaml
profile: kirikiri              # 唯一标识
capability: L1                 # L1|L2|L3|L4(见 3.3)

detect:                        # 引擎检测特征(加权命中)
  archives: ["*.xp3"]          # 封包后缀
  files: ["Config.tjs"]        # 特征文件(可选)
  min_score: 2                 # 命中阈值
  hints:                       # 弱信号,只提示不参与判定
    - "xp3 加密过滤器可能存在(加密游戏需自备解密工具)"

constraints:                   # 约束(向导据此提示)
  encoding_in: shift-jis       # 源编码
  encoding_mode: gbk|sjis_replace   # 中文回填模式(向导选项,默认 gbk)
  max_text_length: null        # 定长限制;未知为 null(注入时预检)
  ruby: true                   # 是否存在注音控制符
  font_check:                  # 缺字风险预检
    scripts: ["Config.tjs"]
    keywords: ["defaultFont", "font.face"]

unpack:                        # 步骤=工具+参数模板(占位符见下)
  tool: msg-tool
  mode: batch                  # batch(推荐,整目录/通配符单次调用)或 file_loop(逐文件循环+细粒度进度)
  size_factor: <默认值,M0 实测校准>  # 解包膨胀系数(E-DISK-SPACE-FULL 预警依据)
  args: "<以 M0 CLI 实测为准> unpack {archive} -o {out_dir}"

extract:
  tool: msg-tool
  mode: batch
  args: "export {script} -f <galtransl-json> -o {out_file}"

inject:
  tool: msg-tool
  mode: batch
  args: "import {script} -i {trans_file} <M0 实测参数>"

package:
  strategy: patch_xp3 | repack | loose_override
  version_dll: auto            # 需要免封包绕过时随产物分发 KirikiriUnencryptedArchive
  patch_sequence: auto         # 游戏已有 patch.xp3 → 自动 patch2.xp3 递增

extraction_fallback:           # 提取兜底(SExtractor)
  tool: sextractor
  args: "<M0 实测>"
inject_fallback:               # 导入兜底(SExtractor trans_replace;受编码限制)
  tool: sextractor
  args: "<M0 实测>"

per_game_override: {}          # 用户按游戏覆盖任意上述字段(优先级最高)
```

参数模板占位符:`{game_dir}` `{archive}` `{script}` `{out_dir}` `{out_file}` `{trans_file}` `{dist_dir}`。
**所有工具实际参数字符串以 M0《工具链验证报告》实测为准,本文档不预设虚构 CLI 语法。**

优先级:`per_game_override > profile > 默认值`。

### 3.2 能力等级(四级兜底矩阵)

| 等级 | 判定 | 自动化范围 | 失败行为 |
|---|---|---|---|
| **L1** | 专用工具具备 export+import(msg-tool 等) | 完整流水线 | 报错可重跑 |
| **L2** | SExtractor 专用预设/BIN 暴力正则的提取+导入 | 完整流水线(导入受编码限制) | 导入失败→**明确降级 L3** 并产出译文文件 |
| **L3** | 仅能提取 | 至翻译产出(译文 JSON + 人工回填指引) | — |
| **L4** | 无适配,用户自备 JSON | 仅翻译 | — |

向导必须据实展示等级与含义;产品文案不得承诺超出等级的能力(需求 FR-B2)。

### 3.3 流水线状态机

```
INIT → DETECT → UNPACK → EXTRACT → TRANSLATE → INJECT → PACKAGE → DONE
         │        │        │          │           │         │
         └────────┴────────┴──────────┴───────────┴─────────┘
                    任意步失败 → FAILED(错误码+指引)
                    任意步完成 → 产物落盘,可从该步重跑(幂等)
                    L3/L4 → 终止于 TRANSLATE 完成(产物含人工回填指引)
```

- 每步前置条件检查(上一步产物存在且校验通过);
- TRANSLATE 步骤委托上游 `doLLMTranslate`(经 JobRegistry 衔接,见 3.5);
- **TRANSLATE 完成判定**:全部输入文件均有对应 translated 产物且行数校验一致;部分文件失败 → 步骤态 FAILED 并列明失败文件清单,重跑经上游缓存仅补失败文件与新增行(FR-D3);INJECT 的前置条件包含 TRANSLATE 状态 = 完成;
- **破坏性写回的原子性(Unity 等模式)**:强制采用 **Staging + Atomic Rename** 策略:修改后的资源先在 `work/injected/` 生成临时文件并校验完整性,通过后再以原子重命名/移动方式替换原始文件;替换前源文件必须已完整镜像备份至 `backup/`;
- **restore(运维操作,非流水线步骤)**:经 `POST /api/pipeline/restore` 触发,将 `backup/` 文件全量还原回源游戏目录;仅允许**无活跃 Job** 时执行;执行后将 INJECT 及之后的步骤快照重置为未执行;以 backup/ 清单校验实现幂等;完成后写审计日志;backup/ 在 PACKAGE 成功后提示归档或清理;
- 取消:复用上游协作式取消机制(stop_event 轮询),JobRegistry 统一转发(外部进程通过 ProcessRunner 强杀,见 3.5)。

### 3.4 workspace 目录规范(PatchProject)

```
<project_dir>/
  project.yaml          # PatchProject:schema_version / 游戏路径 / profile / 覆盖项 / 步骤快照
  dict/                 # GPT 字典/条件字典文件落位(可被 per-game override 指向)
  work/
    unpacked/           # 解包产物
    extracted/          # gt_input/*.json(name-message)
    translated/         # gt_output/*.json
    injected/           # 回写后的临时文件(Staging 区域)
  cache/                # 上游 transl_cache(增量重翻数据源)
  backup/               # 被修改原始文件的强制镜像备份(Unity 破坏性写回前创建)
  dist/                 # 最终补丁:
                        #   - patch.xp3(或对应引擎补丁文件)
                        #   - version.dll(按需,KirikiriUnencryptedArchive)
                        #   - TRANSLATION_NOTICE(AI 翻译说明)
                        #   - LICENSE-THIRD-PARTY.txt(随附 version.dll 等外部组件的原作者版权与 MIT/GPL 许可)
                        #   - 安装说明.txt
  logs/
```

路径语义:project.yaml 记录游戏目录绝对路径;打开工程时校验其存在,缺失则报 `E-PROJECT-GAME-MISSING`(指引:重新指向游戏目录,workspace 内相对产物不受影响);`schema_version` 用于工程文件格式迁移。

### 3.5 JobRegistry 与外部进程管理

- **作业注册**:所有长任务(translate/inject/package)注册为 Job:`{id, project_id, step, cancel_event, progress_topic}`;
- **进度广播**:统一由 JobRegistry 广播到 SSE 通道(沿用上游 SSE 事件格式,新增事件类型:`step_started/step_progress/step_done/step_failed/log`);
- **取消与外部进程生命周期(ProcessRunner)**:
  - Python 内部原生翻译循环:设置 `cancel_event` → 上游 `stop_event` 轮询生效(≤2s);
  - 外部 CLI 子进程(如 msg-tool 执行 3GB 封包解包或多脚本回填):必须经由统一的 `ProcessRunner` 包装调用,记录活跃 PID;
  - 收到取消信号时,通过平台级进程树清理机制(Windows 下调用 `taskkill /F /T /PID {pid}` 或 `psutil.Process(pid).children(recursive=True)` 递归强杀),避免产生占用文件句柄的孤儿进程;
  - 取消完成后 Orchestrator 释放文件句柄并重置状态为 `CANCELED`;
- **多项目任务队列(FR-F7)**:由 Tauri 前端轻量调度器排队,按序向后端调用单个 `/api/pipeline/run`;步骤完成由 SSE 触发 Tauri 原生桌面通知(Notification API);后端保持单活跃工程执行原则,不引入复杂分布式调度器;
- 上游翻译进度(现有打字机/行级回调)在 TRANSLATE 步骤内桥接到 JobRegistry,不改上游签名。

### 3.6 错误码目录(每码 = 人话解释 + 可行动指引)

| 错误码 | 场景 | 指引(摘要) |
|---|---|---|
| E-DETECT-UNKNOWN-ENGINE | 未识别引擎 | 手动选择 profile / 提交 SExtractor 正则需求 / 社区 issue 模板链接 |
| E-UNPACK-ENCRYPTED-XP3 | 加密 xp3(解包零产物,回退解密工具不可用或仍失败) | 自备 xp3brute.exe 放入 tools/bin 后重跑 UNPACK(自动回退解密);或手动解包产物放入 work/unpacked/<封包名>/ 从 EXTRACT 续跑(责任自负声明) |
| E-UNPACK-NO-ARCHIVE | 无封包匹配 unpack.archives | 确认 game_dir;per-game override 调整 archives 模式;已解包目录形态从 EXTRACT 续跑 |
| E-EXTRACT-NO-SCRIPT | 未找到可提取脚本 | 列出已扫描模式;建议手动指定脚本 |
| E-EXTRACT-TOOL-MISSING | 工具未就绪 | 引导工具箱下载/镜像切换 |
| E-TRANSLATE-API-AUTH | 401/403 | 检查 key/endpoint 步骤指引 |
| E-TRANSLATE-RATE-LIMIT | 429/限流 | 自动退避中;建议降低并发/换 token |
| E-TRANSLATE-NETWORK | 超时/连接失败 | 代理设置指引 |
| E-INJECT-LENGTH-OVERFLOW | 译文超长 | 缩短建议/定长引擎截断选项(需确认) |
| E-INJECT-ENCODING-FAIL | 编码缺字(GBK 模式) | 切换 sjis_replace 模式/字体指引 |
| E-INJECT-IMPORT-FAIL | 导入器失败(L2) | 明示降级 L3,产出译文文件 |
| E-PACKAGE-FONT-MISSING | 缺字风险预检命中 | 中文字体替换指引(推荐字体+步骤) |
| E-PACKAGE-ANTIVIRUS | version.dll 疑似被杀软拦截 | 加白指引/误报说明 |
| E-TOOL-PROCESS-CRASH | 外部工具异常终止或挂起超时 | 排查杀软拦截/查看临时日志/尝试命令行重跑 |
| E-DISK-SPACE-FULL | 工作空间目标盘空间耗尽 | 提前预警(依据 profile 声明的解包膨胀系数预估体积)并阻断解包;清理磁盘指引 |
| E-AUTH-UNAUTHORIZED | 本地鉴权 Token 无效(被重置后失效)或 SSE 一次性票据过期 | 引导重新加载前端会话并刷新 Token |
| E-UNITY-IL2CPP | 检出 Il2Cpp | 引导 XUAT 外挂文本方案(文档链接) |
| E-BACKUP-RESTORE | 备份/恢复相关 | restore 步骤操作指引 |
| E-CACHE-BUSY | 翻译 Job 运行期间尝试写缓存 | 翻译进行中,请稍后修改或取消任务后再编辑 |
| E-PROJECT-GAME-MISSING | 工程记录的游戏目录不存在 | 重新指向游戏目录;workspace 产物不受影响 |
| E-BACKEND-PORT-BUSY | 12333 端口被残留后端进程占用 | 结束残留进程指引;安装器将后端托管为 Tauri sidecar(退出级联结束) |

---

## 4. 本地 API 设计(扩展上游 12333 后端)

新增端点(全部挂在 `/api/pipeline/*` 命名空间;风格沿用上游 http.server 手写路由):

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| GET | /api/pipeline/profiles | 已注册 profile 清单+能力等级 | 否 |
| POST | /api/pipeline/detect | `{game_dir}` → 检测结果+置信度 | 否 |
| POST | /api/pipeline/projects | 创建 PatchProject | **token** |
| PUT | /api/pipeline/projects/{id} | 更新覆盖项/配置 | **token** |
| POST | /api/pipeline/run | `{project_id, from_step?}` 启动流水线 | **token** |
| POST | /api/pipeline/cancel | `{job_id}` 取消 | **token** |
| POST | /api/pipeline/restore | `{project_id}` 将 backup/ 镜像全量恢复回源游戏目录 | **token** |
| GET | /api/pipeline/status/{project_id} | 步骤状态/产物清单 | **token** |
| GET | /api/pipeline/events | SSE 进度流(复用上游通道格式,新增事件类型;鉴权用一次性短时票据换取、即用即弃,日志对 query 脱敏) | token(query) |
| GET/PUT | /api/pipeline/font-check | 字体预检结果与指引 | **token** |

### 4.1 安全防御体系

1. **Host 白名单校验(阻断 DNS Rebinding,修复 BLK-01)**:
   - Python 后端入口第一道中间件强制检查 HTTP Request Header `Host`;
   - 其值必须严格等于 `localhost:12333` 或 `127.0.0.1:12333`(或实际绑定的本地端口);
   - 任何带外部域名(如 `evil.com`)、局域网 IP 或非法 Host 的请求,直接响应 **HTTP 403 Forbidden**,彻底切断跨域 DNS Rebind 穿透本地服务的攻击面。
2. **本地 Token 鉴权**:
   - 首启时 GUI 生成高熵随机 Token,DPAPI 加密落盘;Token 为长期凭据(无 TTL),可在设置页手动重置;
   - 后端启动读取校验,所有写操作与敏感状态端点强制校验 `X-Local-Token` 请求头;
   - DPAPI 异常平滑降级:遇提权/跨用户导致解密失败时,弹窗引导手动重新生成会话 Token;**API key 解密失败同理,弹窗引导重新输入(原密文作废,不迁移)**,避免进程崩溃退出。
3. **CORS 收敛**:
   - 从上游默认的 `CORS *` 收敛为**精确 Origin 白名单**,清单以 M0《上游后端协议笔记》实测为准:开发态 `http://127.0.0.1:1420`;打包态 Tauri v2(Windows)实测为 `http://tauri.localhost`(无端口);清单外 Origin 一律拒绝。

---

## 5. 编辑器 ↔ 缓存数据流(v1.0,解上游 #113/#151/#154)

```
双语编辑器(句对网格)
   │ 修改译文
   ▼
写回操作 = 修改缓存条目 pre_zh + 置人工锁定位 locked=true   ← 受控改造缓存层
   │
   ▼
输出重建:输出文件由缓存全量重建(缓存为唯一事实源)
   │
   ▼
增量重翻范围 = 非锁定 且 指纹(post_jp+字典版本)变化 且 未被标记忽略/白名单(FR-D6) 的行
   └─ 已锁定行永不重翻;字典变更不再触发全量重翻(#65);问题状态与缓存行的联动存储随 M4 落地
```

**单写者原则(数据完整性)**:
1. 活跃翻译 Job 运行期间,编辑器写回被拒绝并返回 `E-CACHE-BUSY`(v1.0 取拒绝策略,简单可靠);
2. 缓存落盘一律"临时文件 + 原子替换",杜绝半写损坏;
3. 项目目录维护 `cache.lock` 进程级锁:CLI 与 GUI 双进程并发打开同一工程时,后到者拒绝并给出指引。

约束:缓存 schema 变更(新增 locked 字段)以向上游 PR 形态提交;overlay 期间向后兼容读取旧缓存。

---

## 6. 外部工具托管表

| 工具 | 用途 | License | CLI | 来源 | 版本策略 | 获取 |
|---|---|---|---|---|---|---|
| msg-tool | 解包/提取/注入/打包(骨干) | GPL-3.0 | 有 | lifegpc/msg-tool | pin + SHA-256 | 按需下载+国内镜像(附源码链接) |
| SExtractor | L2 兜底提取+导入 | GPL-3.0 | 待 M0 实测(README 为 GUI/run.py,命令行调用方式待验证) | satan53x/SExtractor | pin | 按需下载 |
| VNTextPatch | 提取/注入(备选) | MIT | 有 | arcusmaximus/VNTranslationTools(**2023-06 归档**) | pin+SHA-256 | 下载 |
| KirikiriTools(Xp3Pack/免封包 DLL) | patch.xp3 打包/version.dll | MIT | 有(`Xp3Pack patch` 等) | arcusmaximus/KirikiriTools(**2023-06 归档**) | pin | 随产物分发 version.dll |
| GalTransl_DumpInjector | 官方 org 的提取/注入 GUI | **MIT(README)/GPL-3.0(仓库标注)矛盾,M0 澄清** | 无(GUI) | GalTransl/GalTransl_DumpInjector | M0 决定是否复用/纳管 | 待定 |
| AssetRipper | Unity 资源定位/导出(FR-C6) | GPL-3.0 | 有 | AssetRipper/AssetRipper | pin+SHA-256(或文档指引自备) | 按需下载+镜像(GPL 附源码链接) |
| UnityPy | Unity TextAsset 读写(首选候选) | MIT | Python 库(pip) | K0lb3/UnityPy | pip 锁版本 | pip |
| AssetsTools.NET | Unity 读写(备选) | MIT | 需自写薄 CLI | nesrak1/AssetsTools.NET | M5 spike 对比后定 | 按需 |
| GARBro | 解包浏览/导出 | MIT | 主程序 GUI(console 子项目已弃更) | morkt/GARbro | 用户自备或托管表下载 | 文档指引 |
| KrkrExtract / xp3-brute | 加密 xp3 提取 | GPL-3.0 | — | xmoezzz 系 | **不分发,用户自备** | 文档指引 |
| KirikiriUnencryptedArchive(version.dll) | 免封包绕过 | MIT(随 KirikiriTools) | — | 同上 | 随产物分发(仅需要时) | 打包 |

镜像策略:GitHub Release 直链为主,国内可达性通过镜像站/CDN 前缀可配置;GPL 工具镜像页必须附源码获取链接;所有下载强制 SHA-256 校验(托管表记录期望值)。

---

## 7. 端到端数据流(kirikiri,L1 为例)

```
游戏目录 ─detect→ kirikiri(L1)
   ─unpack(msg-tool)→ work/unpacked/*.ks
   ─extract(msg-tool)→ work/extracted/*.json(name+message)
   ─translate(上游 doLLMTranslate,词典/缓存/反思)→ work/translated/*.json
   ─inject(msg-tool)→ work/injected/*.ks
   ─package(msg-tool pack 或 Xp3Pack)→ dist/patch.xp3(+version.dll)
                                        + TRANSLATION_NOTICE + 安装说明
```

---

## 8. 测试策略

| 层 | 内容 |
|---|---|
| 单元测试 | 状态机转换/幂等、profile 解析与覆盖优先级、错误码映射、JobRegistry 取消、token 鉴权、DPAPI 存取 |
| 合约测试(stub LLM) | 固定确定性 stub LLM 驱动 galTrans 管线与上游 CLI,断言输出 JSON 结构/行映射一致(FR-D1);缓存并发互斥与原子替换断言(E-CACHE-BUSY/单写者原则) |
| 合约测试 | 工具 wrapper:用固定小样本对 msg-tool/SExtractor 的 export/import 做 round-trip 断言(M0 实测后固化) |
| E2E | **自建 krkrz/KAG3 开源样例游戏**(合法可分发,入仓库供 CI)+ 2-3 款真实游戏本地手动回归(不入库、不分发,清单见开发计划) |
| GUI | 关键向导流程手动回归 checklist;SSE 进度一致性断言 |

---

## 9. 演进路线

- Unity:L3(译文产出)→ L1(TextAsset+TypeTree 自动回封,spike 定 UnityPy/AssetsTools.NET);
- 新引擎:优先评估 msg-tool 覆盖面(20+ 引擎),其次 SExtractor 预设,L4 永远兜底;
- 上游合流:缓存锁定位 PR、CORS 收敛 PR、错误指引增强 PR——合入后移除对应 overlay;
- 多目标语言(#187 方向):中间格式已语言无关,属于 profile/prompt 层扩展,暂不排期。
