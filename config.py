# config.py
import os
from datetime import timedelta
BASEDIR = os.path.abspath(os.path.dirname(__file__))

class BaseConfig:
    """Settings that never change between environments."""
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY   = os.getenv("SECRET_KEY")      # override in env
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    MAIL_SERVER   = os.getenv("MAIL_SERVER", "smtp.ionos.com")
    MAIL_PORT     = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS  = os.getenv("MAIL_USE_TLS", "True").lower() in ("true", "1")
    MAIL_USE_SSL  = False
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    GOOGLE_SERVICE_ACCOUNT_JSON = os.path.join(BASEDIR, "credentials", "service_account.json")
    RECAPTCHA_PUBLIC_KEY  = os.getenv("RECAPTCHA_PUBLIC_KEY")
    RECAPTCHA_PRIVATE_KEY = os.getenv("RECAPTCHA_PRIVATE_KEY")
    COGNITO_REGION        = os.getenv("COGNITO_REGION")
    COGNITO_USER_POOL_ID  = os.getenv("COGNITO_USER_POOL_ID")
    COGNITO_CLIENT_ID     = os.getenv("COGNITO_CLIENT_ID")
    COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET")
    LOGGER_LEVEL  = os.getenv("LOGGER_LEVEL", "INFO")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

    # Flask-Limiter – leave empty to fall back to in-memory
    RATE_LIMIT_STORAGE_URL = os.getenv("RATE_LIMIT_STORAGE_URL", "")
    DEFAULT_RATE_LIMITS    = ["100 per hour"]

    # Security headers / Talisman
    FORCE_HTTPS = False
    STRICT_TRANSPORT_SECURITY = False

class DevelopmentConfig(BaseConfig):
    DEBUG = True
    MAIL_DEBUG = False 
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///ekolinq.db")
    SESSION_COOKIE_SECURE = False            # allow http://localhost
    LOGGER_LEVEL = "DEBUG"                   # noisy logs locally
    RATELIMIT_ENABLED = False

class ProductionConfig(BaseConfig):
    DEBUG = False
    MAIL_DEBUG = False 
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")              # e.g. Postgres on Render
    SESSION_COOKIE_SECURE = True
    FORCE_HTTPS = True                           # redirect to HTTPS
    STRICT_TRANSPORT_SECURITY = True             # sets HSTS
