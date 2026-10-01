#!/usr/bin/env python3
"""Owner-only Unix socket transport for local Bridger execution adapters."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import socket
import stat
import struct
import threading
from typing import Any, Callable

MAX_MESSAGE_BYTES = 3 * 1024 * 1024
RESPONSE_TIMEOUT_SECONDS = 320


class DirectSocketError(RuntimeError):
    pass


class _Pending:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.response: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)


class UnixRequestQueue:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._queue: queue.Queue[_Pending] = queue.Queue()
        self._stop = threading.Event()
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        if parent.is_symlink():
            raise DirectSocketError("direct socket parent must not be a symlink")
        info = parent.stat()
        if info.st_uid != os.getuid() or not stat.S_ISDIR(info.st_mode):
            raise DirectSocketError("direct socket parent must be an owned directory")
        os.chmod(parent, 0o700)
        try:
            existing = self.path.lstat()
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing.st_uid != os.getuid() or not stat.S_ISSOCK(existing.st_mode):
                raise DirectSocketError("refusing to replace non-owned/non-socket direct path")
            self.path.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.path))
        os.chmod(self.path, 0o600)
        listener.listen(16)
        listener.settimeout(0.5)
        self._listener = listener
        self._thread = threading.Thread(target=self._accept_loop, name="bridger-direct-socket", daemon=True)
        self._thread.start()

    def _accept_loop(self) -> None:
        listener = self._listener
        if listener is None:
            return
        while not self._stop.is_set():
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                continue
            threading.Thread(target=self._handle_connection, args=(conn,), daemon=True).start()

    @staticmethod
    def _peer_uid(conn: socket.socket) -> int:
        if not hasattr(socket, "SO_PEERCRED"):
            raise DirectSocketError("SO_PEERCRED is required for local execution socket")
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _, uid, _ = struct.unpack("3i", raw)
        return uid

    def _handle_connection(self, conn: socket.socket) -> None:
        with conn:
            try:
                if self._peer_uid(conn) != os.getuid():
                    raise DirectSocketError("direct socket peer uid is not authorized")
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_MESSAGE_BYTES:
                        raise DirectSocketError("direct socket request exceeds limit")
                    chunks.append(chunk)
                payload = json.loads(b"".join(chunks).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise DirectSocketError("direct socket request must be an object")
                pending = _Pending(payload)
                self._queue.put(pending)
                response = pending.response.get(timeout=RESPONSE_TIMEOUT_SECONDS)
            except Exception as exc:
                response = {"ok": False, "error": type(exc).__name__, "message": str(exc)[:4000]}
            encoded = (json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            try:
                conn.sendall(encoded)
            except OSError:
                pass

    def process_pending(self, handler: Callable[[dict[str, Any]], dict[str, Any]], max_items: int = 16) -> int:
        processed = 0
        while processed < max_items:
            try:
                pending = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                response = handler(pending.payload)
            except Exception as exc:
                response = {"ok": False, "error": type(exc).__name__, "message": str(exc)[:4000]}
            pending.response.put(response)
            processed += 1
        return processed

    def close(self) -> None:
        self._stop.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        try:
            info = self.path.lstat()
            if info.st_uid == os.getuid() and stat.S_ISSOCK(info.st_mode):
                self.path.unlink()
        except FileNotFoundError:
            pass


def submit(path: Path, payload: dict[str, Any], *, timeout: float = RESPONSE_TIMEOUT_SECONDS) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise DirectSocketError("direct socket request exceeds limit")
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    try:
        conn.connect(str(path))
        conn.sendall(encoded)
        conn.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_MESSAGE_BYTES:
                raise DirectSocketError("direct socket response exceeds limit")
            chunks.append(chunk)
    finally:
        conn.close()
    response = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(response, dict):
        raise DirectSocketError("direct socket response must be an object")
    return response
