from flask import Blueprint, request, g
from services.material_service import (
    get_all_materials,
    get_material_by_id,
    create_material,
    update_material,
    delete_material
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response

material_bp = Blueprint('material_bp', __name__, url_prefix='/api/materials')

@material_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_all():
    materials = get_all_materials()
    return success_response(data=materials)


@material_bp.route('/<material_id>', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_one(material_id):
    material = get_material_by_id(material_id)
    if not material:
        return error_response(code="MATERIAL_NOT_FOUND", message="Raw material not found", status_code=404)
    return success_response(data=material)


@material_bp.route('', methods=['POST'])
@token_required
@role_required('Admin', 'Inspector', 'Operator')
def handle_create():
    data = request.get_json() or {}
    record, err, status_code = create_material(data, g.current_user)
    if err:
        return error_response(code="CREATE_MATERIAL_FAILED", message=err, status_code=status_code)
    return success_response(data=record, message="Raw material created successfully", status_code=201)


@material_bp.route('/<material_id>', methods=['PUT'])
@token_required
@role_required('Admin', 'Inspector', 'Operator')
def handle_update(material_id):
    data = request.get_json() or {}
    updated, err, status_code = update_material(material_id, data, g.current_user)
    if err:
        return error_response(code="UPDATE_MATERIAL_FAILED", message=err, status_code=status_code)
    return success_response(data=updated, message="Raw material updated successfully")


@material_bp.route('/<material_id>', methods=['DELETE'])
@token_required
@role_required('Admin', 'Inspector')
def handle_delete(material_id):
    ok, err, status_code = delete_material(material_id, g.current_user)
    if err:
        return error_response(code="DELETE_MATERIAL_FAILED", message=err, status_code=status_code)
    return success_response(data={"material_id": material_id}, message="Raw material deleted successfully")
