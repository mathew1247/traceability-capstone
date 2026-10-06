from flask import Blueprint, request, g
from services.supplier_service import (
    get_all_suppliers,
    get_supplier_by_id,
    create_supplier,
    update_supplier,
    delete_supplier
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response

supplier_bp = Blueprint('supplier_bp', __name__, url_prefix='/api/suppliers')

@supplier_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor')
def handle_get_all():
    suppliers = get_all_suppliers()
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
