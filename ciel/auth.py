"""Optional password gate. The session token is derived from the password,
so changing CIEL_PASSWORD logs every device out."""

import hashlib
import hmac

from .config import settings

COOKIE = "ciel_session"


def enabled() -> bool:
    return bool(settings.password)


def session_token() -> str:
    return hmac.new(settings.password.encode(), b"ciel-session-v1", hashlib.sha256).hexdigest()


def check_password(password: str) -> bool:
    return hmac.compare_digest(password.encode(), settings.password.encode())


def is_authed(cookie: str | None) -> bool:
    if not enabled():
        return True
    return bool(cookie) and hmac.compare_digest(cookie, session_token())
