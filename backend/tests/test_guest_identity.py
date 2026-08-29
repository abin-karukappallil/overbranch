"""
test_guest_identity.py — Unit tests for guest fingerprinting, token signing & verification
"""

import time
import unittest
from unittest.mock import MagicMock
from services.guest_identity import (
    sign_guest_token,
    verify_guest_token,
    compute_device_fingerprint,
    GUEST_TOKEN_COOKIE_NAME,
)


class TestGuestIdentity(unittest.TestCase):
    def test_sign_and_verify_valid_token(self):
        session_id = "test-session-uuid-12345"
        token = sign_guest_token(session_id)
        self.assertIsNotNone(token)
        self.assertEqual(token.count("."), 2)

        verified = verify_guest_token(token)
        self.assertIsNotNone(verified)
        verified_id, verified_ts = verified
        self.assertEqual(verified_id, session_id)
        self.assertLess(abs(verified_ts - int(time.time())), 5)

    def test_tampered_token_rejected(self):
        session_id = "test-session-uuid-12345"
        token = sign_guest_token(session_id)
        parts = token.split(".")

        # Tamper with session_id
        tampered = f"hacked-session-id.{parts[1]}.{parts[2]}"
        self.assertIsNone(verify_guest_token(tampered))

        # Tamper with signature
        tampered_sig = f"{parts[0]}.{parts[1]}.badsignature1234"
        self.assertIsNone(verify_guest_token(tampered_sig))

    def test_expired_token_rejected(self):
        session_id = "test-session-uuid-12345"
        # 25 hours in the past
        past_timestamp = int(time.time()) - (25 * 3600)
        expired_token = sign_guest_token(session_id, timestamp=past_timestamp)

        self.assertIsNone(verify_guest_token(expired_token))

    def test_deterministic_device_fingerprint(self):
        request1 = MagicMock()
        request1.headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64)",
            "accept-language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Chromium";v="124"',
            "sec-ch-ua-platform": '"Linux"',
            "sec-ch-ua-mobile": "?0",
            "x-forwarded-for": "198.51.100.42",
        }
        request1.client.host = "198.51.100.42"

        request2 = MagicMock()
        request2.headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64)",
            "accept-language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Chromium";v="124"',
            "sec-ch-ua-platform": '"Linux"',
            "sec-ch-ua-mobile": "?0",
            "x-forwarded-for": "198.51.100.42",
        }
        request2.client.host = "198.51.100.42"

        fp1 = compute_device_fingerprint(request1)
        fp2 = compute_device_fingerprint(request2)

        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)

        # Change user-agent -> fingerprint must change
        request3 = MagicMock()
        request3.headers = dict(request1.headers)
        request3.headers["user-agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
        request3.client.host = "198.51.100.42"

        fp3 = compute_device_fingerprint(request3)
        self.assertNotEqual(fp3, fp1)


if __name__ == "__main__":
    unittest.main()
