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
