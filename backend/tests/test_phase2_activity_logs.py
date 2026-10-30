"""
Phase 2 Task 5: Activity-Log Queries and Indexes Regression Test Suite

Comprehensive coverage for:
1. Activity-log retrieval (GET /api/logs)
2. Backward compatibility: default unpaginated query returns a list
3. Paginated retrieval: returns { items, page, page_size, total, total_pages }
4. Filtering by supported fields: user_id, action, resource, resource_id
5. Date-range boundaries: start_date, end_date (calendar YYYY-MM-DD and ISO 8601 UTC)
6. Date validation: start_date > end_date returns 400, malformed date returns 400
7. Pagination validation: invalid page, page_size returns 400
8. Sort validation: invalid sort field or sort order returns 400
9. Deterministic tie-breaking: records with identical timestamps order stably by log_id
10. Full-text search (search / q) across actor, action, resource, and details
11. Empty collection & empty filter results return clean 200 responses
12. Sensitive field sanitization: passwords, tokens, API keys stripped from responses
13. Security & RBAC: Admin and Auditor permitted (200), Operator and Inspector forbidden (403), unauthenticated rejected (401)
14. Audit preservation: historical logs are never mutated or deleted
"""

import sys
import os
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Explicitly use local engine for automated unit test execution
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config import Config
from config.firebase import db
from services.activity_log_service import (
    log_activity,
    get_activity_logs,
    sanitize_log_entry,
    parse_iso_or_calendar_date
)


class ActivityLogQueriesAndIndexesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Insert dedicated controlled test fixtures for query testing
        cls.base_time = datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone.utc)
        
        # Test records with controlled timestamps and known fields
        cls.test_records = [
            {
                "log_id": "LOG-TEST-001",
                "user_id": "USR-ADMIN01",
                "username": "Jack Mathew",
                "action": "CREATE",
                "resource": "Product",
                "resource_id": "PRD-TEST-1",
                "ip_address": "192.168.1.10",
                "timestamp": (cls.base_time + timedelta(hours=1)).isoformat(),
                "details": "Created test industrial turbine rotor"
            },
            {
                "log_id": "LOG-TEST-002",
                "user_id": "USR-ADMIN01",
                "username": "Jack Mathew",
                "action": "UPDATE",
                "resource": "Product",
                "resource_id": "PRD-TEST-1",
                "ip_address": "192.168.1.10",
                "timestamp": (cls.base_time + timedelta(hours=2)).isoformat(),
                "details": "Updated turbine rotor specifications"
            },
            {
                "log_id": "LOG-TEST-003",
                "user_id": "USR-AUDITOR01",
                "username": "Arthur Pendelton",
                "action": "SCAN_TRIGGER",
                "resource": "Compliance",
                "resource_id": "CMP-TEST-9",
                "ip_address": "192.168.1.25",
                "timestamp": (cls.base_time + timedelta(hours=3)).isoformat(),
                "details": "Initiated automated compliance audit scan"
            },
            {
                "log_id": "LOG-TEST-004A",
                "user_id": "USR-OPERATOR01",
                "username": "David Bowman",
                "action": "AUTH_LOGIN",
                "resource": "System",
                "resource_id": "SESSION-A",
                "ip_address": "10.0.0.5",
                "timestamp": (cls.base_time + timedelta(hours=4)).isoformat(),
                "details": "Operator session login authenticated"
            },
            {
                # Identical timestamp as 004A to test deterministic tie-breaking on log_id
                "log_id": "LOG-TEST-004B",
                "user_id": "USR-OPERATOR01",
                "username": "David Bowman",
                "action": "AUTH_LOGIN",
                "resource": "System",
                "resource_id": "SESSION-B",
                "ip_address": "10.0.0.5",
                "timestamp": (cls.base_time + timedelta(hours=4)).isoformat(),
                "details": "Secondary operator session login"
            },
            {
                # Log entry with sensitive fields to test sanitization
                "log_id": "LOG-TEST-SENSITIVE",
                "user_id": "USR-ADMIN01",
                "username": "Jack Mathew",
                "action": "AUTH_LOGIN",
                "resource": "System",
                "resource_id": "AUTH-TEST",
                "ip_address": "127.0.0.1",
                "timestamp": (cls.base_time + timedelta(hours=5)).isoformat(),
                "details": {
                    "event": "Login attempt",
                    "password": "super-secret-password",
                    "token": "eyJhbGciOi...",
                    "jwt": "header.payload.signature"
                },
                "password_hash": "sha256$hidden",
                "secret": "master_api_key_should_not_leak"
            }
        ]

        for record in cls.test_records:
            db.collection(Config.COLLECTION_ACTIVITY_LOGS).document(record['log_id']).set(record)

    def get_token(self, email="admin@sentineltrace.local", password="ChangeMe123!"):
        res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })
        data = res.get_json()
        if data.get('success') and 'data' in data:
            return data['data']['token']
        return None

    # -------------------------------------------------------------------------
    # 1. Unpaginated Backward Compatibility & General Retrieval
    # -------------------------------------------------------------------------
    def test_01_unpaginated_returns_list_backwards_compatible(self):
        token = self.get_token("auditor@sentineltrace.local")
        res = self.client.get('/api/logs', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertIsInstance(data.get('data'), list)
        self.assertGreaterEqual(len(data['data']), 6)

    def test_02_unpaginated_custom_limit(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?limit=3', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertIsInstance(logs, list)
        self.assertEqual(len(logs), 3)

    # -------------------------------------------------------------------------
    # 2. Pagination Structure and Controls
    # -------------------------------------------------------------------------
    def test_03_paginated_response_structure(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?page=1&page_size=3', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()['data']
        self.assertIsInstance(payload, dict)
        self.assertIn('items', payload)
        self.assertIn('page', payload)
        self.assertIn('page_size', payload)
        self.assertIn('total', payload)
        self.assertIn('total_pages', payload)
        self.assertEqual(payload['page'], 1)
        self.assertEqual(payload['page_size'], 3)
        self.assertEqual(len(payload['items']), 3)
        self.assertGreaterEqual(payload['total'], 6)

    def test_04_paginate_explicit_flag(self):
        token = self.get_token("auditor@sentineltrace.local")
        res = self.client.get('/api/logs?paginate=true', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()['data']
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload['page'], 1)
        self.assertEqual(payload['page_size'], 10)

    def test_05_page_out_of_range_returns_empty_items(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?page=9999&page_size=10', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()['data']
        self.assertEqual(payload['items'], [])
        self.assertEqual(payload['page'], 9999)

    # -------------------------------------------------------------------------
    # 3. Filtering by Supported Fields
    # -------------------------------------------------------------------------
    def test_06_filter_by_user_id(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?user_id=USR-OPERATOR01', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertGreaterEqual(len(logs), 2)
        for log in logs:
            self.assertEqual(log['user_id'], 'USR-OPERATOR01')

    def test_07_filter_by_action(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?action=SCAN_TRIGGER', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertGreaterEqual(len(logs), 1)
        for log in logs:
            self.assertEqual(log['action'], 'SCAN_TRIGGER')

    def test_08_filter_by_resource(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?resource=Compliance', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertGreaterEqual(len(logs), 1)
        for log in logs:
            self.assertEqual(log['resource'], 'Compliance')

    def test_09_filter_by_resource_id(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?resource_id=PRD-TEST-1', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertEqual(len(logs), 2)
        for log in logs:
            self.assertEqual(log['resource_id'], 'PRD-TEST-1')

    # -------------------------------------------------------------------------
    # 4. Date-Range Boundaries & Validation
    # -------------------------------------------------------------------------
    def test_10_filter_by_date_range_valid(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?start_date=2026-10-15&end_date=2026-10-15', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertGreaterEqual(len(logs), 6)
        for log in logs:
            self.assertTrue(log['timestamp'].startswith('2026-10-15'))

    def test_11_filter_by_date_range_outside_window(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?start_date=2025-01-01&end_date=2025-01-31', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertEqual(logs, [])

    def test_12_date_range_inverted_error(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?start_date=2026-10-20&end_date=2026-10-10', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 400)
        err = res.get_json().get('error', {})
        self.assertIn("start_date cannot be after end_date", err.get('message', ''))

    def test_13_invalid_date_format_error(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?start_date=not-a-valid-date', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 400)
        err = res.get_json().get('error', {})
        self.assertIn("Invalid start_date format", err.get('message', ''))

    # -------------------------------------------------------------------------
    # 5. Full-Text Search
    # -------------------------------------------------------------------------
    def test_14_search_term_matching(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?search=rotor', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertEqual(len(logs), 2)
        for log in logs:
            self.assertIn("rotor", (log.get('details') or '').lower())

    # -------------------------------------------------------------------------
    # 6. Sorting & Deterministic Tie-Breaking
    # -------------------------------------------------------------------------
    def test_15_deterministic_tie_breaking(self):
        token = self.get_token("admin@sentineltrace.local")
        # LOG-TEST-004A and LOG-TEST-004B have identical timestamps and resource="System".
        # When sorted desc by timestamp, tie-breaker log_id desc means 004B must precede 004A.
        res_desc = self.client.get('/api/logs?action=AUTH_LOGIN&user_id=USR-OPERATOR01&resource=System&sort_by=timestamp&sort_order=desc', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_desc.status_code, 200)
        logs_desc = res_desc.get_json()['data']
        ids_desc = [l['log_id'] for l in logs_desc]
        self.assertEqual(ids_desc, ['LOG-TEST-004B', 'LOG-TEST-004A'])

        # When sorted asc by timestamp, tie-breaker log_id asc means 004A must precede 004B.
        res_asc = self.client.get('/api/logs?action=AUTH_LOGIN&user_id=USR-OPERATOR01&resource=System&sort_by=timestamp&sort_order=asc', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_asc.status_code, 200)
        logs_asc = res_asc.get_json()['data']
        ids_asc = [l['log_id'] for l in logs_asc]
        self.assertEqual(ids_asc, ['LOG-TEST-004A', 'LOG-TEST-004B'])

    # -------------------------------------------------------------------------
    # 7. Invalid Parameters & Error Handling
    # -------------------------------------------------------------------------
    def test_16_invalid_page_number_error(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?page=0', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 400)

    def test_17_invalid_page_size_error(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?page_size=500', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 400)

    def test_18_invalid_sort_field_error(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?sort_by=non_existent_field', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 400)

    def test_19_invalid_sort_order_error(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?sort_order=sideways', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 400)

    def test_20_invalid_limit_error(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?limit=-5', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 400)

    # -------------------------------------------------------------------------
    # 8. Security, RBAC & Sensitive Data Scrubbing
    # -------------------------------------------------------------------------
    def test_21_unauthenticated_request_rejected(self):
        res = self.client.get('/api/logs')
        self.assertEqual(res.status_code, 401)

    def test_22_rbac_operator_and_inspector_forbidden(self):
        token_operator = self.get_token("operator@sentineltrace.local")
        res_op = self.client.get('/api/logs', headers={"Authorization": f"Bearer {token_operator}"})
        self.assertEqual(res_op.status_code, 403)

        token_inspector = self.get_token("inspector@sentineltrace.local")
        res_insp = self.client.get('/api/logs', headers={"Authorization": f"Bearer {token_inspector}"})
        self.assertEqual(res_insp.status_code, 403)

    def test_23_rbac_auditor_and_admin_permitted(self):
        token_auditor = self.get_token("auditor@sentineltrace.local")
        res_aud = self.client.get('/api/logs', headers={"Authorization": f"Bearer {token_auditor}"})
        self.assertEqual(res_aud.status_code, 200)

        token_admin = self.get_token("admin@sentineltrace.local")
        res_adm = self.client.get('/api/logs', headers={"Authorization": f"Bearer {token_admin}"})
        self.assertEqual(res_adm.status_code, 200)

    def test_24_sensitive_fields_scrubbed_from_response(self):
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?resource_id=AUTH-TEST', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertEqual(len(logs), 1)
        item = logs[0]
        # Top-level sensitive fields must not be present
        self.assertNotIn('password', item)
        self.assertNotIn('password_hash', item)
        self.assertNotIn('token', item)
        self.assertNotIn('jwt', item)
        self.assertNotIn('secret', item)
        # Nested sensitive fields within details dictionary must not be present
        if isinstance(item.get('details'), dict):
            self.assertNotIn('password', item['details'])
            self.assertNotIn('token', item['details'])
            self.assertNotIn('jwt', item['details'])

    # -------------------------------------------------------------------------
    # 9. Audit Integrity & Record Immutability
    # -------------------------------------------------------------------------
    def test_25_audit_preservation_records_intact(self):
        # Verify initial seed log is still present and unaltered
        token = self.get_token("admin@sentineltrace.local")
        res = self.client.get('/api/logs?resource_id=INITIAL_SEED', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['log_id'], 'LOG-INIT01')
        self.assertEqual(logs[0]['action'], 'CREATE')


if __name__ == '__main__':
    unittest.main()
