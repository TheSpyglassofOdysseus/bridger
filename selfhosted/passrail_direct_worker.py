#!/usr/bin/env python3
"""Local Passrail -> Bridger execution adapter. No GitHub runtime transport."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import shutil
# subprocess is used only for read-only Git queries after authority-root validation.
import subprocess  # nosec B404
import sys
import time
from typing import Any

from bridge_direct_socket import submit
from bridge_execution_grant import load_hex_key, validate_request as validate_direct_request
from bridge_tool_policy import READ_ONLY_TOOLS

DEFAULT_HOME = Path.home()
DEFAULT_PASSRAIL_SRC = DEFAULT_HOME / ".local/lib/passrail/current"
DEFAULT_SOCKET = DEFAULT_HOME / ".local/state/bridge-mailbox/direct/bridger.sock"
DEFAULT_DB = DEFAULT_HOME / ".local/state/passrail/passrail.sqlite3"
ROLE = "bridger-executor"
PAYLOAD_SCHEMA = "passrail-bridger-execution-v1"
RECEIPT_SCHEMA = "passrail-bridger-receipt-v1"
class WorkerError(RuntimeError):
    pass


def load_passrail(src: Path):
    src = Path(src)
    if not src.is_dir():
        raise WorkerError(f"Passrail source path is unavailable: {src}")
    text = str(src)
    if text not in sys.path:
        sys.path.insert(0, text)
    from passrail import InvalidClaim, PassrailError, Rail  # type: ignore
    return Rail, PassrailError, InvalidClaim


def _git_authority_roots() -> list[Path]:
    raw = os.getenv("BRIDGE_GIT_AUTHORITY_ROOTS", "").strip()
    if not raw:
        return [Path.home().resolve()]
    roots = [Path(value.strip()).expanduser().resolve() for value in raw.split(os.pathsep) if value.strip()]
    if not roots:
        raise WorkerError("BRIDGE_GIT_AUTHORITY_ROOTS contains no usable paths")
    return roots


def _git_authority(authority_ref: str, authority_version: str) -> dict[str, Any]:
    prefix = "git:"
    if not authority_ref.startswith(prefix):
        raise WorkerError("consequential execution requires git:<absolute-path> authority_ref")
    repo = Path(authority_ref[len(prefix):]).expanduser().resolve()
    roots = _git_authority_roots()
    if not repo.is_absolute() or not any(repo == root or root in repo.parents for root in roots):
        allowed = os.pathsep.join(str(root) for root in roots)
        raise WorkerError(f"git authority path must be under an allowed root: {allowed}")
    if not (repo / ".git").exists():
        # Worktrees use a .git file, so exists() is sufficient.
        raise WorkerError("git authority path is not a repository/worktree")
    git = shutil.which("git")
    if not git or not os.path.isabs(git):
        raise WorkerError("git executable not found")
    # The executable is absolute and repo has already been constrained to an allowed authority root.
    head = subprocess.check_output([git, "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=10).strip()  # nosec B603
    if head != authority_version:
        raise WorkerError(f"git authority version changed: expected {authority_version}, got {head}")
    status = subprocess.check_output([git, "-C", str(repo), "status", "--porcelain"], text=True, timeout=10)  # nosec B603
    if status.strip():
        raise WorkerError("git authority worktree is not clean")
    return {"type": "git", "path": str(repo), "head": head, "clean": True}


def _host_authority(authority_ref: str, authority_version: str) -> dict[str, Any]:
    user = pwd.getpwuid(os.getuid()).pw_name
    if authority_ref != f"host:{user}":
        raise WorkerError(f"host authority must target the execution owner ({user})")
    if authority_version != "host-admin-v1":
        raise WorkerError("unsupported host authority version")
    return {
        "type": "host",
        "user": user,
        "uid": os.getuid(),
        "hostname": socket.gethostname(),
        "profile": authority_version,
    }


def _authority(authority_ref: str, authority_version: str) -> dict[str, Any]:
    if authority_ref.startswith("git:"):
        return _git_authority(authority_ref, authority_version)
    if authority_ref.startswith("host:"):
        return _host_authority(authority_ref, authority_version)
    raise WorkerError("unsupported consequential authority_ref")


def validate_item(item: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    envelope = item.get("envelope")
    if not isinstance(envelope, dict) or envelope.get("kind") != PAYLOAD_SCHEMA:
        raise WorkerError("unsupported Passrail work kind")
    if envelope.get("role") != ROLE:
        raise WorkerError("Passrail work role is not bridger-executor")
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "request", "completion_policy"}:
        raise WorkerError("invalid Bridger execution payload")
    if payload.get("schema_version") != PAYLOAD_SCHEMA:
        raise WorkerError("unsupported Bridger execution payload schema")
    request = validate_direct_request(payload.get("request"))
    if envelope.get("risk_class") != request["requested_risk_class"]:
        raise WorkerError("Passrail envelope risk_class must match direct request risk class")
    policy = payload.get("completion_policy")
    if policy not in {"AUTO_READ_ONLY", "REQUIRE_RECONCILIATION"}:
        raise WorkerError("invalid completion_policy")
    authority = None
    if request["tool"] in READ_ONLY_TOOLS:
        if policy != "AUTO_READ_ONLY":
            raise WorkerError("read-only tools must use AUTO_READ_ONLY")
    else:
        if request["requested_risk_class"] != "NO_AUTO_RETRY":
            raise WorkerError("consequential tools require NO_AUTO_RETRY")
        if policy != "REQUIRE_RECONCILIATION":
            raise WorkerError("consequential tools require reconciliation")
        authority_ref = envelope.get("authority_ref")
        authority_version = envelope.get("authority_version")
        if not isinstance(authority_ref, str) or not isinstance(authority_version, str):
            raise WorkerError("consequential work requires authority_ref and authority_version")
        authority = _authority(authority_ref, authority_version)
    return request, policy, authority


def execution_receipt(response: dict[str, Any], authority_precheck: dict[str, Any] | None) -> dict[str, Any]:
    execution = response.get("execution") if isinstance(response, dict) else None
    authority = response.get("authority") if isinstance(response, dict) else None
    if not isinstance(execution, dict) or not isinstance(authority, dict):
        raise WorkerError("Bridger direct response missing execution/authority")
    return {
        "schema_version": RECEIPT_SCHEMA,
        "execution": execution,
        "authority": authority,
        "authority_precheck": authority_precheck,
    }


class Worker:
    def __init__(
        self,
        rail,
        *,
        socket_path: Path,
        grant_key: bytes,
        consumer: str = "bridger-local-worker",
        lease_seconds: int = 600,
        grant_ttl_seconds: int = 30,
    ) -> None:
        self.rail = rail
        self.socket_path = Path(socket_path)
        self.grant_key = grant_key
        self.consumer = consumer
        self.lease_seconds = lease_seconds
        self.grant_ttl_seconds = grant_ttl_seconds

    def process_project(self, project: str) -> dict[str, Any] | None:
        try:
            socket_info = self.socket_path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISSOCK(socket_info.st_mode):
            return None
        item = self.rail.claim(project, ROLE, self.consumer, self.lease_seconds)
        if item is None:
            return None
        token = item["claim_token"]
        try:
            request, policy, authority_precheck = validate_item(item)
        except Exception as exc:
            return self.rail.fail(item["id"], token, f"direct adapter validation failed: {exc}")

        grant = self.rail.mint_execution_grant(
            item["id"], token, request, self.grant_key, ttl_seconds=self.grant_ttl_seconds
        )
        submission = {
            "schema_version": "bridger-local-submit-v1",
            "request": request,
            "grant": grant,
        }
        try:
            response = submit(self.socket_path, submission)
        except Exception as exc:
            # The request may have crossed the machine boundary before the
            # response was lost. Never blind-replay this claim.
            return self.rail.mark_unknown(
                item["id"], token,
                {"schema_version": RECEIPT_SCHEMA, "status": "UNKNOWN_OUTCOME", "error": str(exc)[:4000]},
            )
        if not response.get("ok"):
            return self.rail.mark_unknown(
                item["id"], token,
                {"schema_version": RECEIPT_SCHEMA, "status": "UNKNOWN_OUTCOME", "direct_response": response},
            )
        receipt = execution_receipt(response, authority_precheck)
        status = receipt["execution"].get("status")
        try:
            if status == "SUCCEEDED" and policy == "AUTO_READ_ONLY":
                return self.rail.complete(item["id"], token, receipt)
            if status == "REJECTED":
                return self.rail.fail(item["id"], token, "Bridger rejected execution before host effect")
            if status in {"UNKNOWN_OUTCOME", "SUCCEEDED"}:
                # A successful consequential host call still requires project
                # postcondition reconciliation before Passrail may say DONE.
                receipt["status"] = "UNKNOWN_OUTCOME" if status == "UNKNOWN_OUTCOME" else "AWAITING_RECONCILIATION"
                return self.rail.mark_unknown(item["id"], token, receipt)
            return self.rail.fail(item["id"], token, f"Bridger terminal status: {status}")
        except Exception:
            # If the lease expired while the host call ran, expire it now.
            # NO_AUTO_RETRY work becomes UNKNOWN_OUTCOME; SAFE_RETRY read-only
            # work may safely return to READY.
            self.rail.expire()
            raise


def process_cycle(Rail, db: Path, projects: list[str], socket_path: Path, key: bytes) -> int:
    """Process one polling cycle using a fresh SQLite connection.

    Reopening per cycle avoids a long-lived worker retaining stale/unlinked WAL
    sidecars if another Passrail process closes/recreates the SQLite WAL files.
    """
    processed = 0
    with Rail(db) as rail:
        worker = Worker(rail, socket_path=socket_path, grant_key=key)
        for project in projects:
            if worker.process_project(project) is not None:
                processed += 1
    return processed


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Passrail to Bridger execution worker")
    parser.add_argument("--project", action="append", dest="projects")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    projects = args.projects or [p.strip() for p in os.getenv("PASSRAIL_BRIDGER_PROJECTS", "").split(",") if p.strip()]
    if not projects:
        raise SystemExit("at least one --project or PASSRAIL_BRIDGER_PROJECTS entry is required")
    src = Path(os.getenv("PASSRAIL_SRC", str(DEFAULT_PASSRAIL_SRC)))
    Rail, _, _ = load_passrail(src)
    db = Path(os.getenv("PASSRAIL_DB", str(DEFAULT_DB)))
    socket_path = Path(os.getenv("BRIDGE_DIRECT_SOCKET", str(DEFAULT_SOCKET)))
    key_path_raw = os.getenv("BRIDGE_EXECUTION_GRANT_KEY_FILE", "").strip()
    if not key_path_raw:
        raise SystemExit("BRIDGE_EXECUTION_GRANT_KEY_FILE is required")
    key = load_hex_key(Path(key_path_raw))
    while True:
        processed = process_cycle(Rail, db, projects, socket_path, key)
        if args.once:
            print(json.dumps({"ok": True, "processed": processed, "projects": projects}, sort_keys=True))
            return 0
        if processed == 0:
            time.sleep(max(0.1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
