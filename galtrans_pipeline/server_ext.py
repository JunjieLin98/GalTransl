"""server_ext — 上游 12333 后端的流水线扩展(M2)。

挂载点:GalTransl/server.py 的 do_GET/do_POST 入口(受控改造,`# galTrans:` 注记,可上游化):
    if path.startswith("/api/pipeline"):
        from galtrans_pipeline.server_ext import handle_pipeline_get / handle_pipeline_post

安全(架构 §4.1):
    1. Host 白名单(防 DNS Rebinding,实测上游无校验);
    2. 写操作 + 敏感读强制 X-Local-Token(DPAPI 加密落盘);
    3. SSE 用一次性短时票据换取(EventSource 不支持自定义头)。
"""

from __future__ import annotations

import ctypes
import hmac
import json
import os
import queue
import secrets
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any

from .errors import PipelineError
from .orchestrator import Pipeline
from .profile import load_profiles
from .project import PatchProject
from .runner import ProcessRunner
from .toolbox import ToolBox

# ---------------------------------------------------------------- 仓库定位
REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = REPO_ROOT / "profiles"
DEFAULT_TOOLS_DIR = REPO_ROOT / "tools" / "bin"

# ---------------------------------------------------------------- Host 白名单
ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
# GUI 自身来源(Tauri v2: dev=127.0.0.1:1420, 打包态=tauri.localhost);
# token 下发仅允许这些 Origin(外来网页 Origin 为自身域名或 null → 拒绝)
ALLOWED_ORIGINS = {
    "http://127.0.0.1:1420",
    "http://localhost:1420",
    "http://tauri.localhost",
    "https://tauri.localhost",
}


def origin_allowed(handler) -> bool:
    origin = (handler.headers.get("Origin") or "").strip()
    if not origin:
        return True  # 非浏览器客户端(curl 等);仍受 Host 校验与 token 保护
    return origin in ALLOWED_ORIGINS


def host_allowed(handler) -> bool:
    """严格校验 Host 头(修复 BLK-01:上游实测恶意 Host 照常返回 200)。"""
    host = (handler.headers.get("Host") or "").strip().lower()
    if not host:
        return False
    if ":" in host:
        host_part, _, port_part = host.rpartition(":")
        if not port_part.isdigit():
            return False
    else:
        host_part = host
    return host_part in ALLOWED_HOSTS


def _reject_host(handler) -> None:
    handler._gt_cors_origin = ""  # 拒绝响应不携带任何 CORS 头
    body = json.dumps({"error": "E-AUTH-UNAUTHORIZED", "detail": "invalid host"}).encode()
    handler.send_response(HTTPStatus.FORBIDDEN)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


# ---------------------------------------------------------------- Token(DPAPI)
_TOKEN_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "galtrans"
_TOKEN_FILE = _TOKEN_DIR / "local_token.bin"


def _dpapi_protect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = Blob(len(data), ctypes.cast(buf, ctypes.c_void_p))
    blob_out = Blob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.c_void_p(blob_out.pbData))


def _dpapi_unprotect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = Blob(len(data), ctypes.cast(buf, ctypes.c_void_p))
    blob_out = Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.c_void_p(blob_out.pbData))


def load_or_create_token() -> str:
    """本地鉴权 token:首启生成,DPAPI 加密落盘;解密失败引导重新生成。"""
    import os

    try:
        if _TOKEN_FILE.is_file():
            return _dpapi_unprotect(_TOKEN_FILE.read_bytes()).decode("utf-8")
    except OSError:
        pass  # 跨用户/提权导致解密失败 → 重新生成(平滑降级,architecture §4.1)
    token = secrets.token_urlsafe(32)
    _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _TOKEN_FILE.write_bytes(_dpapi_protect(token.encode("utf-8")))
    except OSError:
        # DPAPI 不可用(非 Windows 等):降级明文 + 仅本机目录权限
        _TOKEN_FILE.write_text(token, encoding="utf-8")
    return token


_TOKEN = load_or_create_token()


def token_ok(handler) -> bool:
    supplied = handler.headers.get("X-Local-Token", "")
    return hmac.compare_digest(supplied, _TOKEN)


def _require_token(handler) -> bool:
    if token_ok(handler):
        return True
    _send_json(
        handler,
        {"error": "E-AUTH-UNAUTHORIZED", "detail": "missing or invalid X-Local-Token"},
        status=HTTPStatus.UNAUTHORIZED,
    )
    return False


# ---------------------------------------------------------------- SSE 票据
_SSE_TICKETS: dict[str, float] = {}
_TICKET_TTL = 30.0


def issue_sse_ticket() -> str:
    ticket = secrets.token_urlsafe(16)
    _SSE_TICKETS[ticket] = time.monotonic()
    return ticket


def consume_sse_ticket(ticket: str) -> bool:
    issued = _SSE_TICKETS.pop(ticket, None)
    return issued is not None and (time.monotonic() - issued) <= _TICKET_TTL


# ---------------------------------------------------------------- 流水线管理器
class PipelineManager:
    """进程内单例:活跃流水线 + SSE 事件广播(架构 §3.5 JobRegistry 的服务端形态)。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._subscribers: list[queue.Queue] = []

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def emit(self, event: str, data: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait({"event": event, "data": data})
            except queue.Full:
                pass

    def start_run(
        self,
        project_dir: str,
        from_step: str = "",
        only: str = "",
        api_key: str = "",
        endpoint: str = "",
        model: str = "",
    ) -> str:
        project = PatchProject.load(Path(project_dir))
        profiles = load_profiles(PROFILES_DIR)
        profile = profiles[project.profile_name].apply_override(project.overrides)
        job_id = secrets.token_urlsafe(8)
        runner = ProcessRunner()
        pipeline = Pipeline(project, profile, toolbox=ToolBox(DEFAULT_TOOLS_DIR), runner=runner)
        cancel_event = threading.Event()

        def on_progress(step: str, message: str) -> None:
            self.emit("log", {"job_id": job_id, "step": step, "message": message})

        pipeline.registry.add_progress_callback(on_progress)

        def worker() -> None:
            self.emit("job_started", {"job_id": job_id, "project_dir": project_dir})
            try:
                results = pipeline.run(
                    from_step=from_step or None,
                    only=[s.strip() for s in only.split(",")] if only else None,
                    api_key=api_key,
                    endpoint=endpoint,
                    model=model,
                    cancel_event=cancel_event,
                )
                summary = {
                    key: (value if isinstance(value, int) else len(value))
                    for key, value in results.items()
                }
                self.emit("job_done", {"job_id": job_id, "results": summary})
            except PipelineError as error:
                self.emit(
                    "job_failed",
                    {"job_id": job_id, "code": error.code, "message": str(error)},
                )
            except Exception as error:  # pragma: no cover
                self.emit("job_failed", {"job_id": job_id, "code": "unknown", "message": str(error)})

        thread = threading.Thread(target=worker, daemon=True)
        with self._lock:
            self._jobs[job_id] = {
                "thread": thread,
                "pipeline": pipeline,
                "cancel_event": cancel_event,
                "status": "running",
            }
        thread.start()
        return job_id

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return False
        job["cancel_event"].set()
        job["pipeline"].registry.cancel_active()
        return True

    def has_active(self) -> bool:
        with self._lock:
            return any(job["status"] == "running" for job in self._jobs.values())


MANAGER = PipelineManager()


# ---------------------------------------------------------------- HTTP 工具
def _apply_cors(handler) -> None:
    """标记响应的 CORS 形态:GUI 白名单 Origin 回显;外来 Origin 抑制(浏览器拒读)。

    头部注入由上游 end_headers 统一按 handler._gt_cors_origin 处理(server.py 受控改造)。
    """
    origin = (handler.headers.get("Origin") or "").strip()
    if origin and origin_allowed(handler):
        handler._gt_cors_origin = origin
    else:
        handler._gt_cors_origin = ""


def _send_json(handler, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    _apply_cors(handler)
    handler.end_headers()
    handler.wfile.write(body)


def handle_pipeline_options(handler) -> None:
    """预检:CORS 头由 end_headers 按 handler._gt_cors_origin 统一注入。"""
    if not host_allowed(handler):
        _reject_host(handler)
        return
    origin = (handler.headers.get("Origin") or "").strip()
    handler._gt_cors_origin = origin if origin and origin_allowed(handler) else ""
    handler.send_response(HTTPStatus.NO_CONTENT)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _read_body_json(handler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8")) or {}


# ---------------------------------------------------------------- 路由处理
def handle_pipeline_get(handler, registry) -> None:
    if not host_allowed(handler):
        _reject_host(handler)
        return
    import urllib.parse

    parsed = urllib.parse.urlparse(handler.path)
    path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)

    if path == "/api/pipeline/token":
        # GUI 专用:仅放行 Host 白名单 + GUI Origin;外来网页既过不了 Origin,
        # 也读不到响应(CORS 收敛);本地恶意进程本就与用户同权,不构成增量风险
        if not origin_allowed(handler):
            _reject_host(handler)
            return
        _send_json(handler, {"token": _TOKEN})
        return

    if path == "/api/pipeline/profiles":
        from .detect import detect_engine

        profiles = load_profiles(PROFILES_DIR)
        payload = []
        for name, profile in profiles.items():
            payload.append(
                {
                    "profile": name,
                    "capability": profile.capability,
                    "translator_mode": profile.translator_mode,
                }
            )
        _send_json(handler, {"profiles": payload})
        return

    if path == "/api/pipeline/events":
        ticket = (query.get("ticket") or [""])[0]
        if not consume_sse_ticket(ticket):
            _send_json(
                handler,
                {"error": "E-AUTH-UNAUTHORIZED", "detail": "invalid or expired sse ticket"},
                status=HTTPStatus.UNAUTHORIZED,
            )
            return
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        _apply_cors(handler)
        handler.end_headers()
        q = MANAGER.subscribe()
        try:
            handler.wfile.write(b"event: hello\ndata: {}\n\n")
            handler.wfile.flush()
            while True:
                try:
                    item = q.get(timeout=15)
                except queue.Empty:
                    handler.wfile.write(b": keepalive\n\n")
                    handler.wfile.flush()
                    continue
                frame = f"event: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
                handler.wfile.write(frame.encode("utf-8"))
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            MANAGER.unsubscribe(q)
        return

    if path == "/api/pipeline/status":
        if not _require_token(handler):
            return
        project_dir = (query.get("project_dir") or [""])[0]
        try:
            project = PatchProject.load(Path(project_dir))
        except (FileNotFoundError, PipelineError) as error:
            _send_json(handler, {"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return
        _send_json(
            handler,
            {
                "project_dir": str(project.project_dir),
                "game_dir": str(project.game_dir),
                "profile": project.profile_name,
                "schema_version": project.data.get("schema_version"),
                "steps": project.data.get("steps", {}),
            },
        )
        return

    _send_json(handler, {"error": "not found"}, status=HTTPStatus.NOT_FOUND)


def handle_pipeline_post(handler, registry) -> None:
    if not host_allowed(handler):
        _reject_host(handler)
        return
    import urllib.parse

    path = urllib.parse.urlparse(handler.path).path

    # 全部 POST 路由强制 token(FR-G1);SSE 票据 = 持 token 换短时票据
    if not _require_token(handler):
        return

    body = _read_body_json(handler)

    if path == "/api/pipeline/sse-ticket":
        _send_json(handler, {"ticket": issue_sse_ticket()})
        return

    if path == "/api/pipeline/detect":
        from .detect import detect_engine

        game_dir = Path(str(body.get("game_dir", "")))
        if not game_dir.is_dir():
            _send_json(
                handler,
                {"error": "E-PROJECT-GAME-MISSING", "detail": str(game_dir)},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        profiles = load_profiles(PROFILES_DIR)
        _send_json(handler, {"results": detect_engine(game_dir, profiles)})
        return

    if path == "/api/pipeline/projects":
        game_dir = Path(str(body.get("game_dir", "")))
        profile_name = str(body.get("profile", ""))
        overrides = body.get("overrides") or {}
        project_dir = Path(str(body.get("project_dir", "")))
        if not project_dir:
            _send_json(
                handler, {"error": "project_dir required"}, status=HTTPStatus.BAD_REQUEST
            )
            return
        try:
            project = PatchProject.create(project_dir, game_dir, profile_name, overrides)
        except PipelineError as error:
            _send_json(
                handler, {"error": error.code, "detail": str(error)}, status=HTTPStatus.BAD_REQUEST
            )
            return
        _send_json(
            handler,
            {"project_dir": str(project.project_dir), "profile": project.profile_name},
        )
        return

    if path == "/api/pipeline/run":
        project_dir = str(body.get("project_dir", ""))
        try:
            job_id = MANAGER.start_run(
                project_dir,
                from_step=str(body.get("from_step", "")),
                only=str(body.get("only", "")),
                api_key=str(body.get("api_key", "")),
                endpoint=str(body.get("endpoint", "")),
                model=str(body.get("model", "")),
            )
        except FileNotFoundError as error:
            _send_json(handler, {"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return
        except PipelineError as error:
            _send_json(
                handler, {"error": error.code, "detail": str(error)}, status=HTTPStatus.BAD_REQUEST
            )
            return
        _send_json(handler, {"job_id": job_id})
        return

    if path == "/api/pipeline/cancel":
        ok = MANAGER.cancel(str(body.get("job_id", "")))
        _send_json(handler, {"success": ok})
        return

    if path == "/api/pipeline/restore":
        project_dir = Path(str(body.get("project_dir", "")))
        try:
            project = PatchProject.load(project_dir)
            profiles = load_profiles(PROFILES_DIR)
            profile = profiles[project.profile_name].apply_override(project.overrides)
            pipeline = Pipeline(project, profile, toolbox=ToolBox(DEFAULT_TOOLS_DIR))
            count = pipeline.restore()
        except PipelineError as error:
            _send_json(
                handler, {"error": error.code, "detail": str(error)}, status=HTTPStatus.BAD_REQUEST
            )
            return
        _send_json(handler, {"restored": count})
        return

    _send_json(handler, {"error": "not found"}, status=HTTPStatus.NOT_FOUND)
