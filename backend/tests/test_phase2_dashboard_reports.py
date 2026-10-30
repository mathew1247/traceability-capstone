"""
Phase 2 Functional Reliability & Data Integrity: Task 2 Regression Test Suite
Dashboard and Report Accuracy

Verifies:
1. Dashboard metrics against a known database state.
2. Report totals against a known database state.
3. Dashboard and report calculation consistency where they measure the same metric.
4. Monthly throughput uses real chronological dates and exact quantities without arbitrary synthetic multipliers.
5. Missing historical data and empty collections are represented honestly without fabrication or zero-division errors.
6. Recent batches payload is enriched with product and material names to eliminate duplicate collection requests.
7. Frontend source files contain no arbitrary synthetic monthly coefficients.
8. Dashboard and report API endpoints enforce authentication and return valid schemas.
"""

import sys
import os
import unittest
from pathlib import Path

# Use local Firestore mock for hermetic testing
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config.firebase import db
from config import Config
from services.dashboard_service import get_dashboard_metrics
from services.report_service import get_reports_summary
from services.batch_service import create_batch


class DashboardAndReportAccuracyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Seed fresh local test data
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def get_token(self, email="admin@sentineltrace.local", password="ChangeMe123!"):
        res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })
        data = res.get_json()
        if data and data.get('success') and 'data' in data:
            return data['data']['token']
        return None

    def test_01_dashboard_metrics_against_known_state(self):
        """1. Dashboard metrics match exact known Firestore collection state."""
        metrics = get_dashboard_metrics()

        # Compare directly against actual docs in the database
        products_docs = [d.to_dict() for d in db.collection(Config.COLLECTION_PRODUCTS).get() if d.to_dict()]
        materials_docs = [d.to_dict() for d in db.collection(Config.COLLECTION_RAW_MATERIALS).get() if d.to_dict()]
        batches_docs = [d.to_dict() for d in db.collection(Config.COLLECTION_PRODUCTION_BATCHES).get() if d.to_dict()]
        compliance_docs = [d.to_dict() for d in db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).get() if d.to_dict()]
        alerts_docs = [d.to_dict() for d in db.collection(Config.COLLECTION_ALERTS).get() if d.to_dict()]

        self.assertEqual(metrics['total_products'], len(products_docs))
        self.assertEqual(metrics['total_materials'], len(materials_docs))
        self.assertEqual(metrics['total_batches'], len(batches_docs))

        # Total units produced must be exact sum of batch quantities
        expected_units = sum(int(b.get('quantity', 0)) for b in batches_docs)
        self.assertEqual(metrics['total_units_produced'], expected_units)
        self.assertEqual(metrics['total_units_manufactured'], expected_units)

        # Total material stock must be exact sum of material quantities
        expected_material_stock = sum(float(m.get('quantity', 0)) for m in materials_docs)
        self.assertEqual(metrics['total_material_quantity'], expected_material_stock)

        # Compliance rate calculation
        compliant_count = sum(1 for c in compliance_docs if c.get('status') == 'Compliant')
        expected_rate = round((compliant_count / len(compliance_docs) * 100), 1) if compliance_docs else 100.0
        self.assertEqual(metrics['compliance_rate'], expected_rate)
        self.assertEqual(metrics['compliant_records'], compliant_count)

        # Alerts count
        expected_active = sum(1 for a in alerts_docs if a.get('status') in ('Active', 'Open'))
        expected_critical = sum(1 for a in alerts_docs if a.get('severity') == 'Critical')
        self.assertEqual(metrics['active_alerts'], expected_active)
        self.assertEqual(metrics['critical_alerts'], expected_critical)

    def test_02_reports_summary_against_known_state(self):
        """2. Report summary matches exact known Firestore collection state."""
        summary = get_reports_summary()

        batches_docs = [d.to_dict() for d in db.collection(Config.COLLECTION_PRODUCTION_BATCHES).get() if d.to_dict()]
        compliance_docs = [d.to_dict() for d in db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).get() if d.to_dict()]
        alerts_docs = [d.to_dict() for d in db.collection(Config.COLLECTION_ALERTS).get() if d.to_dict()]

        prod = summary['production']
        comp = summary['compliance']
        alerts = summary['alerts']

        self.assertEqual(prod['total_batches'], len(batches_docs))
        expected_units = sum(int(b.get('quantity', 0)) for b in batches_docs)
        self.assertEqual(prod['total_units_manufactured'], expected_units)

        self.assertEqual(comp['total_certifications'], len(compliance_docs))
        expected_compliant = sum(1 for c in compliance_docs if c.get('status') == 'Compliant')
        self.assertEqual(comp['compliant_count'], expected_compliant)

        expected_active_alerts = sum(1 for a in alerts_docs if a.get('status') in ('Active', 'Open'))
        expected_critical_alerts = sum(1 for a in alerts_docs if a.get('severity') == 'Critical')
        self.assertEqual(alerts['active_alerts'], expected_active_alerts)
        self.assertEqual(alerts['critical_alerts'], expected_critical_alerts)

    def test_03_dashboard_and_reports_calculation_consistency(self):
        """3. Dashboard and report services produce consistent figures for identical metrics."""
        dashboard = get_dashboard_metrics()
        reports = get_reports_summary()

        # Shared metrics must match identically
        self.assertEqual(dashboard['total_batches'], reports['production']['total_batches'])
        self.assertEqual(dashboard['total_units_produced'], reports['production']['total_units_manufactured'])
        self.assertEqual(dashboard['compliance_rate'], reports['compliance']['compliance_rate'])
        self.assertEqual(dashboard['compliant_records'], reports['compliance']['compliant_count'])
        self.assertEqual(dashboard['total_compliance_records'], reports['compliance']['total_certifications'])
        self.assertEqual(dashboard['active_alerts'], reports['alerts']['active_alerts'])
        self.assertEqual(dashboard['critical_alerts'], reports['alerts']['critical_alerts'])
        self.assertEqual(dashboard['warning_alerts'], reports['alerts']['warning_alerts'])
        self.assertEqual(dashboard['total_alerts'], reports['alerts']['total_alerts'])
        self.assertEqual(dashboard['batch_status_distribution'], reports['production']['status_distribution'])

    def test_04_monthly_throughput_chronological_and_real(self):
        """4. Monthly throughput groups batches by real chronological YYYY-MM dates without synthetic multipliers."""
        # Query existing throughput
        dashboard = get_dashboard_metrics()
        throughput = dashboard.get('monthly_throughput', [])

        self.assertIsInstance(throughput, list)
        if len(throughput) > 1:
            keys = [m['month_key'] for m in throughput]
            # Must be sorted chronologically
            self.assertEqual(keys, sorted(keys))

        # Verify that month buckets accurately sum units
        batches_docs = [d.to_dict() for d in db.collection(Config.COLLECTION_PRODUCTION_BATCHES).get() if d.to_dict()]
        for m in throughput:
            m_key = m['month_key']
            matching_batches = [
                b for b in batches_docs
                if (b.get('production_date') or b.get('created_at') or '')[:7] == m_key
            ]
            if matching_batches:
                expected_units = sum(int(b.get('quantity', 0)) for b in matching_batches)
                self.assertEqual(m['total_units'], expected_units)
                self.assertEqual(m['batch_count'], len(matching_batches))

    def test_05_missing_historical_data_represented_honestly(self):
        """5. Absence of historical dates uses honest period grouping without fabricating past months."""
        # Temporarily create a batch with no date to verify graceful fallback
        no_date_batch = {
            "batch_number": "BATCH-NODATE-TEST",
            "quantity": 150,
            "status": "In QA Inspection"
        }
        ref = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document("BATCH-NODATE-TEST")
        ref.set(no_date_batch)

        try:
            dashboard = get_dashboard_metrics()
            month_keys = [m['month_key'] for m in dashboard['monthly_throughput']]
            self.assertIn("Current", month_keys)
            current_entry = next(m for m in dashboard['monthly_throughput'] if m['month_key'] == "Current")
            self.assertGreaterEqual(current_entry['pending_qa_units'], 150)
            self.assertEqual(current_entry['month_label'], "Current Period")
        finally:
            ref.delete()

    def test_06_recent_batches_enrichment_avoids_duplicate_lookups(self):
        """6. Dashboard recent_batches contains pre-joined product and material names."""
        dashboard = get_dashboard_metrics()
        recent = dashboard.get('recent_batches', [])

        self.assertIsInstance(recent, list)
        if recent:
            first = recent[0]
            # Necessary keys for UI cards and table
            self.assertIn('id', first)
            self.assertIn('product', first)
            self.assertIn('product_name', first)
            self.assertIn('material', first)
            self.assertIn('material_name', first)
            self.assertIn('quantity', first)
            self.assertIn('status', first)

    def test_07_absence_of_synthetic_multipliers_in_source_code(self):
        """7. Frontend scripts contain no fabricated historical coefficients or multipliers."""
        dash_js_path = backend_dir.parent / 'frontend' / 'js' / 'dashboard.js'
        reports_js_path = backend_dir.parent / 'frontend' / 'js' / 'reports.js'

        dash_content = dash_js_path.read_text()
        reports_content = reports_js_path.read_text()

        # Previously identified fabricated patterns
        forbidden_patterns = [
            "baseQA * 0.4",
            "baseCompleted * 0.35",
            "completedBase * 0.5",
            "completedBase * 0.7",
            "completedBase * 0.8",
            "completedBase * 0.9",
            "completedBase * 1.1",
            "qaBase * 0.4",
            "qaBase * 0.6",
            "qaBase * 0.8",
            "qaBase * 0.9",
            "qaBase * 1.0",
            "total_scans || 17"
        ]

        for pattern in forbidden_patterns:
            self.assertNotIn(pattern, dash_content, f"Found forbidden synthetic pattern '{pattern}' in dashboard.js")
            self.assertNotIn(pattern, reports_content, f"Found forbidden synthetic pattern '{pattern}' in reports.js")

    def test_08_api_endpoints_consistency_and_auth(self):
        """8. Dashboard and report API routes enforce authentication and return valid schemas."""
        token = self.get_token()
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Dashboard stats endpoint
        res_dash = self.client.get('/api/dashboard/stats', headers=headers)
        self.assertEqual(res_dash.status_code, 200)
        data_dash = res_dash.get_json()
        self.assertTrue(data_dash['success'])
        self.assertIn('total_batches', data_dash['data'])
        self.assertIn('monthly_throughput', data_dash['data'])
        self.assertIn('recent_batches', data_dash['data'])

        # 2. Reports summary endpoint
        res_rep = self.client.get('/api/reports/summary', headers=headers)
        self.assertEqual(res_rep.status_code, 200)
        data_rep = res_rep.get_json()
        self.assertTrue(data_rep['success'])
        self.assertIn('production', data_rep['data'])
        self.assertIn('compliance', data_rep['data'])
        self.assertIn('network', data_rep['data'])
        self.assertIn('alerts', data_rep['data'])

        # 3. Unauthenticated requests must be rejected
        unauth_dash = self.client.get('/api/dashboard/stats')
        self.assertEqual(unauth_dash.status_code, 401)

        unauth_rep = self.client.get('/api/reports/summary')
        self.assertEqual(unauth_rep.status_code, 401)


if __name__ == '__main__':
    unittest.main()
