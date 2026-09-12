# 自建样例游戏(CI/E2E fixture)

## 定位

供 `tests/pipeline/test_sample_game.py` 与 CI 使用的**最小 Kirikiri 样本**:
自有编写的 KS 场景(Shift-JIS)+ msg-tool 打包为 data.xp3。

## 与计划 M0 任务 5 的关系

计划原文要求"基于 KAG3 官方模板(kag3_blank)裁剪出**可运行**样例游戏"。
当前交付为 **fixture 级**:足够支撑提取/注入/打包的自动化回归,
但**不含可运行引擎**(krkrz.exe 需 C++ 构建或官方二进制,涉及分发合规,
推迟到 M2 GUI E2E 阶段再决定引入方式)。

## 版权

scenario/*.ks 为本项目自写内容(仅借用 KAG 语法),无第三方版权;
如未来引入 KAG3 系统脚本,须附带其修正 BSD 许可文本(krkrz/kag3)。

## 重建 data.xp3

```bash
tools/bin/msg_tool.exe pack -t kirikiri-xp3 fixtures/sample_game/scenario fixtures/sample_game/data.xp3
```
