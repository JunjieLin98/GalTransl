# UPSTREAM — 上游基线与同步策略

| 项 | 值 |
|---|---|
| 上游仓库 | https://github.com/GalTransl/GalTransl(GPL-3.0) |
| 锁定基线 | **tag 7.4.0**(commit `fd911be`) |
| fork(origin) | https://github.com/JunjieLin98/GalTransl |
| upstream 远端 | 本仓库 `upstream` → GalTransl/GalTransl |
| 基线锁定日期 | 2026-09-12 |

## 分支模型

- `main`:本 fork 发布线,起点 = 上游 tag 7.4.0(不跟踪 upstream/main);
- `develop`:工作线,里程碑合并到 main;
- 上游同步:每里程碑末评估 `upstream/main` 新提交,升级 = 显式 diff 评估(见 docs/architecture.md §2 三层边界)。

## 上游 main 领先锁定基线的提交(截至锁定日,7 个)

- #211/#212:feat/skip-check(新增 skip_check 跳过检查机制,关联 issue #205)
- #211:feat 单句过长检测与阈值可配置(关联 issue #205)

> 对本项目的意义:上游已部分实现 #205 的"检查项"侧;我们的问题状态管理(FR-D6,确认/忽略/白名单)设计时须评估复用 skip_check 机制,避免重叠(M4 任务输入)。

## 已发现的上游缺陷(待反馈)

1. **测试回归**:tag 7.4.0 与 main 均存在——`tests/test_translate_refactor_regressions.py` 8 项失败,根因 `GalTransl/Backend/ForGalJsonTranslate.py:186` 引用 `self.max_api_retries`,但该属性在类中未定义(测试构造方式暴露)。非 Python 版本问题(3.13 实测复现,预计 3.11 同样失败)。
2. **测试回归**:`tests/test_incremental_cache_append.py::test_batch_translate_saves_only_incremental_results` 失败,根因 `GalTransl/Backend/BaseTranslate.py:1271` 调用 `self.pj_config.getProjectDir()`,而该测试的 `SimpleNamespace` mock 未提供该方法。

**处置:CI 暂时 ignore/deselect(ci.yml 有注记);向上游提 issue/PR 后移除。**

## 同步操作备忘

```bash
git fetch upstream
git log --oneline main..upstream/main   # 评估增量
# 算法层:只评估,不合并代码;缓存/存储层:评估是否影响 locked PR;前端:仅摘取修复
```
