# Sentinel-Trace REST API Documentation

**System**: Intelligent Product Traceability, Compliance Monitoring & Network Security Management System  
**Base URL**: `http://127.0.0.1:5000/api`  
**Authentication Scheme**: JSON Web Token (`Authorization: Bearer <token>`)

---

## 1. System Health & Diagnostics

### `GET /api/health`
Verifies API operational status and database engine.
* **Auth**: None
* **Role**: Public
* **Response (200 OK)**:
```json
{
  "success": true,
  "status": "healthy",
  "service": "sentinel-trace-api",
  "database": "Cloud Firestore",
  "version": "1.0.0"
}
```

---

## 2. Authentication & Session Management

### `POST /api/auth/login`
Authenticates credentials and issues signed JWT token.
* **Auth**: None
* **Role**: Public
* **Request Body**:
```json
{
  "email": "admin@sentineltrace.local",
  "password": "ChangeMe123!"
}
```
* **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "user_id": "USR-ADMIN01",
      "username": "Jack Mathew",
      "email": "admin@sentineltrace.local",
      "role": "Admin",
      "status": "Active"
    }
  },
  "message": "Authentication successful."
}
```
* **Errors**: `401 Unauthorized` (Invalid credentials), `403 Forbidden` (Suspended account)

### `POST /api/auth/register`
Onboards a new user account.
* **Auth**: None
* **Role**: Public (Defaults to `Operator`; Admins can assign roles via `/api/users`)
* **Request Body**:
```json
{
  "username": "Jane Doe",
  "email": "jane@example.com",
  "password": "Password123!",
  "role": "Operator"
}
```
* **Response (201 Created)**: Returns created user object without password hash.
* **Errors**: `400 Bad Request` (Missing fields/invalid email), `409 Conflict` (Email already exists)

### `GET /api/auth/me`
Retrieves currently authenticated session profile.
* **Auth**: Bearer Token
* **Role**: All authenticated roles
* **Response (200 OK)**: Returns user profile dictionary.

---

## 3. User Administration (Admin Only)

| Method | Endpoint | Description | Permitted Roles |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/users` | List all users | `Admin` |
| `GET` | `/api/users/<user_id>` | Get single user details | `Admin` |
| `POST` | `/api/users` | Create user with explicit role | `Admin` |
| `PUT` | `/api/users/<user_id>` | Update user role, username, or password | `Admin` |
| `PUT` | `/api/users/<user_id>/status` | Set status (`Active`, `Inactive`, `Suspended`) | `Admin` |
| `DELETE` | `/api/users/<user_id>` | Permanently delete user | `Admin` |

---

## 4. Suppliers

| Method | Endpoint | Description | Permitted Roles |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/suppliers` | List all suppliers | `Admin`, `Inspector`, `Auditor` |
| `GET` | `/api/suppliers/<supplier_id>` | Get single supplier details | `Admin`, `Inspector`, `Auditor` |
| `POST` | `/api/suppliers` | Create supplier | `Admin`, `Inspector` |
| `PUT` | `/api/suppliers/<supplier_id>` | Update supplier profile | `Admin`, `Inspector` |
| `DELETE` | `/api/suppliers/<supplier_id>` | Delete supplier | `Admin` |

**POST /api/suppliers Example Request**:
```json
{
  "supplier_name": "Titanium Dynamics Inc",
  "contact": "Robert Sterling",
  "email": "r.sterling@titaniumdynamics.com",
  "address": "12 Aerospace Blvd, Seattle, WA",
  "status": "Active"
}
```

---

## 5. Raw Materials Inventory

| Method | Endpoint | Description | Permitted Roles |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/materials` | List raw materials | `Admin`, `Inspector`, `Auditor`, `Operator` |
| `GET` | `/api/materials/<material_id>` | Get single material | `Admin`, `Inspector`, `Auditor`, `Operator` |
| `POST` | `/api/materials` | Create material | `Admin`, `Inspector`, `Operator` |
| `PUT` | `/api/materials/<material_id>` | Update material | `Admin`, `Inspector`, `Operator` |
| `DELETE` | `/api/materials/<material_id>` | Delete material | `Admin`, `Inspector` |

**POST /api/materials Example Request**:
```json
{
  "material_name": "Aircraft Grade Stainless Steel 316L",
  "supplier_id": "SUP101",
  "quantity": 4500,
  "unit": "Kg"
}
```
*Note: Validates that `supplier_id` exists before creation.*

---

## 6. Products

| Method | Endpoint | Description | Permitted Roles |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/products` | List all products | `Admin`, `Inspector`, `Auditor`, `Operator` |
| `GET` | `/api/products/<product_id>` | Get product by ID | `Admin`, `Inspector`, `Auditor`, `Operator` |
| `POST` | `/api/products` | Create product (Unique `product_code`) | `Admin`, `Inspector`, `Operator` |
| `PUT` | `/api/products/<product_id>` | Update product | `Admin`, `Inspector`, `Operator` |
| `DELETE` | `/api/products/<product_id>` | Delete product | `Admin`, `Inspector` |

**POST /api/products Example Request**:
```json
{
  "product_name": "Aerospace Turbine Casing High-Temp",
  "product_code": "TURB-A320-X",
  "description": "High temperature resistant outer turbine stator shell.",
  "status": "Certified"
}
```

---

## 7. Production Batches

| Method | Endpoint | Description | Permitted Roles |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/batches` | List production batches | `Admin`, `Inspector`, `Auditor`, `Operator` |
| `GET` | `/api/batches/<batch_id>` | Get batch by ID | `Admin`, `Inspector`, `Auditor`, `Operator` |
| `POST` | `/api/batches` | Create batch (Links Product + Material) | `Admin`, `Inspector`, `Operator` |
| `PUT` | `/api/batches/<batch_id>` | Update batch status/qty | `Admin`, `Inspector`, `Operator` |
| `DELETE` | `/api/batches/<batch_id>` | Delete batch | `Admin`, `Inspector` |

**POST /api/batches Example Request**:
```json
{
  "product_id": "PRD101",
  "material_id": "RM301",
  "quantity": 120,
  "production_date": "2026-10-06",
  "status": "Completed"
}
```
*Note: Verifies that both `product_id` and `material_id` exist.*

---

## 8. Traceability Lineage Engine

### `GET /api/traceability/<identifier>`
Bidirectional multi-tier graph resolution.
* **Auth**: Bearer Token
* **Role**: `Admin`, `Inspector`, `Auditor`, `Operator`
* **Path Parameter**: `<identifier>` — accepts Product ID (`PRD...`), Batch ID (`BAT...`), Material ID (`RM...`), or Supplier ID (`SUP...`).
* **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "query_id": "BAT201",
    "matched_entity_type": "ProductionBatch",
    "chain_intact": true,
    "traceability": {
      "supplier": {
        "supplier_id": "SUP101",
        "supplier_name": "Apex Alloys Global Corp",
        "email": "elena@apexalloys.com"
      },
      "material": {
        "material_id": "RM301",
        "material_name": "Aircraft Grade Stainless Steel 316L",
        "quantity": 4500,
        "unit": "Kg"
      },
      "batch": {
        "batch_id": "BAT201",
        "product_id": "PRD101",
        "quantity": 120,
        "status": "Completed"
      },
      "product": {
        "product_id": "PRD101",
        "product_name": "Aerospace Turbine Casing High-Temp",
        "product_code": "TURB-A320-X",
        "status": "Certified"
      },
      "compliance": [
        {
          "compliance_id": "CMP401",
          "standard": "ISO 9001:2015",
          "status": "Compliant",
          "expiry_date": "2027-10-06"
        }
      ]
    }
  }
}
```

---

## 9. Regulatory Compliance & Auditing

| Method | Endpoint | Description | Permitted Roles |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/compliance` | List compliance records | `Admin`, `Inspector`, `Auditor` |
| `GET` | `/api/compliance/<compliance_id>` | Get record by ID | `Admin`, `Inspector`, `Auditor` |
| `POST` | `/api/compliance` | Create compliance audit | `Admin`, `Inspector` |
| `PUT` | `/api/compliance/<compliance_id>` | Update compliance record | `Admin`, `Inspector` |
| `DELETE` | `/api/compliance/<compliance_id>` | Delete record | `Admin` |

*Note: Automatically creates Warning alerts if certification expires within 30 days, or Critical alerts if expired.*

---

## 10. Network Security Scanner & Monitor

### `POST /api/network/scan`
Executes backend Nmap discovery scan against authorized scope.
* **Auth**: Bearer Token
* **Role**: `Admin`
* **Request Body**:
```json
{
  "target": "192.168.1.0/24"
}
```
* **Security Enforcement**: Rejects non-private public Internet targets (RFC 1918 enforcement). Automatically detects **previously unseen hosts** compared to baseline scans and flags exposed critical/industrial ports (502 Modbus, 102 S7, 445 SMB).
* **Response (201 Created)**: Returns structured host list, ports, and detection findings.

### `GET /api/network/history`
Returns chronological list of past network scan records.
* **Role**: `Admin`, `Inspector`, `Auditor`

### `GET /api/network/security`
Returns real-time aggregated security monitor dashboard telemetry.
* **Role**: `Admin`, `Inspector`, `Auditor`
* **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "network_status": "Secure",
    "active_devices": 14,
    "suspicious_hosts": 0,
    "open_critical_ports": 1,
    "threat_level": "Low",
    "recent_events": [...]
  }
}
```

---

## 11. Alerts Management

| Method | Endpoint | Description | Permitted Roles |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/alerts` | List alerts (supports `?status=` and `?severity=`) | All roles |
| `GET` | `/api/alerts/<alert_id>` | Get alert details | All roles |
| `PUT` | `/api/alerts/<alert_id>` | Update alert action (`Acknowledge`, `Resolve`, `Dismiss`) | `Admin`, `Inspector` |

**PUT /api/alerts/<alert_id> Request**:
```json
{
  "action": "Acknowledge"
}
```

---

## 12. Executive Dashboard & Analytics Dossiers

### `GET /api/dashboard/stats`
Aggregates live KPIs for the main dashboard view.
* **Auth**: Bearer Token
* **Role**: All authenticated roles
* **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "total_products": 3,
    "total_batches": 3,
    "total_materials": 3,
    "total_suppliers": 3,
    "compliance_rate": 75.0,
    "active_alerts": 2,
    "network_status": "Secure",
    "devices_found": 14,
    "recent_activity": [...]
  }
}
```

### `GET /api/reports/summary`
Aggregates comprehensive analytical breakdown across Production, Compliance, Network, and Alerts.
* **Role**: `Admin`, `Inspector`, `Auditor`

### `GET /api/logs`
Retrieves immutable audit trail of all system mutations and authentication events.
* **Role**: `Admin`, `Auditor`
* **Query Filters**: `?user=`, `?action=`, `?resource=`, `?limit=100`

---

## 13. Standard Error Formats

All error responses adhere to the unified JSON schema:
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable explanation of the issue."
  }
}
```

Common status codes:
* `400`: `VALIDATION_ERROR`, `BAD_REQUEST`
* `401`: `AUTHENTICATION_REQUIRED`, `TOKEN_EXPIRED`, `INVALID_TOKEN`
* `403`: `FORBIDDEN_INSUFFICIENT_ROLE`, `ACCOUNT_DISABLED`
* `404`: `RESOURCE_NOT_FOUND`
* `409`: `RESOURCE_CONFLICT`
* `500`: `INTERNAL_SERVER_ERROR`
