from flask import Blueprint, request, g
from services.compliance_service import (
    get_all_compliance,
    get_compliance_by_id,
    create_compliance_record,
    update_compliance_record,
    delete_compliance_record,
    get_compliance_expiry_status,
    scan_and_alert_compliance_expiries
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response

compliance_bp = Blueprint('compliance_bp', __name__, url_prefix='/api/compliance')

@compliance_bp.route('/expiry-status', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_expiry_status():
    """
    GET /api/compliance/expiry-status
    Returns aggregate compliance certification expiry metrics and filtered records.
    Query params:
    - warning_days: int (default 30)
    - status: expired | expiring_today | expiring_soon | valid | missing_date | invalid_date | expiring | attention
    - standard: ISO 9001:2015 | RoHS | GMP | etc.
    - product_id: product ID filter
    """
    warning_days = request.args.get('warning_days', type=int)
    status_filter = request.args.get('status') or request.args.get('expiry_status')
    standard_filter = request.args.get('standard')
    product_id_filter = request.args.get('product_id')

    result = get_compliance_expiry_status(
        warning_days=warning_days,
        status_filter=status_filter,
        standard_filter=standard_filter,
        product_id_filter=product_id_filter
    )
    return success_response(data=result, message="Compliance expiry status compiled successfully")


@compliance_bp.route('/check-expiries', methods=['POST'])
@token_required
@role_required('Admin', 'Inspector')
def handle_check_expiries():
    """
    POST /api/compliance/check-expiries
    Scans compliance records for expired or expiring certifications and triggers alerts.
    """
    data = request.get_json(silent=True) or {}
    warning_days = data.get('warning_days')
    if warning_days is None:
        warning_days = request.args.get('warning_days', type=int)

    result = scan_and_alert_compliance_expiries(
        warning_days=warning_days,
        current_user=g.current_user
    )
    return success_response(data=result, message="Compliance expiry monitoring scan completed")


@compliance_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_all():
    expiry_status = request.args.get('expiry_status') or request.args.get('status')
    warning_days = request.args.get('warning_days', type=int)
    records = get_all_compliance(expiry_status=expiry_status, warning_days=warning_days)
    return success_response(data=records)


@compliance_bp.route('/<compliance_id>', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_one(compliance_id):
    warning_days = request.args.get('warning_days', type=int)
    record = get_compliance_by_id(compliance_id, warning_days=warning_days)
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
