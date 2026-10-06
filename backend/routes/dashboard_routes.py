from flask import Blueprint
from services.dashboard_service import get_dashboard_metrics
from middleware.auth_middleware import token_required
from utils.response import success_response

dashboard_bp = Blueprint('dashboard_bp', __name__, url_prefix='/api/dashboard')

@dashboard_bp.route('/stats', methods=['GET'])
@token_required
def handle_get_dashboard_stats():
    """
    GET /api/dashboard/stats
    Returns live statistics and KPIs for dashboard overview cards.
    """
    stats = get_dashboard_metrics()
    return success_response(data=stats, message="Dashboard metrics compiled successfully")
