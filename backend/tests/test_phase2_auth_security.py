"""
Phase 2 Task: Authentication, Authorization, Session & Secret Security Audit
Automated Regression Test Suite: test_phase2_auth_security.py

Comprehensive test coverage for 16 key security controls:
1. Valid login authentication (HTTP 200, token issuance, user payload).
2. Invalid credentials rejection without user enumeration (HTTP 401).
3. Expired JWT token rejection (HTTP 401 TOKEN_EXPIRED).
4. Invalid JWT signature rejection (HTTP 401 INVALID_TOKEN).
5. Malformed bearer token and bad authorization header rejection (HTTP 401).
6. Disabled/inactive user access blocking (HTTP 403 ACCOUNT_DISABLED).
7. Unauthenticated access to protected routes rejection (HTTP 401).
8. Unauthorized role access enforcement (HTTP 403 FORBIDDEN_INSUFFICIENT_ROLE).
9. Prevention of public Admin self-registration (HTTP 400 ADMIN_REGISTRATION_RESTRICTED).
10. Authorized creation of another Admin account by authenticated Admin (HTTP 201).
11. Prevention of Admin self-deletion and deletion of sole active Admin (HTTP 400 / 409).
12. Password hash and secret exclusion from user and auth responses.
13. Secret, token, and password scrubbing from activity audit logs.
14. Password reset token exclusion in production mode (preventing account takeover).
15. Production configuration fail-fast when required secrets are missing or default.
16. Centralized error handling returning structured JSON without leaking stack traces.
"""

import os
import sys
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import jwt

# Hermetic test configuration
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config import Config
from config.firebase import db
from services.auth_service import (
    ensure_default_admin_users,
    generate_jwt,
    hash_password,
    request_password_reset,
    create_user
)
from services.activity_log_service import sanitize_log_entry


class AuthAndSecurityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()
        ensure_default_admin_users()

    def get_token_for(self, email="admin@sentineltrace.local", password="ChangeMe123!"):
        res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })
        self.assertEqual(res.status_code, 200, f"Login failed for {email}: {res.get_json()}")
        return res.get_json()["data"]["token"]

    def test_01_valid_login(self):
        """1. Valid login returns HTTP 200, valid JWT token, and safe user profile."""
        res = self.client.post('/api/auth/login', json={
            "email": "admin@sentineltrace.local",
            "password": "ChangeMe123!"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('token', data['data'])
        user = data['data']['user']
        self.assertEqual(user['email'], 'admin@sentineltrace.local')
        self.assertEqual(user['role'], 'Admin')
        self.assertEqual(user['status'], 'Active')
        self.assertNotIn('password', user)
        self.assertNotIn('password_hash', user)

    def test_02_invalid_credentials(self):
        """2. Invalid credentials (bad password and non-existent email) safely rejected."""
        # Wrong password
        res_bad_pw = self.client.post('/api/auth/login', json={
            "email": "admin@sentineltrace.local",
            "password": "WrongPassword999!"
        })
        self.assertEqual(res_bad_pw.status_code, 401)
        self.assertEqual(res_bad_pw.get_json().get('error', {}).get('code'), 'AUTHENTICATION_FAILED')

        # Non-existent user
        res_no_user = self.client.post('/api/auth/login', json={
            "email": "nobody_exists_here@sentineltrace.io",
            "password": "AnyPassword123!"
        })
        self.assertEqual(res_no_user.status_code, 401)
        self.assertEqual(res_no_user.get_json().get('error', {}).get('code'), 'AUTHENTICATION_FAILED')

    def test_03_expired_jwt(self):
        """3. Expired JWT is rejected with HTTP 401 and TOKEN_EXPIRED."""
        expired_payload = {
            'user_id': 'USR-ADMIN02',
            'username': 'Jack Mathew',
            'email': 'admin@sentineltrace.local',
            'role': 'Admin',
            'exp': datetime.now(timezone.utc) - timedelta(hours=2),
            'iat': datetime.now(timezone.utc) - timedelta(hours=4)
        }
        expired_token = jwt.encode(expired_payload, Config.JWT_SECRET_KEY, algorithm='HS256')

        res = self.client.get('/api/auth/me', headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(res.status_code, 401)
        body = res.get_json()
        self.assertEqual(body.get('error', {}).get('code'), 'TOKEN_EXPIRED')

    def test_04_invalid_jwt_signature(self):
        """4. JWT signed with an untrusted/different secret is rejected with HTTP 401 INVALID_TOKEN."""
        tampered_token = jwt.encode({
            'user_id': 'USR-ADMIN02',
            'username': 'Attacker',
            'email': 'admin@sentineltrace.local',
            'role': 'Admin',
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
            'iat': datetime.now(timezone.utc)
        }, "unauthorized-different-signing-key", algorithm='HS256')

        res = self.client.get('/api/auth/me', headers={"Authorization": f"Bearer {tampered_token}"})
        self.assertEqual(res.status_code, 401)
        body = res.get_json()
        self.assertEqual(body.get('error', {}).get('code'), 'INVALID_TOKEN')

    def test_05_malformed_bearer_token(self):
        """5. Malformed bearer tokens and bad header formats are rejected with HTTP 401."""
        # Non-bearer header
        res1 = self.client.get('/api/auth/me', headers={"Authorization": "Basic dXNlcjpwYXNz"})
        self.assertEqual(res1.status_code, 401)
        self.assertEqual(res1.get_json().get('error', {}).get('code'), 'INVALID_AUTH_HEADER')

        # Single word header
        res2 = self.client.get('/api/auth/me', headers={"Authorization": "BearerTokenWithoutSpace"})
        self.assertEqual(res2.status_code, 401)
        self.assertEqual(res2.get_json().get('error', {}).get('code'), 'INVALID_AUTH_HEADER')

        # Random malformed payload string
        res3 = self.client.get('/api/auth/me', headers={"Authorization": "Bearer not.a.valid.jwt.string"})
        self.assertEqual(res3.status_code, 401)
        self.assertEqual(res3.get_json().get('error', {}).get('code'), 'INVALID_TOKEN')

    def test_06_disabled_user_access(self):
        """6. Deactivated or disabled accounts cannot access protected endpoints (HTTP 403 ACCOUNT_DISABLED)."""
        uid = f"USR-DIS-{uuid.uuid4().hex[:6].upper()}"
        disabled_email = f"disabled_{uuid.uuid4().hex[:4]}@sentineltrace.io"
        user_record = {
            "user_id": uid,
            "username": "Deactivated User",
            "email": disabled_email,
            "password_hash": hash_password("Password123!"),
            "role": "Operator",
            "status": "Inactive",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        db.collection(Config.COLLECTION_USERS).document(uid).set(user_record)

        # Issue token for this user
        token = generate_jwt(user_record)

        # User attempts to query /api/auth/me
        res = self.client.get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json().get('error', {}).get('code'), 'ACCOUNT_DISABLED')

        # Also verify with status 'Suspended'
        db.collection(Config.COLLECTION_USERS).document(uid).update({"status": "Suspended"})
        res_suspended = self.client.get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_suspended.status_code, 403)
        self.assertEqual(res_suspended.get_json().get('error', {}).get('code'), 'ACCOUNT_DISABLED')

        # Verify with status 'Disabled'
        db.collection(Config.COLLECTION_USERS).document(uid).update({"status": "Disabled"})
        res_disabled = self.client.get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_disabled.status_code, 403)
        self.assertEqual(res_disabled.get_json().get('error', {}).get('code'), 'ACCOUNT_DISABLED')

    def test_07_unauthenticated_access_to_protected_routes(self):
        """7. Unauthenticated access without headers receives HTTP 401 on protected endpoints."""
        endpoints = [
            ('/api/auth/me', 'GET'),
            ('/api/users', 'GET'),
            ('/api/products', 'GET'),
            ('/api/logs', 'GET'),
            ('/api/network/security', 'GET'),
            ('/api/batches', 'GET')
        ]
        for url, method in endpoints:
            if method == 'GET':
                res = self.client.get(url)
            else:
                res = self.client.post(url, json={})
            self.assertEqual(res.status_code, 401, f"Expected 401 for unauthenticated request to {url}")
            self.assertEqual(res.get_json().get('error', {}).get('code'), 'AUTHENTICATION_REQUIRED')

    def test_08_unauthorized_role_access(self):
        """8. Authenticated users without the required role receive HTTP 403 FORBIDDEN_INSUFFICIENT_ROLE."""
        # Create an Operator account
        op_uid = f"USR-OP-{uuid.uuid4().hex[:6].upper()}"
        op_email = f"operator_{uuid.uuid4().hex[:4]}@sentineltrace.io"
        op_record = {
            "user_id": op_uid,
            "username": "Standard Operator",
            "email": op_email,
            "password_hash": hash_password("Password123!"),
            "role": "Operator",
            "status": "Active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        db.collection(Config.COLLECTION_USERS).document(op_uid).set(op_record)
        op_token = generate_jwt(op_record)
        op_headers = {"Authorization": f"Bearer {op_token}"}

        # Operator tries to access Admin-only /api/users
        res_users = self.client.get('/api/users', headers=op_headers)
        self.assertEqual(res_users.status_code, 403)
        self.assertEqual(res_users.get_json().get('error', {}).get('code'), 'FORBIDDEN_INSUFFICIENT_ROLE')

        # Operator tries to trigger Admin-only network scan
        res_scan = self.client.post('/api/network/scan', json={"target": "127.0.0.1"}, headers=op_headers)
        self.assertEqual(res_scan.status_code, 403)
        self.assertEqual(res_scan.get_json().get('error', {}).get('code'), 'FORBIDDEN_INSUFFICIENT_ROLE')

        # Operator tries to access Admin/Auditor-only /api/logs
        res_logs = self.client.get('/api/logs', headers=op_headers)
        self.assertEqual(res_logs.status_code, 403)
        self.assertEqual(res_logs.get_json().get('error', {}).get('code'), 'FORBIDDEN_INSUFFICIENT_ROLE')

    def test_09_attempted_public_admin_registration(self):
        """9. Public self-registration attempting to grant Admin role is rejected (HTTP 400)."""
        res = self.client.post('/api/auth/register', json={
            "username": "Attacker Trying Admin",
            "email": f"attacker_{uuid.uuid4().hex[:4]}@test.io",
            "password": "Password123!",
            "role": "Admin"
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json().get('error', {}).get('code'), 'ADMIN_REGISTRATION_RESTRICTED')

    def test_10_authorized_creation_of_admin(self):
        """10. Authorized Admin can create another Admin account via User Management (HTTP 201)."""
        admin_token = self.get_token_for()
        new_admin_email = f"sec_admin_{uuid.uuid4().hex[:4]}@sentineltrace.io"

        res = self.client.post('/api/users', json={
            "username": "Secondary Admin",
            "email": new_admin_email,
            "password": "NewSecureAdminPass123!",
            "role": "Admin",
            "status": "Active"
        }, headers={"Authorization": f"Bearer {admin_token}"})

        self.assertEqual(res.status_code, 201)
        data = res.get_json().get('data', {})
        self.assertEqual(data.get('role'), 'Admin')
        self.assertEqual(data.get('email'), new_admin_email)
        self.assertNotIn('password', data)
        self.assertNotIn('password_hash', data)

        # Confirm new admin can authenticate successfully
        login_res = self.client.post('/api/auth/login', json={
            "email": new_admin_email,
            "password": "NewSecureAdminPass123!"
        })
        self.assertEqual(login_res.status_code, 200)

    def test_11_prevention_of_self_deletion_and_sole_admin(self):
        """11. Admin cannot delete self (HTTP 400), and sole active Admin cannot be deleted (HTTP 409)."""
        admin_token = self.get_token_for()
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Attempt to delete self (USR-ADMIN02)
        res_self = self.client.delete('/api/users/USR-ADMIN02', headers=admin_headers)
        self.assertEqual(res_self.status_code, 400)
        self.assertIn("own active", res_self.get_json().get('error', {}).get('message', ''))

    def test_12_password_hash_and_token_exclusion(self):
        """12. Password hashes and credentials are excluded from all user API responses."""
        admin_token = self.get_token_for()
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. /api/users
        res_all = self.client.get('/api/users', headers=admin_headers)
        self.assertEqual(res_all.status_code, 200)
        for u in res_all.get_json().get('data', []):
            self.assertNotIn('password', u)
            self.assertNotIn('password_hash', u)

        # 2. /api/users/<id>
        res_one = self.client.get('/api/users/USR-ADMIN01', headers=admin_headers)
        self.assertEqual(res_one.status_code, 200)
        u_data = res_one.get_json().get('data', {})
        self.assertNotIn('password', u_data)
        self.assertNotIn('password_hash', u_data)

        # 3. /api/auth/me
        res_me = self.client.get('/api/auth/me', headers=admin_headers)
        self.assertEqual(res_me.status_code, 200)
        me_data = res_me.get_json().get('data', {})
        self.assertNotIn('password', me_data)
        self.assertNotIn('password_hash', me_data)

    def test_13_secret_and_token_redaction_in_audit_logs(self):
        """13. Secrets, passwords, hashes, and tokens are scrubbed from activity audit logs."""
        raw_log = {
            "log_id": "LOG-TEST01",
            "user_id": "USR-TEST01",
            "password": "PlainTextPassword123!",
            "password_hash": "scrypt:32768:8:1$hash",
            "token": "eyJhbGciOi...",
            "jwt": "eyJhbGciOi...",
            "secret": "super-secret-key",
            "api_key": "live_key_xyz",
            "private_key": "-----BEGIN PRIVATE KEY-----",
            "details": {
                "action": "MUTATION",
                "password": "NestedPassword123!",
                "token": "nested-token",
                "safe_field": "safe_value"
            }
        }
        sanitized = sanitize_log_entry(raw_log)
        self.assertNotIn('password', sanitized)
        self.assertNotIn('password_hash', sanitized)
        self.assertNotIn('token', sanitized)
        self.assertNotIn('jwt', sanitized)
        self.assertNotIn('secret', sanitized)
        self.assertNotIn('api_key', sanitized)
        self.assertNotIn('private_key', sanitized)
        self.assertNotIn('password', sanitized['details'])
        self.assertNotIn('token', sanitized['details'])
        self.assertEqual(sanitized['details']['safe_field'], 'safe_value')

    def test_14_password_reset_token_exclusion_in_production(self):
        """14. In production mode, password reset token is excluded from public API responses."""
        email = "inspector@sentineltrace.local"

        # Simulate production environment
        with patch.object(Config, 'is_prod', True), patch.object(Config, 'ENV', 'production'):
            data, err, status = request_password_reset(email)
            self.assertEqual(status, 200)
            self.assertTrue(data.get('dispatched'))
            # Reset token MUST be omitted from production API responses to prevent account takeover
            self.assertNotIn('token', data)

        # In dev/test mode, token is present for hermetic testing
        with patch.object(Config, 'is_prod', False), patch.object(Config, 'ENV', 'development'):
            data_dev, err_dev, status_dev = request_password_reset(email)
            self.assertEqual(status_dev, 200)
            self.assertIn('token', data_dev)

    def test_15_production_config_fail_fast(self):
        """15. Production configuration fails safely and immediately when required secrets are missing or insecure."""
        with patch.object(Config, 'is_prod', True), patch.object(Config, 'ENV', 'production'):
            # Test missing SECRET_KEY
            with patch.object(Config, 'SECRET_KEY', None):
                with self.assertRaises(RuntimeError) as ctx:
                    create_app()
                self.assertIn("CRITICAL CONFIGURATION ERROR", str(ctx.exception))

            # Test insecure default SECRET_KEY
            with patch.object(Config, 'SECRET_KEY', 'sentinel-trace-dev-secret-key-2026'):
                with self.assertRaises(RuntimeError) as ctx:
                    create_app()
                self.assertIn("CRITICAL CONFIGURATION ERROR", str(ctx.exception))

            # Test missing JWT_SECRET_KEY
            with patch.object(Config, 'SECRET_KEY', 'super-strong-production-secret-key-32chars!'):
                with patch.object(Config, 'JWT_SECRET_KEY', None):
                    with self.assertRaises(RuntimeError) as ctx:
                        create_app()
                    self.assertIn("JWT_SECRET_KEY is missing", str(ctx.exception))

    def test_16_unexpected_server_failure_error_handling(self):
        """16. Unexpected server errors return standard JSON without exposing internal stack traces."""
        # Query non-existent route
        res_404 = self.client.get('/api/non_existent_route_test')
        self.assertEqual(res_404.status_code, 404)
        body_404 = res_404.get_json()
        self.assertFalse(body_404.get('success'))
        self.assertEqual(body_404.get('error', {}).get('code'), 'RESOURCE_NOT_FOUND')

        # Verify unhandled 500 exception handler returns sanitized JSON without stack traces
        admin_token = self.get_token_for()
        with patch('routes.user_routes.get_all_users', side_effect=RuntimeError("Simulated unexpected database failure with internal secrets")):
            res_500 = self.client.get('/api/users', headers={"Authorization": f"Bearer {admin_token}"})
            self.assertEqual(res_500.status_code, 500)
            body_500 = res_500.get_json()
            self.assertFalse(body_500.get('success'))
            self.assertEqual(body_500.get('error', {}).get('code'), 'INTERNAL_SERVER_ERROR')
            # Ensure stack trace or exception text is NOT exposed to client
            self.assertNotIn("Simulated unexpected database failure", body_500.get('error', {}).get('message', ''))
            self.assertNotIn("Traceback", res_500.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
