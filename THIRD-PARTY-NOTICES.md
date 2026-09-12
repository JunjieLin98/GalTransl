# THIRD-PARTY NOTICES / 第三方组件许可声明

本软件(GalTransl Suite)是上游 GalTransl(GalTransl/GalTransl,GPL-3.0)的分支增强版,
整体以 **GPL-3.0** 发布(见 LICENSE)。以下列出随发布包分发的第三方组件及其许可。
构建工具(不随产物分发代码)单列于文末。

## 随发布包分发的组件

### 上游项目

| 组件 | 许可 | 来源 |
|---|---|---|
| GalTransl(上游 v7.4.0) | GPL-3.0 | https://github.com/GalTransl/GalTransl |

### Python 库(打包进 galtransl_backend.exe)

| 组件 | 许可 |
|---|---|
| UnityPy | MIT |
| PyYAML | MIT |
| orjson | MIT OR Apache-2.0 |
| aiofiles | Apache-2.0 |
| openai (python client) | Apache-2.0 |
| requests | Apache-2.0 |
| tenacity | Apache-2.0 |
| tiktoken | MIT |
| OpenCC (python 绑定) | Apache-2.0 |
| colorlog | MIT |
| openpyxl | MIT |
| packaging | Apache-2.0 OR BSD-2-Clause |
| vaporetto | MIT OR Apache-2.0 |

各库的完整许可文本可在其官方仓库或 PyPI 页面获取。

### 外部命令行工具(tools/bin/,随包分发)

| 工具 | 许可 | 来源 |
|---|---|---|
| msg-tool(v0.4.0-alpha.3) | GPL-3.0 | https://github.com/lifegpc/msg-tool(GPL 分发要求:同版本源码包随 Release 资产附上) |
| Xp3Pack.exe / version.dll(KirikiriTools v1.7 构建产物) | MIT | https://github.com/arcusmaximus/KirikiriTools(已归档,release 1.7 资产) |

**用户自备、不随包分发**:xp3-brute(加密 xp3 恢复,许可证未核实)、SExtractor
(GPL-3.0,长尾兜底场景按需自取)、XUAT 类 Il2Cpp 工具。使用责任归用户。

### 资源文件

| 文件 | 说明 |
|---|---|
| res/bccwj-suw+unidic_pos+pron.model.xz | GenDic 分词模型,随上游 GalTransl 分发,许可以上游仓库声明为准 |

### 前端与桌面框架(desktop/)

| 组件 | 许可 |
|---|---|
| Tauri(含 tauri-plugin-dialog/shell) | Apache-2.0 OR MIT |
| React / React Router | MIT |
| 其余 npm 依赖 | 完整清单与许可见仓库依赖图(package.json / package-lock.json) |

## 构建工具(不随产物分发代码)

| 工具 | 许可 | 说明 |
|---|---|---|
| PyInstaller | GPL-2.0-or-later(附特殊例外) | 例外条款允许用其打包分发任意许可的程序;仅作构建用途 |

## 补丁产物说明

本软件产出的游戏汉化补丁内嵌 TRANSLATION_NOTICE(AI 翻译声明)与
LICENSE-THIRD-PARTY.txt(补丁内嵌的第三方组件,如 KirikiriTools version.dll,MIT)。
补丁不包含游戏资产、不包含本软件代码。

## 许可澄清记录

- GalTransl_DumpInjector:本分支**未使用**(M0 调研后选择直接集成 msg-tool),
  其仓库 license 标注自相矛盾问题不影响本项目。
- msg-tool 部分功能链路依赖 KirikiriTools(MIT)构建产物;项目自身代码未链接
  KirikiriTools,仅在补丁分发场景可选携带其 version.dll(见上)。
