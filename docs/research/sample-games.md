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

## 样例 3:とける風花とシロうさぎ(krkrz,强加密)—— **E-UNPACK-ENCRYPTED-XP3 真实案例**

| 项 | 实测结果 |
|---|---|
| 引擎判定 | Kirikiri(krkrz):xp3+sig+BootStrap+`.cf` |
| 加密 | data.xp3 **加密且 msg-tool 不支持**(826 文件 Error:"method not supported");`--xp3-game-title` 为**内置标题枚举**(实测确认),本作不在库中;exe 自动 key 亦未覆盖 |
| 已有补丁 | `unencrypted.xp3` = 中文补丁(398 文件,真名 `01.txt.scn`…PSB)+ **`!scnlist.txt` 场景清单**(UTF-16,可配合 `--xp3-file-list-path` 恢复哈希名)+ version.dll |
| 可能路径 | ① 用户自备 **xp3-brute**(计划内"用户自备解密工具"路径,E-UNPACK-ENCRYPTED-XP3 指引的真实演练);② `--xp3-file-list-path` + !scnlist 恢复文件名后视解密情况;③ 以 unencrypted.xp3 中文文本做"重翻流水线"演示(非日文原文,仅作流程验证) |
| 能力等级 | 当前 **L3**(提取受阻)→ 解密解决后升 L1;**作为错误指引路径的真实测试用例**价值极高 |
| 决策 | M1 用例 ①优先:请用户确认是否可获取 xp3-brute;否则用 ③ 做流程演示 + ② 做文件名恢复实验 |

---

## 三款样例覆盖的验收维度

| 维度 | 样例 1 マガルミナ | 样例 2 Relirium | 样例 3 とける風花 |
|---|---|---|---|
| L1 全链路 | ✅ 主力 | ✅ 长尾引擎(FR-C5) | — |
| 加密 xp3 自动解密 | ✅(exe key) | —(无需) | ❌(E-UNPACK-ENCRYPTED-XP3 指引实测) |
| patch 递增分支 | ✅(append→append2) | — | ✅(unencrypted 已占) |
| 多引擎 profile | krkrz+PSB | yuris-txt | krkrz(强加密) |
| 编码模式 | PSB 内部 Unicode | SJIS→GBK | 待定 |

## 合规记录

- 三款游戏为用户合法持有;勘查仅读取目录清单与解包到系统临时目录;**任何游戏数据不入仓库、不分发**;PatchProject 引用本机路径。
