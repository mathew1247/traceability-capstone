from flask import Blueprint, request, g
from services.auth_service import login, create_user, request_password_reset, reset_password_with_token
from middleware.auth_middleware import token_required
from utils.response import success_response, error_response
from utils.validators import validate_required_fields, validate_email

auth_bp = Blueprint('auth_bp', __name__, url_prefix='/api/auth')

@auth_bp.route('/login', methods=['POST'])
def handle_login():
    """
    POST /api/auth/login
    Authenticates user and returns JWT.
    """
    data = request.get_json() or {}
    missing = validate_required_fields(data, ['email', 'password'])
    if missing:
        return error_response(
            code="VALIDATION_ERROR",
            message=f"Missing required fields: {', '.join(missing)}",
            status_code=400
        )

    client_ip = request.remote_addr
    result, error_msg, status_code = login(data['email'], data['password'], ip_address=client_ip)

    if error_msg:
        return error_response(
            code="AUTHENTICATION_FAILED",
            message=error_msg,
            status_code=status_code
        )

    return success_response(data=result, message="Authentication successful.", status_code=200)


@auth_bp.route('/register', methods=['POST'])
def handle_register():
    """
    POST /api/auth/register
    Creates new account (public signup or onboarding).
    """
    data = request.get_json() or {}
    missing = validate_required_fields(data, ['username', 'email', 'password'])
    if missing:
        return error_response(
            code="VALIDATION_ERROR",
            message=f"Missing required fields: {', '.join(missing)}",
            status_code=400
        )

    if not validate_email(data['email']):
        return error_response(
            code="INVALID_EMAIL",
            message="Please provide a valid email address.",
            status_code=400
        )

    # Public signups default to Operator role; Admins can promote via /api/users
    role = data.get('role', 'Operator')
    if role not in ('Operator', 'Auditor', 'Inspector'):
        role = 'Operator'

    new_user, error_msg, status_code = create_user(
        username=data['username'],
        email=data['email'],
        password=data['password'],
        role=role
    )

    if error_msg:
        return error_response(
            code="REGISTRATION_FAILED",
            message=error_msg,
            status_code=status_code
        )

    return success_response(data=new_user, message="Account created successfully.", status_code=201)


@auth_bp.route('/me', methods=['GET'])
@token_required
def handle_get_current_user():
    """
    GET /api/auth/me
    Returns current authenticated user details.
    """
    return success_response(data=g.current_user, status_code=200)


@auth_bp.route('/forgot-password', methods=['POST'])
def handle_forgot_password():
    """
    POST /api/auth/forgot-password
    Public endpoint: sends password recovery instructions with secure cryptographic token.
    """
    data = request.get_json() or {}
    email = data.get('email')
    if not email:
        return error_response(code="VALIDATION_ERROR", message="Email address is required.", status_code=400)

    client_ip = request.remote_addr
    result, err, status_code = request_password_reset(email, ip_address=client_ip)
    if err:
        return error_response(code="PASSWORD_RECOVERY_FAILED", message=err, status_code=status_code)

    return success_response(data=result, message=result.get("message", "Password recovery instructions dispatched."))


@auth_bp.route('/reset-password', methods=['POST'])
def handle_reset_password():
    """
    POST /api/auth/reset-password
    Public endpoint: validates reset token and updates password.
    """
    data = request.get_json() or {}
    token = data.get('token')
    new_password = data.get('new_password')
    if not token or not new_password:
        return error_response(code="VALIDATION_ERROR", message="Reset token and new password are required.", status_code=400)

    client_ip = request.remote_addr
    result, err, status_code = reset_password_with_token(token, new_password, ip_address=client_ip)
    if err:
        return error_response(code="PASSWORD_RESET_FAILED", message=err, status_code=status_code)

    return success_response(data=result, message=result.get("message", "Password successfully updated."))
