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

    def get(self, transaction=None):
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

    def collections(self):
        return [LocalCollectionReference(self, name) for name in self._data.keys()]

    def transaction(self):
        return LocalTransaction(self)


class LocalTransaction:
    """Mock transaction implementation for local testing."""
    def __init__(self, db_instance):
        self.db = db_instance
        self._writes = []

    def get(self, doc_ref):
        return doc_ref.get(transaction=self)

    def set(self, doc_ref, data, merge=False):
        self._writes.append(('set', doc_ref, data, merge))

    def update(self, doc_ref, data):
        self._writes.append(('update', doc_ref, data))

    def delete(self, doc_ref):
        self._writes.append(('delete', doc_ref))

    def commit(self):
        for op in self._writes:
            if op[0] == 'set':
                op[1].set(op[2], merge=op[3])
            elif op[0] == 'update':
                op[1].update(op[2])
            elif op[0] == 'delete':
                op[1].delete()
        self._writes.clear()


def resolve_credentials_path(path_str):
    """
    Safely resolves a credential file path without hardcoding local filesystem paths.
    Supports absolute paths (such as Render Secret File '/etc/secrets/serviceAccountKey.json')
    as well as relative paths resolved against current working directory, backend directory,
    and repository root.
    """
    if not path_str:
        return None
    p = Path(path_str)
    if p.is_absolute() and p.is_file():
        return str(p)

    backend_dir = Path(__file__).resolve().parent.parent
    repo_root = backend_dir.parent

    candidates = [
        Path.cwd() / path_str,
        backend_dir / path_str,
        repo_root / path_str,
    ]
    if path_str.startswith('backend/'):
        candidates.append(backend_dir / path_str[len('backend/'):])
    else:
        candidates.append(repo_root / 'backend' / path_str)

    # Render Secret Files mounted at /etc/secrets/<filename>
    filename = Path(path_str).name
    candidates.append(Path('/etc/secrets') / filename)
    candidates.append(Path('/etc/secrets/serviceAccountKey.json'))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def init_firebase():
    """
    Initializes Firebase Admin SDK once at application start using configured credentials.
    Supports:
    1. FIREBASE_SERVICE_ACCOUNT_JSON env var (JSON string for cloud deployment)
    2. GOOGLE_APPLICATION_CREDENTIALS env var (path to Render Secret File or service account file)
    3. FIREBASE_CREDENTIALS_PATH env var / Config setting
    4. Render Secret File mounted at /etc/secrets/serviceAccountKey.json
    5. Local 'serviceAccountKey.json' file

    Enforces:
    - Verifies credentials match configured project ID (Config.FIREBASE_PROJECT_ID).
    - Prevents multiple redundant initializations.
    - Never prints or logs private keys or secrets.
    - Raises a clear configuration error if credentials are missing or invalid,
      without silent fallback to local storage.
    """
    global db, _firebase_initialized

    if _firebase_initialized and db is not None:
        return db

    # Explicit offline test mode check (strictly prohibited in production)
    if os.getenv('USE_LOCAL_FIRESTORE', '').lower() in ('true', '1'):
        if Config.ENV == 'production':
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: USE_LOCAL_FIRESTORE is strictly prohibited when FLASK_ENV=production. "
                "Production requires authentic Google Cloud Firestore connectivity with valid service account credentials."
            )
        logger.warning("USE_LOCAL_FIRESTORE is explicitly set to true. Initializing Local Firestore Engine.")
        db = LocalFirestoreClient()
        _firebase_initialized = True
        return db

    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_dict = None
    cred_source = None

    # 1. Environment variable raw JSON string
    env_service_account_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    if env_service_account_json and env_service_account_json.strip():
        try:
            cred_dict = json.loads(env_service_account_json)
            if isinstance(cred_dict, dict) and 'private_key' in cred_dict:
                cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
            cred_source = "FIREBASE_SERVICE_ACCOUNT_JSON environment variable"
        except Exception as parse_err:
            raise ValueError(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON environment variable: {parse_err}")

    # 2. File-based credentials: GOOGLE_APPLICATION_CREDENTIALS, FIREBASE_CREDENTIALS_PATH, or local serviceAccountKey.json
    if cred_dict is None:
        env_gcp_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        configured_path = Config.FIREBASE_CREDENTIALS_PATH

        paths_to_try = []
        if env_gcp_creds:
            paths_to_try.append((env_gcp_creds, "GOOGLE_APPLICATION_CREDENTIALS"))
        if configured_path:
            paths_to_try.append((configured_path, "FIREBASE_CREDENTIALS_PATH"))
        paths_to_try.append(('serviceAccountKey.json', "local serviceAccountKey.json"))

        resolved_path = None
        for path_cand, source_name in paths_to_try:
            found = resolve_credentials_path(path_cand)
            if found:
                resolved_path = found
                cred_source = f"{source_name} ({Path(found).name})"
                break

        if resolved_path:
            try:
                with open(resolved_path, 'r', encoding='utf-8') as f:
                    cred_dict = json.load(f)
            except Exception as read_err:
                raise RuntimeError(f"Failed to read service account credentials file: {read_err}")
        else:
            raise FileNotFoundError(
                "Firebase Admin service account credentials not found. "
                "Please configure GOOGLE_APPLICATION_CREDENTIALS (e.g. Render Secret File), "
                "FIREBASE_CREDENTIALS_PATH, or place 'serviceAccountKey.json' in the backend directory."
            )

    # 3. Validate credential structure and project ID match
    if not isinstance(cred_dict, dict):
        raise ValueError("Invalid service account credentials: expected a JSON object.")

    cred_project_id = cred_dict.get('project_id')
    expected_project_id = Config.FIREBASE_PROJECT_ID
    if expected_project_id and cred_project_id != expected_project_id:
        raise ValueError(
            f"Firebase project ID mismatch: credentials project ID ('{cred_project_id}') "
            f"does not match configured FIREBASE_PROJECT_ID ('{expected_project_id}')."
        )

    # 4. Initialize Firebase Admin SDK safely (avoid re-initialization)
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {
            'projectId': expected_project_id or cred_project_id
        })
        logger.info(f"Firebase Admin SDK initialized successfully for project '{expected_project_id}' via {cred_source}.")

    # 5. Obtain Firestore client
    db = firestore.client()
    _firebase_initialized = True
    return db


def check_firestore_connectivity():
    """
    Safe backend diagnostic confirming:
    - Firebase Admin SDK initializes successfully.
    - Expected project ID matches configured value (capstone-8ee41).
    - Firestore can be accessed using configured credentials (read-only probe).
    Never logs or returns private keys, client email, or credential contents.
    """
    import firebase_admin
    from firebase_admin import firestore

    diagnostic = {
        "sdk_initialized": False,
        "configured_project_id": Config.FIREBASE_PROJECT_ID,
        "actual_project_id": None,
        "project_id_match": False,
        "firestore_accessible": False,
        "database": "Cloud Firestore",
        "error_category": None,
        "message": ""
    }

    # 1. Check or run initialization
    global db
    if db is None or not firebase_admin._apps:
        try:
            init_firebase()
        except Exception as init_err:
            diagnostic["error_category"] = "INITIALIZATION_FAILED"
            diagnostic["message"] = f"Failed to initialize Firebase Admin SDK: {init_err}"
            return diagnostic

    if hasattr(db, '_persistence_file'):
        diagnostic["sdk_initialized"] = False
        diagnostic["database"] = "Local Firestore Engine"
        diagnostic["firestore_accessible"] = True
        diagnostic["message"] = "Running in Local Firestore Engine mode (USE_LOCAL_FIRESTORE active)."
        return diagnostic

    app = firebase_admin.get_app()
    diagnostic["sdk_initialized"] = True

    # Safely get project ID without accessing secrets
    app_project_id = getattr(app, 'project_id', None) or (app.options.get('projectId') if hasattr(app, 'options') else None)
    if not app_project_id and hasattr(db, 'project'):
        app_project_id = db.project

    diagnostic["actual_project_id"] = app_project_id
    diagnostic["project_id_match"] = (app_project_id == Config.FIREBASE_PROJECT_ID)

    # 2. Read-only connectivity probe using next(db.collections(), None)
    try:
        cols = db.collections()
        _ = next(cols, None)
        diagnostic["firestore_accessible"] = True
        diagnostic["message"] = f"Cloud Firestore is fully accessible for project '{Config.FIREBASE_PROJECT_ID}'."
    except Exception as exc:
        diagnostic["firestore_accessible"] = False
        reason = getattr(exc, 'reason', None) or ""
        code = getattr(exc, 'code', None)
        err_str = str(exc).lower()

        if reason == 'SERVICE_DISABLED' or 'disabled' in err_str or 'not been used' in err_str:
            diagnostic["error_category"] = "SERVICE_DISABLED"
            diagnostic["message"] = (
                f"Cloud Firestore API is not enabled or database has not been created "
                f"for project '{Config.FIREBASE_PROJECT_ID}'. "
                f"Enable Cloud Firestore in the Google Cloud or Firebase Console."
            )
        elif code == 403 or 'permission' in err_str or 'denied' in err_str:
            diagnostic["error_category"] = "PERMISSION_DENIED"
            diagnostic["message"] = "Service account lacks permission to read collections in Cloud Firestore."
        elif code == 401 or 'unauthenticated' in err_str:
            diagnostic["error_category"] = "UNAUTHENTICATED"
            diagnostic["message"] = "Authentication failed. Service account credentials may be expired or invalid."
        elif code == 404 or 'not found' in err_str:
            diagnostic["error_category"] = "DATABASE_NOT_FOUND"
            diagnostic["message"] = f"Cloud Firestore database instance not found for project '{Config.FIREBASE_PROJECT_ID}'."
        else:
            diagnostic["error_category"] = "CONNECTION_ERROR"
            diagnostic["message"] = "Unable to connect to Cloud Firestore service endpoint."

    return diagnostic


# Initialize immediately when module is imported
try:
    db = init_firebase()
except Exception as _init_exc:
    logger.warning(f"Initial Firebase startup check: {_init_exc}")
    db = None
