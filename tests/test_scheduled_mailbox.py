from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

MODULE = Path(__file__).parents[1] / "selfhosted" / "bridge_scheduled_mailbox.py"
sys.path.insert(0, str(MODULE.parent))
spec = importlib.util.spec_from_file_location("bridge_scheduled_mailbox", MODULE)
mailbox = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mailbox)

NOW = dt.datetime(2026, 9, 13, 18, 30, tzinfo=dt.timezone.utc)


def request_body(request_id="req-1", tool="read_file", created="2026-09-13T18:29:00Z", arguments=None):
    return mailbox.REQUEST_MARKER + "\n" + json.dumps({
        "schema_version": mailbox.REQUEST_SCHEMA,
        "request_id": request_id,
        "created_at": created,
        "tool": tool,
        "arguments": arguments if arguments is not None else {"path": "/etc/hostname"},
    })


def trusted_comment(comment_id=1, **kwargs):
    return {
        "id": comment_id,
        "body": request_body(**kwargs),
        "user": {"login": mailbox.DEFAULT_TRUSTED_LOGIN},
        "performed_via_github_app": {"slug": mailbox.DEFAULT_TRUSTED_APP},
    }


class FakeGitHub:
    def __init__(self, comments):
        self.comments = list(comments)
        self.posted = []
        self.next_id = 1000

    def fetch_comments(self):
        return list(self.comments)

    def post_comment(self, body):
        self.posted.append(body)
        self.comments.append({
            "id": self.next_id,
            "body": body,
            "user": {"login": mailbox.DEFAULT_TRUSTED_LOGIN},
            "performed_via_github_app": None,
        })
        self.next_id += 1


class FakeBridge:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result if result is not None else {"content": "example-host"}
        self.error = error

    def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        if self.error:
            raise self.error
        return self.result


class FailOnceGitHub(FakeGitHub):
    def __init__(self, comments):
        super().__init__(comments)
        self.failures_remaining = 1

    def post_comment(self, body):
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("simulated receipt transport failure")
        super().post_comment(body)


class MailboxTests(unittest.TestCase):
    def test_direct_owner_builder_never_constructs_github_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "BRIDGE_ACTIONS_PORT": "18878",
                "BRIDGE_ACTIONS_KEY": "test-secret",
                "BRIDGE_EXECUTION_LEDGER_STATE": str(Path(tmp) / "ledger.json"),
            }
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
                mailbox.GitHubCLI, "__init__", side_effect=AssertionError("GitHub adapter constructed")
            ):
                owner = mailbox.build_direct_owner()
            self.assertIsInstance(owner, mailbox.DirectExecutionOwner)
            self.assertFalse(hasattr(owner, "github"))
            self.assertFalse(hasattr(owner, "state_store"))

    def test_direct_only_owner_does_not_require_github_mailbox_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.update({
                "BRIDGE_ACTIONS_PORT": "18878",
                "BRIDGE_ACTIONS_KEY": "test-secret",
                "BRIDGE_MAILBOX_STATE": str(Path(tmp) / "mailbox.json"),
                "BRIDGE_EXECUTION_LEDGER_STATE": str(Path(tmp) / "ledger.json"),
            })
            env.pop("BRIDGE_MAILBOX_REPO", None)
            env.pop("BRIDGE_MAILBOX_TRUSTED_LOGIN", None)
            proc = subprocess.run(
                [sys.executable, str(MODULE), "--direct-only", "--once"],
                env=env, text=True, capture_output=True, timeout=10, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("BRIDGE_DIRECT_OWNER_ONCE=PASS", proc.stdout)

    def test_bridge_actions_uses_generic_call_for_parity_tools(self):
        captured = {}

        class Response:
            status = 200
            def read(self, _limit):
                return b'{"ok":true,"tool":"create_directory","result":{"content":"ok"}}'

        class Connection:
            def __init__(self, host, port, timeout):
                captured["host"] = host
                captured["port"] = port
                captured["timeout"] = timeout
            def request(self, method, path, body, headers):
                captured["method"] = method
                captured["path"] = path
                captured["body"] = json.loads(body.decode("utf-8"))
                captured["headers"] = headers
            def getresponse(self):
                return Response()
            def close(self):
                captured["closed"] = True

        bridge = mailbox.BridgeActions(18878, "secret")
        with mock.patch.object(mailbox.http.client, "HTTPConnection", Connection):
            result = bridge.call("create_directory", {"path": "/tmp/example"})
        self.assertTrue(result["ok"])
        self.assertEqual(captured["host"], "127.0.0.1")
        self.assertEqual(captured["path"], "/v1/call")
        self.assertTrue(captured["closed"])
        self.assertEqual(captured["body"], {
            "name": "create_directory",
            "arguments": {"path": "/tmp/example"},
        })

    def test_valid_request(self):
        payload = mailbox.parse_marked_json(request_body(), mailbox.REQUEST_MARKER)
        value = mailbox.validate_request(payload, now=NOW)
        self.assertEqual(value["request_id"], "req-1")
        self.assertEqual(value["tool"], "read_file")

    def test_rejects_stale_request(self):
        payload = mailbox.parse_marked_json(request_body(created="2026-09-13T16:00:00Z"), mailbox.REQUEST_MARKER)
        with self.assertRaisesRegex(ValueError, "stale"):
            mailbox.validate_request(payload, now=NOW, max_age_seconds=3600)

    def test_rejects_future_request(self):
        payload = mailbox.parse_marked_json(request_body(created="2026-09-13T19:00:00Z"), mailbox.REQUEST_MARKER)
        with self.assertRaisesRegex(ValueError, "future"):
            mailbox.validate_request(payload, now=NOW)

    def test_rejects_unsupported_tool(self):
        payload = mailbox.parse_marked_json(request_body(tool="set_config_value"), mailbox.REQUEST_MARKER)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            mailbox.validate_request(payload, now=NOW)

    def test_provenance_requires_user_and_app(self):
        comment = trusted_comment()
        self.assertTrue(mailbox.trusted_request_comment(
            comment,
            trusted_login=mailbox.DEFAULT_TRUSTED_LOGIN,
            trusted_app_slug=mailbox.DEFAULT_TRUSTED_APP,
        ))
        comment["performed_via_github_app"] = {"slug": "other"}
        self.assertFalse(mailbox.trusted_request_comment(
            comment,
            trusted_login=mailbox.DEFAULT_TRUSTED_LOGIN,
            trusted_app_slug=mailbox.DEFAULT_TRUSTED_APP,
        ))

    def test_receipt_hash_and_truncation(self):
        small = mailbox.receipt_payload(request_id="x", tool="read_file", status="ok", result={"a": 1}, completed_at=NOW)
        self.assertFalse(small["truncated"])
        self.assertIn("result_sha256", small)
        big = mailbox.receipt_payload(request_id="y", tool="read_file", status="ok", result={"x": "a" * 50000}, completed_at=NOW)
        self.assertTrue(big["truncated"])
        self.assertNotIn("result", big)
        self.assertLessEqual(len(big["result_preview"]), mailbox.MAX_RECEIPT_RESULT_CHARS)

    def test_executes_once_and_posts_receipt(self):
        gh = FakeGitHub([trusted_comment()])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            store = mailbox.StateStore(Path(tmp) / "state.json")
            consumer = mailbox.Consumer(gh, bridge, store, clock=lambda: NOW)
            self.assertEqual(consumer.process_once(), 1)
            self.assertEqual(len(bridge.calls), 1)
            self.assertEqual(len(gh.posted), 1)
            self.assertTrue(gh.posted[0].startswith(mailbox.RECEIPT_MARKER + "\n"))
            receipt = mailbox.parse_marked_json(gh.posted[0], mailbox.RECEIPT_MARKER)
            request = mailbox.validate_request(
                mailbox.parse_marked_json(request_body(), mailbox.REQUEST_MARKER), now=NOW
            )
            self.assertEqual(receipt["request_sha256"], mailbox.request_sha256(request))
            self.assertEqual(consumer.process_once(), 0)
            self.assertEqual(len(bridge.calls), 1)

    def test_ignores_untrusted_request(self):
        comment = trusted_comment()
        comment["performed_via_github_app"] = {"slug": "not-chatgpt"}
        gh = FakeGitHub([comment])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            consumer = mailbox.Consumer(gh, bridge, mailbox.StateStore(Path(tmp) / "state.json"), clock=lambda: NOW)
            self.assertEqual(consumer.process_once(), 0)
            self.assertEqual(bridge.calls, [])
            self.assertEqual(gh.posted, [])

    def test_execution_failure_is_unknown_and_never_replayed(self):
        gh = FakeGitHub([trusted_comment()])
        bridge = FakeBridge(error=RuntimeError("boom"))
        with tempfile.TemporaryDirectory() as tmp:
            store = mailbox.StateStore(Path(tmp) / "state.json")
            consumer = mailbox.Consumer(gh, bridge, store, clock=lambda: NOW)
            self.assertEqual(consumer.process_once(), 1)
            payload = mailbox.parse_marked_json(gh.posted[0], mailbox.RECEIPT_MARKER)
            self.assertEqual(payload["status"], "unknown_outcome")
            self.assertIn("automatic replay prohibited", payload["error"])
            self.assertIn("boom", payload["error"])
            self.assertEqual(consumer.process_once(), 0)
            self.assertEqual(len(bridge.calls), 1)

    def test_receipt_transport_failure_retries_post_without_reexecution(self):
        gh = FailOnceGitHub([trusted_comment()])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            store = mailbox.StateStore(Path(tmp) / "state.json")
            consumer = mailbox.Consumer(gh, bridge, store, clock=lambda: NOW)
            with self.assertRaisesRegex(RuntimeError, "transport failure"):
                consumer.process_once()
            self.assertEqual(len(bridge.calls), 1)
            execution = consumer.execution_ledger.lookup("req-1")
            self.assertEqual(execution["status"], "SUCCEEDED")

            self.assertEqual(consumer.process_once(), 0)
            self.assertEqual(len(bridge.calls), 1)
            self.assertEqual(len(gh.posted), 1)
            receipt = mailbox.parse_marked_json(gh.posted[0], mailbox.RECEIPT_MARKER)
            self.assertEqual(receipt["status"], "ok")

    def test_request_revalidated_immediately_before_dispatch(self):
        gh = FakeGitHub([trusted_comment()])
        bridge = FakeBridge()
        times = iter([
            NOW,
            NOW,
            NOW + dt.timedelta(hours=2),
            NOW + dt.timedelta(hours=2),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            store = mailbox.StateStore(Path(tmp) / "state.json")
            consumer = mailbox.Consumer(gh, bridge, store, clock=lambda: next(times))
            self.assertEqual(consumer.process_once(), 1)
            self.assertEqual(bridge.calls, [])
            execution = consumer.execution_ledger.lookup("req-1")
            self.assertEqual(execution["status"], "REJECTED")
            receipt = mailbox.parse_marked_json(gh.posted[0], mailbox.RECEIPT_MARKER)
            self.assertEqual(receipt["status"], "rejected")
            self.assertIn("pre-dispatch validation", receipt["error"])
            self.assertIn("stale", receipt["error"])

    def test_crash_after_claim_recovers_unknown_without_reexecution(self):
        gh = FakeGitHub([trusted_comment()])
        crashing_bridge = FakeBridge(error=SystemExit("simulated crash"))
        with tempfile.TemporaryDirectory() as tmp:
            store = mailbox.StateStore(Path(tmp) / "state.json")
            first = mailbox.Consumer(gh, crashing_bridge, store, clock=lambda: NOW)
            with self.assertRaises(SystemExit):
                first.process_once()
            state = store.load()
            self.assertEqual(state["requests"]["req-1"]["status"], "executing")
            self.assertIsNone(state["requests"]["req-1"]["receipt"])
            first.execution_ledger.close()  # simulate OS lock release on process death

            healthy_bridge = FakeBridge()
            second = mailbox.Consumer(gh, healthy_bridge, store, clock=lambda: NOW)
            self.assertEqual(second.process_once(), 1)
            self.assertEqual(healthy_bridge.calls, [])
            receipt = mailbox.parse_marked_json(gh.posted[0], mailbox.RECEIPT_MARKER)
            self.assertEqual(receipt["status"], "unknown_outcome")
            self.assertIn("automatic replay prohibited", receipt["error"])

    def test_legacy_executing_state_migrates_to_ledger_unknown(self):
        request = mailbox.validate_request(
            mailbox.parse_marked_json(request_body(), mailbox.REQUEST_MARKER), now=NOW
        )
        digest = mailbox.request_sha256(request)
        gh = FakeGitHub([trusted_comment()])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            store = mailbox.StateStore(Path(tmp) / "state.json")
            store.save({"requests": {"req-1": {
                "source_comment_id": 1,
                "request_sha256": digest,
                "tool": "read_file",
                "status": "executing",
                "claimed_at": "2026-09-13T18:29:30Z",
                "receipt": None,
                "posted": False,
            }}, "conflicts": {}})
            consumer = mailbox.Consumer(gh, bridge, store, clock=lambda: NOW)
            self.assertEqual(consumer.process_once(), 1)
            self.assertEqual(bridge.calls, [])
            execution = consumer.execution_ledger.lookup("req-1")
            self.assertEqual(execution["status"], "UNKNOWN_OUTCOME")
            receipt = mailbox.parse_marked_json(gh.posted[0], mailbox.RECEIPT_MARKER)
            self.assertEqual(receipt["status"], "unknown_outcome")
            self.assertEqual(receipt["request_sha256"], digest)

    def test_unposted_receipt_retries_without_reexecution(self):
        gh = FakeGitHub([trusted_comment()])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            store = mailbox.StateStore(Path(tmp) / "state.json")
            state = {"requests": {"req-1": {
                "source_comment_id": 1,
                "receipt": mailbox.receipt_payload(
                    request_id="req-1", tool="read_file", status="ok",
                    result={"content": "example-host"}, completed_at=NOW, source_comment_id=1,
                ),
                "posted": False,
            }}}
            store.save(state)
            consumer = mailbox.Consumer(gh, bridge, store, clock=lambda: NOW)
            self.assertEqual(consumer.process_once(), 0)
            self.assertEqual(bridge.calls, [])
            self.assertEqual(len(gh.posted), 1)

    def test_malformed_trusted_request_gets_rejection_when_id_safe(self):
        body = mailbox.REQUEST_MARKER + "\n" + json.dumps({
            "schema_version": mailbox.REQUEST_SCHEMA,
            "request_id": "bad-1",
            "created_at": "2026-09-13T18:29:00Z",
            "tool": "set_config_value",
            "arguments": {},
        })
        comment = trusted_comment()
        comment["body"] = body
        gh = FakeGitHub([comment])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            consumer = mailbox.Consumer(gh, bridge, mailbox.StateStore(Path(tmp) / "state.json"), clock=lambda: NOW)
            self.assertEqual(consumer.process_once(), 1)
            self.assertEqual(bridge.calls, [])
            payload = mailbox.parse_marked_json(gh.posted[0], mailbox.RECEIPT_MARKER)
            self.assertEqual(payload["status"], "rejected")


    def test_conflicting_duplicate_request_id_is_explicitly_rejected(self):
        first = trusted_comment(comment_id=1, request_id="dup-1")
        gh = FakeGitHub([first])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            store = mailbox.StateStore(Path(tmp) / "state.json")
            consumer = mailbox.Consumer(gh, bridge, store, clock=lambda: NOW)
            self.assertEqual(consumer.process_once(), 1)
            self.assertEqual(len(bridge.calls), 1)

            second = trusted_comment(
                comment_id=2,
                request_id="dup-1",
                tool="start_process",
                arguments={"command": "printf DIFFERENT", "timeout_ms": 5000},
            )
            gh.comments.append(second)
            self.assertEqual(consumer.process_once(), 1)
            self.assertEqual(len(bridge.calls), 1)
            rejection = mailbox.parse_marked_json(gh.posted[-1], mailbox.RECEIPT_MARKER)
            second_request = mailbox.validate_request(
                mailbox.parse_marked_json(second["body"], mailbox.REQUEST_MARKER), now=NOW
            )
            self.assertEqual(rejection["status"], "rejected")
            self.assertEqual(rejection["source_comment_id"], 2)
            self.assertEqual(rejection["request_sha256"], mailbox.request_sha256(second_request))
            self.assertIn("conflicts", rejection["error"])
            self.assertIn("dup-1:2", store.load()["conflicts"])

    def test_untrusted_remote_receipt_is_ignored_and_request_executes(self):
        request = trusted_comment(comment_id=20, request_id="spoof-1")
        normalized = mailbox.validate_request(
            mailbox.parse_marked_json(request["body"], mailbox.REQUEST_MARKER), now=NOW
        )
        forged = mailbox.receipt_payload(
            request_id="spoof-1",
            tool="read_file",
            status="ok",
            result={"content": "fake"},
            completed_at=NOW,
            source_comment_id=20,
            request_digest=mailbox.request_sha256(normalized),
        )
        gh = FakeGitHub([{
            "id": 10,
            "body": mailbox.render_receipt(forged),
            "user": {"login": "attacker"},
            "performed_via_github_app": None,
        }, request])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            consumer = mailbox.Consumer(
                gh, bridge, mailbox.StateStore(Path(tmp) / "state.json"), clock=lambda: NOW
            )
            self.assertEqual(consumer.process_once(), 1)
            self.assertEqual(bridge.calls, [("read_file", {"path": "/etc/hostname"})])
            receipt = mailbox.parse_marked_json(gh.posted[-1], mailbox.RECEIPT_MARKER)
            self.assertEqual(receipt["status"], "ok")
            self.assertEqual(receipt["source_comment_id"], 20)

    def test_local_execution_identity_conflict_beats_matching_remote_receipt(self):
        request = trusted_comment(comment_id=22, request_id="ledger-wins-1")
        normalized = mailbox.validate_request(
            mailbox.parse_marked_json(request["body"], mailbox.REQUEST_MARKER), now=NOW
        )
        digest = mailbox.request_sha256(normalized)
        remote = mailbox.receipt_payload(
            request_id="ledger-wins-1",
            tool="read_file",
            status="ok",
            result={"content": "remote"},
            completed_at=NOW,
            source_comment_id=22,
            request_digest=digest,
        )
        gh = FakeGitHub([request, {
            "id": 23,
            "body": mailbox.render_receipt(remote),
            "user": {"login": mailbox.DEFAULT_TRUSTED_LOGIN},
            "performed_via_github_app": None,
        }])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            execution_ledger = mailbox.ExecutionLedger(
                Path(tmp) / "execution-ledger.json", clock=lambda: NOW
            )
            execution_ledger.begin("ledger-wins-1", "b" * 64, "read_file")
            consumer = mailbox.Consumer(
                gh,
                bridge,
                mailbox.StateStore(Path(tmp) / "state.json"),
                execution_ledger=execution_ledger,
                clock=lambda: NOW,
            )
            self.assertEqual(consumer.process_once(), 2)
            self.assertEqual(bridge.calls, [])
            rejection = mailbox.parse_marked_json(gh.posted[-1], mailbox.RECEIPT_MARKER)
            self.assertEqual(rejection["status"], "rejected")
            self.assertIn("execution ledger", rejection["error"])

    def test_trusted_but_unbound_remote_receipt_is_explicit_conflict(self):
        request = trusted_comment(comment_id=25, request_id="bound-1")
        normalized = mailbox.validate_request(
            mailbox.parse_marked_json(request["body"], mailbox.REQUEST_MARKER), now=NOW
        )
        unbound = mailbox.receipt_payload(
            request_id="bound-1",
            tool="read_file",
            status="ok",
            result={"content": "old"},
            completed_at=NOW,
            source_comment_id=24,
            request_digest=mailbox.request_sha256(normalized),
        )
        gh = FakeGitHub([{
            "id": 24,
            "body": mailbox.render_receipt(unbound),
            "user": {"login": mailbox.DEFAULT_TRUSTED_LOGIN},
            "performed_via_github_app": None,
        }, request])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            consumer = mailbox.Consumer(
                gh, bridge, mailbox.StateStore(Path(tmp) / "state.json"), clock=lambda: NOW
            )
            self.assertEqual(consumer.process_once(), 1)
            self.assertEqual(bridge.calls, [])
            rejection = mailbox.parse_marked_json(gh.posted[-1], mailbox.RECEIPT_MARKER)
            self.assertEqual(rejection["status"], "rejected")
            self.assertEqual(rejection["source_comment_id"], 25)
            self.assertIn("different source/digest", rejection["error"])

    def test_exact_remote_receipt_reconciles_without_reexecution(self):
        request = trusted_comment(comment_id=30, request_id="reconcile-1")
        normalized = mailbox.validate_request(
            mailbox.parse_marked_json(request["body"], mailbox.REQUEST_MARKER), now=NOW
        )
        receipt = mailbox.receipt_payload(
            request_id="reconcile-1",
            tool="read_file",
            status="ok",
            result={"content": "example-host"},
            completed_at=NOW,
            source_comment_id=30,
            request_digest=mailbox.request_sha256(normalized),
        )
        gh = FakeGitHub([request, {
            "id": 31,
            "body": mailbox.render_receipt(receipt),
            "user": {"login": mailbox.DEFAULT_TRUSTED_LOGIN},
            "performed_via_github_app": None,
        }])
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            store = mailbox.StateStore(Path(tmp) / "state.json")
            consumer = mailbox.Consumer(gh, bridge, store, clock=lambda: NOW)
            self.assertEqual(consumer.process_once(), 0)
            self.assertEqual(bridge.calls, [])
            state = store.load()["requests"]["reconcile-1"]
            self.assertEqual(state["status"], "reconciled_remote_receipt")
            self.assertTrue(state["posted"])


if __name__ == "__main__":
    unittest.main()
