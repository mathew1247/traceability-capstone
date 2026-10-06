from flask import Blueprint
from services.report_service import get_reports_summary
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response

report_bp = Blueprint('report_bp', __name__, url_prefix='/api/reports')

@report_bp.route('/summary', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_report_summary():
    """
    GET /api/reports/summary
    Returns aggregated analytics for Production, Compliance, Network, and Alerts.
    """
    summary = get_reports_summary()
    return success_response(data=summary, message="Analytics dossier compiled successfully")
