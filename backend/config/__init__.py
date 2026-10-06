import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    """Application configuration settings."""
    ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() in ('true', '1', 't')
    PORT = int(os.getenv('FLASK_PORT', 5000))
    
    # Secrets
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-dev-secret-key-change-in-production')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'default-jwt-secret-key-change-in-production')
    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', 24))
    
    # Firebase
    FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', 'sentinel-trace')
    FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH', 'serviceAccountKey.json')
    
    # Network Security Scopes
    ALLOWED_NETWORK_TARGETS = [
        target.strip()
        for target in os.getenv('ALLOWED_NETWORK_TARGETS', '192.168.1.0/24,127.0.0.1,localhost').split(',')
        if target.strip()
    ]
    
    # CORS
    FRONTEND_URL = [
        url.strip()
        for url in os.getenv('FRONTEND_URL', 'http://localhost:3000,http://localhost:5500').split(',')
        if url.strip()
    ]
    
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
