"""本地 mock LLM(OpenAI 兼容 /v1/chat/completions)。

用途:无真实 API key 时驱动 GalTransl 走完整翻译会话,
产出真实缓存(三联键/润色 post_src/分块全部由上游亲自写出),
供双语编辑器与 rebuildr 重建输出的端到端回归。

协议:GalTransl ForGal-json 的 jsonline——请求 user 消息里每行
`sig|{"id": N, "src": "..."}`,响应按行回 `sig|{"id": N, "dst": "〔伪译〕src"}`。

启动:python tools/mock_llm.py [port](默认 18900)
"""

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LINE_RE = re.compile(r"([A-Za-z0-9]{3})\|(\{.*\})")


def fake_translate(user_content: str) -> str:
    out_lines = []
    for raw in user_content.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = LINE_RE.match(line)
        if not match:
            continue
        sig, payload = match.group(1), match.group(2)
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        # 只处理当前批次的输入行(含 src);prompt 里的历史响应行(含 dst)跳过,
        # 否则输出行序与期望的 sig_list 错位
        if "src" not in obj or "dst" in obj:
            continue
        src = str(obj.get("src", ""))
        dst = "〔伪译〕" + src
        out_lines.append(f'{sig}|{json.dumps({"id": obj.get("id"), "dst": dst}, ensure_ascii=False)}')
    return "\n".join(out_lines)


class Handler(BaseHTTPRequestHandler):
    def _sse_chunk(self, content: str) -> str:
        return json.dumps(
            {
                "id": "mock",
                "object": "chat.completion.chunk",
                "choices": [
                    {"index": 0, "finish_reason": None,
                     "delta": {"role": "assistant", "content": content}}
                ],
            },
            ensure_ascii=False,
        )

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages", [])
        user_content = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        content = fake_translate(user_content)

        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            # 流式:分块吐出(可用性检查 max_tokens=1 也要有至少一个非空 chunk)
            self.wfile.write(f"data: {self._sse_chunk(content or '.')}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        resp = {
            "id": "mock",
            "object": "chat.completion",
            "choices": [
                {"index": 0, "finish_reason": "stop",
                 "message": {"role": "assistant", "content": content}}
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        data = json.dumps(resp, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        data = b'{"status":"mock-ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("[mock-llm]", fmt % args)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18900
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"mock LLM listening at http://127.0.0.1:{port}")
    server.serve_forever()
