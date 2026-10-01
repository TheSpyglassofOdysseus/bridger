#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import http.client
import json
import os
from pathlib import Path
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from bridge_passrail_ingress import PassrailIngress, openapi_schema as passrail_openapi_schema

PROTOCOL_VERSION = "2025-11-25"
SERVICE_VERSION = "1.2"
MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

DIRECT_ACTIONS = {
    "/v1/read-file": ("read_file", "readBridgeFile", "Read a file from the managed host"),
    "/v1/write-file": ("write_file", "writeBridgeFile", "Write or append to a file on the managed host"),
    "/v1/edit-file": ("edit_block", "editBridgeFile", "Apply a focused edit to a file"),
    "/v1/start-process": ("start_process", "startBridgeProcess", "Run a terminal process on the managed host"),
    "/v1/process-output": ("read_process_output", "readBridgeProcessOutput", "Read output from a running process"),
    "/v1/process-input": ("interact_with_process", "interactWithBridgeProcess", "Send input to a running process"),
    "/v1/list-directory": ("list_directory", "listBridgeDirectory", "List files and directories on the managed host"),
    "/v1/file-info": ("get_file_info", "getBridgeFileInfo", "Get file or directory metadata"),
    "/v1/list-processes": ("list_processes", "listBridgeProcesses", "List running processes on the managed host"),
    "/v1/search": ("start_search", "startBridgeSearch", "Start a file-name or content search"),
    "/v1/search-results": ("get_more_search_results", "readBridgeSearchResults", "Read results from an active search"),
}

DIRECT_SCHEMAS = {
    "read_file": {"type":"object","required":["path"],"properties":{"path":{"type":"string"},"offset":{"type":"number","default":0},"length":{"type":"number","default":1000},"isUrl":{"type":"boolean","default":False},"sheet":{"type":"string"},"range":{"type":"string"}},"additionalProperties":False},
    "write_file": {"type":"object","required":["path","content"],"properties":{"path":{"type":"string"},"content":{"type":"string"},"mode":{"type":"string","enum":["rewrite","append"],"default":"rewrite"}},"additionalProperties":False},
    "edit_block": {"type":"object","required":["file_path"],"properties":{"file_path":{"type":"string"},"old_string":{"type":"string"},"new_string":{"type":"string"},"expected_replacements":{"type":"number","default":1},"range":{"type":"string"}},"additionalProperties":False},
    "start_process": {"type":"object","required":["command","timeout_ms"],"properties":{"command":{"type":"string"},"timeout_ms":{"type":"number"},"shell":{"type":"string"},"verbose_timing":{"type":"boolean"}},"additionalProperties":False},
    "read_process_output": {"type":"object","required":["pid"],"properties":{"pid":{"type":"number"},"offset":{"type":"number"},"length":{"type":"number"},"timeout_ms":{"type":"number"},"verbose_timing":{"type":"boolean"}},"additionalProperties":False},
    "interact_with_process": {"type":"object","required":["pid","input"],"properties":{"pid":{"type":"number"},"input":{"type":"string"},"timeout_ms":{"type":"number"},"wait_for_prompt":{"type":"boolean"},"verbose_timing":{"type":"boolean"}},"additionalProperties":False},
    "list_directory": {"type":"object","required":["path"],"properties":{"path":{"type":"string"},"depth":{"type":"number","default":2}},"additionalProperties":False},
    "get_file_info": {"type":"object","required":["path"],"properties":{"path":{"type":"string"}},"additionalProperties":False},
    "list_processes": {"type":"object","properties":{},"additionalProperties":False},
    "start_search": {"type":"object","required":["path","pattern"],"properties":{"path":{"type":"string"},"pattern":{"type":"string"},"searchType":{"type":"string","enum":["files","content"],"default":"files"},"maxResults":{"type":"number"},"includeHidden":{"type":"boolean","default":False},"timeout_ms":{"type":"number"},"contextLines":{"type":"number","default":5},"filePattern":{"type":"string"},"ignoreCase":{"type":"boolean","default":True},"earlyTermination":{"type":"boolean"},"literalSearch":{"type":"boolean","default":False}},"additionalProperties":False},
    "get_more_search_results": {"type":"object","required":["sessionId"],"properties":{"sessionId":{"type":"string"},"offset":{"type":"number","default":0},"length":{"type":"number","default":100}},"additionalProperties":False},
}


def _mcp_payload(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    values: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data:
            continue
        try:
            value = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    if not values:
        raise RuntimeError(f"MCP response was neither JSON nor parseable SSE: {text[:500]}")
    return values[-1]


class MCPClient:
    def __init__(self, port: int, api_key: str) -> None:
        self.port = port
        self.api_key = api_key

    def _post(
        self,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        expect_body: bool = True,
    ) -> tuple[dict[str, Any], str | None]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        body = json.dumps(payload, separators=(",", ":"))
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
            headers["Mcp-Protocol-Version"] = PROTOCOL_VERSION
        try:
            conn.request("POST", "/mcp", body=body, headers=headers)
            response = conn.getresponse()
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise RuntimeError("MCP response exceeded Bridge response limit")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(
                    f"MCP HTTP {response.status}: {data.decode('utf-8', errors='replace')[:1000]}"
                )
            returned_session = response.getheader("Mcp-Session-Id") or session_id
            if not expect_body or not data:
                return {}, returned_session
            message = _mcp_payload(data)
            if "error" in message:
                raise RuntimeError(f"MCP error: {json.dumps(message['error'], separators=(',', ':'))}")
            return message, returned_session
        finally:
            conn.close()

    def _session(self) -> str:
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "bridge-gpt-actions", "version": "1.0"},
            },
        }
        message, session_id = self._post(initialize)
        if "result" not in message or not session_id:
            raise RuntimeError("MCP initialize did not return result and session id")
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._post(notification, session_id=session_id, expect_body=False)
        return session_id

    def list_tools(self) -> list[dict[str, Any]]:
        session_id = self._session()
        message, _ = self._post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            session_id=session_id,
        )
        result = message.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
            raise RuntimeError("MCP tools/list returned an unexpected result")
        return result["tools"]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        session_id = self._session()
        message, _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            session_id=session_id,
        )
        if "result" not in message:
            raise RuntimeError("MCP tools/call returned no result")
        return message["result"]


def openapi_schema(public_base_url: str) -> dict[str, Any]:
    response = {"type": "object", "additionalProperties": True}
    paths: dict[str, Any] = {
        "/v1/tools": {
            "get": {
                "operationId": "listBridgeTools",
                "summary": "List all Desktop Commander tools available on the managed host",
                "description": "Use this only when a direct Bridge action does not cover the needed operation.",
                "responses": {"200": {"description": "Available Bridge tools", "content": {"application/json": {"schema": response}}}},
                "security": [{"BridgeKey": []}],
            }
        },
        "/v1/call": {
            "post": {
                "operationId": "callBridgeTool",
                "summary": "Call any Desktop Commander tool on the ARM server",
                "description": "Generic compatibility escape hatch. Prefer a direct Bridge action when one exists.",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object", "required": ["name", "arguments"],
                    "properties": {"name": {"type": "string"}, "arguments": {"type": "object", "additionalProperties": True}},
                    "additionalProperties": False,
                }}}},
                "responses": {"200": {"description": "Desktop Commander MCP tool result", "content": {"application/json": {"schema": response}}}},
                "security": [{"BridgeKey": []}],
            }
        },
    }
    for path, (tool, operation_id, summary) in DIRECT_ACTIONS.items():
        paths[path] = {"post": {
            "operationId": operation_id,
            "summary": summary,
            "description": f"Direct Bridge action backed by Desktop Commander {tool}.",
            "requestBody": {"required": True, "content": {"application/json": {"schema": DIRECT_SCHEMAS[tool]}}},
            "responses": {"200": {"description": "Desktop Commander MCP tool result", "content": {"application/json": {"schema": response}}}},
            "security": [{"BridgeKey": []}],
        }}
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Bridge Actions",
            "version": SERVICE_VERSION,
            "description": (
                "Authenticated self-hosted access to a managed host through Bridge. "
                "Prefer named direct actions for routine file and terminal work; use "
                "listBridgeTools/callBridgeTool only for uncommon Desktop Commander tools."
            ),
        },
        "servers": [{"url": public_base_url.rstrip("/")}],
        "paths": paths,
        "components": {"securitySchemes": {"BridgeKey": {
            "type": "apiKey", "in": "header", "name": "X-Bridge-Key",
            "description": "Bridge GPT Action API key",
        }}},
    }


class Server(ThreadingHTTPServer):
    mcp: MCPClient
    action_key: str
    passrail_key: str
    passrail: PassrailIngress | None
    public_base_url: str


class Handler(BaseHTTPRequestHandler):
    server_version = f"BridgeGPTActions/{SERVICE_VERSION}"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-Bridge-Key", "")
        return bool(supplied) and hmac.compare_digest(supplied, self.server.action_key)

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._json(401, {"ok": False, "error": "unauthorized"})
        return False

    def _passrail_authorized(self) -> bool:
        supplied = self.headers.get("X-Passrail-Key", "")
        return (
            self.server.passrail is not None
            and bool(self.server.passrail_key)
            and bool(supplied)
            and hmac.compare_digest(supplied, self.server.passrail_key)
        )

    def _require_passrail_auth(self) -> bool:
        if self._passrail_authorized():
            return True
        self._json(401, {"ok": False, "error": "unauthorized"})
        return False

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("invalid request size")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise TypeError("request body must be an object")
        return payload

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._json(200, {"ok": True, "service": "bridge-gpt-actions", "version": SERVICE_VERSION})
            return
        if path == "/openapi.json":
            self._json(200, openapi_schema(self.server.public_base_url))
            return
        if path == "/passrail-openapi.json":
            if self.server.passrail is None:
                self._json(404, {"ok": False, "error": "passrail_ingress_disabled"})
                return
            self._json(200, passrail_openapi_schema(self.server.public_base_url))
            return
        if path == "/v1/tools":
            if not self._require_auth():
                return
            try:
                tools = self.server.mcp.list_tools()
                self._json(200, {"ok": True, "tools": tools})
            except Exception as exc:
                self._json(502, {"ok": False, "error": str(exc)})
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in {"/v1/passrail/publish", "/v1/passrail/status", "/v1/passrail/artifact"}:
            if not self._require_passrail_auth():
                return
            try:
                payload = self._read_body()
                passrail = self.server.passrail
                if passrail is None:
                    raise RuntimeError("passrail ingress became unavailable")
                if path == "/v1/passrail/publish":
                    result = passrail.publish(payload)
                elif path == "/v1/passrail/status":
                    if set(payload) != {"item_id", "status_token"}:
                        raise ValueError("status request must contain item_id and status_token only")
                    result = passrail.status(
                        payload["item_id"], payload["status_token"]
                    )
                else:
                    if set(payload) != {"item_id", "status_token", "result_artifact_sha256"}:
                        raise ValueError("artifact request has invalid fields")
                    result = passrail.artifact(
                        payload["item_id"], payload["status_token"], payload["result_artifact_sha256"]
                    )
                self._json(200, result)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                self._json(502, {"ok": False, "error": str(exc)})
            return

        direct = DIRECT_ACTIONS.get(path)
        if path != "/v1/call" and direct is None:
            self._json(404, {"ok": False, "error": "not_found"})
            return
        if not self._require_auth():
            return
        try:
            payload = self._read_body()
            if direct is not None:
                name = direct[0]
                arguments = payload
            else:
                name = payload.get("name")
                arguments = payload.get("arguments")
                if not isinstance(name, str) or not name:
                    raise TypeError("name must be a non-empty string")
                if not isinstance(arguments, dict):
                    raise TypeError("arguments must be an object")
            result = self.server.mcp.call_tool(name, arguments)
            self._json(200, {"ok": True, "tool": name, "result": result})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json(502, {"ok": False, "error": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("BRIDGE_ACTIONS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("BRIDGE_ACTIONS_PORT", "18878")))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("Bridge GPT Actions refuses non-loopback bind", file=sys.stderr)
        return 2
    action_key = os.environ.get("BRIDGE_ACTIONS_KEY", "")
    backend_key = os.environ.get("MCP_PROXY_API_KEY", "")
    backend_port_raw = os.environ.get("BRIDGE_DC_PORT", "")
    public_base_url = os.environ.get("BRIDGE_ACTIONS_PUBLIC_URL", "").strip()
    if not action_key or not backend_key or not backend_port_raw.isdigit() or not public_base_url:
        print("Missing BRIDGE_ACTIONS_KEY, MCP_PROXY_API_KEY, BRIDGE_DC_PORT, or BRIDGE_ACTIONS_PUBLIC_URL", file=sys.stderr)
        return 2

    passrail_key = os.environ.get("BRIDGE_PASSRAIL_INGRESS_KEY", "")
    passrail: PassrailIngress | None = None
    if passrail_key:
        allowed_projects = {
            value.strip()
            for value in os.environ.get("BRIDGE_PASSRAIL_ALLOWED_PROJECTS", "").split(",")
            if value.strip()
        }
        db_raw = os.environ.get("PASSRAIL_DB", "").strip()
        src_raw = os.environ.get(
            "PASSRAIL_SRC", str(Path.home() / ".local/lib/passrail/current")
        ).strip()
        if not allowed_projects or not db_raw or not src_raw:
            print(
                "BRIDGE_PASSRAIL_INGRESS_KEY requires BRIDGE_PASSRAIL_ALLOWED_PROJECTS, PASSRAIL_DB, and PASSRAIL_SRC",
                file=sys.stderr,
            )
            return 2
        artifact_raw = os.environ.get("BRIDGE_EXECUTION_ARTIFACT_DIR", "").strip()
        if not artifact_raw:
            ledger_raw = os.environ.get("BRIDGE_EXECUTION_LEDGER_STATE", "").strip()
            artifact_raw = str(Path(ledger_raw).parent / "artifacts") if ledger_raw else ""
        if not artifact_raw:
            print("Passrail ingress requires BRIDGE_EXECUTION_ARTIFACT_DIR or BRIDGE_EXECUTION_LEDGER_STATE", file=sys.stderr)
            return 2
        passrail = PassrailIngress(
            db_path=Path(db_raw),
            passrail_src=Path(src_raw),
            ingress_key=passrail_key,
            allowed_projects=allowed_projects,
            artifact_dir=Path(artifact_raw),
        )

    server = Server((args.host, args.port), Handler)
    server.mcp = MCPClient(int(backend_port_raw), backend_key)
    server.action_key = action_key
    server.passrail_key = passrail_key
    server.passrail = passrail
    server.public_base_url = public_base_url
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
