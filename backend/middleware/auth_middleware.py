from functools import wraps
from flask import request, g
import jwt
from datetime import datetime, timezone
from config import Config
from config.firebase import db
from utils.response import error_response

def token_required(f):
    """
    Decorator to protect endpoints with JWT authentication.
    Validates Authorization: Bearer <token>
    Attaches authenticated user to flask.g.current_user
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return error_response(
                code="AUTHENTICATION_REQUIRED",
                message="Authorization header with Bearer token is required.",
                status_code=401
            )

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return error_response(
                code="INVALID_AUTH_HEADER",
                message="Authorization header must follow 'Bearer <token>' format.",
                status_code=401
            )

        token = parts[1]

        try:
            payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('user_id')
            if not user_id:
                return error_response(
                    code="INVALID_TOKEN",
                    message="Token payload is missing user identification.",
                    status_code=401
                )

            # Fetch user from Firestore to ensure active status
            user_ref = db.collection(Config.COLLECTION_USERS).document(user_id)
            user_doc = user_ref.get()

            if not user_doc or not user_doc.exists:
                # Query by user_id field if document key differs
                matched = db.collection(Config.COLLECTION_USERS).where('user_id', '==', user_id).get()
                for doc in matched:
                    user_doc = doc
                    break

            if user_doc and user_doc.exists:
                user_data = user_doc.to_dict()
                if user_data.get('status') == 'Inactive' or user_data.get('status') == 'Suspended':
                    return error_response(
                        code="ACCOUNT_DISABLED",
                        message="User account is deactivated. Contact an administrator.",
                        status_code=403
                    )
                g.current_user = {
                    'user_id': user_id,
                    'username': user_data.get('username', payload.get('username')),
                    'email': user_data.get('email', payload.get('email')),
                    'role': user_data.get('role', payload.get('role', 'Operator')),
                    'status': user_data.get('status', 'Active')
                }
            else:
                # Fallback to verified JWT payload context
                g.current_user = {
                    'user_id': user_id,
                    'username': payload.get('username', 'Jack Mathew'),
                    'email': payload.get('email', 'admin@sentineltrace.local'),
                    'role': payload.get('role', 'Admin'),
                    'status': 'Active'
                }

        except jwt.ExpiredSignatureError:
            return error_response(
                code="TOKEN_EXPIRED",
                message="Session token has expired. Please log in again.",
                status_code=401
            )
        except jwt.InvalidTokenError:
            return error_response(
                code="INVALID_TOKEN",
                message="Invalid or tampered authentication token.",
                status_code=401
            )
        except Exception as e:
            return error_response(
                code="AUTH_VERIFICATION_FAILED",
                message="Unable to verify credentials.",
                status_code=401
            )

        return f(*args, **kwargs)

    return decorated


def role_required(*allowed_roles):
    """
    Decorator for Role-Based Access Control (RBAC).
    Usage:
        @token_required
        @role_required('Admin', 'Inspector')
        def my_view(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            current_user = getattr(g, 'current_user', None)
            if not current_user:
                return error_response(
                    code="AUTHENTICATION_REQUIRED",
                    message="Authentication required before checking permissions.",
                    status_code=401
                )

            user_role = current_user.get('role')
            if user_role not in allowed_roles:
                return error_response(
                    code="FORBIDDEN_INSUFFICIENT_ROLE",
                    message=f"Access denied. Requires one of roles: {', '.join(allowed_roles)}. Your role is: {user_role}.",
                    status_code=403
                )

            return f(*args, **kwargs)
        return decorated_function
    return decorator
