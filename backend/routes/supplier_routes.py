from flask import Blueprint, request, g
from services.supplier_service import (
    get_all_suppliers,
    get_supplier_by_id,
    create_supplier,
    update_supplier,
    delete_supplier,
    verify_supplier_documents
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response
from utils.pagination import parse_pagination_params

ALLOWED_SUPPLIER_SORT_FIELDS = {'supplier_id', 'supplier_name', 'contact', 'email', 'status', 'rating', 'created_at'}

supplier_bp = Blueprint('supplier_bp', __name__, url_prefix='/api/suppliers')

@supplier_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_all():
    page, page_size, sort_by, sort_order, is_paginated, err, status_code = parse_pagination_params(
        request.args,
        allowed_sort_fields=ALLOWED_SUPPLIER_SORT_FIELDS,
        default_sort_by='created_at',
        default_sort_order='desc',
        default_page_size=10
    )
    if err:
        return error_response(code="INVALID_PAGINATION_PARAMS", message=err, status_code=status_code)

    search = request.args.get('search') or request.args.get('q')
    status = request.args.get('status')
    if status and not status.strip():
        status = None

    suppliers = get_all_suppliers(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search.strip() if search else None,
        status=status.strip() if status else None,
        is_paginated=is_paginated
    )
    return success_response(data=suppliers)


@supplier_bp.route('/<supplier_id>', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_one(supplier_id):
    supplier = get_supplier_by_id(supplier_id)
    if not supplier:
        return error_response(code="SUPPLIER_NOT_FOUND", message="Supplier not found", status_code=404)
    return success_response(data=supplier)


@supplier_bp.route('', methods=['POST'])
@token_required
@role_required('Admin', 'Inspector')
def handle_create():
    data = request.get_json() or {}
    record, err, status_code = create_supplier(data, g.current_user)
    if err:
        return error_response(code="CREATE_SUPPLIER_FAILED", message=err, status_code=status_code)
    return success_response(data=record, message="Supplier created successfully", status_code=201)


@supplier_bp.route('/<supplier_id>', methods=['PUT'])
@token_required
@role_required('Admin', 'Inspector')
def handle_update(supplier_id):
    data = request.get_json() or {}
    updated, err, status_code = update_supplier(supplier_id, data, g.current_user)
    if err:
        return error_response(code="UPDATE_SUPPLIER_FAILED", message=err, status_code=status_code)
    return success_response(data=updated, message="Supplier updated successfully")


@supplier_bp.route('/<supplier_id>', methods=['DELETE'])
@token_required
@role_required('Admin')
def handle_delete(supplier_id):
    ok, err, status_code = delete_supplier(supplier_id, g.current_user)
    if err:
        return error_response(code="DELETE_SUPPLIER_FAILED", message=err, status_code=status_code)
    return success_response(data={"supplier_id": supplier_id}, message="Supplier deleted successfully")


@supplier_bp.route('/<supplier_id>/verify-documents', methods=['GET', 'POST'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_verify_supplier_documents(supplier_id):
    """
    GET/POST /api/suppliers/<supplier_id>/verify-documents
    Verifies actual compliance records and material links for the vendor.
    """
    result, err, status_code = verify_supplier_documents(supplier_id, g.current_user)
    if err:
        return error_response(code="VERIFY_SUPPLIER_FAILED", message=err, status_code=status_code)
    return success_response(data=result, message=result.get("message", "Supplier documentation verified successfully."))
