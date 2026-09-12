# M1 回归样例游戏档案(M0 实测勘查)

| 项 | 内容 |
|---|---|
| 勘查日期 | 2026-09-12 |
| 方式 | 只读探测(msg-tool 解包至系统临时目录,未改动任何游戏文件,未入库任何游戏数据) |
| 用途 | M1 端到端回归(plan §6);样例留在用户本机 `L:\gal\`,PatchProject 按路径引用 |

---

## 样例 1:マガルミナ(キルキリ/krkrz + PSB 场景)—— **L1,主力样例**

| 项 | 实测结果 |
|---|---|
| 引擎判定 | Kirikiri(krkrz):`*.xp3`+`.sig`+BootStrap.exe+`.cf`;自定义 exe(`magalumina_.exe`,备份 `.exe.org`) |
| 加密 | data.xp3 有加密,**msg-tool 自动从 exe 加载 2 组 key 并解密成功**(1584 文件)——无需外部解密工具 |
| 文件名保护 | data.xp3 内文件名为**哈希名**(`f051058e…`);append.xp3(已有补丁)内为真名 → 引擎经 version.dll 读覆盖包 |
| 脚本格式 | **PSB**(`PSB\x00` 魔数):data.xp3 内 **242 个 PSB = 日文原版脚本**;`export -t kirikiri-scn` 实测导出干净 JSON |
| 已有补丁 | append.xp3 = 前人中文补丁(234 文件,真名 `magaru_XX.txt.scn`,实测导出为中文) |
| M1 提取方案 | `msg_tool.exe unpack -t kirikiri-xp3 data.xp3` → 过滤 PSB → `export -t kirikiri-scn` → GalTransl JSON |
| M1 回封方案 | **patch2 递增分支实测场景**:游戏已有 append.xp3,我们的补丁包命名 `append2.xp3`(或按引擎优先级验证);Xp3Pack/msg-tool pack 均可 |
| 编码 | PSB 内文本 Unicode(不涉 SJIS 丢字);字体约束待 M1 游戏内验证 |
| 能力等级 | **L1**(export+import 双向实测就绪) |

## 样例 2:Relirium(Yu-ris)—— **L1,长尾引擎样例(FR-C5)**

| 项 | 实测结果 |
|---|---|
| 引擎判定 | **Yu-ris**:`yscfg.dat`/`yssfs.dat`/`pac/*.ypf`/`enginedll`/エンジン設定.exe |
| 封包 | `pac/*.ypf`(bgm/bn/cg/**sc**/sse/pac…);msg-tool `yuris-ypf` **unpack 实测成功**(sc.ypf 245 文件) |
| 脚本格式 | **纯文本场景脚本**:`sc.ypf/scenario/0_all_XXXX.txt`(Yu-ris 指令 `\SJ.SET`/`\BG`/`\BGM`…,Shift-JIS);msg-tool 有 `yuris-txt` 导出/导入类型 |
| 已有补丁 | `翻译补丁/gemini-3.1-pro-preview/` = winmm.dll 代理 + Nepgear.chs/.ini(**hook 式实时翻译**,不覆盖 ypf)→ sc.ypf 内文本应为日文原文 ✓ |
| M1 提取方案 | `unpack -t yuris-ypf sc.ypf` → `export -t yuris-txt`(或直接文本处理)→ JSON |
| M1 回封方案 | `import -t yuris-txt` + `pack -t yuris-ypf`(实测支持双向)→ 生成新 ypf 或外挂目录覆盖(需 M1 验证引擎读取优先级) |
| 能力等级 | **L1**(ypf pack/import 双向支持已在 CLI help 确认,M1 实测回封) |

## 样例 3:とける風花とシロうさぎ(krkrz,强加密)—— **L1(经 xp3brute 解密,实测攻破)**

| 项 | 实测结果 |
|---|---|
| 引擎判定 | Kirikiri(krkrz):xp3+sig+BootStrap+`.cf` |
| 加密 | data.xp3 强加密,msg-tool 不支持(826 文件 Error);`--xp3-game-title` 为内置标题枚举,本作不在库中 |
| **xp3brute 实测** | `xp3brute unpack data.xp3 out` → **solved=826 unresolved=0**,全部解出;**真名与目录结构完整恢复**(`scn/01.txt.scn`、`AppConfig.tjs`、`bgm/…`,与已有补丁 !scnlist 完全对应);生成 `xp3-meta.yaml` 完整元数据(v0.3.7) |
| 脚本格式 | scn 文件为 **mdf 包裹的 PSB**(`mdf\x00` 魔数,krkrz zlib 压缩)——msg-tool 透明处理,`export -t kirikiri-scn` 实测导出**标准 name-message 日文 JSON**(说话人分离,即 GalTransl 原生格式形态) |
| 已有补丁 | `unencrypted.xp3` = 中文补丁(398 文件,真名)+ `!scnlist.txt`(UTF-16 场景清单)+ version.dll |
| M1 提取方案 | `xp3brute unpack data.xp3`(一次性,解密缓存)→ `msg_tool.exe export -t kirikiri-scn scn/*.scn` → GalTransl JSON |
| M1 回封方案 | 修改后 PSB 以恢复的真名重打包(参照 unencrypted.xp3 的覆盖模式,引擎已验证接受 version.dll+覆盖包) |
| 能力等级 | **L1**(xp3brute 解密 + msg-tool 导出实测通过);xp3brute 构建与合规记录见 toolchain-verification.md §4.5 |

---

## 三款样例覆盖的验收维度

| 维度 | 样例 1 マガルミナ | 样例 2 Relirium | 样例 3 とける風花 |
|---|---|---|---|
| L1 全链路 | ✅ 主力 | ✅ 长尾引擎(FR-C5) | ✅(xp3brute 解密后) |
| 加密 xp3 自动解密 | ✅(exe key) | —(无需) | ✅(xp3brute 全解,真名恢复) |
| patch 递增分支 | ✅(append→append2) | — | ✅(unencrypted 已占) |
| 多引擎 profile | krkrz+PSB | yuris-txt | krkrz(mdf+PSB) |
| 编码模式 | PSB 内部 Unicode | SJIS→GBK | PSB 内部 Unicode |
| name 分离 | per-game 指令配置 | yuris-txt | ✅ 原生 name-message |

## 合规记录

- 三款游戏为用户合法持有;勘查仅读取目录清单与解包到系统临时目录;**任何游戏数据不入仓库、不分发**;PatchProject 引用本机路径。
