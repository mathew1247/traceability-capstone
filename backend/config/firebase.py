import os
import json
import logging
from pathlib import Path
from config import Config

logger = logging.getLogger('sentinel-trace')

# Global database reference
db = None
_firebase_initialized = False

class LocalDocumentSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data.copy() if self._data else None

class LocalDocumentReference:
    def __init__(self, collection_ref, doc_id):
        self.collection_ref = collection_ref
        self.id = doc_id

    def get(self):
        data = self.collection_ref._store.get(self.id)
        return LocalDocumentSnapshot(self.id, data)

    def set(self, data, merge=False):
        if merge and self.id in self.collection_ref._store:
            existing = self.collection_ref._store[self.id] or {}
            existing.update(data)
            self.collection_ref._store[self.id] = existing
        else:
            self.collection_ref._store[self.id] = data.copy()
        self.collection_ref._persist()
        return True

    def update(self, data):
        if self.id not in self.collection_ref._store:
            raise Exception(f"Document {self.id} does not exist.")
        existing = self.collection_ref._store[self.id] or {}
        existing.update(data)
        self.collection_ref._store[self.id] = existing
        self.collection_ref._persist()
        return True

    def delete(self):
        if self.id in self.collection_ref._store:
            del self.collection_ref._store[self.id]
            self.collection_ref._persist()
        return True

class LocalCollectionReference:
    def __init__(self, db_instance, collection_name):
        self.db = db_instance
        self.name = collection_name
        if collection_name not in self.db._data:
            self.db._data[collection_name] = {}
        self._store = self.db._data[collection_name]
        self._filters = []
        self._limit_count = None
        self._order_field = None
        self._order_direction = 'ASCENDING'

    def _persist(self):
        self.db._save_to_disk()

    def document(self, doc_id=None):
        if not doc_id:
            import uuid
            doc_id = str(uuid.uuid4())
        return LocalDocumentReference(self, doc_id)

    def where(self, field, op, value):
        clone = LocalCollectionReference(self.db, self.name)
        clone._filters = list(self._filters) + [(field, op, value)]
        clone._limit_count = self._limit_count
        clone._order_field = self._order_field
        clone._order_direction = self._order_direction
        return clone

    def order_by(self, field, direction='ASCENDING'):
        clone = LocalCollectionReference(self.db, self.name)
        clone._filters = list(self._filters)
        clone._limit_count = self._limit_count
        clone._order_field = field
        clone._order_direction = direction
        return clone

    def limit(self, count):
        clone = LocalCollectionReference(self.db, self.name)
        clone._filters = list(self._filters)
        clone._limit_count = count
        clone._order_field = self._order_field
        clone._order_direction = self._order_direction
        return clone

    def stream(self):
        results = []
        for doc_id, data in self._store.items():
            if not data:
                continue
            matched = True
            for field, op, value in self._filters:
                doc_val = data.get(field)
                if op == '==' and doc_val != value:
                    matched = False
                    break
                elif op == '!=' and doc_val == value:
                    matched = False
                    break
                elif op == '>' and (doc_val is None or doc_val <= value):
                    matched = False
                    break
                elif op == '>=' and (doc_val is None or doc_val < value):
                    matched = False
                    break
                elif op == '<' and (doc_val is None or doc_val >= value):
                    matched = False
                    break
                elif op == '<=' and (doc_val is None or doc_val > value):
                    matched = False
                    break
                elif op == 'in' and (doc_val not in value):
                    matched = False
                    break
            if matched:
                results.append(LocalDocumentSnapshot(doc_id, data))

        if self._order_field:
            reverse = self._order_direction.upper() == 'DESCENDING'
            results.sort(
                key=lambda item: (item.to_dict().get(self._order_field) is not None, str(item.to_dict().get(self._order_field, ''))),
                reverse=reverse
            )

        if self._limit_count:
            results = results[:self._limit_count]

        return results

    def get(self):
        return self.stream()

class LocalFirestoreClient:
    """Mock/Fallback Firestore implementation that persists to local JSON for seamless development."""
    def __init__(self, persistence_file=None):
        self._persistence_file = persistence_file or Path(__file__).resolve().parent.parent / '.firestore_local.json'
        self._data = {}
        self._load_from_disk()

    def _load_from_disk(self):
        try:
            if Path(self._persistence_file).exists():
                with open(self._persistence_file, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load local firestore file: {e}")
            self._data = {}

        if not self._data:
            try:
                from werkzeug.security import generate_password_hash
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
                pwd_hash = generate_password_hash("password123")
                pwd_admin = generate_password_hash("ChangeMe123!")

                self._data = {
                    "users": {
                        "USR-ADMIN01": {
                            "user_id": "USR-ADMIN01",
                            "username": "Jack Mathew",
                            "email": "jack@sentineltrace.io",
                            "password_hash": pwd_hash,
                            "role": "Admin",
                            "status": "Active",
                            "created_at": now
                        },
                        "USR-ADMIN02": {
                            "user_id": "USR-ADMIN02",
                            "username": "Jack Mathew",
                            "email": "admin@sentineltrace.local",
                            "password_hash": pwd_admin,
                            "role": "Admin",
                            "status": "Active",
                            "created_at": now
                        },
                        "USR-INSPECT01": {
                            "user_id": "USR-INSPECT01",
                            "username": "Sarah Connor",
                            "email": "sarah.chen@sentineltrace.io",
                            "password_hash": pwd_hash,
                            "role": "Inspector",
                            "status": "Active",
                            "created_at": now
                        }
                    },
                    "suppliers": {
                        "SUP101": {
                            "supplier_id": "SUP101",
                            "supplier_name": "Apex Alloys Global Corp",
                            "contact": "+1 (555) 019-2831",
                            "email": "logistics@apexalloys.com",
                            "address": "450 Industrial Parkway, Sector 4, Austin, TX",
                            "status": "Active",
                            "rating": "4.9",
                            "created_at": now
                        }
                    },
                    "raw_materials": {
                        "RM301": {
                            "material_id": "RM301",
                            "material_name": "Aircraft Grade Stainless Steel 316L",
                            "supplier_id": "SUP101",
                            "quantity": 12500.0,
                            "unit": "kg",
                            "status": "Verified",
                            "created_at": now
                        }
                    },
                    "products": {
                        "PRD101": {
                            "product_id": "PRD101",
                            "product_name": "Aerospace Turbine Casing High-Temp",
                            "product_code": "TURB-A320-X",
                            "description": "High-precision heat-resistant alloy casing for industrial turbines.",
                            "status": "In Production",
                            "created_at": now
                        }
                    },
                    "production_batches": {
                        "BAT201": {
                            "batch_id": "BAT201",
                            "product_id": "PRD101",
                            "material_id": "RM301",
                            "quantity": 250,
                            "production_date": now[:10],
                            "status": "Completed",
                            "created_at": now
                        }
                    },
                    "compliance_records": {
                        "CMP401": {
                            "compliance_id": "CMP401",
                            "product_id": "PRD101",
                            "standard": "ISO 9001:2015",
                            "status": "Compliant",
                            "audited_by": "USR-ADMIN01",
                            "expiry_date": "2027-12-31",
                            "remarks": "Fully verified and certified.",
                            "created_at": now
                        }
                    },
                    "alerts": {},
                    "network_scans": {},
                    "activity_logs": {}
                }
            except Exception as seed_err:
                logger.warning(f"Failed initializing default fallback data: {seed_err}")
                self._data = {}

    def _save_to_disk(self):
        try:
            with open(self._persistence_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to persist local firestore: {e}")

    def collection(self, name):
        return LocalCollectionReference(self, name)


def init_firebase():
    """
    Initializes Firebase Admin SDK once at application start.
    Supports FIREBASE_SERVICE_ACCOUNT_JSON env var (for production cloud deployment e.g. Render),
    local serviceAccountKey.json file, or GOOGLE_APPLICATION_CREDENTIALS path.
    Otherwise gracefully falls back to persistent LocalFirestoreClient for development.
    """
    global db, _firebase_initialized

    if _firebase_initialized and db is not None:
        return db

    env_service_account_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    credentials_path = Config.FIREBASE_CREDENTIALS_PATH
    if not os.path.isabs(credentials_path):
        credentials_path = str(Path(__file__).resolve().parent.parent / credentials_path)

    gcp_env_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        # 1. Production environment variable JSON string
        if env_service_account_json and env_service_account_json.strip():
            logger.info("Initializing Firebase Admin SDK using FIREBASE_SERVICE_ACCOUNT_JSON environment variable.")
            try:
                cred_dict = json.loads(env_service_account_json)
                cred = credentials.Certificate(cred_dict)
                if not firebase_admin._apps:
                    firebase_admin.initialize_app(cred)
                db = firestore.client()
                _firebase_initialized = True
                logger.info("Successfully connected to Google Cloud Firestore via FIREBASE_SERVICE_ACCOUNT_JSON.")
                return db
            except Exception as parse_err:
                logger.error(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON environment variable: {parse_err}")

        # 2. Local serviceAccountKey.json file
        if os.path.exists(credentials_path):
            logger.info(f"Initializing Firebase with service account key file: {credentials_path}")
            cred = credentials.Certificate(credentials_path)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred, {
                    'projectId': Config.FIREBASE_PROJECT_ID
                } if Config.FIREBASE_PROJECT_ID else None)
            db = firestore.client()
            _firebase_initialized = True
            logger.info("Successfully connected to Google Cloud Firestore via local service account key file.")
            return db

        # 3. Standard GOOGLE_APPLICATION_CREDENTIALS path
        elif gcp_env_creds and os.path.exists(gcp_env_creds):
            logger.info(f"Initializing Firebase with GOOGLE_APPLICATION_CREDENTIALS path: {gcp_env_creds}")
            cred = credentials.Certificate(gcp_env_creds)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            _firebase_initialized = True
            logger.info("Successfully connected to Google Cloud Firestore.")
            return db

        else:
            logger.warning(
                f"Firebase service account key not found at '{credentials_path}'. "
                "Activating Local Firestore Emulator for development. "
                "For production deployment on Render, set the FIREBASE_SERVICE_ACCOUNT_JSON environment variable."
            )
            db = LocalFirestoreClient()
            _firebase_initialized = True
            return db

    except Exception as e:
        logger.warning(f"Cloud Firestore initialization exception ({e}). Falling back to Local Firestore Engine.")
        db = LocalFirestoreClient()
        _firebase_initialized = True
        return db


# Initialize immediately when module is imported
db = init_firebase()
