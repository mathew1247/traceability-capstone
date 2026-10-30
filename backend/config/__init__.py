import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    """Application configuration settings."""
    ENV = os.getenv('FLASK_ENV', 'development')
    is_prod = (ENV == 'production')
    DEBUG = False if is_prod else os.getenv('FLASK_DEBUG', 'true').lower() in ('true', '1', 't')
    PORT = int(os.getenv('PORT', os.getenv('FLASK_PORT', 5000)))
    
    # Secrets: Fallback keys are only permitted in development and test environments.
    # In production, secrets must be explicitly provided via environment variables.
    if is_prod:
        SECRET_KEY = os.getenv('SECRET_KEY')
        JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    else:
        SECRET_KEY = os.getenv('SECRET_KEY', 'sentinel-trace-dev-secret-key-2026')
        JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'sentinel-trace-dev-jwt-key-2026-secure-fallback')
    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', 24))
    
    # Firebase
    FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', 'capstone-8ee41')
    FIREBASE_CREDENTIALS_PATH = (
        os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        or os.getenv('FIREBASE_CREDENTIALS_PATH')
        or ('/etc/secrets/serviceAccountKey.json' if os.path.isfile('/etc/secrets/serviceAccountKey.json') else 'serviceAccountKey.json')
    )
    
    # Network Security Scopes
    ALLOWED_NETWORK_TARGETS = [
        target.strip()
        for target in os.getenv('ALLOWED_NETWORK_TARGETS', '192.168.1.0/24,127.0.0.1,localhost').split(',')
        if target.strip()
    ]
    
    # CORS Configuration - Allowed Production / Dev Origins
    raw_frontend_urls = os.getenv(
        'FRONTEND_URL',
        'http://localhost:3000,http://localhost:5500,http://127.0.0.1:3000,http://127.0.0.1:5500,https://traceability-capstone.vercel.app,https://sentinel-trace.vercel.app'
    )
    FRONTEND_URL = [
        url.strip()
        for url in raw_frontend_urls.split(',')
        if url.strip()
    ]

    # SMTP Configuration (Production alert emails & recovery)
    SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USER = os.getenv('SMTP_USER', 'probot12309@gmail.com')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() in ('true', '1')
    ALERT_FROM_EMAIL = os.getenv('ALERT_FROM_EMAIL', SMTP_USER)
    
    # Firestore Collection Names
    COLLECTION_USERS = 'users'
    COLLECTION_SUPPLIERS = 'suppliers'
    COLLECTION_RAW_MATERIALS = 'raw_materials'
    COLLECTION_PRODUCTS = 'products'
    COLLECTION_PRODUCTION_BATCHES = 'production_batches'
    COLLECTION_COMPLIANCE_RECORDS = 'compliance_records'
    COLLECTION_NETWORK_SCANS = 'network_scans'
    COLLECTION_ALERTS = 'alerts'
    COLLECTION_ACTIVITY_LOGS = 'activity_logs'
