import uuid
from datetime import datetime, timezone
from config import Config
from config.firebase import db
from services.activity_log_service import log_activity
from utils.logger import app_logger

def create_alert(severity, source, message, resource_id=None):
    """
    Creates a new security or operational alert if not duplicate.
    """
    try:
        alerts_ref = db.collection(Config.COLLECTION_ALERTS)
        
        # Check for existing active identical alert to avoid spam
        existing_query = alerts_ref.where('resource_id', '==', resource_id or '').where('status', '==', 'Active')
        existing = existing_query.get()
        for doc in existing:
            d = doc.to_dict()
            if d.get('message') == message and d.get('source') == source:
                return d  # Return existing without duplicating

        alert_id = f"ALT-{uuid.uuid4().hex[:6].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()

        alert_data = {
            "alert_id": alert_id,
            "severity": severity,          # Critical, Warning, Notice
            "source": source,              # Traceability, Compliance, Nmap Scanner, System
            "message": message,
            "resource_id": resource_id or "",
            "status": "Active",            # Active, Acknowledged, Resolved, Dismissed
            "created_at": now_iso,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "resolved_at": None
        }

        alerts_ref.document(alert_id).set(alert_data)
        app_logger.info(f"ALERT_CREATED [{severity}] [{source}]: {message}")
        return alert_data

    except Exception as e:
        app_logger.error(f"Error creating alert: {str(e)}")
        return None


from services.firestore_service import serialize_value

def get_alerts(status_filter=None, severity_filter=None, limit=50):
    """Fetches list of alerts with optional filters."""
    query = db.collection(Config.COLLECTION_ALERTS)
    if status_filter:
        query = query.where('status', '==', status_filter)
    if severity_filter:
        query = query.where('severity', '==', severity_filter)

    query = query.order_by('created_at', direction='DESCENDING').limit(limit)
    docs = query.get()
    return [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]


def get_alert_by_id(alert_id):
    """Fetches single alert by ID."""
    doc = db.collection(Config.COLLECTION_ALERTS).document(alert_id).get()
    if doc.exists:
        return serialize_value(doc.to_dict())
    return None


def update_alert_action(alert_id, action, user_id, username, user_email=None, ip_address=None):
    """
    Updates alert status (Acknowledge, Resolve, Dismiss) and dispatches email notification.
    """
    from services.email_service import EmailService

    alert_ref = db.collection(Config.COLLECTION_ALERTS).document(alert_id)
    doc = alert_ref.get()
    if not doc.exists:
        return None, "Alert not found"

    now_iso = datetime.now(timezone.utc).isoformat()
    action_clean = action.capitalize()
    updates = {}

    if action_clean in ('Acknowledge', 'Acknowledged'):
        updates['status'] = 'Acknowledged'
        updates['acknowledged_by'] = user_id
        updates['acknowledged_at'] = now_iso
        log_action = "ALERT_ACKNOWLEDGE"
    elif action_clean in ('Resolve', 'Resolved'):
        updates['status'] = 'Resolved'
        updates['resolved_at'] = now_iso
        log_action = "ALERT_RESOLVE"
    elif action_clean in ('Dismiss', 'Dismissed'):
        updates['status'] = 'Dismissed'
        updates['dismissed_at'] = now_iso
        log_action = "ALERT_DISMISS"
    else:
        return None, f"Unsupported alert action '{action}'. Valid: Acknowledge, Resolve, Dismiss"

    alert_ref.update(updates)
    updated_data = alert_ref.get().to_dict()
    updated_data['id'] = alert_id

    # Dispatch email notification for alert action
    target_email = user_email or "jack@sentineltrace.io"
    email_res, _ = EmailService.send_alert_notification(
        alert_dict=updated_data,
        user_email=target_email,
        action=updates['status']
    )
    updated_data['email_notification'] = email_res

    log_activity(
        user_id=user_id,
        username=username,
        action=log_action,
        resource="Alert",
        resource_id=alert_id,
        details=f"Alert {alert_id} marked as {updates['status']} by {username} ({target_email})",
        ip_address=ip_address
    )

    return updated_data, None
