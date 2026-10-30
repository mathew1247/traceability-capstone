from flask import Blueprint, request, g
from services.product_service import (
    get_all_products,
    get_product_by_id,
    create_product,
    update_product,
    delete_product
)
from middleware.auth_middleware import token_required, role_required
from utils.response import success_response, error_response
from utils.pagination import parse_pagination_params

ALLOWED_PRODUCT_SORT_FIELDS = {'product_id', 'product_name', 'product_code', 'status', 'created_at', 'description'}

product_bp = Blueprint('product_bp', __name__, url_prefix='/api/products')

@product_bp.route('', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_all():
    page, page_size, sort_by, sort_order, is_paginated, err, status_code = parse_pagination_params(
        request.args,
        allowed_sort_fields=ALLOWED_PRODUCT_SORT_FIELDS,
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

    products = get_all_products(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search.strip() if search else None,
        status=status.strip() if status else None,
        is_paginated=is_paginated
    )
    return success_response(data=products)


@product_bp.route('/<product_id>', methods=['GET'])
@token_required
@role_required('Admin', 'Inspector', 'Auditor', 'Operator')
def handle_get_one(product_id):
    product = get_product_by_id(product_id)
    if not product:
        return error_response(code="PRODUCT_NOT_FOUND", message="Product not found", status_code=404)
    return success_response(data=product)


@product_bp.route('', methods=['POST'])
@token_required
@role_required('Admin', 'Inspector', 'Operator')
def handle_create():
    data = request.get_json() or {}
    record, err, status_code = create_product(data, g.current_user)
    if err:
        return error_response(code="CREATE_PRODUCT_FAILED", message=err, status_code=status_code)
    return success_response(data=record, message="Product created successfully", status_code=201)


@product_bp.route('/<product_id>', methods=['PUT'])
@token_required
@role_required('Admin', 'Inspector', 'Operator')
def handle_update(product_id):
    data = request.get_json() or {}
    updated, err, status_code = update_product(product_id, data, g.current_user)
    if err:
        return error_response(code="UPDATE_PRODUCT_FAILED", message=err, status_code=status_code)
    return success_response(data=updated, message="Product updated successfully")


@product_bp.route('/<product_id>', methods=['DELETE'])
@token_required
@role_required('Admin', 'Inspector')
def handle_delete(product_id):
    ok, err, status_code = delete_product(product_id, g.current_user)
    if err:
        return error_response(code="DELETE_PRODUCT_FAILED", message=err, status_code=status_code)
    return success_response(data={"product_id": product_id}, message="Product deleted successfully")
