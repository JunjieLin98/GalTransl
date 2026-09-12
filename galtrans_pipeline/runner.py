"""ProcessRunner:外部子进程的统一封装(架构 §3.5 MAJ-02)。

记录活跃 PID;取消时 Windows 下 taskkill /F /T 递归终止进程树,防孤儿进程锁文件。
取消响应粒度 = poll_interval(默认 0.5s),不依赖子进程自身配合。
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field


@dataclass
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    cancelled: bool = False
    output_tail: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self.output_tail:
            self.output_tail = (
                (self.stdout or "")[-800:] + "\n" + (self.stderr or "")[-800:]
            ).strip()


class ProcessRunner:
    def __init__(self, poll_interval: float = 0.5) -> None:
        self.poll_interval = poll_interval
        self._lock = threading.Lock()
        self._active: dict[int, subprocess.Popen] = {}

    def run(
        self,
        args: list[str],
        cancel_event: threading.Event | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> ProcessResult:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            creationflags=creationflags,
        )
        with self._lock:
            self._active[proc.pid] = proc
        try:
            return self._wait(proc, cancel_event, timeout)
        finally:
            with self._lock:
                self._active.pop(proc.pid, None)

    def _wait(
        self,
        proc: subprocess.Popen,
        cancel_event: threading.Event | None,
        timeout: float | None,
    ) -> ProcessResult:
        # 后台线程持续读取管道:否则子进程写满 64KB 缓冲后会阻塞在输出上,
        # poll 轮询永远等不到退出(实测 xp3brute 大量状态输出触发)。
        out_buf: list[bytes] = []
        err_buf: list[bytes] = []
        readers = [
            threading.Thread(target=lambda: out_buf.append(proc.stdout.read())),
            threading.Thread(target=lambda: err_buf.append(proc.stderr.read())),
        ]
        for thread in readers:
            thread.daemon = True
            thread.start()

        deadline = None if timeout is None else time.monotonic() + timeout
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                self._kill_tree(proc)
                return self._join_collect(proc, out_buf, err_buf, cancelled=True)
            if deadline is not None and time.monotonic() > deadline:
                self._kill_tree(proc)
                result = self._join_collect(proc, out_buf, err_buf)
                raise TimeoutError(
                    f"process timed out after {timeout}s: {proc.args}\n{result.output_tail}"
                )
            time.sleep(self.poll_interval)
        for thread in readers:
            thread.join(timeout=10)
        return ProcessResult(
            proc.returncode or 0,
            (out_buf[0] if out_buf else b"").decode("utf-8", errors="replace"),
            (err_buf[0] if err_buf else b"").decode("utf-8", errors="replace"),
        )

    def _join_collect(
        self,
        proc: subprocess.Popen,
        out_buf: list[bytes],
        err_buf: list[bytes],
        cancelled: bool = False,
    ) -> ProcessResult:
        # kill 后管道 EOF 到达,读线程随之结束;短暂等待缓冲落盘
        try:
            proc.wait(timeout=30)
        except Exception:
            self._kill_tree(proc)
        deadline = time.monotonic() + 10
        while (len(out_buf) < 1 or len(err_buf) < 1) and time.monotonic() < deadline:
            time.sleep(0.1)
        return ProcessResult(
            -1 if cancelled else (proc.returncode or 0),
            (out_buf[0] if out_buf else b"").decode("utf-8", errors="replace"),
            (err_buf[0] if err_buf else b"").decode("utf-8", errors="replace"),
            cancelled=cancelled,
        )

    def _kill_tree(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            proc.kill()

    def cancel_all(self) -> None:
        with self._lock:
            procs = list(self._active.values())
        for proc in procs:
            self._kill_tree(proc)
