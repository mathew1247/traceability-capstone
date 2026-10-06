import uuid
from datetime import datetime, timezone
from config import Config
from config.firebase import db
from utils.logger import app_logger

def log_activity(user_id, username, action, resource, resource_id=None, details=None, ip_address=None):
    """
    Centralized activity logger for all mutations and sensitive actions.
    Persists audit entry in the activity_logs Firestore collection.
    """
    try:
        log_id = f"LOG-{uuid.uuid4().hex[:8].upper()}"
        timestamp = datetime.now(timezone.utc).isoformat()

        log_data = {
            "log_id": log_id,
            "user_id": user_id or "SYSTEM",
            "username": username or "System",
            "action": action,
            "resource": resource,
            "resource_id": resource_id or "",
            "ip_address": ip_address or "127.0.0.1",
            "timestamp": timestamp,
            "details": details or f"{action} performed on {resource}"
        }

        db.collection(Config.COLLECTION_ACTIVITY_LOGS).document(log_id).set(log_data)
        app_logger.info(f"AUDIT_LOG [{action}] {resource} ({resource_id}) by {username}")
        return log_data

    except Exception as e:
        app_logger.error(f"Failed to record activity log: {str(e)}")
        return None
