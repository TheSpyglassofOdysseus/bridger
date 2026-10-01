from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


MODULE_PATH = Path(__file__).parents[1] / "selfhosted" / "bridge-gpt-actions.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("bridge_gpt_actions", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
bridge_actions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge_actions)


class FakeMCP:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_tools(self) -> list[dict[str, object]]:
        return [{"name": "read_file"}, {"name": "start_process"}]

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"echo": arguments}


class FakePassrail:
    def __init__(self) -> None:
        self.published = []
        self.status_calls = []
        self.artifact_calls = []

    def publish(self, payload):
        self.published.append(payload)
        return {"ok": True, "item_id": 7, "status_token": "s" * 64}

    def status(self, item_id, status_token):
        self.status_calls.append((item_id, status_token))
        return {"ok": True, "item_id": item_id, "state": "DONE"}

    def artifact(self, item_id, status_token, digest):
        self.artifact_calls.append((item_id, status_token, digest))
        return {"ok": True, "item_id": item_id, "result_artifact_sha256": digest, "result": {"content": "full"}}


class GPTActionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mcp = FakeMCP()
        self.passrail = FakePassrail()
        self.server = bridge_actions.Server(("127.0.0.1", 0), bridge_actions.Handler)
        self.server.mcp = self.mcp
        self.server.action_key = "test-key"
        self.server.passrail_key = "passrail-test-key"
        self.server.passrail = self.passrail
        self.server.public_base_url = "https://example.invalid/bridge-actions"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(
        self,
        path: str,
        payload: dict[str, object],
        *,
        auth: bool = True,
        passrail_auth: bool = False,
    ):
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["X-Bridge-Key"] = "test-key"
        if passrail_auth:
            headers["X-Passrail-Key"] = "passrail-test-key"
        return Request(
            f"{self.base}{path}",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )

    def test_schema_prefers_direct_actions_but_keeps_generic_fallback(self) -> None:
        schema = bridge_actions.openapi_schema(self.server.public_base_url)
        operations = {
            details["post"]["operationId"]
            for details in schema["paths"].values()
            if "post" in details
        }
        self.assertIn("readBridgeFile", operations)
        self.assertIn("writeBridgeFile", operations)
        self.assertIn("editBridgeFile", operations)
        self.assertIn("startBridgeProcess", operations)
        self.assertIn("readBridgeProcessOutput", operations)
        self.assertIn("interactWithBridgeProcess", operations)
        self.assertIn("listBridgeDirectory", operations)
        self.assertIn("getBridgeFileInfo", operations)
        self.assertIn("listBridgeProcesses", operations)
        self.assertIn("startBridgeSearch", operations)
        self.assertIn("readBridgeSearchResults", operations)
        self.assertIn("callBridgeTool", operations)

    def test_direct_read_file_calls_native_tool_once(self) -> None:
        request = self.post("/v1/read-file", {"path": "/tmp/example.txt"})
        with urlopen(request, timeout=2) as response:
            payload = json.load(response)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tool"], "read_file")
        self.assertEqual(self.mcp.calls, [("read_file", {"path": "/tmp/example.txt"})])

    def test_direct_action_rejects_missing_auth(self) -> None:
        request = self.post("/v1/start-process", {"command": "printf test", "timeout_ms": 1000}, auth=False)
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 401)
        self.assertEqual(self.mcp.calls, [])

    def test_generic_fallback_still_calls_requested_tool(self) -> None:
        request = self.post(
            "/v1/call",
            {"name": "list_directory", "arguments": {"path": "/tmp"}},
        )
        with urlopen(request, timeout=2) as response:
            payload = json.load(response)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tool"], "list_directory")
        self.assertEqual(self.mcp.calls, [("list_directory", {"path": "/tmp"})])

    def test_passrail_openapi_exposes_no_machine_control_routes(self) -> None:
        with urlopen(f"{self.base}/passrail-openapi.json", timeout=2) as response:
            schema = json.load(response)
        self.assertEqual(
            set(schema["paths"]),
            {"/v1/passrail/publish", "/v1/passrail/status", "/v1/passrail/artifact"},
        )
        encoded = json.dumps(schema)
        self.assertNotIn("startBridgeProcess", encoded)
        self.assertNotIn("callBridgeTool", encoded)
        self.assertNotIn("Desktop Commander", encoded)

    def test_passrail_key_can_retrieve_scoped_result_artifact(self) -> None:
        digest = "a" * 64
        request = self.post(
            "/v1/passrail/artifact",
            {"item_id": 7, "status_token": "s" * 64, "result_artifact_sha256": digest},
            auth=False,
            passrail_auth=True,
        )
        with urlopen(request, timeout=2) as response:
            result = json.load(response)
        self.assertEqual(result["result"]["content"], "full")
        self.assertEqual(self.passrail.artifact_calls, [(7, "s" * 64, digest)])

    def test_passrail_key_cannot_call_machine_control(self) -> None:
        request = self.post(
            "/v1/start-process",
            {"command": "printf test", "timeout_ms": 1000},
            auth=False,
            passrail_auth=True,
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 401)
        self.assertEqual(self.mcp.calls, [])

    def test_bridge_key_cannot_publish_passrail_work(self) -> None:
        request = self.post(
            "/v1/passrail/publish",
            {"project": "demo"},
            auth=True,
            passrail_auth=False,
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 401)
        self.assertEqual(self.passrail.published, [])

    def test_passrail_key_publishes_and_reads_status(self) -> None:
        publish = self.post(
            "/v1/passrail/publish",
            {"project": "demo"},
            auth=False,
            passrail_auth=True,
        )
        with urlopen(publish, timeout=2) as response:
            result = json.load(response)
        self.assertEqual(result["item_id"], 7)
        self.assertEqual(self.passrail.published, [{"project": "demo"}])
        status = self.post(
            "/v1/passrail/status",
            {"item_id": 7, "status_token": "s" * 64},
            auth=False,
            passrail_auth=True,
        )
        with urlopen(status, timeout=2) as response:
            result = json.load(response)
        self.assertEqual(result["state"], "DONE")
        self.assertEqual(self.passrail.status_calls, [(7, "s" * 64)])

    def test_action_key_rotation_revokes_old_key(self) -> None:
        first = self.post("/v1/read-file", {"path": "/tmp/before.txt"})
        with urlopen(first, timeout=2) as response:
            self.assertTrue(json.load(response)["ok"])

        self.server.action_key = "rotated-action-key"

        stale = self.post("/v1/read-file", {"path": "/tmp/stale.txt"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(stale, timeout=2)
        self.assertEqual(caught.exception.code, 401)

        current = Request(
            f"{self.base}/v1/read-file",
            data=json.dumps({"path": "/tmp/after.txt"}).encode(),
            headers={"Content-Type": "application/json", "X-Bridge-Key": "rotated-action-key"},
            method="POST",
        )
        with urlopen(current, timeout=2) as response:
            self.assertTrue(json.load(response)["ok"])

    def test_passrail_key_rotation_revokes_old_key(self) -> None:
        self.server.passrail_key = "rotated-passrail-key"

        stale = self.post(
            "/v1/passrail/publish",
            {"project": "demo"},
            auth=False,
            passrail_auth=True,
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(stale, timeout=2)
        self.assertEqual(caught.exception.code, 401)

        current = Request(
            f"{self.base}/v1/passrail/publish",
            data=json.dumps({"project": "demo"}).encode(),
            headers={"Content-Type": "application/json", "X-Passrail-Key": "rotated-passrail-key"},
            method="POST",
        )
        with urlopen(current, timeout=2) as response:
            self.assertEqual(json.load(response)["item_id"], 7)


if __name__ == "__main__":
    unittest.main()
