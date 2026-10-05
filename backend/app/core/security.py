from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(
    subject: str,
) -> tuple[str, int]:
    expires_in = settings.access_token_expire_minutes * 60

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes,
    )

    payload = {
        "sub": subject,
        "type": "access",
        "exp": expires_at,
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    return token, expires_in


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )

        if payload.get("type") != "access":
            raise ValueError("Invalid token type")

        subject = payload.get("sub")

        if not subject:
            raise ValueError("Missing token subject")

        return str(subject)

    except (InvalidTokenError, ValueError) as exc:
        raise ValueError("Invalid or expired token") from exc