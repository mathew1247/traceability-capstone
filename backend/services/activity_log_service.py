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


ALLOWED_LOG_SORT_FIELDS = {'timestamp', 'action', 'resource', 'user_id', 'username', 'log_id'}
SENSITIVE_FIELD_NAMES = {'password', 'password_hash', 'token', 'jwt', 'secret', 'api_key', 'private_key'}


def parse_iso_or_calendar_date(date_str, is_end_of_day=False):
    """
    Parses YYYY-MM-DD or ISO 8601 string into an ISO 8601 UTC string.
    Returns (iso_str, is_valid).
    """
    if not date_str or not isinstance(date_str, str):
        return None, False
    clean = date_str.strip()
    if not clean:
        return None, False

    try:
        if 'T' in clean:
            dt = datetime.fromisoformat(clean.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.isoformat(), True
        else:
            dt = datetime.strptime(clean, '%Y-%m-%d')
            if is_end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
            else:
                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            return dt.isoformat(), True
    except (ValueError, TypeError):
        return None, False


def sanitize_log_entry(log_entry):
    """
    Strips sensitive credentials, tokens, or private keys from activity log entries.
    Handles nested dictionaries (e.g. details).
    """
    if not isinstance(log_entry, dict):
        return log_entry
    clean = dict(log_entry)
    for field in SENSITIVE_FIELD_NAMES:
        clean.pop(field, None)
    if isinstance(clean.get('details'), dict):
        clean_details = dict(clean['details'])
        for field in SENSITIVE_FIELD_NAMES:
            clean_details.pop(field, None)
        clean['details'] = clean_details
    return clean


def get_activity_logs(
    user_id=None,
    username=None,
    action=None,
    resource=None,
    resource_id=None,
    start_date=None,
    end_date=None,
    search=None,
    page=1,
    page_size=10,
    sort_by='timestamp',
    sort_order='desc',
    is_paginated=False,
    limit=100
):
    """
    Phase 2 Task 5: Activity-Log Retrieval Engine.
    Retrieves, filters, sorts, and paginates immutable activity logs from Firestore.
    
    Features:
    - Pushes supported equality and range filters to Firestore when possible.
    - Gracefully handles compound query index limitations with in-memory filtering fallback.
    - Validates date parameters and supports date-range boundaries.
    - Deterministic sorting using primary sort field and 'log_id' tie-breaker.
    - Returns sanitized records with sensitive fields removed.
    - Supports backward-compatible unpaginated list format when is_paginated is False.
    """
    from services.firestore_service import serialize_value
    from utils.pagination import paginate_records

    start_iso = None
    if start_date:
        start_iso, valid_start = parse_iso_or_calendar_date(start_date, is_end_of_day=False)
        if not valid_start:
            return None, "Invalid start_date format. Expected YYYY-MM-DD or ISO 8601.", 400

    end_iso = None
    if end_date:
        end_iso, valid_end = parse_iso_or_calendar_date(end_date, is_end_of_day=True)
        if not valid_end:
            return None, "Invalid end_date format. Expected YYYY-MM-DD or ISO 8601.", 400

    if start_iso and end_iso and start_iso > end_iso:
        return None, "start_date cannot be after end_date.", 400

    # Build Firestore query
    query = db.collection(Config.COLLECTION_ACTIVITY_LOGS)

    # Track filters to apply
    pushed_filters = {}
    if user_id:
        pushed_filters['user_id'] = user_id.strip()
    if username:
        pushed_filters['username'] = username.strip()
    if action:
        pushed_filters['action'] = action.strip()
    if resource:
        pushed_filters['resource'] = resource.strip()
    if resource_id:
        pushed_filters['resource_id'] = resource_id.strip()

    # Apply Firestore query
    try:
        f_query = query
        for k, v in pushed_filters.items():
            f_query = f_query.where(k, '==', v)

        if start_iso:
            f_query = f_query.where('timestamp', '>=', start_iso)
        if end_iso:
            f_query = f_query.where('timestamp', '<=', end_iso)

        # Order by sort_by
        f_direction = 'DESCENDING' if sort_order == 'desc' else 'ASCENDING'
        f_query = f_query.order_by(sort_by, direction=f_direction)

        # If unpaginated with explicit limit and no complex in-memory search needed:
        if not is_paginated and not search:
            f_query = f_query.limit(limit)

        docs = f_query.get()
        raw_items = [serialize_value(d.to_dict()) for d in docs if d.to_dict()]

    except Exception as e:
        # Resilient fallback: If live Firestore fails due to missing composite index
        app_logger.warning(f"Firestore query optimization fallback: {e}")
        try:
            # Query by single ordering or basic collection
            docs = query.order_by('timestamp', direction='DESCENDING').get()
            all_docs = [serialize_value(d.to_dict()) for d in docs if d.to_dict()]
        except Exception:
            docs = query.get()
            all_docs = [serialize_value(d.to_dict()) for d in docs if d.to_dict()]

        # Filter in memory
        raw_items = []
        for item in all_docs:
            match = True
            for k, v in pushed_filters.items():
                if item.get(k) != v:
                    match = False
                    break
            if match and start_iso and (item.get('timestamp') or '') < start_iso:
                match = False
            if match and end_iso and (item.get('timestamp') or '') > end_iso:
                match = False
            if match:
                raw_items.append(item)

    # Apply text search if requested
    if search:
        s_term = search.strip().lower()
        filtered = []
        for item in raw_items:
            searchable = " ".join([
                str(item.get('username') or ''),
                str(item.get('user_id') or ''),
                str(item.get('action') or ''),
                str(item.get('resource') or ''),
                str(item.get('resource_id') or ''),
                str(item.get('details') or ''),
                str(item.get('ip_address') or '')
            ]).lower()
            if s_term in searchable:
                filtered.append(item)
        raw_items = filtered

    # Sanitize entries (remove sensitive credentials or tokens)
    sanitized_items = [sanitize_log_entry(item) for item in raw_items]

    # Deterministic sorting with log_id as tie-breaker
    result = paginate_records(
        sanitized_items,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        tie_breaker_field='log_id',
        is_paginated=is_paginated
    )

    # If unpaginated, enforce limit if specified
    if not is_paginated and limit is not None:
        result = result[:limit]

    return result, None, 200

