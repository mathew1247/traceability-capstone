import uuid
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from config import Config
from config.firebase import db
from services.activity_log_service import log_activity
from utils.logger import app_logger
from utils.validators import validate_email, validate_role, VALID_ROLES, VALID_USER_STATUSES

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
    # Production safeguard: never seed known/hardcoded default passwords in production mode.
    if Config.is_prod or Config.ENV == 'production':
        app_logger.info("Production mode active: automatic seeding of default credentials is disabled.")
        return

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
    try:
        clean_email = email.strip().lower() if email else ""
        users_ref = db.collection(Config.COLLECTION_USERS)

        try:
            matched_docs = users_ref.where('email', '==', clean_email).get()
            user_doc = None
            for doc in matched_docs:
                user_doc = doc
                break
        except Exception:
            user_doc = None

        if not user_doc or not user_doc.exists:
            # Attempt auto-seeding only in development/test if first time running
            if not Config.is_prod and Config.ENV != 'production':
                ensure_default_admin_users()
                try:
                    matched_docs = users_ref.where('email', '==', clean_email).get()
                    for doc in matched_docs:
                        user_doc = doc
                        break
                except Exception:
                    pass

        if not user_doc or not user_doc.exists:
            app_logger.warning(f"Failed login attempt for non-existent email: {clean_email}")
            return None, "Invalid email or password.", 401

        user_data = user_doc.to_dict()

        user_status = str(user_data.get('status', 'Active')).strip()
        if user_status.lower() != 'active':
            return None, "User account is suspended or inactive.", 403

        stored_hash = user_data.get('password_hash', '')
        if not verify_password(password, stored_hash):
            app_logger.warning(f"Failed login attempt (wrong password) for: {clean_email}")
            return None, "Invalid email or password.", 401

        token = generate_jwt(user_data)

        # Log successful login
        try:
            log_activity(
                user_id=user_data['user_id'],
                username=user_data['username'],
                action='AUTH_LOGIN',
                resource='Auth',
                resource_id=user_data['user_id'],
                details=f"User {user_data['username']} logged in successfully.",
                ip_address=ip_address
            )
        except Exception as log_err:
            app_logger.warning(f"Activity log failed during login: {log_err}")

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

    except Exception as general_err:
        app_logger.error(f"Login process exception: {general_err}")
        return None, f"Authentication error: {str(general_err)}", 500


def create_user(username, email, password, role='Operator', status='Active', creator_user=None):
    """
    Registers a new user record.
    Returns (user_data, error_message, status_code)
    """
    clean_email = email.strip().lower()
    users_ref = db.collection(Config.COLLECTION_USERS)

    try:
        # Check for email uniqueness
        existing = users_ref.where('email', '==', clean_email).get()
        for _ in existing:
            return None, "A user with this email address already exists.", 409
    except Exception as e:
        app_logger.error(f"Error querying existing users in Firestore: {str(e)}")
        return None, f"Database error during user check: {str(e)}", 500

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

    try:
        users_ref.document(user_id).set(new_user)
    except Exception as e:
        app_logger.error(f"Failed to persist user {user_id} to Firestore: {str(e)}")
        return None, f"Database error: Unable to store user record. {str(e)}", 500

    creator_name = creator_user.get('username') if creator_user else "System"
    creator_id = creator_user.get('user_id') if creator_user else "SYSTEM"

    try:
        log_activity(
            user_id=creator_id,
            username=creator_name,
            action='CREATE',
            resource='User',
            resource_id=user_id,
            details=f"Created user {username} with role {role}"
        )
    except Exception as log_err:
        app_logger.warning(f"Activity logging failed for user creation: {log_err}")

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
    if not doc or not doc.exists:
        matched = db.collection(Config.COLLECTION_USERS).where('user_id', '==', user_id).get()
        for d in matched:
            doc = d
            break
    if not doc or not doc.exists:
        return None
    d = doc.to_dict()
    d.pop('password_hash', None)
    return d


def update_user(user_id, update_data, current_user):
    """Updates user information (role, username, status, etc.)."""
    if current_user and current_user.get('role') != 'Admin':
        return None, "Unauthorized: Only administrators are permitted to edit user accounts.", 403

    user_ref = db.collection(Config.COLLECTION_USERS).document(user_id)
    doc = user_ref.get()
    if not doc or not doc.exists:
        matched = db.collection(Config.COLLECTION_USERS).where('user_id', '==', user_id).get()
        for d in matched:
            user_ref = d.reference
            doc = d
            break
    if not doc or not doc.exists:
        return None, "User not found", 404

    allowed_updates = {}
    if 'username' in update_data:
        uname = str(update_data['username']).strip() if update_data['username'] is not None else ""
        if not uname:
            return None, "Username cannot be empty", 400
        allowed_updates['username'] = uname

    if 'email' in update_data:
        email_val = str(update_data['email']).strip().lower() if update_data['email'] is not None else ""
        if not validate_email(email_val):
            return None, "Invalid email format", 400
        existing = db.collection(Config.COLLECTION_USERS).where('email', '==', email_val).get()
        for d in existing:
            d_dict = d.to_dict()
            if d_dict and d_dict.get('user_id') != user_id and d.id != user_id:
                return None, "A user with this email address already exists.", 409
        allowed_updates['email'] = email_val

    if 'role' in update_data:
        role_val = str(update_data['role']).strip() if update_data['role'] is not None else ""
        if not validate_role(role_val):
            return None, f"Invalid user role '{role_val}'. Valid roles: {', '.join(VALID_ROLES)}", 400
        allowed_updates['role'] = role_val

    if 'status' in update_data:
        status_val = str(update_data['status']).strip() if update_data['status'] is not None else ""
        if status_val not in VALID_USER_STATUSES:
            return None, f"Invalid user status '{status_val}'. Valid: {', '.join(VALID_USER_STATUSES)}", 400
        allowed_updates['status'] = status_val

    if 'password' in update_data and update_data['password']:
        pw_val = str(update_data['password']).strip()
        if pw_val:
            allowed_updates['password_hash'] = hash_password(pw_val)

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

    user_data = doc.to_dict() or {}
    if user_data.get('role') == 'Admin':
        active_admins = db.collection(Config.COLLECTION_USERS)\
                          .where('role', '==', 'Admin')\
                          .where('status', '==', 'Active')\
                          .get()
        if len(active_admins) <= 1:
            return False, "Cannot delete the sole active Administrator account.", 409

    # Prevent deleting self
    if current_user and current_user.get('user_id') == user_id:
        return False, "Cannot delete your own active administrator account.", 400

    # Check if user is referenced as auditor on compliance records
    active_compliance = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS)\
                          .where('audited_by', '==', user_id)\
                          .get()
    if len(active_compliance) > 0:
        return False, f"Cannot delete user {user_id}: User is referenced as auditor on compliance records.", 409

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


def request_password_reset(email, ip_address=None):
    """
    Initiates a secure password reset flow for the given email address.
    Generates a signed time-limited cryptographic token and dispatches recovery instructions.
    """
    from services.email_service import EmailService

    if not email or not isinstance(email, str):
        return None, "Email address is required.", 400

    clean_email = email.strip().lower()
    if not validate_email(clean_email):
        return None, "Please provide a valid email address.", 400

    users_ref = db.collection(Config.COLLECTION_USERS)
    matched_docs = users_ref.where('email', '==', clean_email).get()
    user_doc = None
    for doc in matched_docs:
        user_doc = doc
        break

    # To prevent account enumeration, return generic notice if email is not found
    if not user_doc or not user_doc.exists:
        app_logger.info(f"Password reset requested for unregistered email: {clean_email}")
        return {
            "email": clean_email,
            "dispatched": True,
            "message": "If this email is registered in Sentinel-Trace, password recovery instructions have been dispatched."
        }, None, 200

    user_data = user_doc.to_dict()
    if user_data.get('status') != 'Active':
        return None, "This account is currently suspended or inactive. Please contact an administrator.", 403

    # Generate a signed cryptographic reset token valid for 1 hour
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    reset_payload = {
        'user_id': user_data['user_id'],
        'email': clean_email,
        'purpose': 'password_reset',
        'exp': exp,
        'iat': datetime.now(timezone.utc)
    }
    reset_token = jwt.encode(reset_payload, Config.JWT_SECRET_KEY, algorithm='HS256')

    subject = "[Sentinel-Trace] Password Recovery Token"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
      <h2 style="color: #0f172a;">Sentinel-Trace Password Recovery</h2>
      <p>Hello <strong>{user_data.get('username', 'Operator')}</strong>,</p>
      <p>A password reset request was initiated for your Sentinel-Trace account.</p>
      <p>Your secure password recovery token is valid for 60 minutes:</p>
      <div style="background: #f8fafc; border: 1px solid #cbd5e1; padding: 12px; font-family: monospace; font-size: 0.9rem; word-break: break-all; border-radius: 4px;">
        {reset_token}
      </div>
      <p style="margin-top: 16px; font-size: 0.85rem; color: #64748b;">
        If you did not request this recovery token, please ignore this email or notify your system administrator immediately.
      </p>
    </div>
    """

    email_res, email_err = EmailService.send_email(clean_email, subject, html_content)

    log_activity(
        user_id=user_data['user_id'],
        username=user_data['username'],
        action='AUTH_RESET_REQUEST',
        resource='Auth',
        resource_id=user_data['user_id'],
        details=f"Password recovery instructions dispatched for {clean_email}",
        ip_address=ip_address
    )

    mode = email_res.get('mode') if email_res else 'dispatched'
    if mode == 'smtp_delivered':
        user_msg = f"Password reset instructions successfully delivered to {clean_email}."
    else:
        user_msg = f"Password recovery instructions dispatched for {clean_email}."

    response_data = {
        "email": clean_email,
        "dispatched": True,
        "message": user_msg
    }
    # Security fix: Omit reset token in production to prevent account takeover risks over API responses.
    # Expose token only in non-production environments for automated integration testing.
    if not getattr(Config, 'is_prod', False) and getattr(Config, 'ENV', 'development') != 'production':
        response_data["token"] = reset_token

    return response_data, None, 200


def reset_password_with_token(token, new_password, ip_address=None):
    """
    Completes password reset using a valid cryptographic reset token.
    Never stores or exposes plaintext passwords.
    """
    if not token or not isinstance(token, str):
        return None, "Reset token is required.", 400

    if not new_password or not isinstance(new_password, str) or len(new_password.strip()) < 8:
        return None, "New password must be at least 8 characters long.", 400

    try:
        decoded = jwt.decode(token.strip(), Config.JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None, "Password reset token has expired. Please request a new token.", 400
    except jwt.InvalidTokenError:
        return None, "Invalid or corrupt password reset token.", 400

    if decoded.get('purpose') != 'password_reset':
        return None, "Invalid token purpose.", 400

    user_id = decoded.get('user_id')
    user_ref = db.collection(Config.COLLECTION_USERS).document(user_id)
    doc = user_ref.get()
    if not doc.exists:
        return None, "User account not found.", 404

    # Hash new password securely with scrypt
    hashed_pwd = hash_password(new_password.strip())
    user_ref.update({"password_hash": hashed_pwd})

    log_activity(
        user_id=user_id,
        username=decoded.get('email', user_id),
        action='AUTH_RESET_SUCCESS',
        resource='Auth',
        resource_id=user_id,
        details="User password successfully updated using recovery token",
        ip_address=ip_address
    )

    return {
        "user_id": user_id,
        "message": "Password successfully updated. You may now log in with your new credentials."
    }, None, 200
