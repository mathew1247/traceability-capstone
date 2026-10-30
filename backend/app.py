import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from config import Config
from config.firebase import init_firebase, db, check_firestore_connectivity
from middleware.error_handler import register_error_handlers
from utils.logger import app_logger

# Import Blueprints
from routes.auth_routes import auth_bp
from routes.user_routes import user_bp
from routes.supplier_routes import supplier_bp
from routes.material_routes import material_bp
from routes.product_routes import product_bp
from routes.batch_routes import batch_bp
from routes.compliance_routes import compliance_bp
from routes.traceability_routes import traceability_bp
from routes.network_routes import network_bp
from routes.alert_routes import alert_bp
from routes.dashboard_routes import dashboard_bp
from routes.report_routes import report_bp
from routes.log_routes import log_bp

def create_app():
    """Application factory for Sentinel-Trace Flask backend."""
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
    app = Flask(__name__, static_folder=frontend_dir, static_url_path='')
    app.config.from_object(Config)

    # Initialize CORS for cross-origin frontend requests
    cors_origins = [url.strip() for url in Config.FRONTEND_URL if url.strip()]
    cors_origins.extend([
        r"^https://[a-zA-Z0-9_-]+\.vercel\.app$",
        r"^https://[a-zA-Z0-9_-]+\.onrender\.com$"
    ])
    if Config.ENV != 'production':
        cors_origins.extend([
            r"^http://localhost(:\d+)?$",
            r"^http://127\.0\.0\.1(:\d+)?$"
        ])

    CORS(
        app,
        resources={r"/*": {"origins": cors_origins}},
        supports_credentials=True,
        methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        allow_headers=['Content-Type', 'Authorization', 'X-Requested-With']
    )

    if Config.is_prod or Config.ENV == 'production':
        insecure_keys = {
            'sentinel-trace-prod-secret-key-2026',
            'sentinel-trace-prod-jwt-key-2026-secure-fallback',
            'sentinel-trace-dev-secret-key-2026',
            'sentinel-trace-dev-jwt-key-2026-secure-fallback',
            'secret', 'default', 'changeme', 'password', 'admin'
        }
        if not Config.SECRET_KEY or not str(Config.SECRET_KEY).strip() or str(Config.SECRET_KEY).strip().lower() in insecure_keys:
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: SECRET_KEY is missing or set to an insecure default. "
                "Production requires a strong, unique SECRET_KEY configured via environment variables."
            )
        if not Config.JWT_SECRET_KEY or not str(Config.JWT_SECRET_KEY).strip() or str(Config.JWT_SECRET_KEY).strip().lower() in insecure_keys:
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: JWT_SECRET_KEY is missing or set to an insecure default. "
                "Production requires a strong, unique JWT_SECRET_KEY configured via environment variables."
            )

    # Initialize Firebase Admin / Firestore once at startup
    init_firebase()

    # Register centralized error handlers
    register_error_handlers(app)

    # Register Route Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(user_bp, url_prefix='/api/admin/users', name='admin_user_bp')
    app.register_blueprint(supplier_bp)
    app.register_blueprint(material_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(batch_bp)
    app.register_blueprint(compliance_bp)
    app.register_blueprint(traceability_bp)
    app.register_blueprint(network_bp)
    app.register_blueprint(alert_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(log_bp)

    # Requirement 36: Health check endpoint verifying real Firebase connection
    @app.route('/api/health', methods=['GET'])
    def health_check():
        diag = check_firestore_connectivity()
        if Config.is_prod:
            is_healthy = bool(diag.get('firestore_accessible', False))
            firebase_status = "connected" if is_healthy else "connection_error"
        else:
            is_healthy = diag.get('firestore_accessible', False) or (diag.get('database') == 'Local Firestore Engine')
            firebase_status = "connected" if diag.get('firestore_accessible') else ("active_local_mode" if diag.get('database') == 'Local Firestore Engine' else "connection_error")

        status_code = 200 if is_healthy else 503
        return jsonify({
            "success": is_healthy,
            "status": "healthy" if is_healthy else "degraded",
            "data": {
                "status": "healthy" if is_healthy else "degraded",
                "firebase": firebase_status,
                "database": diag.get('database', 'Cloud Firestore'),
                "project_id": Config.FIREBASE_PROJECT_ID,
                "diagnostic": {
                    "sdk_initialized": diag.get("sdk_initialized"),
                    "project_id_match": diag.get("project_id_match"),
                    "firestore_accessible": diag.get("firestore_accessible"),
                    "error_category": diag.get("error_category")
                }
            }
        }), status_code


    @app.route('/api/diagnostic/firebase', methods=['GET'])
    def firebase_diagnostic():
        """
        Safe backend diagnostic that confirms:
        - Firebase Admin SDK initializes successfully.
        - Expected project ID matches configured value.
        - Firestore can be accessed using credentials (read-only probe).
        Does not return private keys, client email, or sensitive credentials.
        """
        diag = check_firestore_connectivity()
        status_code = 200 if diag.get('firestore_accessible') else 503
        return jsonify({
            "success": diag.get('firestore_accessible', False),
            "data": diag
        }), status_code

    # Serve Sentinel-Trace UI Frontend directly
    @app.route('/', methods=['GET'])
    def index_route():
        welcome_file = os.path.join(frontend_dir, 'welcome.html')
        index_file = os.path.join(frontend_dir, 'index.html')
        if os.path.isfile(welcome_file):
            return send_from_directory(frontend_dir, 'welcome.html')
        elif os.path.isfile(index_file):
            return send_from_directory(frontend_dir, 'index.html')
        return jsonify({
            "service": "SENTINEL-TRACE BACKEND API",
            "status": "ONLINE",
            "documentation": "/api/health"
        }), 200

    @app.route('/<path:filename>', methods=['GET'])
    def serve_frontend_files(filename):
        if filename.startswith('api/'):
            return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "API endpoint not found"}}), 404
        file_path = os.path.join(frontend_dir, filename)
        if os.path.isfile(file_path):
            return send_from_directory(frontend_dir, filename)
        if os.path.isfile(os.path.join(frontend_dir, 'welcome.html')):
            return send_from_directory(frontend_dir, 'welcome.html')
        return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "Resource not found"}}), 404

    return app

app = create_app()

if __name__ == '__main__':
    app_logger.info(f"Starting Sentinel-Trace Production Backend on port {Config.PORT}")
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
