import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///cafe_system.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # QR Code settings
    QR_CODE_EXPIRY_HOURS = 24  # للحضور والانصراف
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = 3600  # ساعة واحدة
    
    # File upload settings
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Domain for QR codes
    BASE_DOMAIN = os.environ.get('BASE_DOMAIN') or 'localhost:5000'
    
    # Cafe settings
    CAFE_NAME = "فكرة كافيه وورك سبيس"
    CAFE_ADDRESS = "العنوان هنا"
    CAFE_PHONE = "+966xxxxxxxxx" 