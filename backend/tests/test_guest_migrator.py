"""
test_guest_migrator.py — Unit tests for atomic guest project migration to registered user
"""

import unittest
from unittest.mock import MagicMock, patch
from services.guest_migrator import migrate_guest_projects_to_user
from services.guest_identity import sign_guest_token


class TestGuestMigrator(unittest.TestCase):
    def test_invalid_token_fails(self):
        with self.assertRaises(ValueError):
            migrate_guest_projects_to_user("invalid.token.here", "user-123")

    def test_nonexistent_user_fails(self):
        token = sign_guest_token("session-abc")
        with patch("services.guest_migrator.get_supabase_client") as mock_sb:
            mock_table = MagicMock()
            mock_sb.return_value.table.return_value = mock_table
            # user query returns empty
            mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

            with self.assertRaises(ValueError) as ctx:
                migrate_guest_projects_to_user(token, "nonexistent-user")
            self.assertIn("does not exist", str(ctx.exception))

    def test_successful_migration(self):
        token = sign_guest_token("session-abc")
        with patch("services.guest_migrator.get_supabase_client") as mock_sb:
            mock_table = MagicMock()
            mock_sb.return_value.table.return_value = mock_table

            def mock_table_side_effect(table_name):
                t = MagicMock()
                if table_name == "user":
                    t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                        {"id": "user-123", "name": "Test User", "email": "test@example.com"}
                    ]
                elif table_name == "guest_projects":
                    t.select.return_value.eq.return_value.is_.return_value.execute.return_value.data = [
                        {"id": "gp-1", "project_id": "proj-100", "expires_at": "2026-08-30T00:00:00Z"}
                    ]
                elif table_name == "project_members":
                    # No existing membership for real user
                    t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
                    # Guest membership exists
                    t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                        {"id": "mem-guest-1"}
                    ]
                return t

            mock_sb.return_value.table.side_effect = mock_table_side_effect

            result = migrate_guest_projects_to_user(token, "user-123")
            self.assertTrue(result["success"])
            self.assertEqual(result["migrated_count"], 1)
            self.assertEqual(result["projects"], ["proj-100"])


if __name__ == "__main__":
    unittest.main()
