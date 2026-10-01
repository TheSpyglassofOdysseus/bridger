import hashlib
import hmac
import json
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "selfhosted"))

import bridge_execution_grant as grants

KEY = b"k" * 32
NOW = 1_000.0


def request(**overrides):
    value = {
        "execution_id": "exec-1",
        "tool": "read_file",
        "arguments": {"path": "/etc/hostname"},
        "requested_risk_class": "SAFE_RETRY",
    }
    value.update(overrides)
    return value


def signed(req=None, **overrides):
    req = req or request()
    payload = {
        "schema_version": grants.GRANT_SCHEMA,
        "audience": grants.GRANT_AUDIENCE,
        "item_id": 7,
        "project": "demo",
        "message_key": "work:7",
        "envelope_hash": "a" * 64,
        "attempt": 1,
        "execution_id": req["execution_id"],
        "tool": req["tool"],
        "request_sha256": grants.request_sha256(req),
        "requested_risk_class": req["requested_risk_class"],
        "issued_at": NOW,
        "expires_at": NOW + 30,
        "nonce": "b" * 32,
    }
    payload.update(overrides)
    signature = hmac.new(KEY, grants.canonical(payload).encode(), hashlib.sha256).hexdigest()
    return {"grant": payload, "signature": signature}


class GrantTests(unittest.TestCase):
    def test_valid_exact_request(self):
        req = request()
        payload = grants.verify_signed_grant(signed(req), req, KEY, clock=lambda: NOW + 1)
        self.assertEqual(payload["execution_id"], "exec-1")

    def test_tamper_or_wrong_request_rejected(self):
        req = request()
        token = signed(req)
        token["grant"]["project"] = "other"
        with self.assertRaisesRegex(grants.GrantValidationError, "signature"):
            grants.verify_signed_grant(token, req, KEY, clock=lambda: NOW + 1)
        with self.assertRaisesRegex(grants.GrantValidationError, "digest"):
            grants.verify_signed_grant(
                signed(req), request(arguments={"path": "/etc/passwd"}), KEY, clock=lambda: NOW + 1
            )

    def test_expired_future_and_wrong_key_rejected(self):
        req = request()
        with self.assertRaisesRegex(grants.GrantValidationError, "expired"):
            grants.verify_signed_grant(signed(req), req, KEY, clock=lambda: NOW + 31)
        with self.assertRaisesRegex(grants.GrantValidationError, "future"):
            grants.verify_signed_grant(signed(req, issued_at=NOW + 20, expires_at=NOW + 40), req, KEY, clock=lambda: NOW)
        with self.assertRaisesRegex(grants.GrantValidationError, "signature"):
            grants.verify_signed_grant(signed(req), req, b"z" * 32, clock=lambda: NOW + 1)

    def test_consequential_tool_requires_no_auto_retry(self):
        req = request(
            tool="start_process",
            arguments={"command": "printf ok", "timeout_ms": 1000},
            requested_risk_class="SAFE_RETRY",
        )
        with self.assertRaisesRegex(grants.GrantValidationError, "NO_AUTO_RETRY"):
            grants.validate_request(req)
        strict = dict(req, requested_risk_class="NO_AUTO_RETRY")
        payload = grants.verify_signed_grant(signed(strict), strict, KEY, clock=lambda: NOW + 1)
        self.assertEqual(payload["requested_risk_class"], "NO_AUTO_RETRY")

    def test_unknown_fields_fail_closed(self):
        req = dict(request(), extra=True)
        with self.assertRaisesRegex(grants.GrantValidationError, "fields"):
            grants.validate_request(req)


if __name__ == "__main__":
    unittest.main()
