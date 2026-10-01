from __future__ import annotations

from pathlib import Path
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SELFHOSTED = Path(__file__).resolve().parents[1] / "selfhosted"
sys.path.insert(0, str(SELFHOSTED))

import passrail_direct_worker as worker_module

KEY = b"k" * 32


def item(request, *, risk_class="SAFE_RETRY", policy="AUTO_READ_ONLY", authority=False):
    envelope = {
        "project": "demo",
        "message_key": "work:1",
        "kind": worker_module.PAYLOAD_SCHEMA,
        "role": worker_module.ROLE,
        "priority": 0,
        "risk_class": risk_class,
        "payload": {
            "schema_version": worker_module.PAYLOAD_SCHEMA,
            "request": request,
            "completion_policy": policy,
        },
    }
    if authority:
        envelope["authority_ref"] = "git:/srv/bridger-demo"
        envelope["authority_version"] = "a" * 40
    return {"id": 1, "claim_token": "token", "envelope": envelope}


class FakeRail:
    def __init__(self, claimed):
        self.claimed = claimed
        self.calls = []

    def claim(self, project, role, consumer, lease_seconds):
        self.calls.append(("claim", project, role, consumer, lease_seconds))
        value, self.claimed = self.claimed, None
        return value

    def mint_execution_grant(self, item_id, token, request, key, ttl_seconds):
        self.calls.append(("grant", item_id, token, request, ttl_seconds))
        return {"grant": {"placeholder": True}, "signature": "x"}

    def complete(self, item_id, token, receipt):
        self.calls.append(("complete", item_id, token, receipt))
        return {"state": "DONE", "receipt": receipt}

    def mark_unknown(self, item_id, token, receipt):
        self.calls.append(("unknown", item_id, token, receipt))
        return {"state": "UNKNOWN_OUTCOME", "receipt": receipt}

    def fail(self, item_id, token, reason):
        self.calls.append(("fail", item_id, token, reason))
        return {"state": "FAILED", "reason": reason}

    def expire(self):
        self.calls.append(("expire",))
        return []


def successful_response(status="SUCCEEDED"):
    return {
        "ok": True,
        "executed": True,
        "execution": {
            "execution_id": "exec-1",
            "tool": "read_file",
            "status": status,
            "request_sha256": "a" * 64,
            "authorization_sha256": "b" * 64,
        },
        "authority": {
            "item_id": 1,
            "project": "demo",
            "message_key": "work:1",
            "attempt": 1,
            "envelope_hash": "c" * 64,
            "authorization_sha256": "b" * 64,
        },
    }


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.original_submit = worker_module.submit
        self.original_git_authority = worker_module._git_authority
        self.temp = tempfile.TemporaryDirectory()
        self.socket_path = Path(self.temp.name) / "bridger.sock"
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(self.socket_path))
        self.addCleanup(self.restore)

    def restore(self):
        worker_module.submit = self.original_submit
        worker_module._git_authority = self.original_git_authority
        self.socket.close()
        self.temp.cleanup()

    def test_host_authority_profile_targets_execution_owner(self):
        import os
        import pwd
        user = pwd.getpwuid(os.getuid()).pw_name
        value = worker_module._host_authority(f"host:{user}", "host-admin-v1")
        self.assertEqual(value["type"], "host")
        self.assertEqual(value["user"], user)
        with self.assertRaisesRegex(worker_module.WorkerError, "version"):
            worker_module._host_authority(f"host:{user}", "wrong")

    def test_git_authority_accepts_configured_root_and_rejects_outside(self):
        authority_root = Path(self.temp.name) / "allowed"
        repo = authority_root / "repo"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Bridger Test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
        (repo / "README.md").write_text("test\n")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "test"], check=True)
        head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        with mock.patch.dict(os.environ, {"BRIDGE_GIT_AUTHORITY_ROOTS": str(authority_root)}):
            value = worker_module._git_authority(f"git:{repo}", head)
            self.assertEqual(value["path"], str(repo.resolve()))
            outside = Path(self.temp.name) / "outside"
            outside.mkdir()
            with self.assertRaisesRegex(worker_module.WorkerError, "allowed root"):
                worker_module._git_authority(f"git:{outside}", head)

    def test_process_cycle_reopens_passrail_connection_each_poll(self):
        instances = []

        class CycleRail:
            def __init__(self, db):
                self.db = db
                instances.append(self)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def claim(self, project, role, consumer, lease_seconds):
                return None

        for _ in range(2):
            processed = worker_module.process_cycle(
                CycleRail, Path('/tmp/passrail.sqlite3'), ['demo'], self.socket_path, KEY
            )
            self.assertEqual(processed, 0)
        self.assertEqual(len(instances), 2)
        self.assertIsNot(instances[0], instances[1])

    def test_read_only_success_completes(self):
        req = {
            "execution_id": "exec-1",
            "tool": "read_file",
            "arguments": {"path": "/etc/hostname"},
            "requested_risk_class": "SAFE_RETRY",
        }
        rail = FakeRail(item(req))
        worker_module.submit = lambda path, payload: successful_response()
        worker = worker_module.Worker(rail, socket_path=self.socket_path, grant_key=KEY)
        result = worker.process_project("demo")
        self.assertEqual(result["state"], "DONE")
        self.assertEqual([call[0] for call in rail.calls], ["claim", "grant", "complete"])

    def test_consequential_success_requires_reconciliation(self):
        req = {
            "execution_id": "exec-1",
            "tool": "start_process",
            "arguments": {"command": "printf ok", "timeout_ms": 1000},
            "requested_risk_class": "NO_AUTO_RETRY",
        }
        rail = FakeRail(item(req, risk_class="NO_AUTO_RETRY", policy="REQUIRE_RECONCILIATION", authority=True))
        worker_module._git_authority = lambda ref, version: {"type": "git", "path": "/srv/bridger-demo", "head": version, "clean": True}
        response = successful_response()
        response["execution"]["tool"] = "start_process"
        worker_module.submit = lambda path, payload: response
        worker = worker_module.Worker(rail, socket_path=self.socket_path, grant_key=KEY)
        result = worker.process_project("demo")
        self.assertEqual(result["state"], "UNKNOWN_OUTCOME")
        unknown = rail.calls[-1][3]
        self.assertEqual(unknown["status"], "AWAITING_RECONCILIATION")
        self.assertEqual(unknown["authority_precheck"]["clean"], True)

    def test_transport_loss_is_unknown_never_retry(self):
        req = {
            "execution_id": "exec-1",
            "tool": "read_file",
            "arguments": {"path": "/etc/hostname"},
            "requested_risk_class": "SAFE_RETRY",
        }
        rail = FakeRail(item(req))
        def lost(path, payload):
            raise TimeoutError("response lost")
        worker_module.submit = lost
        worker = worker_module.Worker(rail, socket_path=self.socket_path, grant_key=KEY)
        result = worker.process_project("demo")
        self.assertEqual(result["state"], "UNKNOWN_OUTCOME")
        self.assertEqual([call[0] for call in rail.calls], ["claim", "grant", "unknown"])

    def test_invalid_work_fails_before_grant(self):
        req = {
            "execution_id": "exec-1",
            "tool": "start_process",
            "arguments": {"command": "printf ok", "timeout_ms": 1000},
            "requested_risk_class": "SAFE_RETRY",
        }
        rail = FakeRail(item(req))
        worker = worker_module.Worker(rail, socket_path=self.socket_path, grant_key=KEY)
        result = worker.process_project("demo")
        self.assertEqual(result["state"], "FAILED")
        self.assertEqual([call[0] for call in rail.calls], ["claim", "fail"])


if __name__ == "__main__":
    unittest.main()
