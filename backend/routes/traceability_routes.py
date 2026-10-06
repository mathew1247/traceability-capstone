from flask import Blueprint
from services.traceability_service import get_traceability_lineage
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response

traceability_bp = Blueprint('traceability_bp', __name__, url_prefix='/api/traceability')

@traceability_bp.route('/<identifier>', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_traceability(identifier):
    """
    GET /api/traceability/<identifier>
    Fetches full forward and backward pedigree relationship tree
    for Product, Batch, Material, or Supplier.
    """
    result, err, status_code = get_traceability_lineage(identifier)
    if err:
        return error_response(code="TRACEABILITY_LOOKUP_FAILED", message=err, status_code=status_code)

    return success_response(data=result, message="Traceability graph retrieved successfully")
