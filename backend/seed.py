#!/usr/bin/env python3
"""
Sentinel-Trace Seed Script
Populates initial development and demonstration data into Firestore.

WARNING:
This script populates sample credentials (ChangeMe123!).
These must be changed immediately prior to production deployment!
"""

import sys
import os
from pathlib import Path

# Ensure backend directory is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from config.firebase import init_firebase, db
from services.auth_service import hash_password
from datetime import datetime, timezone, timedelta

def seed_database():
    print("=" * 60)
    print(" SENTINEL-TRACE: INITIALIZING DATABASE SEED PROCESS")
    print("=" * 60)
    
    init_firebase()

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    future_iso = (now + timedelta(days=365)).strftime('%Y-%m-%d')
    soon_iso = (now + timedelta(days=15)).strftime('%Y-%m-%d')
    expired_iso = (now - timedelta(days=10)).strftime('%Y-%m-%d')

    # 1. Seed Users
    print("\n[1/7] Seeding Users with Role-Based Access Control...")
    users = [
        {
            "user_id": "USR-ADMIN01",
            "username": "Jack Mathew",
            "email": "admin@sentineltrace.local",
            "password_hash": hash_password("ChangeMe123!"),
            "role": "Admin",
            "status": "Active",
            "created_at": now_iso
        },
        {
            "user_id": "USR-INSPECT01",
            "username": "Sarah Connor",
            "email": "inspector@sentineltrace.local",
            "password_hash": hash_password("ChangeMe123!"),
            "role": "Inspector",
            "status": "Active",
            "created_at": now_iso
        },
        {
            "user_id": "USR-AUDIT01",
            "username": "David Chen",
            "email": "auditor@sentineltrace.local",
            "password_hash": hash_password("ChangeMe123!"),
            "role": "Auditor",
            "status": "Active",
            "created_at": now_iso
        },
        {
            "user_id": "USR-OPERATOR01",
            "username": "Marcus Vance",
            "email": "operator@sentineltrace.local",
            "password_hash": hash_password("ChangeMe123!"),
            "role": "Operator",
            "status": "Active",
            "created_at": now_iso
        }
    ]

    for u in users:
        db.collection(Config.COLLECTION_USERS).document(u['user_id']).set(u)
        print(f"  [+] User created: {u['email']} [{u['role']}]")

    # 2. Seed Suppliers
    print("\n[2/7] Seeding Certified Industrial Suppliers...")
    suppliers = [
        {
            "supplier_id": "SUP101",
            "supplier_name": "Apex Alloys Global Corp",
            "contact": "Elena Rostova",
            "email": "elena@apexalloys.com",
            "address": "400 Industrial Way, Pittsburgh, PA",
            "status": "Active",
            "created_at": now_iso
        },
        {
            "supplier_id": "SUP102",
            "supplier_name": "Titanium Dynamics Inc",
            "contact": "Robert Sterling",
            "email": "r.sterling@titaniumdynamics.com",
            "address": "12 Aerospace Blvd, Seattle, WA",
            "status": "Active",
            "created_at": now_iso
        },
        {
            "supplier_id": "SUP103",
            "supplier_name": "CyberCore Semiconductor Fab",
            "contact": "Kenji Sato",
            "email": "ksato@cybercore-semi.jp",
            "address": "7 Tech Park, Hsinchu Science Park",
            "status": "Active",
            "created_at": now_iso
        }
    ]

    for s in suppliers:
        db.collection(Config.COLLECTION_SUPPLIERS).document(s['supplier_id']).set(s)
        print(f"  [+] Supplier created: {s['supplier_id']} - {s['supplier_name']}")

    # 3. Seed Raw Materials
    print("\n[3/7] Seeding Raw Materials Inventory...")
    materials = [
        {
            "material_id": "RM301",
            "material_name": "Aircraft Grade Stainless Steel 316L",
            "supplier_id": "SUP101",
            "quantity": 4500.0,
            "unit": "Kg",
            "created_at": now_iso
        },
        {
            "material_id": "RM302",
            "material_name": "Medical Grade Titanium Ingot Ti-6Al-4V",
            "supplier_id": "SUP102",
            "quantity": 1250.0,
            "unit": "Kg",
            "created_at": now_iso
        },
        {
            "material_id": "RM303",
            "material_name": "Hardware Crypto Microcontroller Cortex-M4",
            "supplier_id": "SUP103",
            "quantity": 8000.0,
            "unit": "Units",
            "created_at": now_iso
        }
    ]

    for m in materials:
        db.collection(Config.COLLECTION_RAW_MATERIALS).document(m['material_id']).set(m)
        print(f"  [+] Material created: {m['material_id']} - {m['material_name']} (Supplier: {m['supplier_id']})")

    # 4. Seed Products
    print("\n[4/7] Seeding Product Catalog...")
    products = [
        {
            "product_id": "PRD101",
            "product_name": "Aerospace Turbine Casing High-Temp",
            "product_code": "TURB-A320-X",
            "description": "High temperature resistant outer turbine stator shell for commercial aircraft engine assemblies.",
            "status": "Certified",
            "created_at": now_iso
        },
        {
            "product_id": "PRD102",
            "product_name": "Sterile Medical Infusion Manifold",
            "product_code": "MED-INF-99",
            "description": "Precision biomedical fluid manifold valve array for ICU multi-line chemotherapy delivery.",
            "status": "In Production",
            "created_at": now_iso
        },
        {
            "product_id": "PRD103",
            "product_name": "Cryptographic OT Network Edge Sentinel",
            "product_code": "CYBER-EDGE-01",
            "description": "Industrial IoT DIN-rail hardware cryptographic gateway with hardware root-of-trust.",
            "status": "Certified",
            "created_at": now_iso
        }
    ]

    for p in products:
        db.collection(Config.COLLECTION_PRODUCTS).document(p['product_id']).set(p)
        print(f"  [+] Product created: {p['product_id']} - {p['product_name']} [{p['product_code']}]")

    # 5. Seed Production Batches
    print("\n[5/7] Seeding Production Batches (Traceability Linking)...")
    batches = [
        {
            "batch_id": "BAT201",
            "product_id": "PRD101",
            "material_id": "RM301",
            "quantity": 120,
            "production_date": now.strftime('%Y-%m-%d'),
            "status": "Completed",
            "created_at": now_iso
        },
        {
            "batch_id": "BAT202",
            "product_id": "PRD102",
            "material_id": "RM302",
            "quantity": 450,
            "production_date": now.strftime('%Y-%m-%d'),
            "status": "In QA Inspection",
            "created_at": now_iso
        },
        {
            "batch_id": "BAT203",
            "product_id": "PRD103",
            "material_id": "RM303",
            "quantity": 1000,
            "production_date": now.strftime('%Y-%m-%d'),
            "status": "Passed",
            "created_at": now_iso
        }
    ]

    for b in batches:
        db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(b['batch_id']).set(b)
        print(f"  [+] Batch created: {b['batch_id']} (Product: {b['product_id']} linked to Material: {b['material_id']})")

    # 6. Seed Compliance Records
    print("\n[6/7] Seeding Compliance Certifications & Audit Dossiers...")
    compliance_records = [
        {
            "compliance_id": "CMP401",
            "product_id": "PRD101",
            "standard": "ISO 9001:2015",
            "status": "Compliant",
            "remarks": "Metallurgical stress and tensile tolerance verification certified without non-conformances.",
            "audited_by": "USR-INSPECT01",
            "expiry_date": future_iso,
            "created_at": now_iso
        },
        {
            "compliance_id": "CMP402",
            "product_id": "PRD101",
            "standard": "RoHS",
            "status": "Compliant",
            "remarks": "Hazardous material screening confirmed zero restricted lead/cadmium compounds.",
            "audited_by": "USR-INSPECT01",
            "expiry_date": future_iso,
            "created_at": now_iso
        },
        {
            "compliance_id": "CMP403",
            "product_id": "PRD102",
            "standard": "GMP",
            "status": "Compliant",
            "remarks": "Cleanroom sterility class 10,000 biological spore assay clean.",
            "audited_by": "USR-AUDIT01",
            "expiry_date": future_iso,
            "created_at": now_iso
        },
        {
            "compliance_id": "CMP404",
            "product_id": "PRD103",
            "standard": "ISO 9001:2015",
            "status": "Review Required",
            "remarks": "Annual re-certification audit window opened. Verification pending cryptographic test.",
            "audited_by": "USR-AUDIT01",
            "expiry_date": soon_iso,
            "created_at": now_iso
        }
    ]

    for c in compliance_records:
        db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).document(c['compliance_id']).set(c)
        print(f"  [+] Compliance created: {c['compliance_id']} - {c['standard']} ({c['status']})")

    # 7. Seed Operational & Security Alerts
    print("\n[7/7] Seeding Security & System Alerts...")
    alerts = [
        {
            "alert_id": "ALT-101",
            "severity": "Warning",
            "source": "Compliance",
            "message": f"Compliance certification for ISO 9001:2015 on Product PRD103 expires in 15 days.",
            "resource_id": "CMP404",
            "status": "Active",
            "created_at": now_iso,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "resolved_at": None
        },
        {
            "alert_id": "ALT-102",
            "severity": "Notice",
            "source": "Nmap Scanner",
            "message": "Industrial OT/IT port 502 (modbus-tcp) observed on SCADA node 192.168.1.10.",
            "resource_id": "SCAN-BASE01",
            "status": "Active",
            "created_at": now_iso,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "resolved_at": None
        }
    ]

    for a in alerts:
        db.collection(Config.COLLECTION_ALERTS).document(a['alert_id']).set(a)
        print(f"  [+] Alert created: {a['alert_id']} [{a['severity']}] - {a['message']}")

    # Seed baseline network scan
    baseline_scan = {
        "scan_id": "SCAN-BASE01",
        "target": "192.168.1.0/24",
        "devices_found": 14,
        "open_ports": [
            {"host": "192.168.1.1", "port": 80, "protocol": "tcp", "service": "http", "state": "open", "is_critical": False},
            {"host": "192.168.1.10", "port": 502, "protocol": "tcp", "service": "modbus-tcp", "state": "open", "is_critical": True}
        ],
        "status": "Completed",
        "created_by": "USR-ADMIN01",
        "scan_date": now_iso,
        "hosts": [
            {"ip": "192.168.1.1", "status": "up", "hostname": "gateway.local", "ports": [{"port": 80, "service": "http", "protocol": "tcp", "state": "open"}]},
            {"ip": "192.168.1.10", "status": "up", "hostname": "plc-node-01.ot", "ports": [{"port": 502, "service": "modbus-tcp", "protocol": "tcp", "state": "open"}]}
        ],
        "scanner_engine": "Nmap Native Engine"
    }
    db.collection(Config.COLLECTION_NETWORK_SCANS).document(baseline_scan['scan_id']).set(baseline_scan)

    # Seed initial activity log
    init_log = {
        "log_id": "LOG-INIT01",
        "user_id": "USR-ADMIN01",
        "username": "Jack Mathew",
        "action": "CREATE",
        "resource": "System",
        "resource_id": "INITIAL_SEED",
        "ip_address": "127.0.0.1",
        "timestamp": now_iso,
        "details": "Database seeded with demonstration factory topology and users."
    }
    db.collection(Config.COLLECTION_ACTIVITY_LOGS).document(init_log['log_id']).set(init_log)

    print("\n" + "=" * 60)
    print(" [+] SEED PROCESS COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print("\nDEFAULT CREDENTIALS:")
    print("------------------------------------------------------------")
    print("  Administrator: admin@sentineltrace.local     / ChangeMe123!")
    print("  Inspector:     inspector@sentineltrace.local / ChangeMe123!")
    print("  Auditor:       auditor@sentineltrace.local   / ChangeMe123!")
    print("  Operator:      operator@sentineltrace.local  / ChangeMe123!")
    print("------------------------------------------------------------")
    print("WARNING: Default passwords MUST be changed prior to production deployment!")
    print("=" * 60 + "\n")

if __name__ == '__main__':
    seed_database()
