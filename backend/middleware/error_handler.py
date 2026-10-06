import logging
from werkzeug.exceptions import HTTPException
from utils.response import error_response

logger = logging.getLogger('sentinel-trace')

def register_error_handlers(app):
    """Registers standardized JSON error handlers across the Flask application."""

    @app.errorhandler(400)
    def handle_bad_request(e):
        return error_response(
            code="BAD_REQUEST",
            message=getattr(e, 'description', 'Bad request syntax or parameters.'),
            status_code=400
        )

    @app.errorhandler(401)
    def handle_unauthorized(e):
        return error_response(
            code="UNAUTHORIZED",
            message=getattr(e, 'description', 'Authentication is required to access this resource.'),
            status_code=401
        )

    @app.errorhandler(403)
    def handle_forbidden(e):
        return error_response(
            code="FORBIDDEN",
            message=getattr(e, 'description', 'You do not have permission to access this resource.'),
            status_code=403
        )

    @app.errorhandler(404)
    def handle_not_found(e):
        return error_response(
            code="RESOURCE_NOT_FOUND",
            message=getattr(e, 'description', 'The requested resource or endpoint was not found.'),
            status_code=404
        )

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        return error_response(
            code="METHOD_NOT_ALLOWED",
            message=getattr(e, 'description', 'The HTTP method is not allowed for this route.'),
            status_code=405
        )

    @app.errorhandler(409)
    def handle_conflict(e):
        return error_response(
            code="RESOURCE_CONFLICT",
            message=getattr(e, 'description', 'Conflict with existing resource state.'),
            status_code=409
        )

    @app.errorhandler(HTTPException)
    def handle_generic_http_exception(e):
        return error_response(
            code=e.name.upper().replace(' ', '_'),
            message=e.description,
            status_code=e.code
        )

    @app.errorhandler(Exception)
    def handle_unhandled_exception(e):
        logger.error(f"Unhandled Exception: {str(e)}", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred. Please try again later.",
            status_code=500
        )
