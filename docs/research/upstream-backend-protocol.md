# 上游后端协议笔记(M0 实测)

| 项 | 内容 |
|---|---|
| 实测基线 | GalTransl **tag 7.4.0**(commit fd911be) |
| 实测环境 | Windows 10 x64,Python **3.13.3**(venv),2026-09-12 |
| 实测人 | M0(自动化实测 + 逐行读码) |
| 结论效力 | 本笔记为 architecture.md §4 的校准依据;凡与调研报告冲突处,以本笔记为准 |

---

## 1. 服务框架与绑定(实测确认)

- `GalTransl/server.py`(2589 行):`http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler`,**同步阻塞模型**(非 asyncio;翻译核心在 `run_job` 内部才用 asyncio);
- 绑定:`127.0.0.1:12333`(默认),`--host/--port` 可配;
- 响应为 **HTTP/1.0**(BaseHTTPRequestHandler 默认)——GUI 侧若依赖 keep-alive 需注意;
- `run_backend.py` = 5 行入口,调 `GalTransl.server.main`;
- **Python 3.13.3 实测可正常运行**(依赖 `pip install -r requirements.txt` 全部安装成功,`/api/version` 返回 `{"version": "7.4.0"}`)——上游 README 标注 3.11.9,实测 3.13 服务端无阻,开发环境锁定 3.13 venv(见 §9)。

## 2. 路由风格(读码确认)

- 分发:`do_GET / do_POST / do_PUT / do_DELETE / do_OPTIONS` 五入口 + `_route_project_api(project_id, sub_path)` 子分发;
- 路径解析:`urlparse(self.path)` 精确匹配字符串,无路由框架;
- 项目寻址:project_id = `encode_project_dir(项目绝对路径)`(路径编码字符串),子路由按 `sub_path` if-elif 链分发;
- **对本项目结论**:新增端点沿用"方法入口 + if-elif"风格,挂在独立命名空间 `/api/pipeline/*`(实测 404 无冲突)。

## 3. 端点清单(读码提取)

**顶层 /api/**:`/version`、`/version/check`、`/translators`、`/jobs`(实测返回 `{"jobs": []}`)、`/app-settings`、`/project-config-template`、`/backend-profiles(/:id)`、`/plugins`、`/problem-types`、`/dictionaries/common(/create|/save|/delete)`、`/openai-models`、`/prompt-templates`、`/translation-guidelines`。

**项目子路由 /api/projects/:id/***:`/config`、`/files`、`/cache`(列表/`/save`/`/delete-entry`/`/delete-file`/`/search`/`/replace`)、`/progress`、`/runtime`、`/stop`(POST,无活跃 Job 时 409)、`/dictionary(/project|/project/create|/save|/delete)`、`/name-table(/generate|/ai-translate|/save)`、`/name-dict`、`/problems`、`/logs`。

**对本项目结论**:`/progress`(缓存文件聚合统计:total/translated/problems/failed,按文件细列)与 `/runtime`(富快照)已覆盖翻译进度轮询;`/stop` 已覆盖协作式取消;**注入/打包/检测/restore 为净新增**。

## 4. 任务模型(读码确认)

- `GalTransl/Service.py`:`JobSpec` / `JobState`(status:`pending → running → failed|…`,`job_id`、`started_at`、`finished_at`);`run_job()` = `asyncio.run(run_job_async(...))`,接受 `stop_event`;
- `server_runtime.py`(849 行):`RUNTIME_REGISTRY`(**每项目单活跃 Job**,`get_project_job` / `request_project_stop`)、`RUNTIME_PROGRESS_CACHE`(进度缓存)、`record_runtime_error/success`、`_ConcurrentLimitError`(并发限制);
- 取消链路:`POST /api/projects/:id/stop` → `registry.request_project_stop()` → job 内部 stop_event 轮询生效;
- **对本项目结论**:architecture §3.5 的 JobRegistry **不复刻**,改为扩展 `RUNTIME_REGISTRY`:新步骤(unpack/extract/inject/package/restore)注册为同类 Job,复用 stop_event 协作取消与 409 语义;**外部子进程强杀(ProcessRunner)为净新增**(上游 Job 全部为 Python 内部任务)。

## 5. 进度与 SSE(读码 + 实测)

- 进度目前为**轮询制**:`/progress` 直接扫描 cache 目录 JSON 统计,`/runtime` 读 RUNTIME_PROGRESS_CACHE 快照;
- SSE 仅一处:`/name-table/ai-translate` 用 `text/event-stream` 做流式响应,手写 `event: {event}\ndata: {json}\n\n` 帧格式(`_sse_send` 局部函数);
- **对本项目结论**:无全局进度 SSE 总线;architecture §4"复用其 SSE 通道"校准为"**复用 `_sse_send` 帧格式模式,新增全局 `/api/pipeline/events` SSE 端点**";GUI 在 SSE 之外仍可回退轮询 `/runtime`。

## 6. 安全实测(2026-09-12,三项全部实证)

| 探测 | 结果 |
|---|---|
| `GET /api/version` + `Origin: http://evil.com` | 200,响应头 `Access-Control-Allow-Origin: *`(**任意 Origin 放行**) |
| `OPTIONS` 预检 + `Access-Control-Request-Headers: x-local-token,content-type` | 204,`Access-Control-Allow-Headers: Content-Type`(**自定义头被拒——X-Local-Token 方案必须同步扩展 ACAH**) |
| `GET /api/version` + `Host: evil.com` | **200 并正常返回数据**——DNS Rebinding 漏洞实锤(BLK-01 场景复现) |
| 全服务鉴权 | 无任何 token/鉴权中间件 |

**对本项目结论**:architecture §4.1 三件套(Host 白名单 → 403、token 校验 → 401、ACAH 扩展 `X-Local-Token`)全部实测验证必要且可行;CORS 收敛实现点 = `server.py` L906-908 与 `do_OPTIONS`(L911)。

## 7. 缓存 schema(读码确认,锁定位兼容性)

- 内部字段名与对外名存在别名映射(`Cache.py` L17-20):`pre_src↔pre_jp`、`post_src↔post_jp`、`pre_dst↔pre_zh`、`proofread_dst↔proofread_zh`;
- 条目字段:`index`、`name`(speaker)、`pre_src`、`pre_dst`、`proofread_dst`、`trans_by`、`proofread_by`、`problem` 等;
- 读取普遍走 `_cache_get(entry, key)` 容错访问;
- **对本项目结论**:新增 `locked` 字段方案兼容(`_cache_get(cache, "locked", False)` 兜底,旧缓存向后兼容),FR-D5 的 PR 路线可行性确认。

## 8. 桌面端(Tauri v2.0.6,读码确认)

- `desktop/src-tauri/tauri.conf.json`:`devUrl = http://127.0.0.1:1420`;`csp: null`(上游未设 CSP);`identifier: com.galtransl.desktop`;前端 `frontendDist: ../dist`;
- 打包态 Windows WebView Origin 预期 `http://tauri.localhost`——**列入 M2 打包时的实测项**(机制已写入 M0 任务 2 与 architecture §4.1)。

## 9. 开发环境决策(M0 记录)

- venv:`.venv`(Python 3.13.3),依赖安装成功;上游声明的 3.11.9 与实测 3.13 并存策略:**服务端/核心用 3.13 venv 开发**,若后续触发 3.13 不兼容(如 pyreqwest 轮子)再引入 3.11 环境(机制:winget/uv 安装,列入风险跟踪);
- fork 仓库:`JunjieLin98/GalTransl`(gh 已认证),本地 `origin` = fork、`upstream` = GalTransl/GalTransl;`main` 锁定 tag **7.4.0**(`fd911be`),`develop` 为工作线;上游 main 领先 tag 7 个提交(含 #205 skip_check/单句过长检测——**上游已部分实现 #205 的检查项,问题状态管理(FR-D6)设计时须评估复用**,记入 M4 任务输入)。

## 10. 遗留与下一步

- 打包态 Origin 实测 → M2 打包时执行;
- 本笔记中"净新增"清单(pipeline 命名空间/SSE 总线/ProcessRunner)为 M1-M2 的实现输入;
- `X-Local-Token` 需加入 `Access-Control-Allow-Headers`(实测依据,§6)。
