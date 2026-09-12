# 工具链验证报告(M0 实测)

| 项 | 内容 |
|---|---|
| 实测日期 | 2026-09-12 |
| 实测环境 | Windows 10 x64 / Python 3.13.3 / 无 cargo |
| 效力 | 本报告为 M1 编写 EngineProfile 参数模板的唯一依据;architecture.md 中"以 M0 实测为准"占位符由此报告固化 |

---

## 1. msg-tool:v0.4.0-alpha.3(x86_64-pc-windows-msvc)

- **来源修正**:此前调研称"无正式 release,需 cargo build"已过时——实测 **30 个 release,最新 v0.4.0-alpha.3(2026-06 构建)**,Windows x64 zip 直下可用。`tools/bin/msg_tool.exe`(SHA256 前 16 位:`62fe396780468200`,完整值入托管表)。
- Kirikiri 覆盖(实测确认):`kirikiri`(KS)、`kirikiri-scn`、`kirikiri-xp3`(归档)、`--kirikiri-name-commands`(人名指令)、`--kirikiri-message-commands`、`--kirikiri-ks-hitret`(Talk~Hitret 区间提取,可自动检测)、`--kirikiri-ks-lf/bom`、xp3 加密参数(`--kirikiri-xp3-game-title` 等)。

### 1.1 KS export → import round-trip(实测通过)

```
样本:合成 Shift-JIS .ks(消息 4 行,含「」会话行、[clean]/[np] 标签)
export: msg_tool.exe export -t kirikiri sample_sjis.ks out_json
  → [{"message": "..."}] JSON 列表(与人名分离需按游戏传 --kirikiri-name-commands,记入 per-game 覆盖)
import: msg_tool.exe import -t kirikiri --patched-encoding gbk sample_sjis.ks translated.json patched.ks
  → 结构保持,指令正确处理([np] 自动补页);OK:1 Error:0
```

**编码约束实证**:默认 SJIS 输出下,简体专用字(这/测/话)写为 `?`;`--patched-encoding gbk` 后 100% 正确。**结论:Kirikiri 注入链必须以 GBK 输出为默认档**(与 architecture `constraints.encoding_mode: gbk` 设计一致,现有了实测依据)。

### 1.2 XP3 pack → unpack round-trip(实测通过,字节级一致)

```
pack:   msg_tool.exe pack -t kirikiri-xp3 <dir> test.xp3     → OK:1(233B)
unpack: msg_tool.exe unpack -t kirikiri-xp3 test.xp3 out_dir  → OK:2,文件字节级一致(diff 通过)
```

**注意两点**(记入 profile/编排层):
1. `pack` **默认不递归子目录**(合成目录含 sub/res.txt 未被打入)——编排层必须显式枚举文件清单传给 pack;
2. `export -t kirikiri-xp3` 会对包内 .ks 尝试按 SJIS 解析,GBK 脚本报 `Failed to decode Shift-JIS`——**校验/解包归档用 `unpack` 命令,不要用 `export`**。

## 2. KirikiriTools v1.7(MIT,已归档;实测通过)

- 下载:`Xp3Pack.exe`(SHA256 前 16 位 `c6f4a6f4d74cd293`)、`version.dll`(免封包代理 DLL)、`KirikiriDescrambler.exe`;
- **用法实测**:`Xp3Pack.exe <folder>` 在**当前工作目录**生成 `<folder名>.xp3`;官方用法 = 补丁目录命名为 `patch` → 生成 `patch.xp3`(253B);
- 互验:`msg_tool.exe unpack -t kirikiri-xp3 patch.xp3` 可读取且字节一致——**patch.xp3 产物链路验证通过**(XP3PATCH_ROUNDTRIP_OK);
- 对 architecture 的影响:`package.strategy: patch_xp3` 的真实形态 = "Xp3Pack + 名为 patch 的工作目录 + cwd 控制",profile 参数模板据此编写;`version.dll` 随 dist 分发时的 SHA256 固定值已可入托管表。

## 3. SExtractor v5.2.0(GPL-3.0,活跃;CLI 形态确认)

- `run.py` 支持**静默提取模式**:`python run.py -e <路径>`(silentMode)+ 可传默认目录;完整能力由 `text_conf.json` + `预设正则.*.ini` 配置驱动;
- **非真 CLI**(PyQt5 QApplication 必需):用户机(有桌面会话)可静默运行;**CI 无头环境不可直接跑**,L2 的 CI 用例需 mock 或标记 skip;
- 引擎预设目录(`tools/`)含 AGSI/AZSystem/AST/AdvHD_WillPlus 等 40+ 子目录,是 L2 覆盖面的直接来源;
- **对本项目结论**:L2 集成路径 = Toolbox 写 per-game `text_conf.json` → `run.py -e` → 收取 JSON 产物(8 种格式含 `{name,message}`,直映 GalTransl)。**BIN 导入回填的 live 实测待 M1 用长尾样例游戏执行**(plan §6 已排"M1 末前"样例),本报告记录调用方式与限制。

## 4. GalTransl_DumpInjector(官方 org;许可证澄清)

- **LICENSE 文件为 GPL-3.0**(GitHub license 字段与 LICENSE 文件一致;此前"README 写 MIT"为 README 陈述误导,**以 LICENSE 为准**);与本项目 GPL-3.0 同源,**无许可冲突**;
- 复用评估:其本体为 ttkbootstrap GUI,内层封装 msg-tool/VNTextPatch/正则模式——本项目编排层直接调用 msg-tool(已实测),GUI 封装无复用必要;其"正则模式"的 per-game 配置样例可作为 L2/长尾适配的参考语料;
- 托管表结论:**不纳入工具分发**(与上游同 org 的 GPL 工具,用户可选);architecture §6 行更新为"许可已澄清:GPL-3.0;不复用、不分发"。

## 4.5 xp3-brute(加密 xp3 提取;本地自用;**实测攻破样例 3**)

- 定位:xmoezzz/xp3-brute(KrkrzExtract 作者的现代替代),**跨平台、无需运行游戏**(逆向+Win32 模拟+符号执行+暴力),用法 `xp3brute unpack data.xp3 out`;
- **license = null(仓库无许可证文件)= 保留所有权利**:与 KrkrExtract/xp3-brute 系"用户自备、不分发"的合规定位一致——**二进制与源码不入仓库、不随工具箱分发**,本节仅记录本地自用构建配方;
- **构建配方**(2026-09-12 实测,依赖链完整记录):Rust 1.98.1(MSVC)→ VS Build Tools VCTools 工作负载(链接器)→ LLVM(libclang,bindgen 用)→ CMake + **Ninja**(unicorn-engine-sys 内置 C 构建必需)→ `cargo build -p xp3-brute --bin xp3brute --release`;注意 windows-gnu 工具链不可行(`windows-sys` 缺 dlltool);
- **实测结果(样例 3 とける風花 data.xp3,826 条目)**:`solved=826 unresolved=0`,真名与目录结构完整恢复(`scn/01.txt.scn`/`AppConfig.tjs`/`bgm/…`),生成 `xp3-meta.yaml` 完整元数据(v0.3.7,schema krkr-xp3-brute/xp3-meta-v1);解出 scn 为 mdf 包裹 PSB,msg-tool 透明解析;
- 用法要点:输出含 `xp3-meta.yaml`(元数据+策略声明,含"do-not-rehash-recovered-names");无声模式 `--no-progress`,`--verbose` 出逐条恢复证据。

## 5. 汇总:profile 参数模板固化表(M1 输入)

| profile 字段 | 实测值 |
|---|---|
| unpack.tool / args | `msg_tool.exe unpack -t kirikiri-xp3 {archive} {out_dir}` |
| pack.tool / args | `msg_tool.exe pack -t kirikiri-xp3 {file_list} {out_xp3}`(**文件清单显式枚举,不递归**) |
| extract.tool / args | `msg_tool.exe export -t kirikiri --kirikiri-remove-empty-lines [--kirikiri-name-commands <cfg>] [--kirikiri-message-commands <cfg>] [--kirikiri-ks-hitret auto] {script} {out_json}` |
| inject.tool / args | `msg_tool.exe import -t kirikiri --patched-encoding gbk {script} {trans_json} {patched}` |
| patch_xp3.tool / args | `Xp3Pack.exe {work_dir_name == "patch"}`,cwd = dist 上级 |
| constraints.encoding_mode | 默认 **gbk**(实测 SJIS 丢字) |
| 校验命令 | `msg_tool.exe unpack`(**禁用 export 做归档校验**,见 §1.2) |
| 版本锁定 | msg-tool v0.4.0-alpha.3 / Xp3Pack & version.dll v1.7(SHA256 见托管表) |

## 6. 遗留(均有机制,不阻塞 M1 开工)

1. BIN 导入回填 live 实测 → M1 长尾样例到位后执行(plan §6);
2. `--kirikiri-name-commands` 的真实游戏配置样例 → 随 M1 真实游戏回归采集;
3. 加密 xp3 解包(KrkrExtract/xp3-brute)→ 用户自备,工具箱只做存在性检测与指引(E-UNPACK-ENCRYPTED-XP3);
4. msg-tool alpha 版本风险:v0.4.0-alpha.3 为 alpha,托管表锁定该版本 + SHA256;若 M1 回归发现 bug,备选 pin 上一稳定 tag 重测。
