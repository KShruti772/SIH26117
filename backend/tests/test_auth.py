import os
import unittest
import sqlite3
import jwt
from datetime import timedelta
from fastapi import status, Depends
from fastapi.testclient import TestClient
from unittest.mock import patch
from backend.app.main import app
from backend.app.config.settings import settings
from backend.security.database import get_db
from backend.security.auth import create_access_token, hash_password
from backend.security.dependencies import RoleChecker

TEST_DB_PATH = "data/private/aegis_auth_test.db"

def get_test_db():
    """FastAPI dependency override yielding a test connection to the temporary database."""
    conn = sqlite3.connect(TEST_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

class TestAegisAuth(unittest.TestCase):
    """Suite to verify all registration, login, JWT token, and RBAC authorization controls."""
    
    @classmethod
    def setUpClass(cls):
        # Ensure private folder exists
        os.makedirs(os.path.dirname(TEST_DB_PATH), exist_ok=True)
        # Setup clean schema
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'utc'))
            )
        """)
        conn.commit()
        conn.close()
        
        # Override dependency in app
        app.dependency_overrides[get_db] = get_test_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        # Clear overrides and remove temp test DB
        app.dependency_overrides.clear()
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    def setUp(self):
        # Clear users table before every test case to keep isolation
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users")
        conn.commit()
        conn.close()

    def test_registration_flow(self):
        """1, 4, 17. Verify successful registration hashes passwords and hides hashes in response."""
        response = self.client.post(
            "/auth/register",
            json={"username": "valid_user", "password": "securepassword123"}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["username"], "valid_user")
        self.assertEqual(data["role"], "user")
        
        # Confirm password hashes are not returned in API responses
        self.assertNotIn("password", data)
        self.assertNotIn("password_hash", data)
        
        # Confirm hash is physically stored in DB (not plaintext)
        conn = sqlite3.connect(TEST_DB_PATH)
        conn.row_factory = sqlite3.Row
        user = conn.execute("SELECT * FROM users WHERE username = ?", ("valid_user",)).fetchone()
        conn.close()
        self.assertIsNotNone(user)
        self.assertNotEqual(user["password_hash"], "securepassword123")
        self.assertTrue(user["password_hash"].startswith("$2b$"))

    def test_registration_duplicate_username(self):
        """2. Verify duplicate usernames trigger 400 Bad Request."""
        self.client.post(
            "/auth/register",
            json={"username": "duplicate_user", "password": "securepassword123"}
        )
        response = self.client.post(
            "/auth/register",
            json={"username": "duplicate_user", "password": "otherpassword123"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("registered", response.json()["detail"])

    def test_registration_weak_password(self):
        """3. Verify short passwords (under 8 chars) are rejected."""
        response = self.client.post(
            "/auth/register",
            json={"username": "test_user", "password": "short"}
        )
        # Pydantic or auth.py raises 400 or 422 depending on implementation
        self.assertIn(response.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY))

    def test_login_success(self):
        """5. Verify login succeeds and returns valid JWT access token."""
        # 1. Register
        self.client.post(
            "/auth/register",
            json={"username": "login_user", "password": "securepassword123"}
        )
        # 2. Login (JSON)
        response = self.client.post(
            "/auth/login",
            json={"username": "login_user", "password": "securepassword123"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["user"]["username"], "login_user")

    def test_login_failures(self):
        """6, 7, 20. Verify bad logins return generic errors to prevent scanning attacks."""
        self.client.post(
            "/auth/register",
            json={"username": "registered_user", "password": "securepassword123"}
        )
        
        # Test incorrect password
        res1 = self.client.post("/auth/login", json={"username": "registered_user", "password": "wrongpassword"})
        self.assertEqual(res1.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res1.json()["detail"], "Invalid username or password")
        
        # Test nonexistent username
        res2 = self.client.post("/auth/login", json={"username": "unknown_user", "password": "securepassword123"})
        self.assertEqual(res2.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res2.json()["detail"], "Invalid username or password")

    def test_me_endpoint_and_jwt_validation(self):
        """8, 14. Verify access token unlocks /auth/me details."""
        self.client.post(
            "/auth/register",
            json={"username": "me_user", "password": "securepassword123"}
        )
        login_res = self.client.post(
            "/auth/login",
            json={"username": "me_user", "password": "securepassword123"}
        )
        token = login_res.json()["access_token"]
        
        # Call /auth/me with Bearer token
        headers = {"Authorization": f"Bearer {token}"}
        me_res = self.client.get("/auth/me", headers=headers)
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        self.assertEqual(me_res.json()["username"], "me_user")

    def test_invalid_and_tampered_jwt(self):
        """10, 11, 12. Verify modified, malformed, or missing tokens return 401."""
        # Missing token
        res_missing = self.client.get("/auth/me")
        self.assertEqual(res_missing.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Malformed token
        headers_malformed = {"Authorization": "Bearer not-a-valid-token-block"}
        res_mal = self.client.get("/auth/me", headers=headers_malformed)
        self.assertEqual(res_mal.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Tampered token (modified signature)
        valid_token = create_access_token("me_user", "user")
        parts = valid_token.split(".")
        # Modify signature (last part)
        tampered_token = f"{parts[0]}.{parts[1]}.modifiedsignature"
        res_tampered = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
        self.assertEqual(res_tampered.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_jwt(self):
        """9. Verify expired JWT tokens return 401 token signature expired."""
        expired_token = create_access_token("expired_user", "user", expires_delta=timedelta(seconds=-10))
        headers = {"Authorization": f"Bearer {expired_token}"}
        res = self.client.get("/auth/me", headers=headers)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res.json()["detail"], "Token signature has expired or is invalid. Please log in again.")

    def test_inactive_user(self):
        """13. Verify inactive profiles are blocked during token requests."""
        # Register and insert inactive manually
        hashed = hash_password("securepassword123")
        conn = sqlite3.connect(TEST_DB_PATH)
        conn.execute("INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)", ("inactive_user", hashed, "user", 0))
        conn.commit()
        conn.close()
        
        # Verify login endpoint blocks inactive
        res_login = self.client.post("/auth/login", json={"username": "inactive_user", "password": "securepassword123"})
        self.assertEqual(res_login.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("inactive", res_login.json()["detail"])
        
        # Verify /auth/me dependency checks block inactive
        token = create_access_token("inactive_user", "user")
        res_me = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_me.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Inactive user", res_me.json()["detail"])

    def test_role_authorization(self):
        """15, 16. Verify user role permissions and admin restrictions."""
        # Mock endpoints with role requirements for testing
        @app.get("/test-user-route")
        def user_route(current_user=Depends(RoleChecker(["user", "admin"]))):
            return {"status": "user_ok"}
            
        @app.get("/test-admin-route")
        def admin_route(current_user=Depends(RoleChecker(["admin"]))):
            return {"status": "admin_ok"}
            
        # Register standard user
        self.client.post("/auth/register", json={"username": "normal_user", "password": "securepassword123"})
        user_token = self.client.post("/auth/login", json={"username": "normal_user", "password": "securepassword123"}).json()["access_token"]
        
        # Register admin user (role mapped automatically because username contains 'admin')
        self.client.post("/auth/register", json={"username": "system_admin", "password": "securepassword123"})
        admin_token = self.client.post("/auth/login", json={"username": "system_admin", "password": "securepassword123"}).json()["access_token"]

        # 1. Standard user visits user route -> PASS
        r1 = self.client.get("/test-user-route", headers={"Authorization": f"Bearer {user_token}"})
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        
        # 2. Standard user visits admin route -> FAIL (403)
        r2 = self.client.get("/test-admin-route", headers={"Authorization": f"Bearer {user_token}"})
        self.assertEqual(r2.status_code, status.HTTP_403_FORBIDDEN)
        
        # 3. Admin user visits admin route -> PASS
        r3 = self.client.get("/test-admin-route", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(r3.status_code, status.HTTP_200_OK)

    def test_production_secret_guard(self):
        """19. Verify settings post-init fails if APP_ENV is production and SECRET_KEY is default."""
        with patch.object(settings, 'APP_ENV', 'production'):
            with patch.object(settings, 'SECRET_KEY', 'CHANGE_ME'):
                with self.assertRaises(ValueError):
                    settings.model_post_init(None)

if __name__ == "__main__":
    unittest.main()
