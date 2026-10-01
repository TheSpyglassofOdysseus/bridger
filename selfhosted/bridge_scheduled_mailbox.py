#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
# subprocess is used only with resolved executables and structured argument lists.
import subprocess  # nosec B404
import tempfile
import time
from typing import Any, Protocol

from bridge_execution_grant import (
    authorization_sha256,
    load_hex_key,
    request_sha256 as direct_request_sha256,
    validate_request as validate_direct_request,
    verify_signed_grant,
)
from bridge_execution_ledger import (
    ExecutionConflict,
    ExecutionInProgress,
    ExecutionLedger,
    TERMINAL_STATES,
)
from bridge_direct_socket import UnixRequestQueue
from bridge_tool_policy import validate_direct_tool_arguments

REQUEST_MARKER = "BRIDGE_REQUEST_V1"
RECEIPT_MARKER = "BRIDGE_RECEIPT_V1"
REQUEST_SCHEMA = "bridge-scheduled-request-v1"
RECEIPT_SCHEMA = "bridge-scheduled-receipt-v1"
DEFAULT_REPO = "owner/private-mailbox"
DEFAULT_ISSUE = 1
DEFAULT_TRUSTED_LOGIN = "owner"
DEFAULT_TRUSTED_APP = "chatgpt-codex-connector"
DEFAULT_POLL_SECONDS = 10
DEFAULT_MAX_AGE_SECONDS = 3600
MAX_FUTURE_SKEW_SECONDS = 300
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_TOOL_ARGUMENT_BYTES = 60 * 1024
MAX_BRIDGE_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RECEIPT_RESULT_CHARS = 40_000
MAX_TIMEOUT_MS = 300_000
MAX_COMMAND_CHARS = 16_384
MAX_INPUT_CHARS = 32_768
MAX_PATH_CHARS = 4096
MAX_TEXT_FIELD_CHARS = 60_000
MAX_READ_LENGTH = 100_000
MAX_SEARCH_RESULTS = 5000
MAX_CONTEXT_LINES = 50
MAX_DIRECTORY_DEPTH = 20
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

DIRECT_PATHS = {
    "read_file": "/v1/read-file",
    "write_file": "/v1/write-file",
    "edit_block": "/v1/edit-file",
    "start_process": "/v1/start-process",
    "read_process_output": "/v1/process-output",
    "interact_with_process": "/v1/process-input",
    "list_directory": "/v1/list-directory",
    "get_file_info": "/v1/file-info",
    "list_processes": "/v1/list-processes",
    "start_search": "/v1/search",
    "get_more_search_results": "/v1/search-results",
}

ALLOWED_ARGUMENT_KEYS = {
    "read_file": {"path", "offset", "length", "isUrl", "sheet", "range"},
    "write_file": {"path", "content", "mode"},
    "edit_block": {"file_path", "old_string", "new_string", "expected_replacements", "range"},
    "start_process": {"command", "timeout_ms", "shell", "verbose_timing"},
    "read_process_output": {"pid", "offset", "length", "timeout_ms", "verbose_timing"},
    "interact_with_process": {"pid", "input", "timeout_ms", "wait_for_prompt", "verbose_timing"},
    "list_directory": {"path", "depth"},
    "get_file_info": {"path"},
    "list_processes": set(),
    "start_search": {"path", "pattern", "searchType", "maxResults", "includeHidden", "timeout_ms", "contextLines", "filePattern", "ignoreCase", "earlyTermination", "literalSearch"},
    "get_more_search_results": {"sessionId", "offset", "length"},
}

REQUIRED_ARGUMENT_KEYS = {
    "read_file": {"path"},
    "write_file": {"path", "content"},
    "edit_block": {"file_path"},
    "start_process": {"command", "timeout_ms"},
    "read_process_output": {"pid"},
    "interact_with_process": {"pid", "input"},
    "list_directory": {"path"},
    "get_file_info": {"path"},
    "list_processes": set(),
    "start_search": {"path", "pattern"},
    "get_more_search_results": {"sessionId"},
}


class MailboxError(RuntimeError):
    pass


class GitHubLike(Protocol):
    def fetch_comments(self) -> list[dict[str, Any]]: ...
    def post_comment(self, body: str) -> None: ...


class BridgeLike(Protocol):
    def call(self, tool: str, arguments: dict[str, Any]) -> Any: ...


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_timestamp(value: str) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("created_at must be a non-empty ISO-8601 string")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def parse_marked_json(body: str, marker: str) -> dict[str, Any] | None:
    if not isinstance(body, str):
        return None
    if len(body.encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
        raise ValueError("comment exceeds Bridge mailbox request limit")
    prefix = marker + "\n"
    if not body.startswith(prefix):
        return None
    payload = json.loads(body[len(prefix):].strip())
    if not isinstance(payload, dict):
        raise ValueError("mailbox payload must be a JSON object")
    return payload


def trusted_request_comment(comment: dict[str, Any], *, trusted_login: str, trusted_app_slug: str) -> bool:
    user = comment.get("user")
    app = comment.get("performed_via_github_app")
    if not isinstance(user, dict) or not isinstance(app, dict):
        return False
    return user.get("login") == trusted_login and app.get("slug") == trusted_app_slug


def _bounded_string(arguments: dict[str, Any], key: str, *, max_chars: int, required: bool = False, allow_empty: bool = True) -> None:
    if key not in arguments:
        if required:
            raise ValueError(f"missing required argument: {key}")
        return
    value = arguments[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{key} must not be empty")
    if len(value) > max_chars:
        raise ValueError(f"{key} exceeds mailbox limit")


def _bounded_int(arguments: dict[str, Any], key: str, *, minimum: int = 0, maximum: int | None = None, required: bool = False) -> None:
    if key not in arguments:
        if required:
            raise ValueError(f"missing required argument: {key}")
        return
    value = arguments[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{key} outside mailbox limit")


def _optional_bool(arguments: dict[str, Any], key: str) -> None:
    if key in arguments and not isinstance(arguments[key], bool):
        raise ValueError(f"{key} must be boolean")


def validate_tool_arguments(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool not in DIRECT_PATHS:
        raise ValueError("unsupported Bridge mailbox tool")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    encoded = json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_TOOL_ARGUMENT_BYTES:
        raise ValueError("arguments exceed Bridge mailbox limit")
    unknown = set(arguments) - ALLOWED_ARGUMENT_KEYS[tool]
    if unknown:
        raise ValueError(f"unsupported arguments for {tool}: {','.join(sorted(unknown))}")
    missing = REQUIRED_ARGUMENT_KEYS[tool] - set(arguments)
    if missing:
        raise ValueError(f"missing required arguments for {tool}: {','.join(sorted(missing))}")

    for key in ("path", "file_path"):
        _bounded_string(arguments, key, max_chars=MAX_PATH_CHARS, allow_empty=False)
    for key in ("sheet", "range", "filePattern", "sessionId", "shell"):
        _bounded_string(arguments, key, max_chars=MAX_PATH_CHARS, allow_empty=False)
    for key in ("old_string", "new_string", "content", "pattern"):
        _bounded_string(arguments, key, max_chars=MAX_TEXT_FIELD_CHARS)

    if tool == "start_process":
        _bounded_string(arguments, "command", max_chars=MAX_COMMAND_CHARS, required=True, allow_empty=False)
        _bounded_int(arguments, "timeout_ms", minimum=1, maximum=MAX_TIMEOUT_MS, required=True)
        _optional_bool(arguments, "verbose_timing")
    elif tool == "read_process_output":
        _bounded_int(arguments, "pid", minimum=1, required=True)
        _bounded_int(arguments, "offset", minimum=0)
        _bounded_int(arguments, "length", minimum=1, maximum=MAX_READ_LENGTH)
        _bounded_int(arguments, "timeout_ms", minimum=1, maximum=MAX_TIMEOUT_MS)
        _optional_bool(arguments, "verbose_timing")
    elif tool == "interact_with_process":
        _bounded_int(arguments, "pid", minimum=1, required=True)
        _bounded_string(arguments, "input", max_chars=MAX_INPUT_CHARS, required=True)
        _bounded_int(arguments, "timeout_ms", minimum=1, maximum=MAX_TIMEOUT_MS)
        _optional_bool(arguments, "wait_for_prompt")
        _optional_bool(arguments, "verbose_timing")
    elif tool == "read_file":
        _bounded_int(arguments, "offset", minimum=0)
        _bounded_int(arguments, "length", minimum=1, maximum=MAX_READ_LENGTH)
        _optional_bool(arguments, "isUrl")
    elif tool == "write_file":
        _bounded_string(arguments, "content", max_chars=MAX_TEXT_FIELD_CHARS, required=True)
        if arguments.get("mode", "rewrite") not in {"rewrite", "append"}:
            raise ValueError("mode must be rewrite or append")
    elif tool == "edit_block":
        _bounded_int(arguments, "expected_replacements", minimum=1, maximum=100)
    elif tool == "list_directory":
        _bounded_int(arguments, "depth", minimum=0, maximum=MAX_DIRECTORY_DEPTH)
    elif tool == "list_processes":
        if arguments:
            raise ValueError("list_processes takes no arguments")
    elif tool == "start_search":
        if arguments.get("searchType", "files") not in {"files", "content"}:
            raise ValueError("searchType must be files or content")
        _bounded_int(arguments, "maxResults", minimum=1, maximum=MAX_SEARCH_RESULTS)
        _bounded_int(arguments, "timeout_ms", minimum=1, maximum=MAX_TIMEOUT_MS)
        _bounded_int(arguments, "contextLines", minimum=0, maximum=MAX_CONTEXT_LINES)
        for key in ("includeHidden", "ignoreCase", "earlyTermination", "literalSearch"):
            _optional_bool(arguments, key)
    elif tool == "get_more_search_results":
        _bounded_int(arguments, "offset", minimum=0)
        _bounded_int(arguments, "length", minimum=1, maximum=MAX_SEARCH_RESULTS)

    return arguments


def validate_request(payload: dict[str, Any], *, now: dt.datetime | None = None, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> dict[str, Any]:
    if payload.get("schema_version") != REQUEST_SCHEMA:
        raise ValueError("unsupported request schema_version")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("invalid request_id")
    tool = payload.get("tool")
    if tool not in DIRECT_PATHS:
        raise ValueError("unsupported Bridge mailbox tool")
    arguments = payload.get("arguments")
    validate_tool_arguments(tool, arguments)
    created = parse_timestamp(payload.get("created_at"))
    current = (now or utcnow()).astimezone(dt.timezone.utc)
    age = (current - created).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS:
        raise ValueError("request timestamp is too far in the future")
    if age > max_age_seconds:
        raise ValueError("request is stale")
    return {"schema_version": REQUEST_SCHEMA, "request_id": request_id, "created_at": created.isoformat().replace("+00:00", "Z"), "tool": tool, "arguments": arguments}


def request_sha256(request: dict[str, Any]) -> str:
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def receipt_payload(*, request_id: str, tool: str, status: str, result: Any = None, error: str | None = None, completed_at: dt.datetime | None = None, source_comment_id: int | None = None, request_digest: str | None = None) -> dict[str, Any]:
    completed = (completed_at or utcnow()).astimezone(dt.timezone.utc)
    payload: dict[str, Any] = {"schema_version": RECEIPT_SCHEMA, "request_id": request_id, "tool": tool, "status": status, "completed_at": completed.isoformat().replace("+00:00", "Z"), "source_comment_id": source_comment_id}
    if request_digest is not None:
        payload["request_sha256"] = request_digest
    if error is not None:
        payload["error"] = str(error)[:4000]
    if result is not None:
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload["result_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if len(encoded) <= MAX_RECEIPT_RESULT_CHARS:
            payload["result"] = result
            payload["truncated"] = False
        else:
            payload["result_preview"] = encoded[:MAX_RECEIPT_RESULT_CHARS]
            payload["truncated"] = True
    return payload


def render_receipt(payload: dict[str, Any]) -> str:
    return RECEIPT_MARKER + "\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def receipt_index(
    comments: list[dict[str, Any]], *, trusted_login: str = DEFAULT_TRUSTED_LOGIN
) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for comment in comments:
        user = comment.get("user")
        if not isinstance(user, dict) or user.get("login") != trusted_login:
            continue
        # Server receipts are posted by the host's GitHub CLI, never by the
        # ChatGPT connector app that is authorized to create requests.
        if comment.get("performed_via_github_app") is not None:
            continue
        try:
            payload = parse_marked_json(comment.get("body", ""), RECEIPT_MARKER)
        except (ValueError, json.JSONDecodeError):
            continue
        if not payload or payload.get("schema_version") != RECEIPT_SCHEMA:
            continue
        request_id = payload.get("request_id")
        source_comment_id = payload.get("source_comment_id")
        digest = payload.get("request_sha256")
        tool = payload.get("tool")
        status = payload.get("status")
        if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
            continue
        if isinstance(source_comment_id, bool) or not isinstance(source_comment_id, int) or source_comment_id <= 0:
            continue
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            continue
        if tool not in DIRECT_PATHS or status not in {"ok", "rejected", "unknown_outcome"}:
            continue
        found.setdefault(request_id, []).append(payload)
    return found


def matching_remote_receipt(
    remote_receipts: dict[str, list[dict[str, Any]]],
    *,
    request_id: str,
    source_comment_id: int,
    request_digest: str,
    tool: str,
) -> dict[str, Any] | None:
    for receipt in remote_receipts.get(request_id, []):
        if (
            receipt.get("source_comment_id") == source_comment_id
            and receipt.get("request_sha256") == request_digest
            and receipt.get("tool") == tool
        ):
            return receipt
    return None


def receipt_from_execution(execution: dict[str, Any], *, source_comment_id: int) -> dict[str, Any]:
    status_map = {
        "SUCCEEDED": "ok",
        "REJECTED": "rejected",
        "UNKNOWN_OUTCOME": "unknown_outcome",
    }
    status = status_map.get(execution.get("status"))
    if status is None:
        raise MailboxError("execution is not a mailbox-projectable terminal state")
    payload: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "request_id": execution["execution_id"],
        "tool": execution["tool"],
        "status": status,
        "completed_at": execution["completed_at"],
        "source_comment_id": source_comment_id,
        "request_sha256": execution["request_sha256"],
    }
    if execution.get("error") is not None:
        payload["error"] = str(execution["error"])[:4000]
    for key in ("result_sha256", "result", "result_preview", "truncated"):
        if key in execution:
            payload[key] = execution[key]
    return payload


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"requests": {}, "conflicts": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MailboxError(f"invalid mailbox state file: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("requests"), dict):
            raise MailboxError("invalid mailbox state shape")
        conflicts = payload.setdefault("conflicts", {})
        if not isinstance(conflicts, dict):
            raise MailboxError("invalid mailbox conflict state shape")
        return payload

    def save(self, state: dict[str, Any]) -> None:
        data = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        fd, tmp_name = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)


class GitHubCLI:
    def __init__(self, repo: str, issue: int) -> None:
        self.repo = repo
        self.issue = issue
        gh = shutil.which("gh")
        if not gh or not os.path.isabs(gh):
            raise MailboxError("GitHub CLI executable not found")
        self.gh = gh

    def _run(self, args: list[str], *, input_text: str | None = None) -> str:
        # Arguments are structured by this adapter and the executable is resolved to an absolute path.
        proc = subprocess.run([self.gh, *args], input=input_text, text=True, capture_output=True, check=False, timeout=30)  # nosec B603
        if proc.returncode != 0:
            raise MailboxError(f"gh command failed rc={proc.returncode}: {proc.stderr.strip()[:2000]}")
        return proc.stdout

    def fetch_comments(self) -> list[dict[str, Any]]:
        endpoint = f"repos/{self.repo}/issues/{self.issue}/comments"
        raw = self._run(["api", "--paginate", "--slurp", endpoint])
        pages = json.loads(raw or "[]")
        if not isinstance(pages, list):
            raise MailboxError("GitHub comments response was not a list")
        comments: list[dict[str, Any]] = []
        for page in pages:
            if isinstance(page, list):
                comments.extend(item for item in page if isinstance(item, dict))
            elif isinstance(page, dict):
                comments.append(page)
        return comments

    def post_comment(self, body: str) -> None:
        endpoint = f"repos/{self.repo}/issues/{self.issue}/comments"
        self._run(["api", "-X", "POST", endpoint, "--input", "-"], input_text=json.dumps({"body": body}, ensure_ascii=False))


class BridgeActions:
    def __init__(self, port: int, key: str) -> None:
        if not (1 <= port <= 65535):
            raise ValueError("invalid Bridge Actions port")
        if not key:
            raise ValueError("Bridge Actions key is required")
        self.port = port
        self.key = key

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        path = DIRECT_PATHS.get(tool)
        payload: dict[str, Any]
        if path is None:
            path = "/v1/call"
            payload = {"name": tool, "arguments": arguments}
        else:
            payload = arguments
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=310)
        try:
            conn.request(
                "POST",
                path,
                body=body,
                headers={"X-Bridge-Key": self.key, "Content-Type": "application/json", "Accept": "application/json"},
            )
            response = conn.getresponse()
            raw = response.read(MAX_BRIDGE_RESPONSE_BYTES + 1)
            if response.status < 200 or response.status >= 300:
                detail = raw[:4000].decode("utf-8", errors="replace")
                raise MailboxError(f"Bridge Actions HTTP {response.status}: {detail}")
        except OSError as exc:
            raise MailboxError(f"Bridge Actions unavailable: {exc}") from exc
        finally:
            conn.close()
        if len(raw) > MAX_BRIDGE_RESPONSE_BYTES:
            raise MailboxError("Bridge Actions response exceeded mailbox limit")
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MailboxError("Bridge Actions returned invalid JSON") from exc


class DirectExecutionOwner:
    def __init__(
        self,
        bridge: BridgeLike,
        execution_ledger: ExecutionLedger,
        *,
        clock=utcnow,
    ) -> None:
        self.bridge = bridge
        self.execution_ledger = execution_ledger
        self.clock = clock

    def process_direct(self, payload: dict[str, Any], grant_key: bytes) -> dict[str, Any]:
        if set(payload) != {"schema_version", "request", "grant"}:
            raise MailboxError("invalid direct submission fields")
        if payload.get("schema_version") != "bridger-local-submit-v1":
            raise MailboxError("unsupported direct submission schema")
        request = validate_direct_request(payload["request"])
        validate_direct_tool_arguments(request["tool"], request["arguments"])
        grant_payload = verify_signed_grant(
            payload["grant"], request, grant_key,
            clock=lambda: self.clock().timestamp(),
        )
        request_digest = direct_request_sha256(request)
        auth_digest = authorization_sha256(grant_payload)

        def pre_dispatch() -> None:
            # Revalidate immediately before the machine boundary. A grant that
            # expires while waiting behind another execution cannot dispatch.
            verify_signed_grant(
                payload["grant"], request, grant_key,
                clock=lambda: self.clock().timestamp(),
            )
            validate_direct_tool_arguments(request["tool"], request["arguments"])

        record, executed = self.execution_ledger.execute(
            request["execution_id"],
            request_digest,
            request["tool"],
            lambda: self.bridge.call(request["tool"], request["arguments"]),
            pre_dispatch=pre_dispatch,
            authorization_sha256=auth_digest,
        )
        return {
            "ok": True,
            "executed": executed,
            "execution": record,
            "authority": {
                "item_id": grant_payload["item_id"],
                "project": grant_payload["project"],
                "message_key": grant_payload["message_key"],
                "attempt": grant_payload["attempt"],
                "envelope_hash": grant_payload["envelope_hash"],
                "authorization_sha256": auth_digest,
            },
        }


class Consumer(DirectExecutionOwner):
    def __init__(
        self,
        github: GitHubLike,
        bridge: BridgeLike,
        state_store: StateStore,
        *,
        execution_ledger: ExecutionLedger | None = None,
        trusted_login: str = DEFAULT_TRUSTED_LOGIN,
        trusted_app_slug: str = DEFAULT_TRUSTED_APP,
        max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
        clock=utcnow,
    ) -> None:
        ledger = execution_ledger or ExecutionLedger(
            state_store.path.with_name("execution-ledger.json"), clock=clock
        )
        super().__init__(bridge, ledger, clock=clock)
        self.github = github
        self.state_store = state_store
        self.trusted_login = trusted_login
        self.trusted_app_slug = trusted_app_slug
        self.max_age_seconds = max_age_seconds

    def _migrate_legacy_inflight(self, state: dict[str, Any]) -> None:
        changed = False
        for request_id, record in list(state.get("requests", {}).items()):
            if not isinstance(record, dict) or record.get("status") != "executing":
                continue
            digest = record.get("request_sha256")
            tool = record.get("tool")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                # Legacy state without a digest remains fail-closed in the adapter.
                continue
            if tool not in DIRECT_PATHS:
                continue
            self.execution_ledger.adopt_inflight(
                request_id,
                digest,
                tool,
                accepted_at=record.get("claimed_at") if isinstance(record.get("claimed_at"), str) else None,
            )
            if record.get("execution_id") != request_id:
                record["execution_id"] = request_id
                changed = True
        if changed:
            self.state_store.save(state)

    def _sync_execution_receipts(self, state: dict[str, Any]) -> None:
        changed = False
        status_map = {
            "SUCCEEDED": "completed",
            "REJECTED": "rejected",
            "UNKNOWN_OUTCOME": "unknown_outcome",
        }
        for request_id, record in list(state.get("requests", {}).items()):
            if not isinstance(record, dict) or record.get("execution_id") != request_id:
                continue
            execution = self.execution_ledger.lookup(request_id)
            if not isinstance(execution, dict) or execution.get("status") not in TERMINAL_STATES:
                continue
            if execution.get("status") == "FAILED":
                # Current mailbox dispatch never creates FAILED. Refuse to project an
                # unknown future semantic into today's receipt schema.
                continue
            receipt = receipt_from_execution(
                execution,
                source_comment_id=int(record.get("source_comment_id") or 0),
            )
            if record.get("receipt") != receipt:
                record["receipt"] = receipt
                record["status"] = status_map[execution["status"]]
                record["completed_at"] = execution["completed_at"]
                record.setdefault("posted", False)
                changed = True
        if changed:
            self.state_store.save(state)

    def _post_stored_receipts(
        self,
        state: dict[str, Any],
        remote_receipts: dict[str, list[dict[str, Any]]],
    ) -> None:
        changed = False
        for bucket_name in ("requests", "conflicts"):
            bucket = state.get(bucket_name, {})
            if not isinstance(bucket, dict):
                continue
            for record in list(bucket.values()):
                if not isinstance(record, dict):
                    continue
                receipt = record.get("receipt")
                if not isinstance(receipt, dict):
                    continue
                remote = matching_remote_receipt(
                    remote_receipts,
                    request_id=str(receipt.get("request_id") or ""),
                    source_comment_id=int(receipt.get("source_comment_id") or 0),
                    request_digest=str(receipt.get("request_sha256") or ""),
                    tool=str(receipt.get("tool") or ""),
                )
                if remote is not None:
                    if not record.get("posted"):
                        record["posted"] = True
                        changed = True
                    continue
                if record.get("posted"):
                    continue
                self.github.post_comment(render_receipt(receipt))
                record["posted"] = True
                remote_receipts.setdefault(str(receipt["request_id"]), []).append(receipt)
                changed = True
        if changed:
            self.state_store.save(state)

    def _record_conflict(
        self,
        state: dict[str, Any],
        remote_receipts: dict[str, list[dict[str, Any]]],
        *,
        request_id: str,
        tool: str,
        source_comment_id: int,
        request_digest: str,
        error: str,
    ) -> bool:
        key = f"{request_id}:{source_comment_id}"
        conflicts = state.setdefault("conflicts", {})
        if key in conflicts:
            return False
        receipt = receipt_payload(
            request_id=request_id,
            tool=tool,
            status="rejected",
            error=error,
            completed_at=self.clock(),
            source_comment_id=source_comment_id,
            request_digest=request_digest,
        )
        conflicts[key] = {
            "source_comment_id": source_comment_id,
            "request_sha256": request_digest,
            "tool": tool,
            "status": "rejected",
            "receipt": receipt,
            "posted": False,
        }
        self.state_store.save(state)
        self.github.post_comment(render_receipt(receipt))
        conflicts[key]["posted"] = True
        self.state_store.save(state)
        remote_receipts.setdefault(request_id, []).append(receipt)
        return True

    def _bind_execution(
        self,
        state: dict[str, Any],
        *,
        request_id: str,
        source_comment_id: int,
        request_digest: str,
        tool: str,
        accepted_at: str,
    ) -> None:
        state["requests"][request_id] = {
            "source_comment_id": source_comment_id,
            "request_sha256": request_digest,
            "tool": tool,
            "execution_id": request_id,
            "status": "executing",
            "claimed_at": accepted_at,
            "receipt": None,
            "posted": False,
        }
        self.state_store.save(state)

    def process_once(self) -> int:
        comments = self.github.fetch_comments()
        remote_receipts = receipt_index(comments, trusted_login=self.trusted_login)
        state = self.state_store.load()

        self._migrate_legacy_inflight(state)
        recovered = self.execution_ledger.recover_inflight()
        processed = len(recovered)
        self._sync_execution_receipts(state)
        self._post_stored_receipts(state, remote_receipts)

        for comment in sorted(comments, key=lambda item: int(item.get("id", 0) or 0)):
            body = comment.get("body", "")
            if not isinstance(body, str) or not body.startswith(REQUEST_MARKER + "\n"):
                continue
            if not trusted_request_comment(
                comment,
                trusted_login=self.trusted_login,
                trusted_app_slug=self.trusted_app_slug,
            ):
                continue
            try:
                raw_payload = parse_marked_json(body, REQUEST_MARKER)
                if raw_payload is None:
                    continue
                request = validate_request(
                    raw_payload,
                    now=self.clock(),
                    max_age_seconds=self.max_age_seconds,
                )
            except (ValueError, json.JSONDecodeError) as exc:
                if len(body.encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
                    continue
                try:
                    candidate = json.loads(body.split("\n", 1)[1])
                except (json.JSONDecodeError, IndexError):
                    continue
                request_id = candidate.get("request_id") if isinstance(candidate, dict) else None
                tool = candidate.get("tool") if isinstance(candidate, dict) else None
                if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
                    continue
                if request_id in remote_receipts or request_id in state["requests"]:
                    continue
                receipt = receipt_payload(
                    request_id=request_id,
                    tool=tool if isinstance(tool, str) else "unknown",
                    status="rejected",
                    error=str(exc),
                    completed_at=self.clock(),
                    source_comment_id=int(comment.get("id", 0) or 0),
                )
                state["requests"][request_id] = {
                    "source_comment_id": int(comment.get("id", 0) or 0),
                    "receipt": receipt,
                    "posted": False,
                }
                self.state_store.save(state)
                self.github.post_comment(render_receipt(receipt))
                state["requests"][request_id]["posted"] = True
                self.state_store.save(state)
                remote_receipts.setdefault(request_id, []).append(receipt)
                processed += 1
                continue

            request_id = request["request_id"]
            source_comment_id = int(comment.get("id", 0) or 0)
            digest = request_sha256(request)
            existing = state["requests"].get(request_id)
            if isinstance(existing, dict):
                existing_digest = existing.get("request_sha256")
                if existing_digest == digest:
                    continue
                if existing_digest is None and isinstance(existing.get("receipt"), dict):
                    # Legacy persisted terminal state predating digest binding: never replay it.
                    continue
                if self._record_conflict(
                    state,
                    remote_receipts,
                    request_id=request_id,
                    tool=request["tool"],
                    source_comment_id=source_comment_id,
                    request_digest=digest,
                    error="request_id conflicts with an existing local request digest; execution prohibited",
                ):
                    processed += 1
                continue

            ledger_record = self.execution_ledger.lookup(request_id)
            if isinstance(ledger_record, dict) and (
                ledger_record.get("request_sha256") != digest
                or ledger_record.get("tool") != request["tool"]
                or ledger_record.get("authorization_sha256") is not None
            ):
                if self._record_conflict(
                    state,
                    remote_receipts,
                    request_id=request_id,
                    tool=request["tool"],
                    source_comment_id=source_comment_id,
                    request_digest=digest,
                    error="request_id conflicts with the Bridger execution ledger; execution prohibited",
                ):
                    processed += 1
                continue

            remote_for_id = remote_receipts.get(request_id, [])
            if remote_for_id:
                remote = matching_remote_receipt(
                    remote_receipts,
                    request_id=request_id,
                    source_comment_id=source_comment_id,
                    request_digest=digest,
                    tool=request["tool"],
                )
                if remote is not None:
                    state["requests"][request_id] = {
                        "source_comment_id": source_comment_id,
                        "request_sha256": digest,
                        "tool": request["tool"],
                        "status": "reconciled_remote_receipt",
                        "receipt": remote,
                        "posted": True,
                    }
                    self.state_store.save(state)
                    continue
                if self._record_conflict(
                    state,
                    remote_receipts,
                    request_id=request_id,
                    tool=request["tool"],
                    source_comment_id=source_comment_id,
                    request_digest=digest,
                    error="request_id has a remote receipt bound to a different source/digest; execution prohibited",
                ):
                    processed += 1
                continue

            if isinstance(ledger_record, dict):
                if ledger_record.get("status") == "EXECUTING":
                    # Startup recovery should normally have converted this to
                    # UNKNOWN_OUTCOME. Fail closed if another owner is active.
                    continue
                self._bind_execution(
                    state,
                    request_id=request_id,
                    source_comment_id=source_comment_id,
                    request_digest=digest,
                    tool=request["tool"],
                    accepted_at=str(ledger_record.get("accepted_at") or ""),
                )
                self._sync_execution_receipts(state)
                self._post_stored_receipts(state, remote_receipts)
                processed += 1
                continue

            def accepted(execution: dict[str, Any]) -> None:
                self._bind_execution(
                    state,
                    request_id=request_id,
                    source_comment_id=source_comment_id,
                    request_digest=digest,
                    tool=request["tool"],
                    accepted_at=str(execution["accepted_at"]),
                )

            def freshness_check() -> None:
                # Revalidate immediately before machine dispatch to close the
                # scan/queue expiry race. This callback runs after EXECUTING is
                # durably recorded but before the Bridge action is invoked.
                validate_request(
                    request,
                    now=self.clock(),
                    max_age_seconds=self.max_age_seconds,
                )

            try:
                _, executed = self.execution_ledger.execute(
                    request_id,
                    digest,
                    request["tool"],
                    lambda: self.bridge.call(request["tool"], request["arguments"]),
                    on_accepted=accepted,
                    pre_dispatch=freshness_check,
                )
            except ExecutionConflict:
                if self._record_conflict(
                    state,
                    remote_receipts,
                    request_id=request_id,
                    tool=request["tool"],
                    source_comment_id=source_comment_id,
                    request_digest=digest,
                    error="request_id conflicted during Bridger execution claim; execution prohibited",
                ):
                    processed += 1
                continue
            except ExecutionInProgress:
                continue

            self._sync_execution_receipts(state)
            self._post_stored_receipts(state, remote_receipts)
            if executed:
                processed += 1
        return processed


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise MailboxError(f"{name} must be an integer") from exc


def build_direct_owner() -> DirectExecutionOwner:
    port = env_int("BRIDGE_ACTIONS_PORT", 0)
    key = os.getenv("BRIDGE_ACTIONS_KEY", "")
    if not port or not key:
        raise MailboxError("BRIDGE_ACTIONS_PORT/BRIDGE_ACTIONS_KEY are required")
    ledger_path = Path(os.getenv("BRIDGE_EXECUTION_LEDGER_STATE", str(Path.home() / ".local/state/bridge/execution-ledger.json")))
    return DirectExecutionOwner(
        BridgeActions(port, key),
        ExecutionLedger(ledger_path),
    )


def build_consumer(args: argparse.Namespace) -> Consumer:
    port = env_int("BRIDGE_ACTIONS_PORT", 0)
    key = os.getenv("BRIDGE_ACTIONS_KEY", "")
    if not port or not key:
        raise MailboxError("BRIDGE_ACTIONS_PORT/BRIDGE_ACTIONS_KEY are required")
    state_path = Path(os.getenv("BRIDGE_MAILBOX_STATE", str(Path.home() / ".local/state/bridge/mailbox/state.json")))
    ledger_path = Path(os.getenv("BRIDGE_EXECUTION_LEDGER_STATE", str(Path.home() / ".local/state/bridge/execution-ledger.json")))
    if state_path.resolve() == ledger_path.resolve():
        raise MailboxError("mailbox adapter state and execution ledger must use different files")
    return Consumer(
        GitHubCLI(args.repo, args.issue),
        BridgeActions(port, key),
        StateStore(state_path),
        execution_ledger=ExecutionLedger(ledger_path),
        trusted_login=args.trusted_login,
        trusted_app_slug=args.trusted_app,
        max_age_seconds=args.max_age_seconds,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridger execution owner with optional GitHub compatibility mailbox")
    parser.add_argument("--direct-only", action="store_true", default=os.getenv("BRIDGE_DIRECT_ONLY", "").strip().lower() in {"1", "true", "yes", "on"})
    parser.add_argument("--repo", default=os.getenv("BRIDGE_MAILBOX_REPO", DEFAULT_REPO))
    parser.add_argument("--issue", type=int, default=env_int("BRIDGE_MAILBOX_ISSUE", DEFAULT_ISSUE))
    parser.add_argument("--trusted-login", default=os.getenv("BRIDGE_MAILBOX_TRUSTED_LOGIN", DEFAULT_TRUSTED_LOGIN))
    parser.add_argument("--trusted-app", default=os.getenv("BRIDGE_MAILBOX_TRUSTED_APP", DEFAULT_TRUSTED_APP))
    parser.add_argument("--max-age-seconds", type=int, default=env_int("BRIDGE_MAILBOX_MAX_AGE_SECONDS", DEFAULT_MAX_AGE_SECONDS))
    parser.add_argument("--poll-seconds", type=int, default=env_int("BRIDGE_MAILBOX_POLL_SECONDS", DEFAULT_POLL_SECONDS))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.issue <= 0 or args.max_age_seconds <= 0 or args.poll_seconds <= 0:
        raise SystemExit("issue/max-age/poll values must be positive")
    if not args.direct_only:
        if args.repo == DEFAULT_REPO or args.trusted_login == DEFAULT_TRUSTED_LOGIN:
            raise SystemExit("BRIDGE_MAILBOX_REPO and BRIDGE_MAILBOX_TRUSTED_LOGIN must be configured explicitly")
        if "/" not in args.repo or not args.trusted_app.strip():
            raise SystemExit("mailbox repo must be owner/repo and trusted app must be non-empty")
    direct_owner = build_direct_owner() if args.direct_only else None
    consumer = None if args.direct_only else build_consumer(args)
    if args.once:
        if args.direct_only:
            print("BRIDGE_DIRECT_OWNER_ONCE=PASS processed=0")
            return 0
        if consumer is None:
            raise SystemExit("mailbox consumer was not initialized")
        count = consumer.process_once()
        print(f"BRIDGE_MAILBOX_ONCE=PASS processed={count}")
        return 0

    socket_raw = os.getenv("BRIDGE_DIRECT_SOCKET", "").strip()
    key_file_raw = os.getenv("BRIDGE_EXECUTION_GRANT_KEY_FILE", "").strip()
    if bool(socket_raw) != bool(key_file_raw):
        raise SystemExit("BRIDGE_DIRECT_SOCKET and BRIDGE_EXECUTION_GRANT_KEY_FILE must be configured together")
    if args.direct_only and not socket_raw:
        raise SystemExit("direct-only execution owner requires BRIDGE_DIRECT_SOCKET and BRIDGE_EXECUTION_GRANT_KEY_FILE")
    direct_queue: UnixRequestQueue | None = None
    grant_key: bytes | None = None
    if socket_raw:
        grant_key = load_hex_key(Path(key_file_raw))
        direct_queue = UnixRequestQueue(Path(socket_raw))
        direct_queue.start()

    next_mailbox_poll = float("inf") if args.direct_only else 0.0
    try:
        while True:
            now = time.monotonic()
            if not args.direct_only and now >= next_mailbox_poll:
                try:
                    if consumer is None:
                        raise MailboxError("mailbox consumer was not initialized")
                    consumer.process_once()
                except Exception as exc:
                    print(f"bridge-mailbox iteration failed: {exc}", flush=True)
                next_mailbox_poll = time.monotonic() + args.poll_seconds
            if direct_queue is not None and grant_key is not None:
                direct_queue.process_pending(
                    lambda payload: (direct_owner or consumer).process_direct(payload, grant_key),
                    max_items=16,
                )
                time.sleep(0.1)
            else:
                time.sleep(min(1.0, max(0.1, next_mailbox_poll - time.monotonic())))
    finally:
        if direct_queue is not None:
            direct_queue.close()


if __name__ == "__main__":
    raise SystemExit(main())
