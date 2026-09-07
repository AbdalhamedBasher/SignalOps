"""
Password hashing and access tokens.

Kept free of FastAPI and of the database so the rules can be tested directly.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

JWT_ALGORITHM = "HS256"
TOKEN_LIFETIME = timedelta(hours=8)

_hasher = PasswordHasher()


class Role(StrEnum):
    # A machine principal. Collectors push alarms and nothing else; they are
    # not people and must not be able to approve anything.
    COLLECTOR = "collector"
    ENGINEER = "engineer"
    SUPERVISOR = "supervisor"


# Who may act as whom. A supervisor can do everything an engineer can, because
# in an operations centre a supervisor is an engineer with extra authority.
ROLE_IMPLIES: dict[Role, set[Role]] = {
    Role.COLLECTOR: {Role.COLLECTOR},
    Role.ENGINEER: {Role.ENGINEER},
    Role.SUPERVISOR: {Role.SUPERVISOR, Role.ENGINEER},
}


class InvalidToken(Exception):
    """The token was missing, malformed, expired, or signed by someone else."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def satisfies(actual: Role, required: Role) -> bool:
    return required in ROLE_IMPLIES[actual]


def issue_token(
    *,
    username: str,
    role: Role,
    secret: str,
    now: datetime | None = None,
    lifetime: timedelta = TOKEN_LIFETIME,
) -> str:
    issued_at = now or datetime.now(UTC)

    return jwt.encode(
        {
            "sub": username,
            "role": role.value,
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + lifetime).timestamp()),
        },
        secret,
        algorithm=JWT_ALGORITHM,
    )


def read_token(token: str, *, secret: str) -> tuple[str, Role]:
    """
    Decode a token and return who it claims to be.

    `algorithms` is pinned on purpose. Accepting whatever algorithm the token
    header names is the classic JWT vulnerability: an attacker sets it to
    "none", drops the signature, and the library cheerfully believes them.
    """
    try:
        claims = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as error:
        raise InvalidToken(str(error)) from error

    username = claims.get("sub")
    raw_role = claims.get("role")

    if not isinstance(username, str) or not isinstance(raw_role, str):
        raise InvalidToken("The token is missing a subject or a role.")

    try:
        role = Role(raw_role)
    except ValueError as error:
        raise InvalidToken(f"Unknown role {raw_role!r}.") from error

    return username, role
