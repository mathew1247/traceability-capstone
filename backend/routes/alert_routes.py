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
    user_email = data.get('recipient_email') or g.current_user.get('email') or 'probot12309@gmail.com'
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
    email_info = updated.get('email_notification', {})
    recipient = email_info.get('recipient', user_email)
    mode = email_info.get('mode', 'simulated')

    if mode == 'smtp_delivered':
        msg = f"Alert {alert_id} {action_label}! Live email delivered to {recipient}."
    elif mode == 'smtp_error':
        msg = f"Alert {alert_id} {action_label}! Email error: {email_info.get('error', 'Authentication failed')}. Check Google App Password."
    else:
        msg = f"Alert {alert_id} {action_label}! Notification queued for {recipient}."

    return success_response(data=updated, message=msg)


@alert_bp.route('/test-email', methods=['POST'])
@token_required
def handle_test_email():
    """
    POST /api/alerts/test-email
    Body: { "recipient": "...", "app_password": "..." }
    """
    import os
    from datetime import datetime, timezone
    from services.email_service import EmailService

    data = request.get_json() or {}
    recipient = data.get('recipient') or os.environ.get('ALERT_NOTIFICATION_EMAIL') or 'probot12309@gmail.com'
    app_pwd = data.get('app_password')
    if app_pwd:
        os.environ['SMTP_PASSWORD'] = app_pwd.strip()
    
    test_alert = {
        "id": "ALT-TEST-VERIFY",
        "severity": "Warning",
        "message": "Manual test notification triggered from Sentinel-Trace Security Console.",
        "source": "OT-Gateway-192.168.1.1",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    }

    result, err = EmailService.send_alert_notification(test_alert, recipient, action="Test Triggered")
    if err:
        return error_response(code="EMAIL_SEND_FAILED", message=f"Failed to transmit email: {err}", status_code=400)
    
    return success_response(data=result, message=result.get("message", f"Test email dispatched to {recipient}"))
