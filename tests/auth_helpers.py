"""
Test-only auth setup: fixed test credentials and ready-made auth headers.

Environment values set here override .env for the test process only
(python-dotenv never overwrites variables that are already set), so the
tests don't depend on — or reveal — the real credentials in .env.
"""

import os

TEST_USERS = {
    "admin": ("test-admin", "test-admin-password"),
    "analyst": ("test-analyst", "test-analyst-password"),
}

os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-that-is-long-enough-0123456789"
os.environ["ADMIN_USERNAME"], os.environ["ADMIN_PASSWORD"] = TEST_USERS["admin"]
os.environ["ANALYST_USERNAME"], os.environ["ANALYST_PASSWORD"] = TEST_USERS["analyst"]

from services.auth import create_access_token  # noqa: E402


def auth_headers(role: str = "admin") -> dict:
    username = TEST_USERS[role][0]
    token, _ = create_access_token(username, role)
    return {"Authorization": f"Bearer {token}"}


ADMIN_HEADERS = auth_headers("admin")
ANALYST_HEADERS = auth_headers("analyst")
