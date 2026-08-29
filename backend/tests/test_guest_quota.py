"""
test_guest_quota.py — Unit tests for guest conversion quota calculation and enforcement
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from services.guest_quota import (
    check_guest_conversion_quota,
    CONVERSION_LIMIT_PER_24H,
)


class TestGuestQuota(unittest.TestCase):
    def test_quota_allowed_for_fresh_session(self):
        session = {
            "id": "session-1",
            "conversions_used": 0,
            "last_conversion_at": None,
        }
        fingerprint = "dummy-fingerprint-hash"

        with patch("services.guest_quota.get_supabase_client") as mock_sb:
            mock_table = MagicMock()
            mock_sb.return_value.table.return_value = mock_table
            mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

            allowed, used, resets_at, reason = check_guest_conversion_quota(session, fingerprint)
            self.assertTrue(allowed)
            self.assertEqual(used, 0)
            self.assertIsNone(resets_at)
            self.assertIsNone(reason)

    def test_quota_blocked_when_limit_reached(self):
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        session = {
            "id": "session-1",
            "conversions_used": 1,
            "last_conversion_at": one_hour_ago.isoformat(),
        }
        fingerprint = "dummy-fingerprint-hash"

        with patch("services.guest_quota.get_supabase_client") as mock_sb:
            allowed, used, resets_at, reason = check_guest_conversion_quota(session, fingerprint)
            self.assertFalse(allowed)
            self.assertEqual(used, 1)
            self.assertIsNotNone(resets_at)
            self.assertIn("Daily guest limit reached", reason)

    def test_cross_session_fingerprint_block(self):
        """If user clears cookies, cross-session check detects the same fingerprint in previous sessions."""
        fresh_session = {
            "id": "session-2",
            "conversions_used": 0,
            "last_conversion_at": None,
        }
        fingerprint = "same-device-fingerprint"

        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

        with patch("services.guest_quota.get_supabase_client") as mock_sb:
            mock_table = MagicMock()
            mock_sb.return_value.table.return_value = mock_table
            mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "session-1", "conversions_used": 1, "last_conversion_at": two_hours_ago}
            ]

            allowed, used, resets_at, reason = check_guest_conversion_quota(fresh_session, fingerprint)
            self.assertFalse(allowed)
            self.assertEqual(used, 1)
            self.assertIsNotNone(resets_at)
            self.assertIn("Daily guest limit reached for this device", reason)


if __name__ == "__main__":
    unittest.main()
