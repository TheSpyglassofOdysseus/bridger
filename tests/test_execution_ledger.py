from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import sys
import tempfile
import unittest

SELFHOSTED = Path(__file__).parents[1] / "selfhosted"
sys.path.insert(0, str(SELFHOSTED))

import bridge_execution_ledger as ledger
from bridge_result_artifacts import read_result_artifact

NOW = dt.datetime(2026, 9, 17, 3, 30, tzinfo=dt.timezone.utc)
DIGEST = "a" * 64


class ExecutionLedgerTests(unittest.TestCase):
    def make_ledger(self, root: str, *, clock=lambda: NOW):
        return ledger.ExecutionLedger(Path(root) / "execution-ledger.json", clock=clock)

    def test_persist_before_dispatch_and_exact_replay(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_ledger(tmp)
            record, executed = store.execute(
                "exec-1", DIGEST, "read_file", lambda: calls.append("run") or {"content": "host"}
            )
            self.assertTrue(executed)
            self.assertEqual(calls, ["run"])
            self.assertEqual(record["status"], "SUCCEEDED")
            self.assertEqual(store.lookup("exec-1")["result"]["content"], "host")

            replay, executed = store.execute(
                "exec-1", DIGEST, "read_file", lambda: calls.append("duplicate")
            )
            self.assertFalse(executed)
            self.assertEqual(replay["status"], "SUCCEEDED")
            self.assertEqual(calls, ["run"])

    def test_large_result_is_preserved_as_owner_only_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ledger.ExecutionLedger(
                Path(tmp) / "execution-ledger.json", clock=lambda: NOW, max_result_chars=32
            )
            result = {"content": "x" * 4096}
            record, executed = store.execute("exec-large", DIGEST, "read_file", lambda: result)
            self.assertTrue(executed)
            self.assertTrue(record["truncated"])
            self.assertNotIn("result", record)
            digest = record["result_artifact_sha256"]
            artifact = Path(tmp) / "artifacts" / f"{digest}.json"
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
            self.assertEqual(read_result_artifact(Path(tmp) / "artifacts", digest), result)

    def test_conflicting_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_ledger(tmp)
            store.begin("exec-1", DIGEST, "read_file")
            with self.assertRaises(ledger.ExecutionConflict):
                store.begin("exec-1", "b" * 64, "read_file")
            with self.assertRaises(ledger.ExecutionConflict):
                store.begin("exec-1", DIGEST, "start_process")

    def test_same_request_cannot_cross_authority_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_ledger(tmp)
            first, created = store.begin(
                "exec-1", DIGEST, "read_file", authorization_sha256="a" * 64
            )
            self.assertTrue(created)
            self.assertEqual(first["authorization_sha256"], "a" * 64)
            with self.assertRaises(ledger.ExecutionConflict):
                store.begin(
                    "exec-1", DIGEST, "read_file", authorization_sha256="b" * 64
                )

    def test_process_death_recovers_unknown_and_never_replays(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_ledger(tmp)

            def crash():
                calls.append("first")
                raise SystemExit("simulated process death")

            with self.assertRaises(SystemExit):
                store.execute("exec-1", DIGEST, "start_process", crash)
            self.assertEqual(store.lookup("exec-1")["status"], "EXECUTING")
            store.close()

            restarted = self.make_ledger(tmp)
            recovered = restarted.recover_inflight()
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0]["status"], "UNKNOWN_OUTCOME")
            self.assertIn("automatic replay prohibited", recovered[0]["error"])

            replay, executed = restarted.execute(
                "exec-1", DIGEST, "start_process", lambda: calls.append("second")
            )
            self.assertFalse(executed)
            self.assertEqual(replay["status"], "UNKNOWN_OUTCOME")
            self.assertEqual(calls, ["first"])

    def test_pre_dispatch_rejection_never_calls_action(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_ledger(tmp)

            def reject():
                raise ValueError("stale")

            record, executed = store.execute(
                "exec-1",
                DIGEST,
                "write_file",
                lambda: calls.append("action"),
                pre_dispatch=reject,
            )
            self.assertTrue(executed)
            self.assertEqual(calls, [])
            self.assertEqual(record["status"], "REJECTED")
            self.assertIn("pre-dispatch validation", record["error"])

    def test_state_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_ledger(tmp)
            store.begin("exec-1", DIGEST, "read_file")
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            os.chmod(store.path, 0o644)
            store.lookup("exec-1")
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)

    def test_concurrent_execution_owner_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.make_ledger(tmp)
            lock_path = first.path.with_name(first.path.name + ".owner.lock")
            self.assertEqual(lock_path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(
                ledger.ExecutionLedgerError, "already has an active owner"
            ):
                self.make_ledger(tmp)
            first.close()
            os.chmod(lock_path, 0o644)
            second = self.make_ledger(tmp)
            self.assertEqual(lock_path.stat().st_mode & 0o777, 0o600)
            second.close()

    def test_symlink_owner_lock_is_rejected(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("platform has no O_NOFOLLOW")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.lock"
            target.write_text("not a lock")
            lock_path = root / "execution-ledger.json.owner.lock"
            lock_path.symlink_to(target)
            with self.assertRaisesRegex(
                ledger.ExecutionLedgerError, "open execution owner lock safely"
            ):
                self.make_ledger(tmp)

    def test_symlink_ledger_path_is_rejected(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("platform has no O_NOFOLLOW")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.json"
            target.write_text('{"schema_version":"bridger-execution-ledger-v1","executions":{}}')
            link = root / "execution-ledger.json"
            link.symlink_to(target)
            store = ledger.ExecutionLedger(link, clock=lambda: NOW)
            with self.assertRaisesRegex(ledger.ExecutionLedgerError, "open execution ledger safely"):
                store.lookup("exec-1")


if __name__ == "__main__":
    unittest.main()
