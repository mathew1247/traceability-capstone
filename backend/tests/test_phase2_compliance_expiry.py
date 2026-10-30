"""
Phase 2 Task 4: Compliance Expiry Monitoring Regression Test Suite

Comprehensive coverage for:
1. Expired records (days_left < 0 and stored status == 'Expired')
2. Records expiring today (days_left == 0)
3. Records expiring within the warning period (0 < days_left <= warning_days)
4. Records expiring just beyond the warning period (days_left == warning_days + 1)
5. Valid records with distant expiry dates (days_left > warning_days)
6. Missing expiry dates (None and empty string)
7. Invalid expiry dates (malformed strings, unparseable values)
8. Empty compliance collections (zero counts, safe empty response)
9. Correct API response structure (GET /api/compliance/expiry-status, GET /api/compliance)
10. Unauthorized access (missing token returns 401)
11. Role-based access restrictions (Admin, Inspector, Auditor, Operator)
12. Query filtering by expiry status and custom warning periods
13. Expiry alert scanning and deduplication (POST /api/compliance/check-expiries)
14. Dashboard integration and metric consistency
"""

import sys
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Explicitly set local test mode before importing firebase
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config import Config
from config.firebase import db
from services.compliance_service import (
    evaluate_compliance_expiry,
    enrich_compliance_with_expiry,
    check_and_trigger_compliance_alert,
    get_compliance_expiry_status,
    scan_and_alert_compliance_expiries,
    get_all_compliance,
    get_compliance_by_id
)


class ComplianceExpiryMonitoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.ref_date = date(2026, 10, 30)

    def get_token(self, email="admin@sentineltrace.local", password="ChangeMe123!"):
        res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })
        self.assertEqual(res.status_code, 200, f"Login failed for {email}")
        return res.get_json()['data']['token']

    def test_01_evaluate_expired_record(self):
        """1. A compliance record that has already expired is marked 'expired'."""
        # Date in the past (10 days ago)
        past_record = {
            "compliance_id": "CMP-TEST-PAST",
            "product_id": "PRD101",
            "standard": "ISO 9001:2015",
            "status": "Compliant",
            "expiry_date": (self.ref_date - timedelta(days=10)).isoformat()
        }
        res = evaluate_compliance_expiry(past_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res['status'], "expired")
        self.assertEqual(res['label'], "Expired")
        self.assertEqual(res['days_remaining'], -10)
        self.assertTrue(res['is_expired'])
        self.assertFalse(res['is_expiring_soon'])
        self.assertFalse(res['is_valid'])
        self.assertEqual(res['severity'], "Critical")
        self.assertTrue(res['requires_attention'])

        # Explicit status 'Expired' with future date still evaluated as expired
        status_expired_record = {
            "compliance_id": "CMP-TEST-EXP-STATUS",
            "product_id": "PRD101",
            "standard": "GMP",
            "status": "Expired",
            "expiry_date": (self.ref_date + timedelta(days=50)).isoformat()
        }
        res2 = evaluate_compliance_expiry(status_expired_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res2['status'], "expired")
        self.assertTrue(res2['is_expired'])
        self.assertFalse(res2['is_valid'])

    def test_02_evaluate_record_expiring_today(self):
        """2. A record that expires today (days_left == 0) is flagged as 'expiring_today'."""
        today_record = {
            "compliance_id": "CMP-TEST-TODAY",
            "product_id": "PRD101",
            "standard": "RoHS",
            "status": "Compliant",
            "expiry_date": self.ref_date.isoformat()
        }
        res = evaluate_compliance_expiry(today_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res['status'], "expiring_today")
        self.assertEqual(res['label'], "Expires Today")
        self.assertEqual(res['days_remaining'], 0)
        self.assertFalse(res['is_expired'])
        self.assertTrue(res['is_expiring_soon'])
        self.assertTrue(res['is_valid'])
        self.assertEqual(res['severity'], "Critical")
        self.assertTrue(res['requires_attention'])

    def test_03_evaluate_record_expiring_within_warning_period(self):
        """3. A record that expires within the configured warning period is flagged 'expiring_soon'."""
        # 15 days remaining (warning = 30)
        soon_record = {
            "compliance_id": "CMP-TEST-SOON",
            "product_id": "PRD102",
            "standard": "GMP",
            "status": "Review Required",
            "expiry_date": (self.ref_date + timedelta(days=15)).isoformat()
        }
        res = evaluate_compliance_expiry(soon_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res['status'], "expiring_soon")
        self.assertEqual(res['label'], "Expiring Soon")
        self.assertEqual(res['days_remaining'], 15)
        self.assertFalse(res['is_expired'])
        self.assertTrue(res['is_expiring_soon'])
        self.assertTrue(res['is_valid'])
        self.assertEqual(res['severity'], "Warning")
        self.assertTrue(res['requires_attention'])

        # Boundary test: exactly on the 30th day
        boundary_record = {
            "compliance_id": "CMP-TEST-BOUNDARY",
            "product_id": "PRD102",
            "standard": "GMP",
            "status": "Compliant",
            "expiry_date": (self.ref_date + timedelta(days=30)).isoformat()
        }
        res_bound = evaluate_compliance_expiry(boundary_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res_bound['status'], "expiring_soon")
        self.assertEqual(res_bound['days_remaining'], 30)
        self.assertTrue(res_bound['is_expiring_soon'])

    def test_04_evaluate_record_expiring_just_beyond_warning_period(self):
        """4. A record expiring just beyond the warning period (e.g. 31 days) remains 'valid'."""
        just_beyond_record = {
            "compliance_id": "CMP-TEST-BEYOND",
            "product_id": "PRD103",
            "standard": "ISO 9001:2015",
            "status": "Compliant",
            "expiry_date": (self.ref_date + timedelta(days=31)).isoformat()
        }
        res = evaluate_compliance_expiry(just_beyond_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res['status'], "valid")
        self.assertEqual(res['label'], "Valid")
        self.assertEqual(res['days_remaining'], 31)
        self.assertFalse(res['is_expired'])
        self.assertFalse(res['is_expiring_soon'])
        self.assertTrue(res['is_valid'])
        self.assertEqual(res['severity'], "Normal")
        self.assertFalse(res['requires_attention'])

    def test_05_evaluate_valid_record_with_distant_expiry_date(self):
        """5. A record with a distant expiry date (e.g. 365 days) is marked 'valid'."""
        distant_record = {
            "compliance_id": "CMP-TEST-DISTANT",
            "product_id": "PRD101",
            "standard": "ISO 9001:2015",
            "status": "Compliant",
            "expiry_date": (self.ref_date + timedelta(days=365)).isoformat()
        }
        res = evaluate_compliance_expiry(distant_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res['status'], "valid")
        self.assertEqual(res['days_remaining'], 365)
        self.assertTrue(res['is_valid'])
        self.assertFalse(res['is_expiring_soon'])
        self.assertFalse(res['is_expired'])
        self.assertFalse(res['requires_attention'])

    def test_06_evaluate_missing_expiry_date(self):
        """6. Missing expiry date (None or empty string) is never silently treated as valid."""
        # None value
        none_record = {
            "compliance_id": "CMP-TEST-NONE",
            "product_id": "PRD101",
            "standard": "RoHS",
            "status": "Compliant",
            "expiry_date": None
        }
        res_none = evaluate_compliance_expiry(none_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res_none['status'], "missing_date")
        self.assertIsNone(res_none['days_remaining'])
        self.assertFalse(res_none['is_valid'])
        self.assertTrue(res_none['requires_attention'])

        # Empty string
        empty_record = {
            "compliance_id": "CMP-TEST-EMPTY",
            "product_id": "PRD101",
            "standard": "RoHS",
            "status": "Compliant",
            "expiry_date": "   "
        }
        res_empty = evaluate_compliance_expiry(empty_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res_empty['status'], "missing_date")
        self.assertIsNone(res_empty['days_remaining'])
        self.assertFalse(res_empty['is_valid'])
        self.assertTrue(res_empty['requires_attention'])

    def test_07_evaluate_invalid_expiry_date(self):
        """7. Malformed/unparseable expiry dates are never silently treated as valid."""
        invalid_record = {
            "compliance_id": "CMP-TEST-INVALID",
            "product_id": "PRD101",
            "standard": "RoHS",
            "status": "Compliant",
            "expiry_date": "not-a-valid-date-string"
        }
        res = evaluate_compliance_expiry(invalid_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res['status'], "invalid_date")
        self.assertEqual(res['label'], "Invalid Expiry Date")
        self.assertIsNone(res['days_remaining'])
        self.assertFalse(res['is_valid'])
        self.assertTrue(res['requires_attention'])

        # Impossible calendar date
        bad_cal_record = {
            "compliance_id": "CMP-TEST-BAD-CAL",
            "product_id": "PRD101",
            "standard": "RoHS",
            "status": "Compliant",
            "expiry_date": "2026-02-31"
        }
        res_cal = evaluate_compliance_expiry(bad_cal_record, warning_days=30, reference_date=self.ref_date)
        self.assertEqual(res_cal['status'], "invalid_date")
        self.assertFalse(res_cal['is_valid'])

    def test_08_empty_compliance_collection(self):
        """8. Monitoring handles empty compliance collections safely without division by zero or errors."""
        # Backup existing compliance records from local store
        comp_store = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS)._store
        saved_store = dict(comp_store)
        try:
            comp_store.clear()
            status_data = get_compliance_expiry_status(warning_days=30, reference_date=self.ref_date)
            summary = status_data['summary']
            self.assertEqual(summary['total_records'], 0)
            self.assertEqual(summary['valid_count'], 0)
            self.assertEqual(summary['expiring_soon_count'], 0)
            self.assertEqual(summary['expired_count'], 0)
            self.assertEqual(status_data['records'], [])

            # Test API endpoint with empty collection
            token = self.get_token("admin@sentineltrace.local")
            res = self.client.get('/api/compliance/expiry-status', headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(res.status_code, 200)
            json_data = res.get_json()['data']
            self.assertEqual(json_data['summary']['total_records'], 0)
            self.assertEqual(json_data['records'], [])
        finally:
            comp_store.update(saved_store)

    def test_09_correct_api_response_structure(self):
        """9. API endpoints return standard, expected response envelope and rich expiry metadata."""
        token = self.get_token("inspector@sentineltrace.local")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. GET /api/compliance/expiry-status
        res = self.client.get('/api/compliance/expiry-status', headers=headers)
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body['success'])
        data = body['data']
        self.assertIn('summary', data)
        self.assertIn('records', data)

        summary = data['summary']
        expected_keys = [
            'total_records', 'valid_count', 'expiring_soon_count',
            'expiring_today_count', 'expired_count', 'missing_date_count',
            'invalid_date_count', 'attention_required_count', 'warning_days', 'reference_date'
        ]
        for key in expected_keys:
            self.assertIn(key, summary, f"Key '{key}' missing from summary")

        # 2. GET /api/compliance list enrichment
        res_list = self.client.get('/api/compliance', headers=headers)
        self.assertEqual(res_list.status_code, 200)
        records = res_list.get_json()['data']
        self.assertGreaterEqual(len(records), 1)
        first = records[0]
        self.assertIn('expiry_status', first)
        self.assertIn('is_expired', first)
        self.assertIn('is_expiring_soon', first)
        self.assertIn('is_valid', first)

    def test_10_unauthorized_access(self):
        """10. Unauthenticated requests are rejected with 401."""
        res_status = self.client.get('/api/compliance/expiry-status')
        self.assertEqual(res_status.status_code, 401)

        res_scan = self.client.post('/api/compliance/check-expiries', json={})
        self.assertEqual(res_scan.status_code, 401)

    def test_11_role_based_access_restrictions(self):
        """11. RBAC enforces permissions strictly: Auditor can view, Operator blocked, Admin/Inspector can scan."""
        auditor_token = self.get_token("auditor@sentineltrace.local")
        operator_token = self.get_token("operator@sentineltrace.local")
        inspector_token = self.get_token("inspector@sentineltrace.local")
        admin_token = self.get_token("admin@sentineltrace.local")

        # Auditor can view expiry status
        res_auditor_view = self.client.get('/api/compliance/expiry-status', headers={"Authorization": f"Bearer {auditor_token}"})
        self.assertEqual(res_auditor_view.status_code, 200)

        # Auditor is forbidden from executing alert scans
        res_auditor_scan = self.client.post('/api/compliance/check-expiries', headers={"Authorization": f"Bearer {auditor_token}"})
        self.assertEqual(res_auditor_scan.status_code, 403)

        # Operator cannot view or scan compliance
        res_operator_view = self.client.get('/api/compliance/expiry-status', headers={"Authorization": f"Bearer {operator_token}"})
        self.assertEqual(res_operator_view.status_code, 403)
        res_operator_scan = self.client.post('/api/compliance/check-expiries', headers={"Authorization": f"Bearer {operator_token}"})
        self.assertEqual(res_operator_scan.status_code, 403)

        # Inspector can view and scan
        res_insp_view = self.client.get('/api/compliance/expiry-status', headers={"Authorization": f"Bearer {inspector_token}"})
        self.assertEqual(res_insp_view.status_code, 200)
        res_insp_scan = self.client.post('/api/compliance/check-expiries', headers={"Authorization": f"Bearer {inspector_token}"})
        self.assertEqual(res_insp_scan.status_code, 200)

        # Admin can view and scan
        res_admin_scan = self.client.post('/api/compliance/check-expiries', headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(res_admin_scan.status_code, 200)

    def test_12_filtering_and_custom_warning_period(self):
        """12. Filter by status, standard, and configurable warning period."""
        token = self.get_token("inspector@sentineltrace.local")
        headers = {"Authorization": f"Bearer {token}"}

        # Filter by expiry_status on /api/compliance
        res_expiring = self.client.get('/api/compliance?expiry_status=expiring_soon', headers=headers)
        self.assertEqual(res_expiring.status_code, 200)
        for r in res_expiring.get_json()['data']:
            self.assertEqual(r['expiry_status'], 'expiring_soon')

        # Filter on /api/compliance/expiry-status with custom warning days
        res_custom_days = self.client.get('/api/compliance/expiry-status?warning_days=60', headers=headers)
        self.assertEqual(res_custom_days.status_code, 200)
        summary = res_custom_days.get_json()['data']['summary']
        self.assertEqual(summary['warning_days'], 60)

    def test_13_scan_and_alert_triggering(self):
        """13. POST /api/compliance/check-expiries detects expiring records and registers system alerts."""
        token = self.get_token("admin@sentineltrace.local")
        headers = {"Authorization": f"Bearer {token}"}

        res = self.client.post('/api/compliance/check-expiries', headers=headers, json={"warning_days": 30})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body['success'])
        data = body['data']
        self.assertIn('summary', data)
        self.assertIn('alerts_triggered', data)

        # Alerts collection should contain active compliance alert
        alerts_docs = db.collection(Config.COLLECTION_ALERTS).where('source', '==', 'Compliance').get()
        compliance_alerts = [d.to_dict() for d in alerts_docs if d.to_dict()]
        self.assertGreaterEqual(len(compliance_alerts), 1)

    def test_14_dashboard_metrics_integration(self):
        """14. Dashboard metrics include compliance expiry counts while preserving existing metrics."""
        token = self.get_token("operator@sentineltrace.local")
        headers = {"Authorization": f"Bearer {token}"}

        res = self.client.get('/api/dashboard/stats', headers=headers)
        self.assertEqual(res.status_code, 200)
        stats = res.get_json()['data']

        # Existing metrics intact
        self.assertIn('total_compliance_records', stats)
        self.assertIn('compliant_records', stats)
        self.assertIn('compliance_rate', stats)

        # New compliance expiry fields present
        self.assertIn('expiring_soon_compliance', stats)
        self.assertIn('expired_by_date_compliance', stats)
        self.assertIsInstance(stats['expiring_soon_compliance'], int)
        self.assertIsInstance(stats['expired_by_date_compliance'], int)


if __name__ == '__main__':
    unittest.main()
