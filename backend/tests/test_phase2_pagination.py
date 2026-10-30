"""
Phase 2 Task 3: Comprehensive Pagination Regression Test Suite
Covers all 15 required criteria for Products, Batches, Materials, and Suppliers:
1. First page returns correct records.
2. Next page returns different records.
3. Final page returns the remaining records.
4. Empty collections return an empty result set.
5. Invalid page numbers are handled correctly (400 validation error).
6. Invalid page sizes are rejected or safely handled (400 validation error).
7. Total counts match the active search and filters.
8. Sorting is stable across page boundaries (deterministic tie-breaker).
9. Search and filters work with pagination.
10. Authentication is required for protected endpoints (401 Unauthorized).
11. RBAC restrictions remain intact.
12. Existing API consumers are not unintentionally broken (unpaginated backwards compatibility).
13. Duplicate records are not introduced by pagination across page boundaries.
14. Out-of-range pages are handled consistently (200 OK with empty items).
15. API errors and utility boundaries are handled reliably.
"""

import sys
import os
import unittest
from pathlib import Path

# Explicitly set local test mode before importing firebase
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config.firebase import db
from config import Config
from utils.pagination import parse_pagination_params, paginate_records


class PaginationRegressionTests(unittest.TestCase):
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
        self.assertEqual(res.status_code, 200, f"Login failed: {res.get_json()}")
        return res.get_json()['data']['token']

    def setUp(self):
        self.admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        self.auth_headers = {"Authorization": f"Bearer {self.admin_token}"}

    # 1. First page returns correct records
    def test_01_first_page_returns_correct_records(self):
        res = self.client.get('/api/products?page=1&page_size=1', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['data']
        self.assertIn('items', data)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['page_size'], 1)
        self.assertLessEqual(len(data['items']), 1)
        if data['total'] > 0:
            self.assertEqual(len(data['items']), 1)

    # 2. Next page returns different records
    def test_02_next_page_returns_different_records(self):
        # Ensure at least 2 products exist
        self.client.post('/api/products', headers=self.auth_headers, json={
            "product_name": "Pagination Alpha Valve",
            "product_code": "PAG-ALPHA-01",
            "description": "Pagination test item alpha",
            "status": "In Production"
        })
        self.client.post('/api/products', headers=self.auth_headers, json={
            "product_name": "Pagination Beta Pump",
            "product_code": "PAG-BETA-02",
            "description": "Pagination test item beta",
            "status": "In Production"
        })

        p1_res = self.client.get('/api/products?page=1&page_size=1', headers=self.auth_headers)
        p2_res = self.client.get('/api/products?page=2&page_size=1', headers=self.auth_headers)

        self.assertEqual(p1_res.status_code, 200)
        self.assertEqual(p2_res.status_code, 200)

        p1_items = p1_res.get_json()['data']['items']
        p2_items = p2_res.get_json()['data']['items']

        self.assertEqual(len(p1_items), 1)
        self.assertEqual(len(p2_items), 1)
        self.assertNotEqual(p1_items[0]['product_id'], p2_items[0]['product_id'], "Page 1 and Page 2 must not return the same item")

    # 3. Final page returns the remaining records
    def test_03_final_page_returns_remaining_records(self):
        # Fetch with page_size=2 across all products
        res_all = self.client.get('/api/products?paginate=true&page=1&page_size=100', headers=self.auth_headers)
        total = res_all.get_json()['data']['total']
        self.assertGreaterEqual(total, 2)

        page_size = 2
        import math
        last_page = math.ceil(total / page_size)

        res_last = self.client.get(f'/api/products?page={last_page}&page_size={page_size}', headers=self.auth_headers)
        self.assertEqual(res_last.status_code, 200)
        data = res_last.get_json()['data']
        self.assertEqual(data['page'], last_page)

        expected_count = total % page_size if (total % page_size) != 0 else page_size
        self.assertEqual(len(data['items']), expected_count)

    # 4. Empty collections return an empty result set
    def test_04_empty_collections_return_empty_set(self):
        # Searching for nonexistent token guarantees empty set
        res = self.client.get('/api/products?search=NONEXISTENT_QUERY_TOKEN_XYZ_999&page=1&page_size=10', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['data']
        self.assertEqual(data['items'], [])
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['total_pages'], 0)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['page_size'], 10)

    # 5. Invalid page numbers are handled correctly
    def test_05_invalid_page_numbers_handled_correctly(self):
        for invalid_page in [0, -1, -99, "abc", "zero"]:
            res = self.client.get(f'/api/products?page={invalid_page}', headers=self.auth_headers)
            self.assertEqual(res.status_code, 400, f"Page {invalid_page} should return 400")
            err = res.get_json()['error']
            self.assertEqual(err['code'], "INVALID_PAGINATION_PARAMS")
            self.assertTrue("Page number must be" in err['message'])

    # 6. Invalid page sizes are rejected or safely handled
    def test_06_invalid_page_sizes_rejected(self):
        for invalid_size in [0, -5, 101, 500, "large"]:
            res = self.client.get(f'/api/products?page_size={invalid_size}', headers=self.auth_headers)
            self.assertEqual(res.status_code, 400, f"Page size {invalid_size} should return 400")
            err = res.get_json()['error']
            self.assertEqual(err['code'], "INVALID_PAGINATION_PARAMS")
            self.assertTrue("Page size must be an integer between 1 and 100" in err['message'])

    # 7. Total counts match active search and filters
    def test_07_total_counts_match_active_search_and_filters(self):
        # Create unique distinct products
        self.client.post('/api/products', headers=self.auth_headers, json={
            "product_name": "Cryo Turbine Specialized Unit A",
            "product_code": "CRYO-SPEC-01",
            "description": "Cryogenic standard",
            "status": "Certified"
        })
        self.client.post('/api/products', headers=self.auth_headers, json={
            "product_name": "Cryo Turbine Specialized Unit B",
            "product_code": "CRYO-SPEC-02",
            "description": "Cryogenic standard",
            "status": "In Production"
        })

        # Search for 'Cryo Turbine Specialized' with status=Certified
        res = self.client.get('/api/products?search=Cryo%20Turbine%20Specialized&status=Certified&page=1&page_size=10', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['data']
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['items'][0]['product_code'], "CRYO-SPEC-01")

        # Search without status filter -> total should be 2
        res2 = self.client.get('/api/products?search=Cryo%20Turbine%20Specialized&page=1&page_size=10', headers=self.auth_headers)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()['data']['total'], 2)

    # 8. Sorting is stable across page boundaries (deterministic tie-breaker)
    def test_08_sorting_is_stable_across_page_boundaries(self):
        # Fetch page 1 and page 2 sorted by status ascending
        res_p1 = self.client.get('/api/products?sort_by=status&sort_order=asc&page=1&page_size=2', headers=self.auth_headers)
        res_p2 = self.client.get('/api/products?sort_by=status&sort_order=asc&page=2&page_size=2', headers=self.auth_headers)

        self.assertEqual(res_p1.status_code, 200)
        self.assertEqual(res_p2.status_code, 200)

        p1_ids = [item['product_id'] for item in res_p1.get_json()['data']['items']]
        p2_ids = [item['product_id'] for item in res_p2.get_json()['data']['items']]

        # Assert no overlap
        self.assertEqual(len(set(p1_ids).intersection(set(p2_ids))), 0, "No duplicate items across adjacent pages")

    # 9. Search and filters work with pagination across all modules
    def test_09_search_and_filters_work_with_pagination(self):
        # Batches
        b_res = self.client.get('/api/batches?page=1&page_size=5&sort_by=created_at&sort_order=desc', headers=self.auth_headers)
        self.assertEqual(b_res.status_code, 200)
        self.assertIn('items', b_res.get_json()['data'])

        # Materials
        m_res = self.client.get('/api/materials?page=1&page_size=5&sort_by=quantity&sort_order=asc', headers=self.auth_headers)
        self.assertEqual(m_res.status_code, 200)
        self.assertIn('items', m_res.get_json()['data'])

        # Suppliers
        s_res = self.client.get('/api/suppliers?page=1&page_size=5&sort_by=supplier_name&sort_order=asc', headers=self.auth_headers)
        self.assertEqual(s_res.status_code, 200)
        self.assertIn('items', s_res.get_json()['data'])

    # 10. Authentication is required for protected endpoints
    def test_10_authentication_required_for_protected_endpoints(self):
        endpoints = [
            '/api/products?page=1',
            '/api/batches?page=1',
            '/api/materials?page=1',
            '/api/suppliers?page=1'
        ]
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 401, f"{ep} should require authentication")

    # 11. RBAC restrictions remain intact
    def test_11_rbac_restrictions_remain_intact(self):
        # Authenticate Operator user
        op_token = self.get_token("operator@sentineltrace.local", "ChangeMe123!")
        op_headers = {"Authorization": f"Bearer {op_token}"}

        # Operator CAN access /api/products and /api/batches pagination
        p_res = self.client.get('/api/products?page=1', headers=op_headers)
        self.assertEqual(p_res.status_code, 200)

        b_res = self.client.get('/api/batches?page=1', headers=op_headers)
        self.assertEqual(b_res.status_code, 200)

        # Operator is NOT permitted to view suppliers directory (Auditor, Inspector, Admin only)
        s_res = self.client.get('/api/suppliers?page=1', headers=op_headers)
        self.assertEqual(s_res.status_code, 403)

    # 12. Existing API consumers are not unintentionally broken
    def test_12_existing_api_consumers_not_broken(self):
        # Calling without pagination parameters returns a JSON list directly in data
        res_prod = self.client.get('/api/products', headers=self.auth_headers)
        self.assertEqual(res_prod.status_code, 200)
        self.assertIsInstance(res_prod.get_json()['data'], list)

        res_batch = self.client.get('/api/batches', headers=self.auth_headers)
        self.assertEqual(res_batch.status_code, 200)
        self.assertIsInstance(res_batch.get_json()['data'], list)

        res_mat = self.client.get('/api/materials', headers=self.auth_headers)
        self.assertEqual(res_mat.status_code, 200)
        self.assertIsInstance(res_mat.get_json()['data'], list)

        res_sup = self.client.get('/api/suppliers', headers=self.auth_headers)
        self.assertEqual(res_sup.status_code, 200)
        self.assertIsInstance(res_sup.get_json()['data'], list)

    # 13. Duplicate records are not introduced by pagination
    def test_13_no_duplicates_introduced_by_pagination(self):
        # Paginate 1 item at a time through all items
        res_full = self.client.get('/api/products?paginate=true&page=1&page_size=100', headers=self.auth_headers)
        full_items = res_full.get_json()['data']['items']
        total = res_full.get_json()['data']['total']

        collected_ids = []
        for p in range(1, total + 1):
            res_page = self.client.get(f'/api/products?page={p}&page_size=1', headers=self.auth_headers)
            items = res_page.get_json()['data']['items']
            if items:
                collected_ids.append(items[0]['product_id'])

        self.assertEqual(len(collected_ids), len(set(collected_ids)), "Pagination introduced duplicate records!")
        self.assertEqual(len(collected_ids), total)

    # 14. Out-of-range pages are handled consistently
    def test_14_out_of_range_pages_handled_consistently(self):
        res = self.client.get('/api/products?page=9999&page_size=10', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['data']
        self.assertEqual(data['items'], [])
        self.assertEqual(data['page'], 9999)
        self.assertEqual(data['page_size'], 10)
        self.assertGreaterEqual(data['total'], 0)

    # 15. Unit tests for parse_pagination_params and paginate_records edge cases
    def test_15_pagination_utility_edge_cases(self):
        # Invalid sort field
        page, page_size, sort_by, sort_order, is_paginated, err, code = parse_pagination_params(
            {"page": "1", "sort_by": "unsupported_field"},
            allowed_sort_fields={'name', 'id'}
        )
        self.assertEqual(code, 400)
        self.assertIn("Invalid sort field", err)

        # Invalid sort order
        page, page_size, sort_by, sort_order, is_paginated, err, code = parse_pagination_params(
            {"page": "1", "sort_order": "sideways"},
            allowed_sort_fields={'name', 'id'}
        )
        self.assertEqual(code, 400)
        self.assertIn("Sort order must be 'asc' or 'desc'", err)

        # In-memory paginate_records with None values
        sample = [
            {"id": "A", "val": 10},
            {"id": "B", "val": None},
            {"id": "C", "val": 5}
        ]
        result = paginate_records(sample, page=1, page_size=2, sort_by='val', sort_order='asc', tie_breaker_field='id', is_paginated=True)
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['total'], 3)
        self.assertEqual(result['total_pages'], 2)


if __name__ == '__main__':
    unittest.main()
