#!/usr/bin/env python3
"""Owner-only content-addressed storage for large Bridger execution results."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_ARTIFACT_BYTES = 3 * 1024 * 1024


class ResultArtifactError(RuntimeError):
    pass


def _secure_dir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ResultArtifactError("result artifact directory must not be a symlink")
    info = path.stat()
    if info.st_uid != os.getuid() or not stat.S_ISDIR(info.st_mode):
        raise ResultArtifactError("result artifact directory must be owned by the service user")
    os.chmod(path, 0o700)
    return path


def _encoded_result(result: Any) -> bytes:
    try:
        text = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ResultArtifactError(f"execution result is not finite standard JSON: {exc}") from exc
    data = text.encode("utf-8")
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ResultArtifactError("execution result exceeds artifact limit")
    return data


def store_result_artifact(directory: Path, result: Any) -> dict[str, Any]:
    root = _secure_dir(directory)
    data = _encoded_result(result)
    digest = hashlib.sha256(data).hexdigest()
    target = root / f"{digest}.json"
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags)
    except FileNotFoundError:
        fd = -1
    if fd >= 0:
        try:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
                raise ResultArtifactError("existing result artifact is not an owned regular file")
            existing = os.read(fd, MAX_ARTIFACT_BYTES + 1)
            if existing != data:
                raise ResultArtifactError("result artifact digest collision/content mismatch")
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        return {"result_artifact_sha256": digest, "result_artifact_bytes": len(data)}

    fd, tmp_name = tempfile.mkstemp(prefix=f".{digest}.", dir=str(root))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
        dir_fd = os.open(root, os.O_RDONLY | (os.O_DIRECTORY if hasattr(os, "O_DIRECTORY") else 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return {"result_artifact_sha256": digest, "result_artifact_bytes": len(data)}


def read_result_artifact(directory: Path, digest: str) -> Any:
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ResultArtifactError("invalid result artifact digest")
    root = _secure_dir(directory)
    target = root / f"{digest}.json"
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags)
    except FileNotFoundError as exc:
        raise ResultArtifactError("result artifact not found") from exc
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
            raise ResultArtifactError("result artifact is not an owned regular file")
        if info.st_size > MAX_ARTIFACT_BYTES:
            raise ResultArtifactError("result artifact exceeds limit")
        data = os.read(fd, MAX_ARTIFACT_BYTES + 1)
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ResultArtifactError("result artifact digest mismatch")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResultArtifactError("result artifact is invalid JSON") from exc
