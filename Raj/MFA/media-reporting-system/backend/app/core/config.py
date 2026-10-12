"""
Core configuration for Media Reporting System Backend.
"""
import os
from typing import List, Optional

class Settings:
    PROJECT_NAME: str = "Media Reporting System"
    VERSION: str = "0.2.0"
    API_PREFIX: str = "/api"

    # Single administrator configuration
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "rajxy71@gmail.com").strip().lower()

    # Session settings
    SESSION_COOKIE_NAME: str = "mrs_session"
    SESSION_DURATION_HOURS: int = 8  # 8 hours maximum session lifetime
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 15

    # Password recovery email. For Gmail, use an App Password in SMTP_PASSWORD.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "").strip()
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "").strip()
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes", "on")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    PASSWORD_RESET_MINUTES: int = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))

    # Gmail Mailer Ingestion settings
    GMAIL_EMAIL: str = os.getenv("GMAIL_EMAIL", "rajxy101@gmail.com").strip().lower()
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "mqkvthzywlkfwudg").strip()
    GMAIL_IMAP_SERVER: str = os.getenv("GMAIL_IMAP_SERVER", "imap.gmail.com").strip()
    GMAIL_IMAP_PORT: int = int(os.getenv("GMAIL_IMAP_PORT", "993"))

    # Configurable CORS origins for local and LAN company access
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://192.168.50.134:8000",
        "*"
    ]

settings = Settings()
