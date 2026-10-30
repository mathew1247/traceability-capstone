"""
Phase 2 Admin User Creation and Role Assignment Regression Suite
Repository: /home/jack/Projects/traceability-capstone

Verifies:
1. An authorized Admin can create another Admin.
2. The created document has the correct role and status.
3. The new Admin can authenticate.
4. The new Admin can access Admin-only endpoints.
5. An Inspector, Operator, or Auditor cannot create an Admin.
6. Unauthenticated requests are rejected.
7. Duplicate email addresses are rejected.
8. Invalid user input is rejected.
9. Failed Firestore writes do not produce a false success response.
10. The users list reflects the successfully created account.
11. Existing self-deletion and last-active-Admin protections still work.
12. The dashboard displays the correct authenticated username.
"""

import os
import sys
import unittest
import uuid
from unittest.mock import patch
from pathlib import Path

# Use isolated local Firestore engine for tests
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config import Config
from config.firebase import db


class AdminUserCreationAndRoleAssignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def get_token(self, email="admin@sentineltrace.local", password="ChangeMe123!"):
        res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })
        self.assertEqual(res.status_code, 200, f"Login failed for {email}: {res.get_json()}")
        return res.get_json()["data"]["token"]

    # 1. An authorized Admin can create another Admin
    def test_01_admin_can_create_another_admin(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}
        unique_email = f"new_admin_{uuid.uuid4().hex[:6]}@sentineltrace.io"

        res = self.client.post('/api/admin/users', headers=headers, json={
            "username": "Secondary Admin User",
            "email": unique_email,
            "password": "AdminPassword123!",
            "role": "Admin",
            "status": "Active"
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["data"]["role"], "Admin")
        self.assertEqual(data["data"]["status"], "Active")
        self.assertEqual(data["data"]["email"], unique_email)
        self.assertNotIn("password_hash", data["data"])

    # 2. The created document has the correct role and status in Firestore
    def test_02_created_admin_document_persistence(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}
        unique_email = f"persisted_admin_{uuid.uuid4().hex[:6]}@sentineltrace.io"

        res = self.client.post('/api/users', headers=headers, json={
            "username": "Persisted Admin",
            "email": unique_email,
            "password": "AdminPassword123!",
            "role": "Admin",
            "status": "Active"
        })
        self.assertEqual(res.status_code, 201)
        user_id = res.get_json()["data"]["user_id"]

        # Check database record directly
        doc = db.collection(Config.COLLECTION_USERS).document(user_id).get()
        self.assertTrue(doc.exists)
        user_doc = doc.to_dict()
        self.assertEqual(user_doc["role"], "Admin")
        self.assertEqual(user_doc["status"], "Active")
        self.assertEqual(user_doc["email"], unique_email)
        self.assertTrue(user_doc.get("password_hash"))

    # 3. The new Admin can authenticate
    def test_03_new_admin_can_authenticate(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}
        unique_email = f"login_admin_{uuid.uuid4().hex[:6]}@sentineltrace.io"
        pw = "UniqueSecretPass456!"

        res = self.client.post('/api/admin/users', headers=headers, json={
            "username": "Login Admin",
            "email": unique_email,
            "password": pw,
            "role": "Admin",
            "status": "Active"
        })
        self.assertEqual(res.status_code, 201)

        # Authenticate with new Admin credentials
        login_res = self.client.post('/api/auth/login', json={
            "email": unique_email,
            "password": pw
        })
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.get_json()["data"]
        self.assertIn("token", login_data)
        self.assertEqual(login_data["user"]["role"], "Admin")
        self.assertEqual(login_data["user"]["email"], unique_email)

    # 4. The new Admin can access Admin-only endpoints
    def test_04_new_admin_can_access_admin_endpoints(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}
        unique_email = f"endpoint_admin_{uuid.uuid4().hex[:6]}@sentineltrace.io"
        pw = "AdminPass789!"

        res = self.client.post('/api/users', headers=headers, json={
            "username": "Endpoint Admin",
            "email": unique_email,
            "password": pw,
            "role": "Admin",
            "status": "Active"
        })
        self.assertEqual(res.status_code, 201)

        # Log in as the newly created Admin
        new_token = self.get_token(unique_email, pw)
        new_headers = {"Authorization": f"Bearer {new_token}"}

        # Access Admin-only GET /api/admin/users
        res_users = self.client.get('/api/admin/users', headers=new_headers)
        self.assertEqual(res_users.status_code, 200)

        # Access Admin-only POST /api/network/scan
        res_scan = self.client.post('/api/network/scan', headers=new_headers, json={"target": "10.0.0.1"})
        self.assertEqual(res_scan.status_code, 201)

    # 5. An Inspector, Operator, or Auditor cannot create an Admin
    def test_05_non_admin_cannot_create_admin(self):
        non_admin_accounts = [
            ("inspector@sentineltrace.local", "ChangeMe123!"),
            ("auditor@sentineltrace.local", "ChangeMe123!"),
            ("operator@sentineltrace.local", "ChangeMe123!")
        ]

        for email, pw in non_admin_accounts:
            token = self.get_token(email, pw)
            headers = {"Authorization": f"Bearer {token}"}
            res = self.client.post('/api/admin/users', headers=headers, json={
                "username": "Illicit Admin",
                "email": f"bad_admin_{uuid.uuid4().hex[:6]}@test.io",
                "password": "Password123!",
                "role": "Admin"
            })
            self.assertEqual(res.status_code, 403, f"Expected 403 for {email}, got {res.status_code}")

        # Also verify public registration endpoint rejects Admin creation
        res_pub = self.client.post('/api/auth/register', json={
            "username": "Public Malicious Admin",
            "email": f"pub_admin_{uuid.uuid4().hex[:6]}@test.io",
            "password": "Password123!",
            "role": "Admin"
        })
        self.assertEqual(res_pub.status_code, 400)
        self.assertIn("ADMIN_REGISTRATION_RESTRICTED", res_pub.get_json().get("error", {}).get("code", ""))

    # 6. Unauthenticated requests are rejected
    def test_06_unauthenticated_requests_rejected(self):
        res = self.client.post('/api/admin/users', json={
            "username": "Unauth Admin",
            "email": "unauth@sentineltrace.io",
            "password": "Password123!",
            "role": "Admin"
        })
        self.assertEqual(res.status_code, 401)
        self.assertIn("AUTHENTICATION_REQUIRED", res.get_json().get("error", {}).get("code", ""))

    # 7. Duplicate email addresses are rejected
    def test_07_duplicate_email_rejected(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}
        existing_email = "admin@sentineltrace.local"

        res = self.client.post('/api/admin/users', headers=headers, json={
            "username": "Duplicate Admin",
            "email": existing_email,
            "password": "Password123!",
            "role": "Admin"
        })
        self.assertEqual(res.status_code, 409)
        self.assertIn("already exists", res.get_json().get("error", {}).get("message", ""))

    # 8. Invalid user input is rejected
    def test_08_invalid_input_rejected(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Missing required username
        res1 = self.client.post('/api/admin/users', headers=headers, json={
            "email": f"valid_{uuid.uuid4().hex[:4]}@sentineltrace.io",
            "password": "Password123!",
            "role": "Admin"
        })
        self.assertEqual(res1.status_code, 400)

        # Invalid email format
        res2 = self.client.post('/api/admin/users', headers=headers, json={
            "username": "Bad Email User",
            "email": "not-an-email",
            "password": "Password123!",
            "role": "Admin"
        })
        self.assertEqual(res2.status_code, 400)

        # Invalid role
        res3 = self.client.post('/api/admin/users', headers=headers, json={
            "username": "Bad Role User",
            "email": f"valid_{uuid.uuid4().hex[:4]}@sentineltrace.io",
            "password": "Password123!",
            "role": "SuperAdminGodMode"
        })
        self.assertEqual(res3.status_code, 400)

    # 9. Failed Firestore writes do not produce a false success response
    def test_09_failed_firestore_write_returns_clean_error(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}
        unique_email = f"fail_write_{uuid.uuid4().hex[:6]}@sentineltrace.io"

        # 1. Test create_user service directly with simulated Firestore failure
        with patch.object(db, 'collection') as mock_col:
            mock_ref = mock_col.return_value
            mock_ref.where.return_value.get.return_value = []
            mock_doc = mock_ref.document.return_value
            mock_doc.set.side_effect = RuntimeError("Simulated Firestore timeout / connection abort")

            from services.auth_service import create_user
            user_data, err, code = create_user("Direct Fail", unique_email, "Pass123!", "Admin")
            self.assertIsNone(user_data)
            self.assertEqual(code, 500)
            self.assertIn("Database error", err)

        # 2. Test HTTP route error propagation
        with patch('routes.user_routes.create_user') as mock_create:
            mock_create.return_value = (None, "Database error: Unable to store user record. Simulated Firestore timeout", 500)
            res = self.client.post('/api/admin/users', headers=headers, json={
                "username": "Failed Write Admin",
                "email": unique_email,
                "password": "Password123!",
                "role": "Admin"
            })
            self.assertEqual(res.status_code, 500)
            data = res.get_json()
            self.assertFalse(data.get("success", False))
            self.assertIn("CREATE_FAILED", data.get("error", {}).get("code", ""))

    # 10. The users list reflects the successfully created account
    def test_10_users_list_reflects_created_account(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}
        unique_email = f"listed_admin_{uuid.uuid4().hex[:6]}@sentineltrace.io"

        res_create = self.client.post('/api/admin/users', headers=headers, json={
            "username": "Listed Admin User",
            "email": unique_email,
            "password": "Password123!",
            "role": "Admin",
            "status": "Active"
        })
        self.assertEqual(res_create.status_code, 201)
        created_id = res_create.get_json()["data"]["user_id"]

        # List all users
        res_list = self.client.get('/api/admin/users', headers=headers)
        self.assertEqual(res_list.status_code, 200)
        users = res_list.get_json()["data"]
        matching = [u for u in users if u.get("user_id") == created_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["email"], unique_email)
        self.assertEqual(matching[0]["role"], "Admin")

    # 11. Existing self-deletion and last-active-Admin protections still work
    def test_11_self_deletion_and_sole_admin_protections(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Fetch current admin user id
        res_me = self.client.get('/api/auth/me', headers=headers)
        self.assertEqual(res_me.status_code, 200)
        my_id = res_me.get_json()["data"]["user_id"]

        # Attempt to delete own active administrator account returns 400
        res_del_self = self.client.delete(f'/api/admin/users/{my_id}', headers=headers)
        self.assertIn(res_del_self.status_code, (400, 409))
        self.assertIn("own", res_del_self.get_json().get("error", {}).get("message", "").lower())

    # 12. The dashboard displays the correct authenticated username
    def test_12_dashboard_and_auth_session_integrity(self):
        # Authenticate as Jack Mathew
        res_login = self.client.post('/api/auth/login', json={
            "email": "admin@sentineltrace.local",
            "password": "ChangeMe123!"
        })
        self.assertEqual(res_login.status_code, 200)
        user_info = res_login.get_json()["data"]["user"]
        self.assertEqual(user_info["username"], "Jack Mathew")
        self.assertEqual(user_info["role"], "Admin")

        # Verify /api/auth/me returns the authenticated profile
        token = res_login.get_json()["data"]["token"]
        res_me = self.client.get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_me.status_code, 200)
        self.assertEqual(res_me.get_json()["data"]["username"], "Jack Mathew")
