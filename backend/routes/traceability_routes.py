from flask import Blueprint, request, g
from services.traceability_service import get_traceability_lineage, audit_lineage_chain
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response

traceability_bp = Blueprint('traceability_bp', __name__, url_prefix='/api/traceability')

@traceability_bp.route('/<identifier>', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_traceability(identifier):
    """
    GET /api/traceability/<identifier>?direction=forward|backward
    Fetches full forward or backward pedigree relationship tree
    for Product, Batch, Material, Supplier, or Compliance record.
    """
    direction = request.args.get('direction', 'forward').strip().lower()
    if direction not in ('forward', 'backward', 'both'):
        direction = 'forward'

    result, err, status_code = get_traceability_lineage(identifier, direction=direction)
    if err:
        return error_response(code="TRACEABILITY_LOOKUP_FAILED", message=err, status_code=status_code)

    return success_response(data=result, message="Traceability graph retrieved successfully")


@traceability_bp.route('/<identifier>/audit', methods=['POST', 'GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_audit_traceability(identifier):
    """
    POST/GET /api/traceability/<identifier>/audit
    Audits and validates multi-tier lineage relationship integrity against Firestore ledger.
    """
    result, err, status_code = audit_lineage_chain(identifier, g.current_user)
    if err:
        return error_response(code="LINEAGE_AUDIT_FAILED", message=err, status_code=status_code)

    return success_response(data=result, message=result.get("message", "Traceability lineage audit completed successfully."))
