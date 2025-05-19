# config.py
import os

BASEDIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'my_dev_secret_key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///ekolinq.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.ionos.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1']
    MAIL_USE_SSL = False  # set to True if your IONOS setup requires SSL instead of TLS
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    GOOGLE_SERVICE_ACCOUNT_JSON = os.path.join(BASEDIR, 'credentials', 'service_account.json')
    RECAPTCHA_PUBLIC_KEY = os.environ.get('RECAPTCHA_PUBLIC_KEY')
    RECAPTCHA_PRIVATE_KEY = os.environ.get('RECAPTCHA_PRIVATE_KEY')
    COGNITO_REGION        = os.getenv("COGNITO_REGION")
    COGNITO_USER_POOL_ID  = os.getenv("COGNITO_USER_POOL_ID")
    COGNITO_CLIENT_ID     = os.getenv("COGNITO_CLIENT_ID")
    COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET")
    LOGGER_LEVEL = os.getenv('LOGGER_LEVEL')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')