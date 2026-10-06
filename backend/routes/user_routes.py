from flask import Blueprint, request, g
from services.auth_service import (
    get_all_users,
    get_user_by_id,
    create_user,
    update_user,
    delete_user
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response
from utils.validators import validate_required_fields, validate_email, validate_role

user_bp = Blueprint('user_bp', __name__, url_prefix='/api/users')

@user_bp.route('', methods=['GET'])
@token_required
@role_required('Admin')
def handle_get_users():
    users = get_all_users()
    return success_response(data=users)


@user_bp.route('/<user_id>', methods=['GET'])
@token_required
@role_required('Admin')
def handle_get_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return error_response(code="USER_NOT_FOUND", message="User not found", status_code=404)
    return success_response(data=user)


@user_bp.route('', methods=['POST'])
@token_required
@role_required('Admin')
def handle_create_user():
    data = request.get_json() or {}
    missing = validate_required_fields(data, ['username', 'email', 'password', 'role'])
    if missing:
        return error_response(code="VALIDATION_ERROR", message=f"Missing fields: {', '.join(missing)}", status_code=400)

    if not validate_email(data['email']):
        return error_response(code="INVALID_EMAIL", message="Invalid email format", status_code=400)

    if not validate_role(data['role']):
        return error_response(code="INVALID_ROLE", message="Invalid user role", status_code=400)

    new_user, err, status_code = create_user(
        username=data['username'],
        email=data['email'],
        password=data['password'],
        role=data['role'],
        status=data.get('status', 'Active'),
        creator_user=g.current_user
    )

    if err:
        return error_response(code="CREATE_FAILED", message=err, status_code=status_code)

    return success_response(data=new_user, message="User created successfully", status_code=201)


@user_bp.route('/<user_id>', methods=['PUT'])
@token_required
@role_required('Admin')
def handle_update_user(user_id):
    data = request.get_json() or {}
    updated, err, status_code = update_user(user_id, data, g.current_user)
    if err:
        return error_response(code="UPDATE_FAILED", message=err, status_code=status_code)
    return success_response(data=updated, message="User updated successfully")


@user_bp.route('/<user_id>/status', methods=['PUT'])
@token_required
@role_required('Admin')
def handle_update_status(user_id):
    data = request.get_json() or {}
    status = data.get('status')
    if status not in ('Active', 'Inactive', 'Suspended'):
        return error_response(code="INVALID_STATUS", message="Status must be Active, Inactive, or Suspended", status_code=400)

    updated, err, status_code = update_user(user_id, {'status': status}, g.current_user)
    if err:
        return error_response(code="UPDATE_FAILED", message=err, status_code=status_code)
    return success_response(data=updated, message=f"User status changed to {status}")


@user_bp.route('/<user_id>', methods=['DELETE'])
@token_required
@role_required('Admin')
def handle_delete_user(user_id):
    ok, err, status_code = delete_user(user_id, g.current_user)
    if err:
        return error_response(code="DELETE_FAILED", message=err, status_code=status_code)
    return success_response(data={"user_id": user_id}, message="User deleted successfully")
