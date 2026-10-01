#!/usr/bin/env python3
"""Transport-neutral durable execution-attempt ledger for Bridger.

The ledger owns execution identity, persist-before-dispatch, replay conflict
protection, bounded result evidence, and fail-closed crash recovery. Ingress
adapters (GitHub mailbox, Passrail, future MCP/A2A adapters) own their transport
provenance and presentation, not execution state.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import contextlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Callable

from bridge_result_artifacts import store_result_artifact

LEDGER_SCHEMA = "bridger-execution-ledger-v1"
EXECUTION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "REJECTED", "UNKNOWN_OUTCOME"}
MAX_RESULT_CHARS = 40_000
MAX_ERROR_CHARS = 4_000


class ExecutionLedgerError(RuntimeError):
    pass


class ExecutionConflict(ExecutionLedgerError):
    pass


class ExecutionInProgress(ExecutionLedgerError):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def timestamp(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_identity(
    execution_id: str,
    request_sha256: str,
    tool: str,
    authorization_sha256: str | None = None,
) -> None:
    if not isinstance(execution_id, str) or not EXECUTION_ID_RE.fullmatch(execution_id):
        raise ValueError("invalid execution_id")
    if not isinstance(request_sha256, str) or not SHA256_RE.fullmatch(request_sha256):
        raise ValueError("invalid request_sha256")
    if not isinstance(tool, str) or not tool or len(tool) > 256:
        raise ValueError("invalid tool")
    if authorization_sha256 is not None and (
        not isinstance(authorization_sha256, str) or not SHA256_RE.fullmatch(authorization_sha256)
    ):
        raise ValueError("invalid authorization_sha256")


def _result_evidence(result: Any, max_result_chars: int, artifact_dir: Path) -> dict[str, Any]:
    try:
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ExecutionLedgerError(f"execution result is not JSON serializable: {exc}") from exc
    evidence: dict[str, Any] = {
        "result_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }
    if len(encoded) <= max_result_chars:
        evidence["result"] = result
        evidence["truncated"] = False
    else:
        evidence["result_preview"] = encoded[:max_result_chars]
        evidence["truncated"] = True
        evidence.update(store_result_artifact(artifact_dir, result))
    return evidence


class ExecutionLedger:
    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], dt.datetime] = utcnow,
        max_result_chars: int = MAX_RESULT_CHARS,
        artifact_dir: Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.clock = clock
        self.max_result_chars = max_result_chars
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else self.path.parent / "artifacts"
        if self.max_result_chars < 1:
            raise ValueError("max_result_chars must be positive")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._owner_fd = self._acquire_owner_lock()

    def _acquire_owner_lock(self) -> int:
        lock_path = self.path.with_name(self.path.name + ".owner.lock")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise ExecutionLedgerError(f"cannot open execution owner lock safely: {exc}") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ExecutionLedgerError("execution owner lock must be a regular file")
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ExecutionLedgerError(
                    "execution ledger already has an active owner; refusing concurrent execution authority"
                ) from exc
            return fd
        except BaseException:
            os.close(fd)
            raise

    def close(self) -> None:
        fd = getattr(self, "_owner_fd", None)
        if fd is None:
            return
        self._owner_fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> "ExecutionLedger":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __del__(self) -> None:
        # Destructors must never raise during interpreter teardown.
        with contextlib.suppress(Exception):
            self.close()

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": LEDGER_SCHEMA, "executions": {}}

    def _load(self) -> dict[str, Any]:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags)
        except FileNotFoundError:
            return self._empty()
        except OSError as exc:
            raise ExecutionLedgerError(f"cannot open execution ledger safely: {exc}") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ExecutionLedgerError("execution ledger must be a regular file")
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                fd = -1
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ExecutionLedgerError(f"invalid execution ledger: {exc}") from exc
        finally:
            if fd >= 0:
                os.close(fd)
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != LEDGER_SCHEMA
            or not isinstance(payload.get("executions"), dict)
        ):
            raise ExecutionLedgerError("invalid execution ledger shape")
        return payload

    def _save(self, state: dict[str, Any]) -> None:
        data = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        fd, tmp_name = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
            dir_flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                dir_flags |= os.O_DIRECTORY
            dir_fd = os.open(self.path.parent, dir_flags)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @staticmethod
    def _copy(record: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(record, ensure_ascii=False))

    @staticmethod
    def _matching(
        record: dict[str, Any],
        request_sha256: str,
        tool: str,
        authorization_sha256: str | None,
    ) -> bool:
        return (
            record.get("request_sha256") == request_sha256
            and record.get("tool") == tool
            and record.get("authorization_sha256") == authorization_sha256
        )

    def lookup(self, execution_id: str) -> dict[str, Any] | None:
        state = self._load()
        record = state["executions"].get(execution_id)
        return self._copy(record) if isinstance(record, dict) else None

    def begin(
        self,
        execution_id: str,
        request_sha256: str,
        tool: str,
        *,
        accepted_at: str | None = None,
        authorization_sha256: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        _validate_identity(execution_id, request_sha256, tool, authorization_sha256)
        state = self._load()
        existing = state["executions"].get(execution_id)
        if isinstance(existing, dict):
            if not self._matching(existing, request_sha256, tool, authorization_sha256):
                raise ExecutionConflict("execution_id conflicts with existing request/authority binding")
            return self._copy(existing), False
        now = accepted_at or timestamp(self.clock())
        record = {
            "execution_id": execution_id,
            "request_sha256": request_sha256,
            "authorization_sha256": authorization_sha256,
            "tool": tool,
            "status": "EXECUTING",
            "accepted_at": now,
            "started_at": now,
            "completed_at": None,
        }
        state["executions"][execution_id] = record
        self._save(state)
        return self._copy(record), True

    def adopt_inflight(
        self,
        execution_id: str,
        request_sha256: str,
        tool: str,
        *,
        accepted_at: str | None = None,
    ) -> dict[str, Any]:
        """Import legacy persisted `executing` state without dispatching work."""
        record, _ = self.begin(
            execution_id, request_sha256, tool, accepted_at=accepted_at
        )
        return record

    def _settle(
        self,
        execution_id: str,
        request_sha256: str,
        tool: str,
        status: str,
        *,
        result: Any = None,
        error: str | None = None,
        authorization_sha256: str | None = None,
    ) -> dict[str, Any]:
        _validate_identity(execution_id, request_sha256, tool, authorization_sha256)
        if status not in TERMINAL_STATES:
            raise ValueError("invalid terminal status")
        state = self._load()
        record = state["executions"].get(execution_id)
        if not isinstance(record, dict):
            raise ExecutionLedgerError("execution does not exist")
        if not self._matching(record, request_sha256, tool, authorization_sha256):
            raise ExecutionConflict("execution identity does not match stored request/authority")
        if record.get("status") in TERMINAL_STATES:
            return self._copy(record)
        if record.get("status") != "EXECUTING":
            raise ExecutionLedgerError("execution is not in EXECUTING state")
        record["status"] = status
        record["completed_at"] = timestamp(self.clock())
        if error is not None:
            record["error"] = str(error)[:MAX_ERROR_CHARS]
        if result is not None:
            record.update(_result_evidence(result, self.max_result_chars, self.artifact_dir))
        self._save(state)
        return self._copy(record)

    def succeed(
        self, execution_id: str, request_sha256: str, tool: str, result: Any,
        *, authorization_sha256: str | None = None,
    ) -> dict[str, Any]:
        return self._settle(
            execution_id, request_sha256, tool, "SUCCEEDED", result=result,
            authorization_sha256=authorization_sha256,
        )

    def fail(
        self, execution_id: str, request_sha256: str, tool: str, error: str,
        *, authorization_sha256: str | None = None,
    ) -> dict[str, Any]:
        return self._settle(
            execution_id, request_sha256, tool, "FAILED", error=error,
            authorization_sha256=authorization_sha256,
        )

    def reject(
        self, execution_id: str, request_sha256: str, tool: str, error: str,
        *, authorization_sha256: str | None = None,
    ) -> dict[str, Any]:
        return self._settle(
            execution_id, request_sha256, tool, "REJECTED", error=error,
            authorization_sha256=authorization_sha256,
        )

    def mark_unknown(
        self, execution_id: str, request_sha256: str, tool: str, error: str,
        *, authorization_sha256: str | None = None,
    ) -> dict[str, Any]:
        return self._settle(
            execution_id, request_sha256, tool, "UNKNOWN_OUTCOME", error=error,
            authorization_sha256=authorization_sha256,
        )

    def recover_inflight(self) -> list[dict[str, Any]]:
        state = self._load()
        recovered: list[dict[str, Any]] = []
        changed = False
        for record in state["executions"].values():
            if not isinstance(record, dict) or record.get("status") != "EXECUTING":
                continue
            record["status"] = "UNKNOWN_OUTCOME"
            record["completed_at"] = timestamp(self.clock())
            record["error"] = (
                "Bridger restarted with execution already in progress; "
                "automatic replay prohibited"
            )
            recovered.append(self._copy(record))
            changed = True
        if changed:
            self._save(state)
        return recovered

    def execute(
        self,
        execution_id: str,
        request_sha256: str,
        tool: str,
        action: Callable[[], Any],
        *,
        on_accepted: Callable[[dict[str, Any]], None] | None = None,
        pre_dispatch: Callable[[], None] | None = None,
        authorization_sha256: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        record, created = self.begin(
            execution_id, request_sha256, tool,
            authorization_sha256=authorization_sha256,
        )
        if not created:
            if record.get("status") == "EXECUTING":
                raise ExecutionInProgress("execution is already in progress")
            return record, False
        if on_accepted is not None:
            on_accepted(record)
        if pre_dispatch is not None:
            try:
                pre_dispatch()
            except Exception as exc:
                return (
                    self.reject(
                        execution_id,
                        request_sha256,
                        tool,
                        "pre-dispatch validation rejected execution: " + str(exc),
                        authorization_sha256=authorization_sha256,
                    ),
                    True,
                )
        try:
            result = action()
        except Exception as exc:
            return (
                self.mark_unknown(
                    execution_id,
                    request_sha256,
                    tool,
                    "execution call did not return a trustworthy result; automatic replay prohibited: "
                    + str(exc),
                    authorization_sha256=authorization_sha256,
                ),
                True,
            )
        return self.succeed(
            execution_id, request_sha256, tool, result,
            authorization_sha256=authorization_sha256,
        ), True
