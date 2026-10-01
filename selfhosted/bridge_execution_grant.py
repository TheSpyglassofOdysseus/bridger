#!/usr/bin/env python3
"""Validation for Passrail-minted, request-bound Bridger execution grants."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import stat
import time
from typing import Any, Callable

from bridge_tool_policy import CONSEQUENTIAL_TOOLS, SUPPORTED_TOOLS

GRANT_SCHEMA = "passrail-execution-grant-v1"
GRANT_AUDIENCE = "bridger-local-execution"
REQUEST_FIELDS = {"execution_id", "tool", "arguments", "requested_risk_class"}
GRANT_FIELDS = {
    "schema_version", "audience", "item_id", "project", "message_key",
    "envelope_hash", "attempt", "execution_id", "tool", "request_sha256",
    "requested_risk_class", "issued_at", "expires_at", "nonce",
}
RISK_CLASSES = {"SAFE_RETRY", "NO_AUTO_RETRY"}
AUTH_BINDING_FIELDS = (
    "schema_version", "audience", "item_id", "project", "message_key",
    "envelope_hash", "attempt", "execution_id", "tool", "request_sha256",
    "requested_risk_class",
)
MAX_REQUEST_BYTES = 256 * 1024
MAX_CLOCK_SKEW_SECONDS = 5


class GrantValidationError(ValueError):
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
        raise GrantValidationError("value must be finite, standard JSON")
    validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def validate_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != REQUEST_FIELDS:
        raise GrantValidationError("invalid direct execution request fields")
    execution_id = value["execution_id"]
    tool = value["tool"]
    arguments = value["arguments"]
    risk_class = value["requested_risk_class"]
    if not isinstance(execution_id, str) or not execution_id or len(execution_id) > 128:
        raise GrantValidationError("invalid execution_id")
    if not all(ch.isalnum() or ch in "._:-" for ch in execution_id):
        raise GrantValidationError("invalid execution_id")
    if not isinstance(tool, str) or not tool or len(tool) > 256:
        raise GrantValidationError("invalid tool")
    if tool not in SUPPORTED_TOOLS:
        raise GrantValidationError("unsupported Bridger host tool")
    if not isinstance(arguments, dict):
        raise GrantValidationError("arguments must be an object")
    if risk_class not in RISK_CLASSES:
        raise GrantValidationError("invalid requested_risk_class")
    if tool in CONSEQUENTIAL_TOOLS and risk_class != "NO_AUTO_RETRY":
        raise GrantValidationError("consequential tool requires NO_AUTO_RETRY")
    if len(canonical(value).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise GrantValidationError("direct execution request exceeds limit")
    return dict(value)


def request_sha256(value: Any) -> str:
    return hashlib.sha256(canonical(validate_request(value)).encode("utf-8")).hexdigest()


def validate_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise GrantValidationError("execution-grant key must contain at least 32 bytes")
    return key


def load_hex_key(path: Path) -> bytes:
    path = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise GrantValidationError(f"cannot open execution-grant key safely: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise GrantValidationError("execution-grant key must be a regular file")
        if info.st_uid != os.getuid():
            raise GrantValidationError("execution-grant key must be owned by the service user")
        if info.st_mode & 0o077:
            raise GrantValidationError("execution-grant key must not be group/world accessible")
        raw = os.read(fd, 512).decode("ascii").strip()
    finally:
        os.close(fd)
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise GrantValidationError("execution-grant key must be hexadecimal") from exc
    return validate_key(key)


def authorization_sha256(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise GrantValidationError("grant payload must be an object")
    binding = {field: payload.get(field) for field in AUTH_BINDING_FIELDS}
    if any(value is None for value in binding.values()):
        raise GrantValidationError("grant is missing authority-binding fields")
    return hashlib.sha256(canonical(binding).encode("utf-8")).hexdigest()


def verify_signed_grant(
    signed: Any,
    execution_request: Any,
    key: bytes,
    *,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    validate_key(key)
    request = validate_request(execution_request)
    if not isinstance(signed, dict) or set(signed) != {"grant", "signature"}:
        raise GrantValidationError("invalid signed grant shape")
    payload = signed["grant"]
    signature = signed["signature"]
    if not isinstance(payload, dict) or set(payload) != GRANT_FIELDS:
        raise GrantValidationError("invalid grant fields")
    if not isinstance(signature, str) or len(signature) != 64:
        raise GrantValidationError("invalid grant signature")
    expected = hmac.new(validate_key(key), canonical(payload).encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise GrantValidationError("grant signature mismatch")
    if payload.get("schema_version") != GRANT_SCHEMA or payload.get("audience") != GRANT_AUDIENCE:
        raise GrantValidationError("grant schema/audience mismatch")
    if type(payload.get("item_id")) is not int or payload["item_id"] <= 0:
        raise GrantValidationError("invalid grant item_id")
    if type(payload.get("attempt")) is not int or payload["attempt"] <= 0:
        raise GrantValidationError("invalid grant attempt")
    for field in ("project", "message_key", "execution_id", "tool", "envelope_hash", "request_sha256", "requested_risk_class", "nonce"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise GrantValidationError(f"invalid grant {field}")
    if len(payload["envelope_hash"]) != 64 or len(payload["request_sha256"]) != 64:
        raise GrantValidationError("invalid grant digest")
    if payload["requested_risk_class"] not in RISK_CLASSES:
        raise GrantValidationError("invalid grant risk class")
    for field in ("issued_at", "expires_at"):
        if type(payload.get(field)) not in (int, float) or not math.isfinite(payload[field]):
            raise GrantValidationError(f"invalid grant {field}")
    now = float(clock())
    if payload["issued_at"] > now + MAX_CLOCK_SKEW_SECONDS:
        raise GrantValidationError("grant issued in the future")
    if payload["expires_at"] <= now:
        raise GrantValidationError("grant expired")
    if payload["expires_at"] <= payload["issued_at"]:
        raise GrantValidationError("invalid grant lifetime")
    if payload["execution_id"] != request["execution_id"] or payload["tool"] != request["tool"]:
        raise GrantValidationError("grant execution identity mismatch")
    if payload["requested_risk_class"] != request["requested_risk_class"]:
        raise GrantValidationError("grant risk-class mismatch")
    if payload["request_sha256"] != request_sha256(request):
        raise GrantValidationError("grant request digest mismatch")
    return dict(payload)
