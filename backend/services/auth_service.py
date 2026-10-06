import uuid
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from config import Config
from config.firebase import db
from services.activity_log_service import log_activity
from utils.logger import app_logger

def hash_password(password: str) -> str:
    """Securely hashes plaintext password with salt."""
    return generate_password_hash(password, method='scrypt')


def verify_password(password: str, hashed_password: str) -> bool:
    """Verifies plaintext password against stored hash."""
    return check_password_hash(hashed_password, password)


def generate_jwt(user_dict: dict) -> str:
    """Generates signed JWT token with expiration timestamp."""
    exp = datetime.now(timezone.utc) + timedelta(hours=Config.JWT_EXPIRATION_HOURS)
    payload = {
        'user_id': user_dict['user_id'],
        'username': user_dict['username'],
        'email': user_dict['email'],
        'role': user_dict['role'],
        'exp': exp,
        'iat': datetime.now(timezone.utc)
    }
    token = jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm='HS256')
    return token


def ensure_default_admin_users():
    """Ensures primary default admin and inspector accounts exist in Firestore if database is unseeded."""
    try:
        users_ref = db.collection(Config.COLLECTION_USERS)
        now_iso = datetime.now(timezone.utc).isoformat()
        default_users = [
            {
                "user_id": "USR-ADMIN01",
                "username": "Jack Mathew",
                "email": "jack@sentineltrace.io",
                "password_hash": hash_password("password123"),
                "role": "Admin",
                "status": "Active",
                "created_at": now_iso
            },
            {
                "user_id": "USR-ADMIN02",
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
                "user_id": "USR-INSPECT02",
                "username": "Sarah Connor",
                "email": "sarah.chen@sentineltrace.io",
                "password_hash": hash_password("password123"),
                "role": "Inspector",
                "status": "Active",
                "created_at": now_iso
            }
        ]
        for u in default_users:
            existing = users_ref.where('email', '==', u['email']).get()
            if not list(existing):
                users_ref.document(u['user_id']).set(u)
    except Exception as e:
        app_logger.warning(f"Default user auto-seed failed: {e}")

def login(email, password, ip_address=None):
    """
    Authenticates user credentials and generates JWT.
    Returns (result_dict, error_message, status_code)
    """
    clean_email = email.strip().lower() if email else ""
    users_ref = db.collection(Config.COLLECTION_USERS)
    
    matched_docs = users_ref.where('email', '==', clean_email).get()
    user_doc = None
    for doc in matched_docs:
        user_doc = doc
        break

    if not user_doc or not user_doc.exists:
        # Attempt auto-seeding if first time running on cloud Firestore
        ensure_default_admin_users()
        matched_docs = users_ref.where('email', '==', clean_email).get()
        for doc in matched_docs:
            user_doc = doc
            break

    if not user_doc or not user_doc.exists:
        app_logger.warning(f"Failed login attempt for non-existent email: {clean_email}")
        return None, "Invalid email or password.", 401

    user_data = user_doc.to_dict()

    if user_data.get('status') != 'Active':
        return None, "User account is suspended or inactive.", 403

    stored_hash = user_data.get('password_hash', '')
    if not verify_password(password, stored_hash):
        app_logger.warning(f"Failed login attempt (wrong password) for: {clean_email}")
        return None, "Invalid email or password.", 401

    token = generate_jwt(user_data)

    # Log successful login
    log_activity(
        user_id=user_data['user_id'],
        username=user_data['username'],
        action='AUTH_LOGIN',
        resource='Auth',
        resource_id=user_data['user_id'],
        details=f"User {user_data['username']} logged in successfully.",
        ip_address=ip_address
    )

    return {
        "token": token,
        "user": {
            "user_id": user_data['user_id'],
            "username": user_data['username'],
            "email": user_data['email'],
            "role": user_data['role'],
            "status": user_data['status']
        }
    }, None, 200


def create_user(username, email, password, role='Operator', status='Active', creator_user=None):
    """
    Registers a new user record.
    Returns (user_data, error_message, status_code)
    """
    clean_email = email.strip().lower()
    users_ref = db.collection(Config.COLLECTION_USERS)

    # Check for email uniqueness
    existing = users_ref.where('email', '==', clean_email).get()
    for _ in existing:
        return None, "A user with this email address already exists.", 409

    # Generate readable ID
    user_id = f"USR-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    new_user = {
        "user_id": user_id,
        "username": username.strip(),
        "email": clean_email,
        "password_hash": hash_password(password),
        "role": role,
        "status": status,
        "created_at": now_iso
    }

    users_ref.document(user_id).set(new_user)

    creator_name = creator_user.get('username') if creator_user else "System"
    creator_id = creator_user.get('user_id') if creator_user else "SYSTEM"

    log_activity(
        user_id=creator_id,
        username=creator_name,
        action='CREATE',
        resource='User',
        resource_id=user_id,
        details=f"Created user {username} with role {role}"
    )

    safe_data = new_user.copy()
    del safe_data['password_hash']
    return safe_data, None, 201


def get_all_users():
    """Fetches all users excluding password hashes."""
    docs = db.collection(Config.COLLECTION_USERS).get()
    users = []
    for doc in docs:
        d = doc.to_dict()
        if d:
            safe = d.copy()
            safe.pop('password_hash', None)
            users.append(safe)
    return users


def get_user_by_id(user_id):
    """Fetches single user details."""
    doc = db.collection(Config.COLLECTION_USERS).document(user_id).get()
    if not doc.exists:
        return None
    d = doc.to_dict()
    d.pop('password_hash', None)
    return d


def update_user(user_id, update_data, current_user):
    """Updates user information (role, username, status, etc.)."""
    user_ref = db.collection(Config.COLLECTION_USERS).document(user_id)
    doc = user_ref.get()
    if not doc.exists:
        return None, "User not found", 404

    allowed_updates = {}
    if 'username' in update_data and update_data['username']:
        allowed_updates['username'] = update_data['username'].strip()
    if 'role' in update_data and update_data['role']:
        allowed_updates['role'] = update_data['role']
    if 'status' in update_data and update_data['status']:
        allowed_updates['status'] = update_data['status']
    if 'password' in update_data and update_data['password']:
        allowed_updates['password_hash'] = hash_password(update_data['password'])

    if not allowed_updates:
        return None, "No valid update fields provided", 400

    user_ref.update(allowed_updates)
    updated = user_ref.get().to_dict()
    updated.pop('password_hash', None)

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='User',
        resource_id=user_id,
        details=f"Updated user {user_id} fields: {list(allowed_updates.keys())}"
    )

    return updated, None, 200


def delete_user(user_id, current_user):
    """Deletes user record."""
    user_ref = db.collection(Config.COLLECTION_USERS).document(user_id)
    doc = user_ref.get()
    if not doc.exists:
        return False, "User not found", 404

    # Prevent deleting self
    if current_user.get('user_id') == user_id:
        return False, "Cannot delete your own active administrator account.", 400

    user_ref.delete()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='DELETE',
        resource='User',
        resource_id=user_id,
        details=f"Deleted user {user_id}"
    )

    return True, None, 200
