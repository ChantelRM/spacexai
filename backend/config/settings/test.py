"""Settings for the automated test suite. Never talks to the real xAI API."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

from .base import *  # noqa: E402,F401,F403
from .base import REST_FRAMEWORK  # noqa: E402

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# A fake key so we can assert it never leaks into responses or logs.
XAI_API_KEY = "xai-TEST-SECRET-KEY-should-never-leak"
XAI_MODEL = "grok-test-model"
XAI_BASE_URL = "https://api.x.ai/v1"
XAI_MAX_RETRIES = 0

# Throttles are tested explicitly; keep them generous for the rest of the suite.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/min",
        "user": "10000/min",
        "auth": "10000/min",
        "ai_chat": "10000/min",
    },
}
