from flask import Blueprint, request, g
from services.alert_service import (
    get_alerts,
    get_alert_by_id,
    create_alert,
    update_alert_action
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response

alert_bp = Blueprint('alert_bp', __name__, url_prefix='/api/alerts')

@alert_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_alerts():
    status = request.args.get('status')
    severity = request.args.get('severity')
    limit = request.args.get('limit', default=50, type=int)

    alerts = get_alerts(status_filter=status, severity_filter=severity, limit=limit)
    return success_response(data=alerts)


@alert_bp.route('', methods=['POST'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_create_alert():
    """
    POST /api/alerts
    Body: { "severity": "...", "source": "...", "message": "...", "resource_id": "..." }
    """
    data = request.get_json() or {}
    severity = data.get('severity', 'Warning')
    source = data.get('source', 'System')
    message = data.get('message')
    resource_id = data.get('resource_id')

    if not message:
        return error_response(code="VALIDATION_ERROR", message="Alert message is required.", status_code=400)

    alert = create_alert(severity=severity, source=source, message=message, resource_id=resource_id)
    if not alert:
        return error_response(code="ALERT_CREATION_FAILED", message="Failed to create alert.", status_code=500)

    return success_response(data=alert, message="Alert generated successfully", status_code=201)


@alert_bp.route('/<alert_id>', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_alert(alert_id):
    alert = get_alert_by_id(alert_id)
    if not alert:
        return error_response(code="ALERT_NOT_FOUND", message="Alert not found", status_code=404)
    return success_response(data=alert)


@alert_bp.route('/<alert_id>', methods=['PUT'])
@token_required
@role_required('Admin', 'Inspector', 'Operator')
def handle_update_alert_action(alert_id):
    """
    PUT /api/alerts/<alert_id>
    Body: { "action": "Acknowledge" | "Resolve" | "Dismiss" }
    """
    data = request.get_json() or {}
    action = data.get('action') or data.get('status')
    if not action:
        return error_response(code="VALIDATION_ERROR", message="Action ('Acknowledge', 'Resolve', 'Dismiss') is required.", status_code=400)

    client_ip = request.remote_addr
    user_email = g.current_user.get('email') or data.get('email') or 'jack@sentineltrace.io'
    updated, err = update_alert_action(
        alert_id=alert_id,
        action=action,
        user_id=g.current_user.get('user_id'),
        username=g.current_user.get('username'),
        user_email=user_email,
        ip_address=client_ip
    )

    if err:
        return error_response(code="ALERT_UPDATE_FAILED", message=err, status_code=400)

    action_label = updated.get('status', action)
    return success_response(
        data=updated,
        message=f"Alert {alert_id} updated: {action_label}. Email notification sent to {user_email}."
    )
