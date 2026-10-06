from flask import Blueprint, request, g
from services.network_service import (
    execute_network_scan,
    get_scan_history,
    get_security_monitor_summary
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response
from utils.validators import validate_required_fields

network_bp = Blueprint('network_bp', __name__, url_prefix='/api/network')

@network_bp.route('/scan', methods=['POST'])
@token_required
@role_required('Admin')
def handle_run_scan():
    """
    POST /api/network/scan
    Triggers scoped network discovery scan via backend Nmap service.
    """
    data = request.get_json() or {}
    missing = validate_required_fields(data, ['target'])
    if missing:
        return error_response(code="VALIDATION_ERROR", message="Network scan 'target' (IP/CIDR) is required.", status_code=400)

    client_ip = request.remote_addr
    scan_data, err, status_code = execute_network_scan(data['target'], g.current_user, ip_address=client_ip)

    if err:
        return error_response(code="SCAN_EXECUTION_FAILED", message=err, status_code=status_code)

    return success_response(data=scan_data, message="Network scan completed successfully", status_code=201)


@network_bp.route('/history', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_history():
    """
    GET /api/network/history
    Retrieves chronological past scan logs.
    """
    limit = request.args.get('limit', default=20, type=int)
    history = get_scan_history(limit=limit)
    return success_response(data=history)


@network_bp.route('/security', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_security_summary():
    """
    GET /api/network/security
    Returns real-time OT/IT infrastructure security telemetry & threat rating.
    """
    summary = get_security_monitor_summary()
    return success_response(data=summary)
