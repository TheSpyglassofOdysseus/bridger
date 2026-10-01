#!/usr/bin/env python3
"""Narrow ChatGPT-facing ingress into Passrail coordination.

This module intentionally does not expose machine tools. A remote caller may
publish a bounded Bridger execution envelope and inspect only an item for which
it holds the returned per-item status capability.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
from pathlib import Path
import sys
from typing import Any

from bridge_execution_grant import validate_request as validate_direct_request
from bridge_tool_policy import READ_ONLY_TOOLS
from bridge_result_artifacts import read_result_artifact

PAYLOAD_SCHEMA = "passrail-bridger-execution-v1"
ROLE = "bridger-executor"
MAX_ENVELOPE_BYTES = 250 * 1024
class IngressError(ValueError):
    pass


def canonical(value: Any) -> str:
    def validate(obj: Any) -> None:
        if obj is None or type(obj) in (str, bool, int):
            return
        if type(obj) is float and math.isfinite(obj):
            return
        if type(obj) is list:
            for child in obj:
                validate(child)
            return
        if type(obj) is dict and all(type(key) is str for key in obj):
            for child in obj.values():
                validate(child)
            return
        raise IngressError("value must be finite standard JSON")
    validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def validate_envelope(value: Any, allowed_projects: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IngressError("envelope must be an object")
    encoded = canonical(value).encode("utf-8")
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise IngressError("envelope exceeds ingress limit")
    project = value.get("project")
    if not isinstance(project, str) or project not in allowed_projects:
        raise IngressError("project is not authorized for this ingress")
    if value.get("kind") != PAYLOAD_SCHEMA or value.get("role") != ROLE:
        raise IngressError("ingress accepts only bridger-executor work")
    payload = value.get("payload")
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "request", "completion_policy"}:
        raise IngressError("invalid Bridger execution payload")
    if payload.get("schema_version") != PAYLOAD_SCHEMA:
        raise IngressError("unsupported payload schema")
    request = validate_direct_request(payload.get("request"))
    if value.get("risk_class") != request["requested_risk_class"]:
        raise IngressError("envelope risk_class must match request risk class")
    policy = payload.get("completion_policy")
    if request["tool"] in READ_ONLY_TOOLS:
        if policy != "AUTO_READ_ONLY":
            raise IngressError("read-only request must use AUTO_READ_ONLY")
    else:
        if request["requested_risk_class"] != "NO_AUTO_RETRY":
            raise IngressError("consequential request requires NO_AUTO_RETRY")
        if policy != "REQUIRE_RECONCILIATION":
            raise IngressError("consequential request must require reconciliation")
        if not isinstance(value.get("authority_ref"), str) or not value["authority_ref"].strip():
            raise IngressError("consequential request requires authority_ref")
        if not isinstance(value.get("authority_version"), str) or not value["authority_version"].strip():
            raise IngressError("consequential request requires authority_version")
    return dict(value)


def load_passrail(src: Path):
    src = Path(src)
    if not src.is_dir():
        raise IngressError(f"Passrail source path is unavailable: {src}")
    text = str(src)
    if text not in sys.path:
        sys.path.insert(0, text)
    from passrail import Rail  # type: ignore
    return Rail


class PassrailIngress:
    def __init__(
        self,
        *,
        db_path: Path,
        passrail_src: Path,
        ingress_key: str,
        allowed_projects: set[str],
        artifact_dir: Path | None = None,
    ) -> None:
        if not isinstance(ingress_key, str) or len(ingress_key.encode("utf-8")) < 32:
            raise IngressError("Passrail ingress key must contain at least 32 bytes")
        if not allowed_projects:
            raise IngressError("at least one Passrail ingress project is required")
        self.db_path = Path(db_path)
        self.ingress_key = ingress_key.encode("utf-8")
        self.allowed_projects = set(allowed_projects)
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else None
        self.Rail = load_passrail(passrail_src)

    def _status_token(self, item: dict[str, Any]) -> str:
        identity = {
            "item_id": item["id"],
            "project": item["project"],
            "message_key": item["envelope"]["message_key"],
            "envelope_hash": item["envelope_hash"],
        }
        return hmac.new(
            self.ingress_key,
            ("passrail-status-v1:" + canonical(identity)).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def publish(self, envelope: Any) -> dict[str, Any]:
        validated = validate_envelope(envelope, self.allowed_projects)
        with self.Rail(self.db_path) as rail:
            item = rail.publish(validated)
        return {
            "ok": True,
            "item_id": item["id"],
            "project": item["project"],
            "message_key": item["envelope"]["message_key"],
            "state": item["state"],
            "envelope_hash": item["envelope_hash"],
            "status_token": self._status_token(item),
        }

    def _authorized_item(self, item_id: Any, status_token: Any) -> dict[str, Any]:
        if type(item_id) is not int or item_id <= 0:
            raise IngressError("item_id must be a positive integer")
        if not isinstance(status_token, str) or len(status_token) != 64:
            raise IngressError("invalid status_token")
        with self.Rail(self.db_path) as rail:
            item = rail.inspect(item_id)
        if item["project"] not in self.allowed_projects:
            raise IngressError("item project is not authorized for this ingress")
        expected = self._status_token(item)
        if not hmac.compare_digest(status_token, expected):
            raise IngressError("status capability mismatch")
        return item

    def status(self, item_id: Any, status_token: Any) -> dict[str, Any]:
        item = self._authorized_item(item_id, status_token)
        return {
            "ok": True,
            "item_id": item["id"],
            "project": item["project"],
            "message_key": item["envelope"]["message_key"],
            "state": item["state"],
            "attempts": item["attempts"],
            "updated_at": item["updated_at"],
            "envelope_hash": item["envelope_hash"],
            "transitions": item["transitions"],
            "receipts": item["receipts"],
        }

    @staticmethod
    def _receipt_references_artifact(value: Any, digest: str) -> bool:
        if isinstance(value, dict):
            if value.get("result_artifact_sha256") == digest:
                return True
            return any(PassrailIngress._receipt_references_artifact(child, digest) for child in value.values())
        if isinstance(value, list):
            return any(PassrailIngress._receipt_references_artifact(child, digest) for child in value)
        return False

    def artifact(self, item_id: Any, status_token: Any, digest: Any) -> dict[str, Any]:
        if self.artifact_dir is None:
            raise IngressError("result artifact retrieval is disabled")
        if not isinstance(digest, str):
            raise IngressError("result_artifact_sha256 must be a string")
        item = self._authorized_item(item_id, status_token)
        if not any(self._receipt_references_artifact(entry, digest) for entry in item.get("receipts", [])):
            raise IngressError("result artifact is not authorized for this item")
        result = read_result_artifact(self.artifact_dir, digest)
        return {"ok": True, "item_id": item["id"], "result_artifact_sha256": digest, "result": result}


def openapi_schema(public_base_url: str) -> dict[str, Any]:
    response = {"type": "object", "additionalProperties": True}
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Bridger Passrail Ingress",
            "version": "1.0",
            "description": (
                "Narrow durable-work ingress. This API can enqueue bounded Passrail work and "
                "read the resulting item status; it does not expose host-control tools."
            ),
        },
        "servers": [{"url": public_base_url.rstrip("/")}],
        "paths": {
            "/v1/passrail/publish": {
                "post": {
                    "operationId": "publishPassrailWork",
                    "summary": "Publish bounded work to Passrail",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": response}}},
                    "responses": {"200": {"description": "Published work identity", "content": {"application/json": {"schema": response}}}},
                    "security": [{"PassrailKey": []}],
                }
            },
            "/v1/passrail/status": {
                "post": {
                    "operationId": "getPassrailWorkStatus",
                    "summary": "Read status/receipts for one published item",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object",
                        "required": ["item_id", "status_token"],
                        "properties": {"item_id": {"type": "integer"}, "status_token": {"type": "string"}},
                        "additionalProperties": False,
                    }}}},
                    "responses": {"200": {"description": "Work status", "content": {"application/json": {"schema": response}}}},
                    "security": [{"PassrailKey": []}],
                }
            },
            "/v1/passrail/artifact": {
                "post": {
                    "operationId": "getPassrailResultArtifact",
                    "summary": "Retrieve a large execution result referenced by this Passrail item",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object",
                        "required": ["item_id", "status_token", "result_artifact_sha256"],
                        "properties": {
                            "item_id": {"type": "integer"},
                            "status_token": {"type": "string"},
                            "result_artifact_sha256": {"type": "string"},
                        },
                        "additionalProperties": False,
                    }}}},
                    "responses": {"200": {"description": "Full content-addressed execution result", "content": {"application/json": {"schema": response}}}},
                    "security": [{"PassrailKey": []}],
                }
            },
        },
        "components": {"securitySchemes": {"PassrailKey": {
            "type": "apiKey", "in": "header", "name": "X-Passrail-Key",
            "description": "Narrow Passrail ingress key; not valid for machine-control endpoints.",
        }}},
    }
