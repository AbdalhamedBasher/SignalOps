"""
Turning a request into a known principal.

Everything above this line is FastAPI plumbing; the rules it enforces live in
`security.py` and are tested there without a web framework.
"""

import logging
import secrets
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.models import AuthenticatedUser
from app.security import InvalidToken, Role, hash_password, read_token, satisfies
from app.tables import UserRow

logger = logging.getLogger(__name__)

UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sign in to use the SignalOps API.",
    # Tells a client this is an authentication problem it can fix by presenting
    # a token, rather than a permanent refusal.
    headers={"WWW-Authenticate": "Bearer"},
)


def resolve_secret() -> str:
    """
    The signing secret, or a fresh random one if nothing is configured.

    Generating one is deliberately noisy. The alternative — a hardcoded default
    — means anyone who has read the source can mint themselves a supervisor
    token, which is indistinguishable from having no authentication at all.
    """
    configured = get_settings().jwt_secret

    if configured:
        return configured

    generated = secrets.token_urlsafe(48)
    logger.warning(
        "JWT_SECRET is not set; generated a random signing secret. Tokens will "
        "stop working when this process restarts. Set JWT_SECRET to fix that."
    )

    return generated


# Resolved once. Re-generating per request would invalidate every token issued
# a moment earlier.
SIGNING_SECRET = resolve_secret()


def bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")

    if scheme.lower() != "bearer" or not token.strip():
        raise UNAUTHENTICATED

    return token.strip()


def current_user(
    token: str = Depends(bearer_token),
    session: Session = Depends(get_session),
) -> AuthenticatedUser:
    try:
        username, role = read_token(token, secret=SIGNING_SECRET)
    except InvalidToken as error:
        raise UNAUTHENTICATED from error

    row = session.get(UserRow, username)

    # The token may be valid and the account gone, or its role changed since
    # the token was issued. The database is the authority, not the token.
    if row is None or row.role != role.value:
        raise UNAUTHENTICATED

    return AuthenticatedUser(
        username=row.username, display_name=row.display_name, role=row.role
    )


def require_role(required: Role) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    def dependency(
        user: AuthenticatedUser = Depends(current_user),
    ) -> AuthenticatedUser:
        if not satisfies(Role(user.role), required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the {required.value} role.",
            )

        return user

    return dependency


def seed_users_if_empty(session: Session) -> int:
    """Create the demonstration logins in a database that has none."""
    if session.scalar(select(func.count()).select_from(UserRow)):
        return 0

    settings = get_settings()
    now = datetime.now(UTC)

    people = [
        ("nadia.k", "Nadia Karim", Role.ENGINEER, settings.seed_engineer_password),
        ("sam.o", "Sam Okafor", Role.SUPERVISOR, settings.seed_supervisor_password),
        (
            "collector-01",
            "Northern Region Collector",
            Role.COLLECTOR,
            settings.seed_collector_password,
        ),
    ]

    for username, display_name, role, password in people:
        session.add(
            UserRow(
                username=username,
                display_name=display_name,
                role=role.value,
                password_hash=hash_password(password),
                created_at=now,
            )
        )

    session.commit()

    return len(people)
