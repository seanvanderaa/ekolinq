# config.py
from __future__ import annotations

import os
from pathlib import Path
from datetime import timedelta
from typing import Type

from upstash_redis import Redis

BASE_DIR = Path(__file__).parent


def require(name: str, default: str | None = None) -> str:
    """Return an env var or raise in prod; use a default only in dev."""
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Missing required env var {name!r}")
    return val


class BaseConfig:
    """Values common to every environment."""
    # ───── Flask ────────────────────────────────────────────────────────
    SECRET_KEY = require("SECRET_KEY")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_USE_SIGNER = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ───── Mail ────────────────────────────────────────────────────────
    MAIL_SERVER   = require("MAIL_SERVER", "smtp.ionos.com")
    MAIL_PORT     = int(require("MAIL_PORT", 587))
    MAIL_USE_TLS  = require("MAIL_USE_TLS", "True").lower() in ("true", "1")
    MAIL_USERNAME = require("MAIL_USERNAME")
    MAIL_PASSWORD = require("MAIL_PASSWORD")
    MAIL_DEBUG = False 
    MAIL_ERROR_ADDRESS = require("MAIL_ERROR_ADDRESS")

    # ───── Rate limiting / Redis ────────────────────────────────────────
    RATE_LIMIT_STORAGE_URL = ""
    DEFAULT_RATE_LIMITS    = ["100 per hour"]

    # ───── Security headers (Flask-Talisman) ───────────────────────────
    FORCE_HTTPS = False
    STRICT_TRANSPORT_SECURITY = False

    COGNITO_USER_POOL_ID=require("COGNITO_USER_POOL_ID")
    COGNITO_CLIENT_ID=require("COGNITO_CLIENT_ID")
    COGNITO_CLIENT_SECRET=require("COGNITO_CLIENT_SECRET")
    COGNITO_REGION=require("COGNITO_REGION")
    COGNITO_DOMAIN=require("COGNITO_DOMAIN")

    # ───── RECAPTCHA ───────────────────────────
    RECAPTCHA_PUBLIC_KEY=require("RECAPTCHA_PUBLIC_KEY")
    RECAPTCHA_PRIVATE_KEY=require("RECAPTCHA_PRIVATE_KEY")

    # ───── GOOGLE ───────────────────────────
    GOOGLE_API_KEY=require("GOOGLE_API_KEY")
    GOOGLE_BACKEND_API_KEY=require("GOOGLE_BACKEND_API_KEY")

class DevelopmentConfig(BaseConfig):
    DEBUG = True
    LOGGER_LEVEL = "DEBUG"
    SQLALCHEMY_DATABASE_URI = require("DATABASE_URI", "sqlite:///dev.db")
    SESSION_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    RATELIMIT_STORAGE_URI  = "memory://"
    SITE_URL=require("SITE_URL")
    SESSION_TYPE = "filesystem"       # keep dev sessions on disk
    SESSION_FILE_DIR = "/tmp/flask_session"


class ProductionConfig(BaseConfig):
    DEBUG = False
    PROPAGATE_EXCEPTIONS=False
    LOGGER_LEVEL = "INFO"
    SESSION_COOKIE_SECURE = True
    FORCE_HTTPS = True
    STRICT_TRANSPORT_SECURITY = True
    RATELIMIT_ENABLED = True
    SQLALCHEMY_DATABASE_URI = require("DATABASE_URI")
    UPSTASH_REDIS_REST_URL  = require("UPSTASH_REDIS_REST_URL")
    UPSTASH_REDIS_REST_TOKEN = require("UPSTASH_REDIS_REST_TOKEN")
    RATELIMIT_STORAGE_URI = require("UPSTASH_REDIS_TLS_URL")
    SITE_URL=require("SITE_URL")
    SESSION_TYPE = "redis"
    SESSION_REDIS = Redis.from_env()

