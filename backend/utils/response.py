from flask import jsonify

def success_response(data=None, message=None, status_code=200):
    """
    Standardized API success response formatter.
    {
        "success": true,
        "data": { ... }
    }
    """
    payload = {
        "success": True
    }
    if data is not None:
        payload["data"] = data
    if message:
        payload["message"] = message
        
    return jsonify(payload), status_code


def error_response(code, message, status_code=400, details=None):
    """
    Standardized API error response formatter.
    {
        "success": false,
        "error": {
            "code": "ERROR_CODE",
            "message": "Human readable message"
        }
    }
    """
    error_obj = {
        "code": code,
        "message": message
    }
    if details:
        error_obj["details"] = details

    return jsonify({
        "success": False,
        "error": error_obj
    }), status_code
