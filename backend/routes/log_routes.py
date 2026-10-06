from flask import Blueprint, request
from config import Config
from config.firebase import db
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response

log_bp = Blueprint('log_bp', __name__, url_prefix='/api/logs')

@log_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Auditor')
def handle_get_logs():
    """
    GET /api/logs
    Fetches immutable audit logs with optional filters (user, action, resource).
    """
    user_filter = request.args.get('user') or request.args.get('user_id')
    action_filter = request.args.get('action')
    resource_filter = request.args.get('resource')
    limit = request.args.get('limit', default=100, type=int)

    query = db.collection(Config.COLLECTION_ACTIVITY_LOGS)

    if user_filter:
        query = query.where('user_id', '==', user_filter)
    if action_filter:
        query = query.where('action', '==', action_filter)
    if resource_filter:
        query = query.where('resource', '==', resource_filter)

    query = query.order_by('timestamp', direction='DESCENDING').limit(limit)
    docs = query.get()

    from services.firestore_service import serialize_value
    logs = [serialize_value(d.to_dict()) for d in docs if d.to_dict()]
    return success_response(data=logs, message="Audit logs retrieved successfully")
