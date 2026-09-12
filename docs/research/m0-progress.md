# M0 工程启动 · 进度报告

| 项 | 内容 |
|---|---|
| 日期 | 2026-09-12(M0 开工日,第一阶段完成) |
| 基线 | GalTransl tag 7.4.0(fd911be),fork:JunjieLin98/GalTransl |
| 关联 | [upstream-backend-protocol.md](upstream-backend-protocol.md) · [toolchain-verification.md](toolchain-verification.md) · [../development-plan.md](../development-plan.md) M0 |

---

## 任务状态总览

| # | M0 任务(计划原文) | 状态 | 产出/说明 |
|---|---|---|---|
| 1 | Fork+clone,跑通 v7 CLI 与桌面端 | ✅ 大部分完成 | fork `JunjieLin98/GalTransl` 已建;本地 main=7.4.0/develop 工作线;**后端实测运行成功**(Python 3.13.3 venv,`/api/version` 响应);CLI 入口 `run_GalTransl.py --help` 正常;桌面端 exe 未启动实测(见遗留#3) |
| 2 | 上游后端协议调研+打包态 Origin | ✅ 静态+实测完成 | 《协议笔记》:路由/端点清单/任务模型/进度机制/缓存 schema/安全实测(三项漏洞实锤)。**打包态 Origin 实测移至 M2 打包时**(机制已在 architecture §4.1,无阻塞) |
| 3 | 工具链验证报告 | ✅ 核心完成 | msg-tool v0.4.0-alpha.3 **KS export/import + GBK 编码 + XP3 pack/unpack 字节级 round-trip 全部通过**;Xp3Pack patch.xp3 链路通过;SExtractor 静默模式确认;profile 参数模板固化表已产出 |
| 4 | DumpInjector 许可证澄清 | ✅ 完成 | LICENSE 文件为准 = **GPL-3.0**(此前"README 写 MIT"为误导);与本项目同源无冲突;不复用、不分发 |
| 5 | 自建 krkr 样例游戏(kag3_blank 裁剪) | ⏳ 未开工 | 依赖 Xp3Pack/KAG3 模板工程搭建;工具已就绪,下一步执行(预计 0.5-1 天) |
| 6 | 真实游戏本地回归样例 | ✅ 完成 | 用户已提供 3 款(マガルミナ/Relirium/とける風花),勘查档案见 [sample-games.md](sample-games.md):①krkrz+PSB(L1 主力,自动解密+append2 递增分支)②Yu-ris 纯文本场景(L1 长尾,FR-C5)③强加密(E-UNPACK-ENCRYPTED-XP3 真实指引案例);**三款正好覆盖 L1/长尾/兜底三条验收线** |
| 7 | CI 骨架 | ✅ 完成 | `.github/workflows/ci.yml`(backend pytest 3.11+3.13 matrix / frontend build);**发现并绕过上游 8 项自带测试回归**(见 UPSTREAM.md,待向上游反馈) |
| 8 | PatchProject 路径语义定稿 | ✅ 已在架构文档 | architecture §3.4(schema_version/E-PROJECT-GAME-MISSING),M1 编码时按协议笔记校准 |
| 9 | xp3-brute 寻找与实测(计划外,用户指令) | ✅ 完成 | 源码构建成功(配方见 toolchain-verification §4.5);**样例 3 强加密 data.xp3 全解**(826/826,真名恢复)→ 三款样例全部 L1,M0 完成度 100% |

## 关键实测发现(影响后续里程碑)

1. **DNS Rebinding 漏洞实锤**:恶意 Host 头(evil.com)请求后端返回 200+数据 → Host 白名单中间件必要性确认,实现点锁定 `server.py` L906-911;
2. **X-Local-Token 必须扩 ACAH**:上游预检仅放行 `Content-Type`,自定义鉴权头会被预检拦截 → M2 实现时同步修改 `Access-Control-Allow-Headers`;
3. **GBK 编码为 Kirikiri 注入硬要求**:SJIS 输出下简体字丢字实证 → profile 默认 `encoding_mode: gbk` 有了实测依据;
4. **上游任务模型可复用**:`RUNTIME_REGISTRY`(单活跃 Job/request_project_stop)可直接扩展承载我们的流水线步骤,JobRegistry 不另造;
5. **msg-tool 有正式 release**(推翻"需 cargo build"的旧调研)→ 无 Rust 工具链依赖;但注意 v0.4.0 为 **alpha**,已锁定版本+SHA256;
6. **上游自带 8 项测试回归**(max_api_retries 未定义,tag 与 main 均有)→ CI 已 ignore 并留痕,列入"待向上游反馈"清单;
7. **上游已实现 #205 的 skip_check/单句过长检测** → FR-D6(问题状态管理)M4 设计时须评估复用,避免重叠。

## 遗留与机制

| 遗留项 | 机制 | 归属 |
|---|---|---|
| 打包态 WebView Origin 实测 | M2 打包时实测,回填 CORS 白名单(architecture §4.1) | M2 |
| 桌面端 exe 启动实测 | M2 GUI 开工前执行(需下载 release 或本地 Tauri 构建) | M2 前 |
| BIN 导入回填 live 实测 | M1 长尾样例游戏到位后(plan §6:M1 末前) | M1 |
| 样例游戏(kag3_blank 裁剪 <5MB) | 工具已就绪,单独工作段执行 | M0 收尾 |
| 真实游戏样例 ×3 | ✅ 已提供并勘查(sample-games.md) | 完成 |
| 上游 8 项测试回归反馈 | 向上游提 issue/PR(我们的首次上游贡献机会) | M1 期间 |

## 环境记录

- Python 3.13.3 venv(`.venv/`)——上游标注 3.11.9,3.13 服务端/CLI/29+ 测试实测可用;CI 矩阵保留 3.11+3.13 双轨;
- 工具缓存:`tools/bin/`(已 gitignore):msg_tool.exe(62fe3967…ab5d)、Xp3Pack.exe(c6f4a6f4…7cb6)、version.dll(52745037…358d);
- 分支:main=7.4.0(锁定)、develop=工作线;文档与 M0 产物当前为未提交状态,提交/推送节奏待用户指示。
