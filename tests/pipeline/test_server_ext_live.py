"""M2 后端安全与功能套件(单进程直连 12333)。"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, r"L:\doc\AI-Project\galTrans")
from galtrans_pipeline.server_ext import (  # noqa: E402
    load_or_create_token,
    issue_sse_ticket,
    consume_sse_ticket,
)

BASE = "http://127.0.0.1:12333"
TOKEN = load_or_create_token()
RESULTS = []


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8") or "{}")
    except Exception as error:  # 连接失败等
        return -1, {"detail": str(error)}


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


# 0. 服务可达
status, body = call("GET", "/api/version")
check("backend alive", status == 200, str(body))

# 1. 恶意 Host → 403(BLK-01 防护)
status, body = call("GET", "/api/pipeline/profiles", headers={"Host": "evil.com"})
check("malicious host rejected", status == 403, f"{status} {body}")

# 2. profiles 正常读取
status, body = call("GET", "/api/pipeline/profiles")
check("profiles list", status == 200 and any(p["profile"] == "kirikiri" for p in body.get("profiles", [])), str(body)[:80])

# 3. detect 无 token → 401(FR-G1)
status, body = call("POST", "/api/pipeline/detect", {"game_dir": "L:/gal"})
check("detect without token -> 401", status == 401, f"{status}")

# 4. detect 带 token → 200
status, body = call(
    "POST",
    "/api/pipeline/detect",
    {"game_dir": "L:/gal/Relirium -レリリウム- 遺跡と出逢いと冒険と"},
    headers={"X-Local-Token": TOKEN},
)
detected = body.get("results", [{}])[0].get("profile") == "yuris"
check("detect with token", status == 200 and detected, str(body)[:100])

# 5. SSE 票据:签发→消费成功→重放失败
ticket = issue_sse_ticket()
check("sse ticket issue+consume", consume_sse_ticket(ticket))
check("sse ticket replay rejected", not consume_sse_ticket(ticket))

# 6. 无 token 的 sse-ticket 签发 → 401
status, body = call("POST", "/api/pipeline/sse-ticket", {})
check("sse-ticket requires token", status == 401, f"{status}")

# 7. 创建工程 + run(桩:走到 TRANSLATE 会因无 key 停,这里只验证 run 受理)
proj = r"C:\Users\74994\AppData\Local\Temp\e2e\http_proj"
status, body = call(
    "POST",
    "/api/pipeline/projects",
    {"game_dir": "L:/gal/とける風花とシロうさぎ", "profile": "kirikiri", "project_dir": proj},
    headers={"X-Local-Token": TOKEN},
)
check("create project", status == 200, str(body)[:100])

# 8. status 带 token
status, body = call(
    "GET", "/api/pipeline/status?project_dir=" + proj.replace("\\", "/"),
    headers={"X-Local-Token": TOKEN},
)
check("status with token", status == 200 and body.get("profile") == "kirikiri", str(body)[:100])

# 9. status 无 token → 401
status, body = call("GET", "/api/pipeline/status?project_dir=" + proj.replace("\\", "/"))
check("status without token -> 401", status == 401, f"{status}")

failed = [name for name, ok, _ in RESULTS if not ok]
print()
print(f"套件结果: {len(RESULTS) - len(failed)}/{len(RESULTS)} 通过; 失败: {failed or '无'}")
sys.exit(1 if failed else 0)
