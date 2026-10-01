from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest

SELFHOSTED = Path(__file__).resolve().parents[1] / "selfhosted"
sys.path.insert(0, str(SELFHOSTED))

import bridge_execution_grant as grants
import bridge_scheduled_mailbox as mailbox
from bridge_direct_socket import UnixRequestQueue, submit
from bridge_execution_ledger import ExecutionConflict

KEY = b"k" * 32
NOW = dt.datetime(2026, 9, 17, 13, 30, tzinfo=dt.timezone.utc)


class FakeGitHub:
    def fetch_comments(self):
        return []

    def post_comment(self, body):
        raise AssertionError("direct execution must not post GitHub comments")


class FakeBridge:
    def __init__(self):
        self.calls = []

    def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        return {"ok": True, "result": "example-host"}


def request(execution_id="direct-1", **overrides):
    value = {
        "execution_id": execution_id,
        "tool": "read_file",
        "arguments": {"path": "/etc/hostname"},
        "requested_risk_class": "SAFE_RETRY",
    }
    value.update(overrides)
    return value


def signed(req, *, item_id=1, attempt=1, issued=None, expires=None):
    issued = NOW.timestamp() if issued is None else issued
    expires = issued + 30 if expires is None else expires
    payload = {
        "schema_version": grants.GRANT_SCHEMA,
        "audience": grants.GRANT_AUDIENCE,
        "item_id": item_id,
        "project": "demo",
        "message_key": f"work:{item_id}",
        "envelope_hash": hashlib.sha256(f"envelope:{item_id}".encode()).hexdigest(),
        "attempt": attempt,
        "execution_id": req["execution_id"],
        "tool": req["tool"],
        "request_sha256": grants.request_sha256(req),
        "requested_risk_class": req["requested_risk_class"],
        "issued_at": issued,
        "expires_at": expires,
        "nonce": "ab" * 16,
    }
    signature = hmac.new(KEY, grants.canonical(payload).encode(), hashlib.sha256).hexdigest()
    return {"grant": payload, "signature": signature}


def submission(req, grant):
    return {"schema_version": "bridger-local-submit-v1", "request": req, "grant": grant}


class DirectExecutionTests(unittest.TestCase):
    def make_consumer(self, tmp, bridge=None):
        bridge = bridge or FakeBridge()
        consumer = mailbox.Consumer(
            FakeGitHub(),
            bridge,
            mailbox.StateStore(Path(tmp) / "mailbox.json"),
            clock=lambda: NOW,
        )
        return consumer, bridge

    def test_valid_direct_execution_and_exact_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer, bridge = self.make_consumer(tmp)
            req = request()
            payload = submission(req, signed(req))
            first = consumer.process_direct(payload, KEY)
            second = consumer.process_direct(payload, KEY)
            self.assertTrue(first["executed"])
            self.assertFalse(second["executed"])
            self.assertEqual(first["execution"]["status"], "SUCCEEDED")
            self.assertEqual(len(bridge.calls), 1)
            self.assertIsNotNone(first["execution"]["authorization_sha256"])
            self.assertEqual(
                first["authority"]["authorization_sha256"],
                first["execution"]["authorization_sha256"],
            )

    def test_different_passrail_work_cannot_reuse_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer, bridge = self.make_consumer(tmp)
            req = request()
            consumer.process_direct(submission(req, signed(req, item_id=1)), KEY)
            with self.assertRaises(ExecutionConflict):
                consumer.process_direct(submission(req, signed(req, item_id=2)), KEY)
            self.assertEqual(len(bridge.calls), 1)

    def test_expired_or_tampered_grant_never_calls_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer, bridge = self.make_consumer(tmp)
            req = request()
            expired = signed(req, issued=NOW.timestamp() - 60, expires=NOW.timestamp() - 1)
            with self.assertRaisesRegex(grants.GrantValidationError, "expired"):
                consumer.process_direct(submission(req, expired), KEY)
            tampered = signed(req)
            tampered["grant"]["item_id"] = 99
            with self.assertRaisesRegex(grants.GrantValidationError, "signature"):
                consumer.process_direct(submission(req, tampered), KEY)
            self.assertEqual(bridge.calls, [])

    def test_consequential_request_requires_no_auto_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer, bridge = self.make_consumer(tmp)
            req = request(
                tool="start_process",
                arguments={"command": "printf ok", "timeout_ms": 1000},
                requested_risk_class="SAFE_RETRY",
            )
            with self.assertRaisesRegex(grants.GrantValidationError, "NO_AUTO_RETRY"):
                consumer.process_direct(submission(req, {"grant": {}, "signature": ""}), KEY)
            self.assertEqual(bridge.calls, [])

    def test_owner_only_unix_socket_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "direct" / "bridger.sock"
            server = UnixRequestQueue(path)
            server.start()
            self.addCleanup(server.close)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(stat.S_ISSOCK(path.stat().st_mode))
            result = {}

            def client():
                result.update(submit(path, {"ping": "pong"}, timeout=5))

            thread = threading.Thread(target=client)
            thread.start()
            deadline = time.time() + 5
            while thread.is_alive() and time.time() < deadline:
                server.process_pending(lambda payload: {"ok": True, "echo": payload})
                time.sleep(0.01)
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result, {"ok": True, "echo": {"ping": "pong"}})


if __name__ == "__main__":
    unittest.main()
