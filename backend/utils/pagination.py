import math

def parse_pagination_params(args, allowed_sort_fields, default_sort_by='created_at', default_sort_order='desc', default_page_size=10):
    """
    Parses and validates pagination parameters from query arguments.
    Returns:
        (page, page_size, sort_by, sort_order, is_paginated, error_msg, status_code)
    """
    page_raw = args.get('page')
    page_size_raw = args.get('page_size')
    sort_by_raw = args.get('sort_by')
    sort_order_raw = args.get('sort_order')
    paginate_raw = args.get('paginate')

    # Determine if pagination is explicitly requested
    is_paginated = (
        page_raw is not None or
        page_size_raw is not None or
        (paginate_raw is not None and paginate_raw.lower() in ('true', '1', 'yes'))
    )

    page = 1
    page_size = default_page_size
    sort_by = default_sort_by
    sort_order = default_sort_order.lower()

    if page_raw is not None:
        try:
            page = int(page_raw)
            if page < 1:
                return None, None, None, None, None, "Page number must be a positive integer (>= 1).", 400
        except (ValueError, TypeError):
            return None, None, None, None, None, "Page number must be a positive integer (>= 1).", 400

    if page_size_raw is not None:
        try:
            page_size = int(page_size_raw)
            if page_size < 1 or page_size > 100:
                return None, None, None, None, None, "Page size must be an integer between 1 and 100.", 400
        except (ValueError, TypeError):
            return None, None, None, None, None, "Page size must be an integer between 1 and 100.", 400

    if sort_by_raw is not None:
        cleaned_sort_by = sort_by_raw.strip().lower()
        matched_field = None
        for f in allowed_sort_fields:
            if f.lower() == cleaned_sort_by:
                matched_field = f
                break
        if not matched_field:
            return None, None, None, None, None, (
                f"Invalid sort field '{sort_by_raw}'. Allowed sort fields: {', '.join(sorted(allowed_sort_fields))}."
            ), 400
        sort_by = matched_field

    if sort_order_raw is not None:
        cleaned_order = sort_order_raw.strip().lower()
        if cleaned_order not in ('asc', 'desc'):
            return None, None, None, None, None, "Sort order must be 'asc' or 'desc'.", 400
        sort_order = cleaned_order

    return page, page_size, sort_by, sort_order, is_paginated, None, 200


def paginate_records(items, page, page_size, sort_by=None, sort_order='desc', tie_breaker_field=None, is_paginated=True):
    """
    Deterministically sorts and paginates a list of records.
    If is_paginated is False, returns the sorted list directly (backwards compatibility).
    """
    if sort_by:
        reverse = (sort_order == 'desc')

        def sort_key(item):
            primary = item.get(sort_by)
            if primary is None:
                primary_cmp = (0, 0, "")
            elif isinstance(primary, (int, float)):
                primary_cmp = (1, float(primary), "")
            else:
                primary_cmp = (2, 0, str(primary).lower())

            secondary = item.get(tie_breaker_field) if tie_breaker_field else ""
            if secondary is None:
                sec_cmp = ""
            else:
                sec_cmp = str(secondary).lower()

            return (primary_cmp, sec_cmp)

        items = sorted(items, key=sort_key, reverse=reverse)

    total = len(items)

    if not is_paginated:
        return items

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    if page < 1:
        page = 1

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    if start_idx >= total:
        paged_items = []
    else:
        paged_items = items[start_idx:end_idx]

    return {
        "items": paged_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages
    }
