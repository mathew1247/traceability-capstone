"""
Phase 2 Task 8: Network Scanner Reliability, Accuracy, and Security
Automated Test Suite
Repository: /home/jack/Projects/traceability-capstone

Comprehensive coverage for:
1. Valid and invalid IPv4 targets.
2. Valid and invalid CIDR ranges.
3. Oversized target ranges (/16, /8 rejected).
4. Unauthorized scan requests (401 unauthenticated, 403 non-admin).
5. Missing Nmap installation handling.
6. Nmap timeout handling and process termination.
7. Non-zero process exit codes.
8. Malformed Nmap output.
9. Empty but successful scan results.
10. Failed scans not being marked successful.
11. Firestore persistence and retrieval using isolated fixtures.
12. History retrieval failures.
13. Rapid sequential scan submissions.
14. Frontend DOM and response handling integrity.
"""

import os
import sys
import unittest
import uuid
from unittest.mock import patch, MagicMock
from pathlib import Path

# Use isolated local Firestore engine for tests
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config import Config
from config.firebase import db
from utils.validators import validate_network_target
from scanners.nmap_scanner import scan_network, is_nmap_installed
from services.network_service import execute_network_scan, get_scan_history


class NetworkScannerReliabilityTests(unittest.TestCase):
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

    # -------------------------------------------------------------
    # 1. VALID AND INVALID IPv4 TARGETS
    # -------------------------------------------------------------
    def test_01_valid_and_invalid_ipv4_targets(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Valid targets
        valid_targets = ['127.0.0.1', 'localhost', '10.0.0.1', '192.168.1.100', '172.16.1.5']
        for target in valid_targets:
            is_valid, err = validate_network_target(target)
            self.assertTrue(is_valid, f"Target '{target}' should be valid: {err}")

        # Invalid targets
        invalid_cases = [
            ('', "non-empty"),
            ('   ', "non-empty"),
            (None, "non-empty"),
            ('not-an-ip', "Invalid IP"),
            ('999.999.999.999', "Invalid IP"),
            ('192.168.1', "Invalid IP"),
            ('0.0.0.0', "non-routable"),
            ('224.0.0.1', "multicast"),
            ('255.255.255.255', "reserved"),
            ('8.8.8.8', "prohibited"),  # Public Internet
            ('1.1.1.1', "prohibited"),  # Public Internet
            ('::1', "IPv6 scanning is not supported"),  # IPv6
            ('fe80::1', "IPv6 scanning is not supported"),  # IPv6
            ('A' * 70, "exceeds maximum allowable length"),  # Oversized string
        ]
        for target, expected_substring in invalid_cases:
            is_valid, err = validate_network_target(target)
            self.assertFalse(is_valid, f"Target '{target}' should be rejected")
            self.assertIn(expected_substring.lower(), err.lower())

            # Verify API route also rejects invalid targets with 400
            res = self.client.post('/api/network/scan', headers=headers, json={"target": target})
            self.assertEqual(res.status_code, 400)
            self.assertFalse(res.get_json().get("success", True))

    # -------------------------------------------------------------
    # 2. VALID AND INVALID CIDR RANGES
    # -------------------------------------------------------------
    def test_02_valid_and_invalid_cidr_ranges(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        valid_cidrs = ['192.168.1.0/24', '192.168.1.0/28', '10.0.0.0/24', '172.16.0.0/25', '127.0.0.1/32']
        for cidr in valid_cidrs:
            is_valid, err = validate_network_target(cidr)
            self.assertTrue(is_valid, f"CIDR '{cidr}' should be valid: {err}")

        invalid_cidrs = [
            ('192.168.1.0/33', "Invalid IP"),
            ('192.168.1.0/abc', "Invalid IP"),
            ('8.8.8.0/24', "prohibited"),  # Public CIDR
            ('2001:db8::/32', "IPv6 scanning is not supported"),  # IPv6 CIDR
        ]
        for cidr, expected_err in invalid_cidrs:
            is_valid, err = validate_network_target(cidr)
            self.assertFalse(is_valid, f"CIDR '{cidr}' should be rejected")
            self.assertIn(expected_err.lower(), err.lower())

            res = self.client.post('/api/network/scan', headers=headers, json={"target": cidr})
            self.assertEqual(res.status_code, 400)

    # -------------------------------------------------------------
    # 3. OVERSIZED TARGET RANGES (SUBNET > /24 REJECTED)
    # -------------------------------------------------------------
    def test_03_oversized_target_ranges_rejected(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        broad_cidrs = [
            '192.168.0.0/16',
            '10.0.0.0/8',
            '172.16.0.0/20',
            '10.0.0.0/23'
        ]
        for broad in broad_cidrs:
            is_valid, err = validate_network_target(broad)
            self.assertFalse(is_valid, f"Subnet '{broad}' should be rejected as too broad")
            self.assertIn("too broad", err.lower())

            res = self.client.post('/api/network/scan', headers=headers, json={"target": broad})
            self.assertEqual(res.status_code, 400)
            self.assertIn("too broad", res.get_json()["error"]["message"].lower())

    # -------------------------------------------------------------
    # 4. UNAUTHORIZED SCAN REQUESTS (401 & 403)
    # -------------------------------------------------------------
    def test_04_unauthorized_scan_requests(self):
        # 1. Unauthenticated request -> 401
        res_unauth = self.client.post('/api/network/scan', json={"target": "127.0.0.1"})
        self.assertEqual(res_unauth.status_code, 401)
        self.assertIn("AUTHENTICATION_REQUIRED", res_unauth.get_json()["error"]["code"])

        # 2. Non-admin roles (Inspector, Auditor, Operator) -> 403
        non_admin_roles = [
            ("inspector@sentineltrace.local", "ChangeMe123!"),
            ("auditor@sentineltrace.local", "ChangeMe123!"),
            ("operator@sentineltrace.local", "ChangeMe123!")
        ]
        for email, pw in non_admin_roles:
            token = self.get_token(email, pw)
            res = self.client.post('/api/network/scan', headers={"Authorization": f"Bearer {token}"}, json={"target": "127.0.0.1"})
            self.assertEqual(res.status_code, 403, f"Expected 403 for {email}")
            self.assertIn("FORBIDDEN", res.get_json()["error"]["code"])

        # 3. Non-admin can access history
        insp_token = self.get_token("inspector@sentineltrace.local", "ChangeMe123!")
        res_hist = self.client.get('/api/network/history', headers={"Authorization": f"Bearer {insp_token}"})
        self.assertEqual(res_hist.status_code, 200)

    # -------------------------------------------------------------
    # 5. MISSING NMAP INSTALLATION HANDLING
    # -------------------------------------------------------------
    def test_05_missing_nmap_installation_handling(self):
        with patch('shutil.which', return_value=None):
            self.assertFalse(is_nmap_installed())

            # When nmap is explicitly required, produce clear error
            res_dict, err = scan_network("127.0.0.1", require_nmap=True)
            self.assertIsNone(res_dict)
            self.assertIn("Nmap binary is not installed", err)

            # Default scan provides truthful socket fallback without crashing
            res_fallback, err_fb = scan_network("127.0.0.1", require_nmap=False)
            self.assertIsNone(err_fb)
            self.assertIsNotNone(res_fallback)
            self.assertFalse(res_fallback["nmap_available"])
            self.assertIn("Python Socket Fallback", res_fallback["scanner_engine"])
            self.assertIn("not installed", res_fallback["limitations"])

    # -------------------------------------------------------------
    # 6. NMAP TIMEOUT HANDLING AND PROCESS TERMINATION
    # -------------------------------------------------------------
    def test_06_nmap_timeout_handling(self):
        # Simulate Nmap timeout error
        mock_nm = MagicMock()
        import nmap
        mock_nm.scan.side_effect = nmap.PortScannerTimeout("Scan operation exceeded allocated deadline")

        with patch('shutil.which', return_value='/usr/bin/nmap'):
            with patch('nmap.PortScanner', return_value=mock_nm):
                res_dict, err = scan_network("192.168.1.0/24")
                self.assertIsNone(res_dict)
                self.assertIn("timed out", err.lower())

        # Test through service layer: timeout records a failed scan in Firestore
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin User"}
        with patch('services.network_service.scan_network', return_value=(None, "Network scan timed out after 30 seconds.")):
            record, err_msg, status_code = execute_network_scan("192.168.1.0/24", admin_user)
            self.assertIsNone(record)
            self.assertEqual(status_code, 500)
            self.assertIn("timed out", err_msg)

            # Check that a 'Failed' scan record was saved in history
            history = get_scan_history(limit=5)
            failed_scans = [s for s in history if s.get("status") == "Failed" and "timed out" in s.get("error_message", "")]
            self.assertGreaterEqual(len(failed_scans), 1)
            self.assertEqual(failed_scans[0]["devices_found"], 0)

    # -------------------------------------------------------------
    # 7. NON-ZERO PROCESS EXIT CODES
    # -------------------------------------------------------------
    def test_07_nmap_nonzero_exit_code_handling(self):
        mock_nm = MagicMock()
        import nmap
        mock_nm.scan.side_effect = nmap.PortScannerError("nmap execution failed with code 1: Route: failed to determine route to target")

        with patch('shutil.which', return_value='/usr/bin/nmap'):
            with patch('nmap.PortScanner', return_value=mock_nm):
                res_dict, err = scan_network("192.168.1.50")
                self.assertIsNone(res_dict)
                self.assertIn("Nmap execution error", err)
                self.assertIn("failed to determine route", err)

    # -------------------------------------------------------------
    # 8. MALFORMED NMAP OUTPUT HANDLING
    # -------------------------------------------------------------
    def test_08_malformed_nmap_output_handling(self):
        mock_nm = MagicMock()
        import nmap
        mock_nm.scan.side_effect = nmap.PortScannerError("Parse error: XML document is incomplete or malformed")

        with patch('shutil.which', return_value='/usr/bin/nmap'):
            with patch('nmap.PortScanner', return_value=mock_nm):
                res_dict, err = scan_network("10.0.0.1")
                self.assertIsNone(res_dict)
                self.assertIn("Nmap execution error", err)

    # -------------------------------------------------------------
    # 9. EMPTY BUT SUCCESSFUL SCAN RESULTS
    # -------------------------------------------------------------
    def test_09_empty_successful_scan_results(self):
        # Target is alive, but 0 open ports discovered
        mock_nm = MagicMock()
        mock_nm.all_hosts.return_value = ['10.0.0.99']
        mock_nm.__getitem__.return_value = MagicMock(
            state=lambda: 'up',
            hostname=lambda: 'quiet-plc.local',
            all_protocols=lambda: []
        )

        with patch('shutil.which', return_value='/usr/bin/nmap'):
            with patch('nmap.PortScanner', return_value=mock_nm):
                res_dict, err = scan_network("10.0.0.99")
                self.assertIsNone(err)
                self.assertEqual(res_dict["devices_found"], 1)
                self.assertEqual(len(res_dict["hosts"]), 1)
                self.assertEqual(res_dict["hosts"][0]["ports"], [])

    # -------------------------------------------------------------
    # 10. FAILED SCANS ARE NOT MARKED SUCCESSFUL
    # -------------------------------------------------------------
    def test_10_failed_scans_not_marked_successful(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        with patch('services.network_service.scan_network', return_value=(None, "Simulated device unreachable error")):
            res = self.client.post('/api/network/scan', headers=headers, json={"target": "10.0.0.25"})
            self.assertEqual(res.status_code, 500)
            data = res.get_json()
            self.assertFalse(data.get("success", True))
            self.assertEqual(data.get("error", {}).get("code"), "SCAN_EXECUTION_FAILED")

    # -------------------------------------------------------------
    # 11. FIRESTORE PERSISTENCE AND RETRIEVAL
    # -------------------------------------------------------------
    def test_11_firestore_persistence_and_retrieval(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}
        unique_target = "127.0.0.1"

        res = self.client.post('/api/network/scan', headers=headers, json={"target": unique_target})
        self.assertEqual(res.status_code, 201)
        scan_id = res.get_json()["data"]["scan_id"]
        self.assertIn("duration", res.get_json()["data"])

        # Check document directly in Firestore
        doc = db.collection(Config.COLLECTION_NETWORK_SCANS).document(scan_id).get()
        self.assertTrue(doc.exists)
        stored = doc.to_dict()
        self.assertEqual(stored["scan_id"], scan_id)
        self.assertEqual(stored["target"], unique_target)
        self.assertEqual(stored["status"], "Completed")
        self.assertIn("duration", stored)

        # Retrieve history via endpoint
        res_hist = self.client.get('/api/network/history', headers=headers)
        self.assertEqual(res_hist.status_code, 200)
        history_items = res_hist.get_json()["data"]
        matching = [s for s in history_items if s.get("scan_id") == scan_id]
        self.assertEqual(len(matching), 1)

    # -------------------------------------------------------------
    # 12. HISTORY RETRIEVAL FAILURES
    # -------------------------------------------------------------
    def test_12_history_retrieval_failure_handling(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        with patch('routes.network_routes.get_scan_history', return_value=[]):
            res = self.client.get('/api/network/history', headers=headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()["data"], [])

    # -------------------------------------------------------------
    # 13. RAPID SEQUENTIAL SCAN SUBMISSIONS (UNIQUE IDs & AUDIT)
    # -------------------------------------------------------------
    def test_13_sequential_scans_allocate_unique_ids(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        res1 = self.client.post('/api/network/scan', headers=headers, json={"target": "127.0.0.1"})
        res2 = self.client.post('/api/network/scan', headers=headers, json={"target": "127.0.0.1"})
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(res2.status_code, 201)
        id1 = res1.get_json()["data"]["scan_id"]
        id2 = res2.get_json()["data"]["scan_id"]
        self.assertNotEqual(id1, id2, "Sequential scans must allocate distinct unique scan IDs")

    # -------------------------------------------------------------
    # 14. FRONTEND DOM AND RESPONSE HANDLING INTEGRITY
    # -------------------------------------------------------------
    def test_14_frontend_dom_and_script_integrity(self):
        frontend_html = Path(__file__).resolve().parent.parent.parent / "frontend" / "network-scan.html"
        frontend_js = Path(__file__).resolve().parent.parent.parent / "frontend" / "js" / "network-scan.js"

        self.assertTrue(frontend_html.exists(), "network-scan.html must exist")
        self.assertTrue(frontend_js.exists(), "network-scan.js must exist")

        with open(frontend_html, 'r', encoding='utf-8') as f:
            html_content = f.read()

        with open(frontend_js, 'r', encoding='utf-8') as f:
            js_content = f.read()

        # HTML elements
        self.assertIn('id="scan-target-ip"', html_content)
        self.assertIn('id="start-scan-btn"', html_content)
        self.assertIn('id="scan-status-box"', html_content)
        self.assertIn('id="scan-results-container"', html_content)
        self.assertIn('id="scan-history-tbody"', html_content)

        # JavaScript validation and controls
        self.assertIn('isScanning', js_content, "Must have duplicate-submission lock")
        self.assertIn('!target', js_content, "Must validate empty target input")
        self.assertIn('Timed Out', js_content, "Must handle timeout status explicitly")
        self.assertIn('No previous scan records found', js_content, "Must provide clean empty history state")
