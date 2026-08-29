"""
test_guest_routes.py — Integration tests for guest FastAPI endpoints
"""

import unittest
from fastapi.testclient import TestClient
from main import app
from services.guest_identity import GUEST_TOKEN_COOKIE_NAME, sign_guest_token


class TestGuestRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_guest_session_endpoint(self):
        response = self.client.get(
            "/api/guest/session",
            headers={
                "User-Agent": "Mozilla/5.0 (Integration Test)",
                "Accept-Language": "en-US",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("session_id", data)
        self.assertIn("allowed", data)
        self.assertIn("conversions_limit", data)
        self.assertEqual(data["conversions_limit"], 1)
        self.assertIn("token", data)
        # Check Set-Cookie header
        self.assertIn(GUEST_TOKEN_COOKIE_NAME, response.headers.get("set-cookie", ""))


if __name__ == "__main__":
    unittest.main()
