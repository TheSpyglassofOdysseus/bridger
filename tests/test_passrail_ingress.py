from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SELFHOSTED = Path(__file__).resolve().parents[1] / "selfhosted"
sys.path.insert(0, str(SELFHOSTED))

import bridge_passrail_ingress as ingress
from bridge_result_artifacts import store_result_artifact


def read_only_envelope(project="demo", **overrides):
    value = {
        "project": project,
        "message_key": "heartbeat:1",
        "kind": ingress.PAYLOAD_SCHEMA,
        "role": ingress.ROLE,
        "priority": 0,
        "risk_class": "SAFE_RETRY",
        "payload": {
            "schema_version": ingress.PAYLOAD_SCHEMA,
            "request": {
                "execution_id": "exec-1",
                "tool": "read_file",
                "arguments": {"path": "/etc/hostname"},
                "requested_risk_class": "SAFE_RETRY",
            },
            "completion_policy": "AUTO_READ_ONLY",
        },
    }
    value.update(overrides)
    return value


class FakeRail:
    items = {}
    next_id = 1

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def publish(self, envelope):
        key = (envelope["project"], envelope["message_key"])
        existing = next((i for i in self.items.values() if (i["project"], i["envelope"]["message_key"]) == key), None)
        if existing:
            return existing
        item_id = self.next_id
        type(self).next_id += 1
        item = {
            "id": item_id,
            "project": envelope["project"],
            "state": "READY",
            "attempts": 0,
            "updated_at": 1000.0,
            "envelope": envelope,
            "envelope_hash": "a" * 64,
            "transitions": [{"event": "publish"}],
            "receipts": [],
        }
        self.items[item_id] = item
        return item

    def inspect(self, item_id):
        return self.items[item_id]


class IngressTests(unittest.TestCase):
    def setUp(self):
        FakeRail.items = {}
        FakeRail.next_id = 1
        self.ingress = ingress.PassrailIngress.__new__(ingress.PassrailIngress)
        self.ingress.db_path = Path("/tmp/fake.sqlite3")
        self.ingress.ingress_key = b"k" * 32
        self.ingress.allowed_projects = {"demo"}
        self.ingress.Rail = FakeRail
        self.ingress.artifact_dir = None

    def test_read_only_publish_returns_scoped_status_capability(self):
        result = self.ingress.publish(read_only_envelope())
        self.assertEqual(result["state"], "READY")
        self.assertEqual(len(result["status_token"]), 64)
        status = self.ingress.status(result["item_id"], result["status_token"])
        self.assertEqual(status["state"], "READY")
        self.assertEqual(status["message_key"], "heartbeat:1")
        with self.assertRaisesRegex(ingress.IngressError, "capability"):
            self.ingress.status(result["item_id"], "0" * 64)

    def test_large_result_artifact_requires_scoped_item_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            evidence = store_result_artifact(root, {"content": "x" * 50000})
            self.ingress.artifact_dir = root
            published = self.ingress.publish(read_only_envelope())
            FakeRail.items[published["item_id"]]["receipts"] = [{
                "receipt": {"execution": evidence}
            }]
            result = self.ingress.artifact(
                published["item_id"], published["status_token"], evidence["result_artifact_sha256"]
            )
            self.assertEqual(result["result"]["content"], "x" * 50000)
            with self.assertRaisesRegex(ingress.IngressError, "capability"):
                self.ingress.artifact(published["item_id"], "0" * 64, evidence["result_artifact_sha256"])
            with self.assertRaisesRegex(ingress.IngressError, "not authorized"):
                self.ingress.artifact(published["item_id"], published["status_token"], "0" * 64)

    def test_project_and_work_type_are_allowlisted(self):
        with self.assertRaisesRegex(ingress.IngressError, "project"):
            self.ingress.publish(read_only_envelope(project="other"))
        with self.assertRaisesRegex(ingress.IngressError, "bridger-executor"):
            self.ingress.publish(read_only_envelope(role="admin"))
        with self.assertRaisesRegex(ingress.IngressError, "bridger-executor"):
            self.ingress.publish(read_only_envelope(kind="arbitrary"))

    def test_consequential_work_requires_no_auto_retry_authority_and_reconciliation(self):
        value = read_only_envelope()
        value["risk_class"] = "NO_AUTO_RETRY"
        value["payload"] = {
            "schema_version": ingress.PAYLOAD_SCHEMA,
            "request": {
                "execution_id": "exec-2",
                "tool": "start_process",
                "arguments": {"command": "printf ok", "timeout_ms": 1000},
                "requested_risk_class": "NO_AUTO_RETRY",
            },
            "completion_policy": "REQUIRE_RECONCILIATION",
        }
        with self.assertRaisesRegex(ingress.IngressError, "authority_ref"):
            self.ingress.publish(value)
        value["authority_ref"] = "git:/srv/bridger-demo"
        with self.assertRaisesRegex(ingress.IngressError, "authority_version"):
            self.ingress.publish(value)
        value["authority_version"] = "a" * 40
        result = self.ingress.publish(value)
        self.assertEqual(result["state"], "READY")

    def test_read_only_cannot_request_reconciliation_policy(self):
        value = read_only_envelope()
        value["payload"]["completion_policy"] = "REQUIRE_RECONCILIATION"
        with self.assertRaisesRegex(ingress.IngressError, "AUTO_READ_ONLY"):
            self.ingress.publish(value)


if __name__ == "__main__":
    unittest.main()
