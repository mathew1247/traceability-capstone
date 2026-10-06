import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from config import Config
from config.firebase import init_firebase, db
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

    # Initialize CORS with dynamic origin reflection for local live servers & production domains
    CORS(
        app,
        origins=True,
        supports_credentials=True,
        methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        allow_headers=['Content-Type', 'Authorization', 'X-Requested-With']
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
        try:
            # Active connectivity probe
            collections = db.collections()
            # Stream or check existence of at least 0 collections without error
            _ = next(collections, None)
            firebase_status = "connected"
        except Exception as e:
            app_logger.error(f"Health check Firebase probe failed: {e}")
            firebase_status = "disconnected"

        is_healthy = (firebase_status == "connected")
        return jsonify({
            "success": is_healthy,
            "status": "healthy" if is_healthy else "degraded",
            "data": {
                "status": "healthy" if is_healthy else "degraded",
                "firebase": firebase_status,
                "database": "Cloud Firestore" if not hasattr(db, '_persistence_file') else "Local Firestore Engine",
                "project_id": Config.FIREBASE_PROJECT_ID
            }
        }), (200 if is_healthy else 503)

    # Serve Sentinel-Trace UI Frontend directly
    @app.route('/', methods=['GET'])
    def index_route():
        if os.path.exists(os.path.join(frontend_dir, 'welcome.html')):
            return send_from_directory(frontend_dir, 'welcome.html')
        elif os.path.exists(os.path.join(frontend_dir, 'index.html')):
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
        if os.path.exists(file_path):
            return send_from_directory(frontend_dir, filename)
        if os.path.exists(os.path.join(frontend_dir, 'welcome.html')):
            return send_from_directory(frontend_dir, 'welcome.html')
        return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "Resource not found"}}), 404

    return app

app = create_app()

if __name__ == '__main__':
    app_logger.info(f"Starting Sentinel-Trace Production Backend on port {Config.PORT}")
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
