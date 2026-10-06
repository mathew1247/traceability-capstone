from flask import Blueprint, request, g
from services.compliance_service import (
    get_all_compliance,
    get_compliance_by_id,
    create_compliance_record,
    update_compliance_record,
    delete_compliance_record
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response

compliance_bp = Blueprint('compliance_bp', __name__, url_prefix='/api/compliance')

@compliance_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_all():
    records = get_all_compliance()
    return success_response(data=records)


@compliance_bp.route('/<compliance_id>', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_one(compliance_id):
    record = get_compliance_by_id(compliance_id)
    if not record:
        return error_response(code="COMPLIANCE_RECORD_NOT_FOUND", message="Compliance audit record not found", status_code=404)
    return success_response(data=record)


@compliance_bp.route('', methods=['POST'])
@token_required
@role_required('Admin', 'Inspector')
def handle_create():
    data = request.get_json() or {}
    record, err, status_code = create_compliance_record(data, g.current_user)
    if err:
        return error_response(code="CREATE_COMPLIANCE_FAILED", message=err, status_code=status_code)
    return success_response(data=record, message="Compliance audit record created successfully", status_code=201)


@compliance_bp.route('/<compliance_id>', methods=['PUT'])
@token_required
@role_required('Admin', 'Inspector')
def handle_update(compliance_id):
    data = request.get_json() or {}
    updated, err, status_code = update_compliance_record(compliance_id, data, g.current_user)
    if err:
        return error_response(code="UPDATE_COMPLIANCE_FAILED", message=err, status_code=status_code)
    return success_response(data=updated, message="Compliance record updated successfully")


@compliance_bp.route('/<compliance_id>', methods=['DELETE'])
@token_required
@role_required('Admin')
def handle_delete(compliance_id):
    ok, err, status_code = delete_compliance_record(compliance_id, g.current_user)
    if err:
        return error_response(code="DELETE_COMPLIANCE_FAILED", message=err, status_code=status_code)
    return success_response(data={"compliance_id": compliance_id}, message="Compliance record deleted successfully")
