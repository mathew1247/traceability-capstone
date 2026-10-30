from flask import Blueprint, request, g
from services.batch_service import (
    get_all_batches,
    get_batch_by_id,
    create_batch,
    update_batch,
    delete_batch
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response
from utils.pagination import parse_pagination_params

ALLOWED_BATCH_SORT_FIELDS = {'batch_id', 'product_id', 'material_id', 'quantity', 'production_date', 'status', 'created_at'}

batch_bp = Blueprint('batch_bp', __name__, url_prefix='/api/batches')

@batch_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_all():
    page, page_size, sort_by, sort_order, is_paginated, err, status_code = parse_pagination_params(
        request.args,
        allowed_sort_fields=ALLOWED_BATCH_SORT_FIELDS,
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

    batches = get_all_batches(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search.strip() if search else None,
        status=status.strip() if status else None,
        is_paginated=is_paginated
    )
    return success_response(data=batches)


@batch_bp.route('/<batch_id>', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_one(batch_id):
    batch = get_batch_by_id(batch_id)
    if not batch:
        return error_response(code="BATCH_NOT_FOUND", message="Production batch not found", status_code=404)
    return success_response(data=batch)


@batch_bp.route('', methods=['POST'])
@token_required
@role_required('Admin', 'Inspector', 'Operator')
def handle_create():
    data = request.get_json() or {}
    record, err, status_code = create_batch(data, g.current_user)
    if err:
        return error_response(code="CREATE_BATCH_FAILED", message=err, status_code=status_code)
    return success_response(data=record, message="Production batch created successfully", status_code=201)


@batch_bp.route('/<batch_id>', methods=['PUT'])
@token_required
@role_required('Admin', 'Inspector', 'Operator')
def handle_update(batch_id):
    data = request.get_json() or {}
    updated, err, status_code = update_batch(batch_id, data, g.current_user)
    if err:
        return error_response(code="UPDATE_BATCH_FAILED", message=err, status_code=status_code)
    return success_response(data=updated, message="Production batch updated successfully")


@batch_bp.route('/<batch_id>', methods=['DELETE'])
@token_required
@role_required('Admin', 'Inspector')
def handle_delete(batch_id):
    ok, err, status_code = delete_batch(batch_id, g.current_user)
    if err:
        return error_response(code="DELETE_BATCH_FAILED", message=err, status_code=status_code)
    return success_response(data={"batch_id": batch_id}, message="Production batch deleted successfully")
