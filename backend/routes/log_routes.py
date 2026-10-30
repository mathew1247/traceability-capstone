from flask import Blueprint, request
from middleware.auth_middleware import token_required, role_required
from services.activity_log_service import get_activity_logs, ALLOWED_LOG_SORT_FIELDS
from utils.pagination import parse_pagination_params
from utils.response import success_response, error_response

log_bp = Blueprint('log_bp', __name__, url_prefix='/api/logs')

@log_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Auditor')
def handle_get_logs():
    """
    GET /api/logs
    Fetches immutable audit logs with optional filters (user, action, resource, resource_id),
    date range boundaries (start_date, end_date), full-text search, pagination, and deterministic sorting.
    Allowed roles: Admin, Auditor.
    """
    page, page_size, sort_by, sort_order, is_paginated, error_msg, status_code = parse_pagination_params(
        request.args,
        allowed_sort_fields=ALLOWED_LOG_SORT_FIELDS,
        default_sort_by='timestamp',
        default_sort_order='desc',
        default_page_size=10
    )
    if error_msg:
        return error_response(code="INVALID_PAGINATION_PARAMS", message=error_msg, status_code=status_code)

    user_filter = request.args.get('user') or request.args.get('user_id')
    username_filter = request.args.get('username')
    action_filter = request.args.get('action')
    resource_filter = request.args.get('resource')
    resource_id_filter = request.args.get('resource_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search = request.args.get('search') or request.args.get('q')

    # Handle unpaginated limit (backwards compatibility for legacy clients)
    limit = None
    if not is_paginated:
        limit_raw = request.args.get('limit', default=100)
        try:
            limit = int(limit_raw)
            if limit < 1 or limit > 1000:
                return error_response(code="INVALID_LIMIT", message="Limit must be an integer between 1 and 1000.", status_code=400)
        except (ValueError, TypeError):
            return error_response(code="INVALID_LIMIT", message="Limit must be an integer between 1 and 1000.", status_code=400)

    result, err, code = get_activity_logs(
        user_id=user_filter,
        username=username_filter,
        action=action_filter,
        resource=resource_filter,
        resource_id=resource_id_filter,
        start_date=start_date,
        end_date=end_date,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        is_paginated=is_paginated,
        limit=limit
    )

    if err:
        return error_response(code="INVALID_FILTER_PARAMS", message=err, status_code=code)

    return success_response(data=result, message="Audit logs retrieved successfully")

